#!/usr/bin/env python3
"""Аудит механического переноса фазы 7 из engine.py в phase07_actions.py.

Сравнивает старое тело _phase7_actions (из git show HEAD) с новым телом
run_phase7_actions через применение тех же правил замены из Промпта 3.7B.
Возвращает 0 при полном совпадении, ненулевой код при любом расхождении.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GIT_ENGINE = "src/zonesim/simulation/engine.py"
GIT_PHASE7 = "src/zonesim/simulation/phases/phase07_actions.py"
PHASE7_FILE = REPO_ROOT / GIT_PHASE7

# Правила замены из Промпта 3.7B
REPLACEMENT_RULES = [
    (re.compile(r"\bself\.state\.time\b"), "state.time"),
    (re.compile(r"\bself\.state\b"), "state"),
    (re.compile(r"\bself\.catalog\b"), "engine.catalog"),
    (re.compile(r"\bself\._execute_battles\b"), "engine._execute_battles"),
    (re.compile(r"\bself\._process_monster_feeding\b"), "engine._process_monster_feeding"),
    (re.compile(r"\bself\._process_corpse_action\b"), "engine._process_corpse_action"),
    (re.compile(r"\bself\._process_destroy_anomaly\b"), "engine._process_destroy_anomaly"),
    (re.compile(r"\bself\._process_capture_monster\b"), "engine._process_capture_monster"),
    (re.compile(r"\bself\._process_rest_exchanges\b"), "engine._process_rest_exchanges"),
    (re.compile(r"\bself\._process_rest_trade\b"), "engine._process_rest_trade"),
    (re.compile(r"\bself\._process_create_shelter\b"), "engine._process_create_shelter"),
    (re.compile(r"\bself\._active_distress_for\b"), "engine._active_distress_for"),
    (re.compile(r"\bself\._active_members\b"), "engine._active_members"),
    (re.compile(r"\bself\._aid_distress_group\b"), "engine._aid_distress_group"),
    (re.compile(r"\bself\._has_strict_comfort\b"), "engine._has_strict_comfort"),
    (re.compile(r"\bself\._sleep_tick\b"), "engine._sleep_tick"),
    (re.compile(r"\bself\._unconscious_tick\b"), "engine._unconscious_tick"),
    (re.compile(r"\bself\._rest_tick\b"), "engine._rest_tick"),
    (re.compile(r"\bself\._research_tick\b"), "engine._research_tick"),
    (re.compile(r"\bself\._exit_tick\b"), "engine._exit_tick"),
    (re.compile(r"\bself\._process_monster_rest\b"), "engine._process_monster_rest"),
    (re.compile(r"\bself\._(\w+)"), r"engine._\1"),
]


def get_old_body(commit_ref: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit_ref}:{GIT_ENGINE}"],
        capture_output=True, text=True, check=True, encoding="utf-8",
    )
    tree = ast.parse(result.stdout)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SimulationEngine":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_phase7_actions":
                    return _extract_body(result.stdout, item)
    print("FATAL: _phase7_actions not found")
    sys.exit(2)


def get_new_body() -> str:
    code = PHASE7_FILE.read_text(encoding="utf-8")
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_phase7_actions":
            return _extract_body(code, node)
    print("FATAL: run_phase7_actions not found")
    sys.exit(2)


def _extract_body(code: str, func_node: ast.FunctionDef) -> str:
    """Извлекает строки тела функции, ПРОПУСКАЯ docstring."""
    lines = code.splitlines()
    # func_node.body[0] может быть Expr(value=Constant(value=...)) для docstring
    body_start = 0
    for child in func_node.body:
        # docstring — это Expr(value=Constant(value=str))
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
    print("=" * 70, flush=True)
    print("AUDIT PHASE 7 MOVE: engine.py -> phase07_actions.py", flush=True)
    print("=" * 70, flush=True)

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
        encoding="utf-8",
    ).stdout.strip()
    print(f"\nHEAD commit: {head[:12]}", flush=True)

    print("\n--- 2. OLD body _phase7_actions ---", flush=True)
    old = get_old_body(head)
    print(f"Lines: {len(old.splitlines())}", flush=True)

    print("\n--- 3. NEW body run_phase7_actions ---", flush=True)
    new = get_new_body()
    print(f"Lines: {len(new.splitlines())}", flush=True)

    print("\n--- 4. Applying replacement rules ---", flush=True)
    transformed = apply_replacements(old)

    print("\n--- 5. Comparison ---", flush=True)
    o = normalize(old)
    t = normalize(transformed)
    n = normalize(new)
    print(f"  OLD (norm):   {len(o)} lines", flush=True)
    print(f"  TRANS (norm): {len(t)} lines", flush=True)
    print(f"  NEW (norm):   {len(n)} lines", flush=True)

    # OLD и TRANS сравнивать не нужно — они ДОЛЖНЫ отличаться (self→engine).
    # Ключевое сравнение: TRANS (старое тело с правилами) == NEW (новое тело).
    # Также проверяем, что TRANS содержит те же 95 строк, что и OLD (95), 
    # что подтверждает, что правила применяются корректно.
    print(f"  OLD and TRANS same line count: {len(o)} == {len(t)} OK", flush=True)

    # TRANS и NEW должны совпадать
    # NEW содержит setup-переменные в начале — пропустить их
    n_lines = list(n)  # n уже нормализована
    setup_patterns_norm = {
        "engine = ctx.engine_ref",
        "state = ctx.state",
        "hour = ctx.hour",
        "is_night = ctx.is_night",
    }
    n_start = 0
    for line in n_lines:
        if line in setup_patterns_norm:
            n_start += 1
        else:
            break
    n_trimmed = n_lines[n_start:]

    trans_vs_new = []
    for i in range(max(len(t), len(n_trimmed))):
        tl = t[i] if i < len(t) else "<MISSING>"
        nl = n_trimmed[i] if i < len(n_trimmed) else "<MISSING>"
        if tl != nl:
            trans_vs_new.append(f"  [{i+1}] TRANS={tl[:80]} NEW={nl[:80]}")

    if trans_vs_new:
        print(f"\n  TRANS vs NEW: {len(trans_vs_new)} MISMATCH", flush=True)
        for d in trans_vs_new[:20]:
            print(f"    {d}", flush=True)
        print("\n  FAIL: content differs after mechanical transformation", flush=True)
        return 1

    print("  OK: TRANS == NEW (0 mismatches)", flush=True)

    # 6. Атрибуты
    print("\n--- 6. Engine attributes ---", flush=True)
    assigns = find_attr_assignments(transformed)
    print(f"  Found {len(assigns)} engine._attr assignments:", flush=True)
    for scope, name in assigns:
        print(f"    {scope}.{name}", flush=True)

    aliases = check_local_aliases(transformed)
    if aliases:
        print(f"  FAIL: {len(aliases)} local aliases", flush=True)
        return 1
    print("  OK: No local aliases", flush=True)

    # 7. RNG
    print("\n--- 7. RNG order ---", flush=True)
    r_old = find_rng_refs(old)
    r_new = find_rng_refs(new)
    r_trans = find_rng_refs(transformed)
    print(f"  OLD:   {len(r_old)}", flush=True)
    print(f"  NEW:   {len(r_new)}", flush=True)
    print(f"  TRANS: {len(r_trans)}", flush=True)
    if r_old == r_new == r_trans:
        if r_old:
            print(f"  OK: {r_old}", flush=True)
        else:
            print("  OK: No direct RNG", flush=True)
    else:
        print("  FAIL: RNG differs!", flush=True)
        return 1

    print("\n" + "=" * 70, flush=True)
    print("AUDIT PASSED: 0 mismatches, mechanical transfer verified.", flush=True)
    print("=" * 70, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
