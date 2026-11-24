#!/usr/bin/env python3
"""Аудит механического переноса фаз 8, 9, 10 из engine.py в simulation/phases/.

Сравнивает старые тела _phase8_environment, _phase9_consequences,
_phase10_report (из git show) с новыми телами run_phase*_ через применение
тех же правил замены из Промпта 3.8B.
Возвращает 0 при полном совпадении, ненулевой код при любом расхождении.

Базовый коммит: fcab1b9 (до переноса фаз 8-10).
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GIT_ENGINE = "src/zonesim/simulation/engine.py"
BASELINE_COMMIT = "fcab1b9"

PHASE_PAIRS = [
    ("_phase8_environment", "run_phase8_environment",
     "src/zonesim/simulation/phases/phase08_environment.py"),
    ("_phase9_consequences", "run_phase9_consequences",
     "src/zonesim/simulation/phases/phase09_consequences.py"),
    ("_phase10_report", "run_phase10_report",
     "src/zonesim/simulation/phases/phase10_report.py"),
]

# Правила замены из Промпта 3.8B (порядок важен - длинные паттерны раньше)
REPLACEMENT_RULES = [
    (re.compile(r"\bself\.state\.time\b"), "state.time"),
    (re.compile(r"\bself\.state\b"), "state"),
    (re.compile(r"\bself\.catalog\b"), "engine.catalog"),
    (re.compile(r"\bself\.save_manager\b"), "engine.save_manager"),
    (re.compile(r"\bself\._anomaly_move_candidates\b"), "engine._anomaly_move_candidates"),
    (re.compile(r"\bself\._roll_trail_blockage\b"), "engine._roll_trail_blockage"),
    (re.compile(r"\bself\._sync_human_groups\b"), "engine._sync_human_groups"),
    (re.compile(r"\bself\._process_daily_export\b"), "engine._process_daily_export"),
    (re.compile(r"\bself\.save\("), "engine.save("),
    # Общий паттерн для всех остальных self._ -> engine._
    (re.compile(r"\bself\._(\w+)"), r"engine._\1"),
]


def get_base_commit() -> str:
    """Определяем коммит для base-версии engine.py."""
    for candidate in [BASELINE_COMMIT, "HEAD"]:
        result = subprocess.run(
            ["git", "rev-parse", candidate],
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode == 0:
            print("Используем коммит: {}".format(result.stdout.strip()[:12]))
            return result.stdout.strip()
    print("FATAL: не найден базовый коммит ({})".format(BASELINE_COMMIT))
    sys.exit(2)


def get_old_body(commit: str, method_name: str) -> str:
    """Извлекает тело метода из указанного коммита (AST-based, пропускает docstring)."""
    result = subprocess.run(
        ["git", "show", f"{commit}:{GIT_ENGINE}"],
        capture_output=True, text=True, check=True, encoding="utf-8",
    )
    tree = ast.parse(result.stdout)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SimulationEngine":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return _extract_body(result.stdout, item)
    print("FATAL: {} not found in {}".format(method_name, commit))
    sys.exit(2)


def get_new_body(mod_path: str) -> str:
    """Извлекает тело функции из нового модуля (AST-based, пропускает docstring)."""
    file_path = REPO_ROOT / mod_path
    code = file_path.read_text(encoding="utf-8")
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            return _extract_body(code, node)
    print("FATAL: function not found in {}".format(mod_path))
    sys.exit(2)


def _extract_body(code: str, func_node: ast.FunctionDef) -> str:
    """Извлекает строки тела функции, ПРОПУСКАЯ docstring (первый Expr(Constant))."""
    lines = code.splitlines()
    body_start = 0
    for child in func_node.body:
        if (isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant)
                and isinstance(child.value.value, str)):
            body_start += 1
        else:
            break
    start = func_node.body[body_start].lineno - 1
    end = func_node.end_lineno
    return "\n".join(lines[start:end])


def apply_replacements(text: str) -> str:
    result = text
    for pattern, replacement in REPLACEMENT_RULES:
        result = pattern.sub(replacement, result)
    return result


def normalize(text: str) -> list[str]:
    cleaned = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
            continue
        cleaned.append(s)
    return cleaned


def find_rng_refs(text: str) -> list[str]:
    return re.findall(r"\.?state\.rng\.(random|choice|randint)\b", text)


def find_attr_assignments(text: str) -> list[str]:
    return re.findall(
        r"(engine|self)\._(\w+)\s*(?:=|\.clear|\.pop|\.append|\.add|\.remove)", text
    )


def check_local_aliases(text: str) -> list[tuple[str, str]]:
    pat = re.compile(r"(\w+)\s*=\s*engine\._(\w+)\s*\n(?s:.*?)(?:\n|^)\s*\1\s*=")
    return pat.findall(text)


def main() -> int:
    print("=" * 70)
    print("AUDIT PHASES 8, 9, 10 MOVE: engine.py -> phase*/")
    print("=" * 70)

    commit = get_base_commit()

    all_ok = True
    overall_diffs = 0

    for name_old, name_new, mod_path in PHASE_PAIRS:
        print()
        print("=" * 70)
        print("PAIR: {} -> {}".format(name_old, name_new))
        print("=" * 70)

        # 1. Извлекаем тела
        old_body = get_old_body(commit, name_old)
        new_body = get_new_body(mod_path)

        old_lines = len(old_body.splitlines())
        new_lines = len(new_body.splitlines())
        print("")
        print("OLD body:    {} lines".format(old_lines))
        print("NEW body:    {} lines".format(new_lines))

        # 2. Применяем замены
        transformed = apply_replacements(old_body)

        # 3. Нормализация и сравнение
        o = normalize(old_body)
        t = normalize(transformed)
        n = normalize(new_body)

        print("")
        print("OLD (norm):   {} operators".format(len(o)))
        print("TRANS (norm): {} operators".format(len(t)))
        print("NEW (norm):   {} operators".format(len(n)))

        # Сравнение TRANS vs NEW (пропускаем setup-переменные в NEW)
        n_lines = list(n)
        setup_patterns = {
            "engine = ctx.engine_ref",
            "state = ctx.state",
            "hour = ctx.hour",
            "is_night = ctx.is_night",
        }
        n_start = 0
        for line in n_lines:
            if line in setup_patterns:
                n_start += 1
            else:
                break
        n_trimmed = n_lines[n_start:]

        diffs = []
        max_lines = max(len(t), len(n_trimmed))
        for i in range(max_lines):
            tl = t[i] if i < len(t) else "<MISSING>"
            nl = n_trimmed[i] if i < len(n_trimmed) else "<MISSING>"
            if tl != nl:
                diffs.append("  [{}] TRANS={} NEW={}".format(i+1, tl[:90], nl[:90]))

        if diffs:
            print("")
            print("MISMATCHES: {}".format(len(diffs)))
            for d in diffs[:30]:
                print("  " + d)
            if len(diffs) > 30:
                print("  ... and {} more".format(len(diffs) - 30))
            all_ok = False
            overall_diffs += len(diffs)
        else:
            print("")
            print("OK: 0 mismatches - transfer mechanical")

        # 4. Атрибуты
        print("")
        print("--- Attributes ---")
        assigns = find_attr_assignments(transformed)
        print("  {} engine._attr assignments".format(len(assigns)))
        for scope, name in assigns:
            print("    {}.{}".format(scope, name))

        aliases = check_local_aliases(transformed)
        if aliases:
            print("  FAIL: {} local aliases found!".format(len(aliases)))
            all_ok = False
        else:
            print("  OK: No local aliases")

        # 5. RNG
        print("")
        print("--- RNG ---")
        r_old = find_rng_refs(old_body)
        r_new = find_rng_refs(new_body)
        r_trans = find_rng_refs(transformed)
        print("  OLD:   {}".format(len(r_old)))
        print("  NEW:   {}".format(len(r_new)))
        print("  TRANS: {}".format(len(r_trans)))
        if r_old == r_new == r_trans:
            if r_old:
                print("  OK: Identical: {}".format(r_old))
            else:
                print("  OK: No direct RNG")
        else:
            print("  FAIL: RNG order differs!")
            all_ok = False

    # Итог
    print("")
    print("=" * 70)
    if all_ok:
        print("AUDIT PASSED: all pairs mechanical, 0 mismatches.")
        print("=" * 70)
        return 0
    else:
        print("AUDIT FAILED: {} total mismatches.".format(overall_diffs))
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
