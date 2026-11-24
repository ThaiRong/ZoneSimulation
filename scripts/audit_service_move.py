#!/usr/bin/env python3
"""Аудит выноса сервисных методов из engine.py в доменные модули.

Поддерживает батчи через --batch, расширяемый список пар.
По умолчанию проверяет батч B1: 7 методов.

Возвращает 0 при полном совпадении, ненулевой код при расхождениях.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "zonesim"

# Батчи: имя -> список пар (old_method, target_module, new_function)
BATCHES: dict[str, list[tuple[str, str, str]]] = {
    "B1": [
        ("_has_strict_comfort", "needs/comfort.py", "has_strict_comfort"),
        ("_group_faction", "world/faction.py", "group_faction"),
        ("_home_sector_id", "world/faction.py", "home_sector_id"),
        ("_distance_to_border", "world/faction.py", "distance_to_border"),
        ("_sector_humans", "world/sectors.py", "sector_humans"),
        ("_squad_power", "combat/power.py", "squad_power"),
        ("_monster_group_power", "combat/power.py", "monster_group_power"),
    ],
}

# Строковые шаблоны для поиска старых вызовов
OLD_CALL_PATTERNS = [
    (r"engine\._has_strict_comfort", "_has_strict_comfort"),
    (r"self\._group_faction", "_group_faction"),
    (r"engine\._group_faction", "_group_faction"),
    (r"engine\._home_sector_id", "_home_sector_id"),
    (r"self\._home_sector_id", "_home_sector_id"),
    (r"engine\._distance_to_border", "_distance_to_border"),
    (r"self\._distance_to_border", "_distance_to_border"),
    (r"self\._sector_humans\(", "_sector_humans"),
    (r"engine\._sector_humans\(", "_sector_humans"),
    (r"self\._squad_power", "_squad_power"),
    (r"engine\._squad_power", "_squad_power"),
    (r"self\._monster_group_power", "_monster_group_power"),
    (r"engine\._monster_group_power", "_monster_group_power"),
    (r"self\._has_strict_comfort", "_has_strict_comfort"),
    (r"engine\._has_strict_comfort", "_has_strict_comfort"),
]


def scan_files(directory: Path, exclude: set[str] | None = None) -> list[Path]:
    """Рекурсивно сканирует .py файлы в директории."""
    exclude = exclude or set()
    result = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.endswith(".py"):
                p = Path(root) / f
                if p.name not in exclude:
                    result.append(p)
    return result


def check_method_removed(method: str) -> tuple[bool, str]:
    """Проверяет, что метод удалён из engine.py."""
    engine_file = SRC / "simulation" / "engine.py"
    code = engine_file.read_text(encoding="utf-8")
    count = len(re.findall(rf"\bdef {method}\b", code))
    if count == 0:
        return True, f"  {method}: удалён OK"
    return False, f"  {method}: НАЙДЕН в engine.py ({count} вхождений)"


def check_no_old_calls(root: Path) -> tuple[bool, str]:
    """Проверяет, что нет старых вызовов в src/ и tests/."""
    exclude = {"audit_phase7_move.py"}
    found = []
    for fpath in scan_files(root, exclude):
        try:
            code = fpath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern, name in OLD_CALL_PATTERNS:
            if re.search(pattern, code):
                rel = str(fpath.relative_to(root))
                found.append(f"    {rel}: {name}")
    if not found:
        return True, "  Все файлы: нет старых вызовов OK"
    return False, "  Найдены старые вызовы:\n" + "\n".join(found[:10])


def check_no_engine_import(target_mod: str) -> tuple[bool, str]:
    """Проверяет, что целевой модуль не импортирует simulation.engine."""
    mod_path = SRC / target_mod
    if not mod_path.exists():
        return False, f"  {target_mod}: файл не найден"
    code = mod_path.read_text(encoding="utf-8")
    if "simulation.engine" in code:
        return False, f"  {target_mod}: импортирует simulation.engine"
    return True, f"  {target_mod}: нет импорта engine OK"


def check_new_function_exists(target_mod: str, new_func: str) -> tuple[bool, str]:
    """Проверяет, что новая функция определена в целевом модуле."""
    mod_path = SRC / target_mod
    if not mod_path.exists():
        return False, f"  {target_mod}::{new_func}: файл не найден"
    code = mod_path.read_text(encoding="utf-8")
    if re.search(rf"\bdef {new_func}\b", code):
        return True, f"  {target_mod}::{new_func}: определена OK"
    return False, f"  {target_mod}::{new_func}: НЕ НАЙДЕНА"


def check_engine_size() -> tuple[bool, str]:
    """Проверяет, что engine.py уменьшился."""
    engine_file = SRC / "simulation" / "engine.py"
    lines = len(engine_file.read_text(encoding="utf-8").splitlines())
    if lines < 3730:
        return True, f"  engine.py: {lines} строк (< 3730) OK"
    return False, f"  engine.py: {lines} строк (≥ 3730) FAIL"


def check_baseline_hashes() -> tuple[bool, str]:
    """Проверяет эталонные хеши baseline файлов."""
    baseline_dir = REPO_ROOT / "tests" / "_baseline"
    expected = {
        "engine_state_seed42.json": "febae09ef46cc7ce",
        "engine_state_seed7.json": "681f47ddc8103918",
        "engine_state_seed123.json": "aec39f13625cae13",
    }
    results = []
    all_ok = True
    for fname, prefix in expected.items():
        fpath = baseline_dir / fname
        if not fpath.exists():
            results.append(f"  {fname}: файл не найден")
            all_ok = False
            continue
        h = hashlib.sha256(fpath.read_bytes()).hexdigest()
        if h.startswith(prefix):
            results.append(f"  {fname}: OK ({h[:16]})")
        else:
            results.append(f"  {fname}: РАСХОЖДЕНИЕ! expected={prefix} got={h[:16]}")
            all_ok = False
    return all_ok, "\n".join(results)


def run_pytest(pytest_args: list[str]) -> tuple[bool, str]:
    """Запускает pytest и возвращает результат."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest"] + pytest_args + ["-q"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
        timeout=600,
    )
    output = result.stdout.strip()
    if result.returncode == 0:
        return True, f"  pytest: PASSED\n  {output[-300:]}"
    return False, f"  pytest: FAILED (rc={result.returncode})\n{output[-300:]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Аудит выноса сервисных методов")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--batch", choices=sorted(BATCHES.keys()), help="Имя батча")
    group.add_argument("--all", action="store_true", help="Проверить все батчи")
    args = parser.parse_args()

    if not args.batch and not args.all:
        args.batch = "B1"

    batches_to_check = sorted(BATCHES.keys()) if args.all else [args.batch]

    print("=" * 70, flush=True)
    print(f"AUDIT SERVICE MOVE: batches {batches_to_check}", flush=True)
    print("=" * 70, flush=True)

    all_ok = True
    total_checks = 0
    total_failed = 0

    for batch_name in batches_to_check:
        methods = BATCHES[batch_name]
        print(f"\n--- Batch {batch_name}: {len(methods)} methods ---", flush=True)

        for old_method, target_mod, new_func in methods:
            checks = [
                check_method_removed(old_method),
                check_new_function_exists(target_mod, new_func),
                check_no_engine_import(target_mod),
            ]
            for ok, msg in checks:
                total_checks += 1
                if not ok:
                    total_failed += 1
                    all_ok = False
                print(msg, flush=True)

    # Глобальная проверка: старые вызовы
    print("\n--- Old call check (src/ + tests/) ---", flush=True)
    ok, msg = check_no_old_calls(REPO_ROOT)
    total_checks += 1
    if not ok:
        total_failed += 1
        all_ok = False
    print(msg, flush=True)

    # Глобальные проверки
    print("\n--- Global checks ---", flush=True)
    checks = [check_engine_size(), check_baseline_hashes()]
    for ok, msg in checks:
        for line in msg.strip().splitlines():
            total_checks += 1
            if line.strip().startswith("FAIL") or "РАСХОЖДЕНИЕ" in line or "НЕ НАЙДЕН" in line:
                all_ok = False
                total_failed += 1
        print(msg, flush=True)

    # Pytest: характеристика
    print("\n--- Pytest: characterization ---", flush=True)
    ok, msg = run_pytest(["tests/test_engine_characterization.py"])
    print(msg, flush=True)
    if not ok:
        all_ok = False
        total_failed += 1
    total_checks += 1

    # Pytest: полный набор
    print("\n--- Pytest: full suite ---", flush=True)
    ok, msg = run_pytest(["tests"])
    print(msg, flush=True)
    if not ok:
        all_ok = False
        total_failed += 1
    total_checks += 1

    # Итог
    print("\n" + "=" * 70, flush=True)
    if all_ok:
        print(f"AUDIT PASSED: {total_checks}/{total_checks} checks, 0 failures.", flush=True)
    else:
        print(f"AUDIT FAILED: {total_failed}/{total_checks} checks failed.", flush=True)
    print("=" * 70, flush=True)

    return 1 if not all_ok else 0


if __name__ == "__main__":
    sys.exit(main())
