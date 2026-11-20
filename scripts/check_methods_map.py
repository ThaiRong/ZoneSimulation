#!/usr/bin/env python3
"""Скрипт проверки полноты карты методов engine.py.

Этап 3, Промпт 3.3 (корректировка): проверка что карта содержит все
уникальные методы SimulationEngine ровно один раз.

Запуск:
    python scripts/check_methods_map.py
    python scripts/check_methods_map.py docs/engine_methods_map.md

Выход:
    0 — зелёный (0 missing, 0 extra, 0 duplicates)
    1 — есть расхождения
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path


# Путь к файлам
BASE_DIR = Path(__file__).resolve().parent.parent
ENGINE_PATH = BASE_DIR / "src" / "zonesim" / "simulation" / "engine.py"


# ---------------------------------------------------------------------------
# Парсинг engine.py
# ---------------------------------------------------------------------------

def parse_engine_methods(engine_path: Path) -> dict[str, int]:
    """Возвращает {имя_метода: номер_строки} для всех методов SimulationEngine."""
    with engine_path.open(encoding="utf-8") as f:
        lines = f.readlines()

    # Находим начало класса SimulationEngine
    class_start = None
    for i, line in enumerate(lines):
        if "class SimulationEngine:" in line:
            class_start = i
            break

    if class_start is None:
        print("ERROR: class SimulationEngine not found in engine.py")
        return {}

    # Собираем методы: методы имеют отступ >= 8 (4 базовый + 4 def)
    methods: dict[str, int] = {}
    for i in range(class_start + 1, len(lines)):
        line = lines[i]
        # Остановка при начале нового модульного класса (пустая строка + "class " без отступа)
        stripped = line.strip()
        if stripped.startswith("class ") and not line.startswith("    "):
            break
        # Ищем методы
        match = re.match(r"    def\s+(\w+)\s*\(", line)
        if match:
            methods[match.group(1)] = i + 1  # 1-based

    return methods


# ---------------------------------------------------------------------------
# Парсинг карты методов (Markdown)
# ---------------------------------------------------------------------------

@dataclass
class MethodInMap:
    name: str
    line_num: str
    domain: str
    target: str
    phases: str
    description: str


def parse_methods_map(map_path: Path) -> list[MethodInMap]:
    """Парсит таблицу из Markdown-карты методов."""
    with map_path.open(encoding="utf-8") as f:
        lines = f.readlines()

    methods: list[MethodInMap] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        parts = [p.strip() for p in stripped.split("|")]
        parts = [p for p in parts if p]
        if len(parts) < 3:
            continue
        # Первая колонка — номер в таблице
        try:
            num = int(parts[0])
        except ValueError:
            continue
        # Вторая колонка — имя метода
        name = parts[1]
        # Пропускаем строки-разделители
        if name == "---" or name == "#":
            continue
        if len(parts) < 7:
            continue
        line_num = parts[2]
        domain = parts[3]
        description = parts[4]
        target = parts[5]
        phases = parts[6]

        methods.append(MethodInMap(
            name=name,
            line_num=line_num,
            domain=domain,
            target=target,
            phases=phases,
            description=description,
        ))

    return methods


# ---------------------------------------------------------------------------
# Сравнение и отчёт
# ---------------------------------------------------------------------------

def main(map_file: str | None = None) -> int:
    if map_file is None:
        map_file = str(BASE_DIR / "docs" / "engine_methods_map.md")

    map_path = Path(map_file)
    if not map_path.exists():
        print(f"ERROR: map file not found: {map_path}")
        return 1

    print("=" * 60)
    print(f"Проверка карты методов: {map_path.name}")
    print("=" * 60)
    print()

    # 1. Парсим engine.py
    print("Парсинг engine.py...")
    engine_methods = parse_engine_methods(ENGINE_PATH)
    print(f"  Найдено методов в SimulationEngine: {len(engine_methods)}")
    print()

    if not engine_methods:
        print("ERROR: не удалось распарсить методы engine.py")
        return 1

    # 2. Парсим карту
    print("Парсинг карты методов...")
    map_methods = parse_methods_map(map_path)
    print(f"  Найдено строк с методами в карте: {len(map_methods)}")
    unique_names = {m.name for m in map_methods}
    print(f"  Уникальных имён методов: {len(unique_names)}")
    print()

    # 3. Сравниваем
    print("Сравнение...")
    engine_names = set(engine_methods.keys())
    map_names = unique_names

    missing = sorted(engine_names - map_names)
    extra = sorted(map_names - engine_names)

    # Дубли
    name_counts: dict[str, int] = {}
    for m in map_methods:
        name_counts[m.name] = name_counts.get(m.name, 0) + 1
    duplicates = sorted(n for n, c in name_counts.items() if c > 1)

    print(f"  Всего методов в engine:     {len(engine_names)}")
    print(f"  В карте строк:              {len(map_methods)}")
    print(f"  В карте уникальных:         {len(unique_names)}")
    print(f"  Пропущено (missing):        {len(missing)}")
    print(f"  Лишние (extra):             {len(extra)}")
    print(f"  Дубликаты (duplicates):     {len(duplicates)}")
    print()

    ok = True

    if missing:
        ok = False
        print("ПРОПУЩЕНО из engine.py:")
        for name in missing:
            print(f"    - {name} (строка {engine_methods[name]})")
        print()

    if extra:
        ok = False
        print("ЛИШНИЕ в карте:")
        for name in extra:
            print(f"    + {name}")
        print()

    if duplicates:
        ok = False
        print("ДУБЛИКАТЫ в карте (встречается > 1 раз):")
        for name in duplicates:
            print(f"    x {name} -> {name_counts[name]} раз(а)")
        print()

    if ok:
        print("OK: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ:")
        print(f"   - Все {len(engine_names)} методов найдены в карте")
        print(f"   - Нет пропущенных (missing = 0)")
        print(f"   - Нет лишних (extra = 0)")
        print(f"   - Нет дубликатов (duplicates = 0)")
        print(f"   - Уникальных методов в карте: {len(unique_names)}")
        return 0
    else:
        print("ERROR: ЕСТЬ РАСХОЖДЕНИЯ — карта нуждается в исправлении")
        return 1


if __name__ == "__main__":
    map_file = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(main(map_file))
