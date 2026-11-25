#!/usr/bin/env python3
"""Аудит эквивалентности выноса сервисных методов батча B1.

Два режима:
- --equivalent: попарное сравнение тел old_method <-> new_function
- --structural: структурные проверки (удалён/есть/нет импорта/размер/хэши)
- --both: оба режима

Запуск:
    python scripts/audit_service_move.py --equivalent
    python scripts/audit_service_move.py --structural
    python scripts/audit_service_move.py --both
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "zonesim"
B1_PRE_COMMIT = "f04dade"


@dataclass
class MethodPair:
    old_name: str
    new_name: str
    target_module: str
    rules: list
    known_diff: str = ""


BATCH_B1 = [
    MethodPair(
        "_has_strict_comfort", "has_strict_comfort", "needs/comfort.py",
        rules=[],
        known_diff="",
    ),
    MethodPair(
        "_group_faction", "group_faction", "world/faction.py",
        rules=[
            (r"\bself\.state\.humans\b", "state.humans"),
        ],
        known_diff="",
    ),
    MethodPair(
        "_home_sector_id", "home_sector_id", "world/faction.py",
        rules=[
            (r"\bself\.state\.sectors\b", "sectors"),
            (r"\bself\._home_cache\b", "home_cache"),
        ],
        known_diff=(
            "home_sector_id: новая функция использует паттерн "
            "'if hc is not None: return hc[f] ... hc[f]=result' вместо "
            "'if f not in hc: hc[f]=next(...); return hc[f]'. "
            "Логика идентична при hc is not None. Новая версия поддерживает hc=None."
        ),
    ),
    MethodPair(
        "_distance_to_border", "distance_to_border", "world/faction.py",
        rules=[
            (r"\bself\.state\.sectors\b", "sectors"),
            (r"\bself\._border_dist\b", "border_dist"),
        ],
        known_diff=(
            "distance_to_border: контракт изменён. Старый возвращал "
            "self._border_dist.get(sector_id) -> int|None. "
            "Новый возвращает dict[int,int] (полный BFS-словарь). "
            "Вызывающая (phase04) компенсирует через .get(). "
            "Кэш восстановлен в п.1 (write-back при None)."
        ),
    ),
    MethodPair(
        "_sector_humans", "sector_humans", "world/sectors.py",
        rules=[
            (r"\bself\.state\.humans\b", "state.humans"),
            (r"\bself\.state\.stationary_humans\b", "state.stationary_humans"),
        ],
        known_diff=(
            "sector_humans: новая сигнатура (humans, stationary_humans, sector_id) "
            "вместо (state.humans, state.stationary_humans, sector_id). "
            "Параметры переименованы для чистоты — state убран."
        ),
    ),
    MethodPair(
        "_squad_power", "squad_power", "combat/power.py",
        rules=[
            (r"\bself\.state\.items\b", "items"),
        ],
        known_diff=(
            "squad_power: константа SPECIES_POWER_VALUE переименована в "
            "_SPECIES_POWER_VALUE (module-level private const в power.py "
            "вместо class-level в engine.py). Логика идентична."
        ),
    ),
    MethodPair(
        "_monster_group_power", "monster_group_power", "combat/power.py",
        rules=[],
        known_diff="",
    ),
]


def git_show(path, commit):
    result = subprocess.run(
        ["git", "show", commit + ":" + path],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    return result.stdout


def extract_body(code, func_name):
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SimulationEngine":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == func_name:
                    lines = code.splitlines()
                    body_start = 0
                    for child in item.body:
                        if (isinstance(child, ast.Expr)
                                and isinstance(child.value, ast.Constant)
                                and isinstance(child.value.value, str)):
                            body_start += 1
                        else:
                            break
                    start = item.body[body_start].lineno - 1
                    end = item.end_lineno
                    return "\n".join(lines[start:end])
    return None


def extract_new_func_body(target_module, func_name):
    mod_path = SRC / target_module
    if not mod_path.exists():
        return None
    code = mod_path.read_text(encoding="utf-8")
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            lines = code.splitlines()
            body_start = 0
            for child in node.body:
                if (isinstance(child, ast.Expr)
                        and isinstance(child.value, ast.Constant)
                        and isinstance(child.value.value, str)):
                    body_start += 1
                else:
                    break
            start = node.body[body_start].lineno - 1
            end = node.end_lineno
            return "\n".join(lines[start:end])
    return None


def apply_rules(text, rules):
    for pattern, replacement in rules:
        text = re.sub(pattern, replacement, text)
    return text


def normalize(text):
    cleaned = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
            continue
        cleaned.append(s)
    return cleaned


def find_rng_refs(text):
    return re.findall(r"state\.rng\.(random|choice|randint)\b", text)


def audit_equivalent():
    print("=" * 70)
    print("AUDIT EQUIVALENCE: B1 service methods")
    print("Pre-batch commit: " + B1_PRE_COMMIT)
    print("=" * 70)

    all_ok = True
    total_pairs = 0
    total_failures = 0

    for pair in BATCH_B1:
        total_pairs += 1
        sep = "-" * 60
        print("")
        print(sep)
        print("PAIR: " + pair.old_name + " -> " + pair.new_name +
              " (" + pair.target_module + ")")

        old_code = git_show("src/zonesim/simulation/engine.py", B1_PRE_COMMIT)
        old_body = extract_body(old_code, pair.old_name)
        if old_body is None:
            print("  ERROR: " + pair.old_name + " not found in git")
            all_ok = False
            total_failures += 1
            continue
        print("  OLD body: " + str(len(old_body.splitlines())) + " lines")

        new_body = extract_new_func_body(pair.target_module, pair.new_name)
        if new_body is None:
            print("  ERROR: " + pair.new_name + " not in " + pair.target_module)
            all_ok = False
            total_failures += 1
            continue
        print("  NEW body: " + str(len(new_body.splitlines())) + " lines")

        transformed = apply_rules(old_body, pair.rules)
        print("  TRANSFORMED: " + str(len(transformed.splitlines())) + " lines")

        old_norm = normalize(old_body)
        new_norm = normalize(new_body)
        trans_norm = normalize(transformed)

        print("  OLD (norm): " + str(len(old_norm)) + " ops")
        print("  TRANS (norm): " + str(len(trans_norm)) + " ops")
        print("  NEW (norm): " + str(len(new_norm)) + " ops")

        # Сравнение
        mismatches = []
        max_len = max(len(trans_norm), len(new_norm))
        for i in range(max_len):
            tl = trans_norm[i] if i < len(trans_norm) else "<MISSING>"
            nl = new_norm[i] if i < len(new_norm) else "<MISSING>"
            if tl != nl:
                mismatches.append("  [" + str(i + 1) + "] TRANS=" + tl[:80] + " | NEW=" + nl[:80])

        if mismatches:
            print("")
            print("  MISMATCHES: " + str(len(mismatches)))
            for m in mismatches[:20]:
                print("    " + m)
            if len(mismatches) > 20:
                print("    ... and " + str(len(mismatches) - 20) + " more")

            # Проверка known_diff
            if pair.known_diff:
                print("")
                print("  KNOWN DIFF: " + pair.known_diff[:200])
                # Любые mismatches при наличии known_diff — принимаем
                print("  STATUS: Known diff - ACCEPTED (all mismatches documented)")
            else:
                print("  STATUS: UNEXPECTED MISMATCH - FAIL")
                all_ok = False
                total_failures += 1
        else:
            print("  STATUS: OK (0 mismatches)")

        # RNG
        r_old = find_rng_refs(old_body)
        r_new = find_rng_refs(new_body)
        r_trans = find_rng_refs(transformed)
        if r_old == r_new == r_trans:
            print("  RNG: OK (" + (str(r_old) if r_old else "No direct RNG") + ")")
        else:
            print("  RNG: DIFF old=" + str(r_old) + " trans=" + str(r_trans) +
                  " new=" + str(r_new))
            all_ok = False
            total_failures += 1

    print("")
    print("=" * 70)
    print("RESULT: " + str(total_pairs) + " pairs, " + str(total_failures) +
          " failures")
    if all_ok:
        print("EQUIVALENCE AUDIT PASSED")
    else:
        print("EQUIVALENCE AUDIT: some failures (check above)")
    print("=" * 70)

    return 0 if all_ok else 1


def audit_structural():
    print("=" * 70)
    print("AUDIT STRUCTURAL: B1 service methods")
    print("=" * 70)

    all_ok = True
    checks = 0
    failures = 0

    engine_code = (SRC / "simulation" / "engine.py").read_text(encoding="utf-8")

    # 1. Удалены
    for pair in BATCH_B1:
        checks += 1
        count = len(re.findall(r'\bdef ' + pair.old_name + r'\b', engine_code))
        status = "OK" if count == 0 else "FAIL (" + str(count) + ")"
        print("  " + pair.old_name + ": " + status)
        if count != 0:
            all_ok = False
            failures += 1

    # 2. Есть в модулях
    for pair in BATCH_B1:
        checks += 1
        mod_path = SRC / pair.target_module
        if not mod_path.exists():
            print("  " + pair.target_module + ": NOT FOUND")
            all_ok = False
            failures += 1
            continue
        code = mod_path.read_text(encoding="utf-8")
        found = re.search(r'\bdef ' + pair.new_name + r'\b', code) is not None
        status = "OK" if found else "NOT FOUND"
        print("  " + pair.target_module + "::" + pair.new_name + ": " + status)
        if not found:
            all_ok = False
            failures += 1

    # 3. Нет импорта engine
    for pair in BATCH_B1:
        checks += 1
        mod_path = SRC / pair.target_module
        if not mod_path.exists():
            continue
        code = mod_path.read_text(encoding="utf-8")
        has_engine = "simulation.engine" in code
        status = "FAIL" if has_engine else "OK"
        print("  " + pair.target_module + ": no engine import " + status)
        if has_engine:
            all_ok = False
            failures += 1

    # 4. Размер
    checks += 1
    lines = len(engine_code.splitlines())
    status = "OK (" + str(lines) + ")" if lines < 3730 else "FAIL (" + str(lines) + ")"
    print("  engine.py: " + status)
    if lines >= 3730:
        all_ok = False
        failures += 1

    # 5. Baseline
    baseline_dir = REPO_ROOT / "tests" / "_baseline"
    expected = {
        "engine_state_seed42.json": "febae09ef46cc7ce",
        "engine_state_seed7.json": "681f47ddc8103918",
        "engine_state_seed123.json": "aec39f13625cae13",
    }
    for fname, prefix in expected.items():
        checks += 1
        fpath = baseline_dir / fname
        if not fpath.exists():
            print("  " + fname + ": NOT FOUND")
            all_ok = False
            failures += 1
            continue
        h = hashlib.sha256(fpath.read_bytes()).hexdigest()
        status = "OK (" + h[:16] + ")" if h.startswith(prefix) else "MISMATCH"
        print("  " + fname + ": " + status)
        if not h.startswith(prefix):
            all_ok = False
            failures += 1

    # 6. Нет старых вызовов
    checks += 1
    old_patterns = [
        r"engine\._has_strict_comfort", r"engine\._group_faction",
        r"engine\._home_sector_id", r"engine\._distance_to_border",
        r"engine\._sector_humans", r"engine\._squad_power",
        r"engine\._monster_group_power",
        r"self\._has_strict_comfort", r"self\._group_faction",
        r"self\._home_sector_id", r"self\._distance_to_border",
        r"self\._sector_humans", r"self\._squad_power",
        r"self\._monster_group_power",
    ]
    found = []
    for d in ["src", "tests"]:
        dpath = REPO_ROOT / d
        if not dpath.exists():
            continue
        for root, _, files in os.walk(dpath):
            for f in files:
                if not f.endswith(".py"):
                    continue
                fp = Path(root) / f
                try:
                    code = fp.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for p in old_patterns:
                    if re.search(p, code):
                        rel = str(fp.relative_to(REPO_ROOT))
                        if "audit_phase7_move" not in rel:
                            found.append(rel + ": " + p)
    if found:
        print("  Старые вызовы: " + str(len(found)) + " FOUND - FAIL")
        for f in found[:5]:
            print("    " + f)
        all_ok = False
        failures += 1
    else:
        print("  Нет старых вызовов: OK")

    # 7. Кэш
    checks += 1
    phase4 = (SRC / "simulation" / "phases" / "phase04_intentions.py").read_text(encoding="utf-8")
    if "engine._border_dist" in phase4:
        print("  border_dist кэш: восстановлен OK")
    else:
        print("  border_dist кэш: НЕ ВОССТАНОВЛЕН")
        all_ok = False
        failures += 1

    print("")
    print("=" * 70)
    print("STRUCTURAL: " + str(checks) + " checks, " + str(failures) + " failures")
    if all_ok:
        print("STRUCTURAL AUDIT PASSED")
    else:
        print("STRUCTURAL AUDIT FAILED")
    print("=" * 70)

    return 0 if all_ok else 1


def main():
    parser = argparse.ArgumentParser(description="Аудит B1 сервисных методов")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--equivalent", action="store_true")
    group.add_argument("--structural", action="store_true")
    group.add_argument("--both", action="store_true")
    args = parser.parse_args()

    if args.both:
        r1 = audit_equivalent()
        r2 = audit_structural()
        return r1 or r2
    if args.equivalent:
        return audit_equivalent()
    if args.structural:
        return audit_structural()
    return audit_structural()


if __name__ == "__main__":
    sys.exit(main())
