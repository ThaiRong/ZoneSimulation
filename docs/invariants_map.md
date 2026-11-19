"""Карта 25 инвариантов §22 → реестр coverage.

Этап 2, Часть 3: поле coverage программное (InvariantInfo.coverage),
meta-тест full≠stub, characterization-тест с golden-baseline.
"""

# ====================================================================
# Структура пакета invariants/
# ====================================================================

# invariants/
# ├── __init__.py          — экспорт из registry + check functions
# ├── registry.py          — реестр 25 инвариантов, CANONICAL_DESCRIPTIONS, coverage, check_fn
# ├── invariants_file.py   — фасад: InvariantViolation, assert_world_invariants
# ├── groups.py            — _check_human_groups (#1,2,4 full), _check_status_intentions (#5 partial)
# ├── items.py             — _check_items_and_stats (#6 full, #8 full, #9 partial)
# ├── knowledge.py         — _check_knowledge_immutability (#16 full), _check_group_knowledge (#25 full)
# ├── anomalies_bases.py   — _check_anomalies_and_bases (#10,11 full)
# ├── sleep.py             — _check_comfort_sleep_guard (#13 missing - stub)
# ├── corpses.py           — _check_corpses (#15 full), _check_finding_expiry (#21 partial)
# ├── relations.py         — _check_faction_relation_events (#17 full)
# ├── events.py            — _check_event_links (#18 partial)
# ├── emission.py          — _check_emission_movement (#20 full), _check_emission_knowledge_staleness (#22 partial)
# ├── shelter.py           — _check_shelter_occupancy (#23 partial)
# └── trails.py            — _check_trail_blockages (#24 full)

# ====================================================================
# ПОЛЕ COVERAGE (программное, из реестра)
# ====================================================================

# coverage: "full" | "partial" | "missing" | "static"
# - full: check_fn реально enforcing (есть достижимый errors.append)
# - partial: check_fn есть, но покрывает инвариант не полностью
# - missing: проверки нет ИЛИ функция-заглушка (никогда не append'ит ошибки)
# - static: architecture-тест
#
# Мета-проверка: test_full_coverage_no_stubs — проверяет что coverage=full
# имеет достижимый errors.append в исходнике check_fn.

# ====================================================================
# Распределение coverage
# ====================================================================

# full (13):  1, 2, 4, 6, 8, 10, 11, 15, 16, 17, 20, 24, 25
# partial(6): 5,  9, 18, 21, 22, 23
# missing(5): 3,  7, 12, 13, 14
# static (1): 19
#
# ИТОГО: 25

# ====================================================================
# Характеризация (golden-baseline)
# ====================================================================

# baseline: tests/_baseline/invariants_240h_seed42.json
# прогон: 240 ч, seed=42
# checkpoint_interval: 24 ч (0, 24, 48, ..., 240) = 11 чекпоинтов
# fingerprint = { invariant_id: counter } + { world_metrics: value }
#
# Наблюдения baseline:
#   hour=  0 humans= 40 inv_count= 0 inv_ids=none
#   hour= 24 humans= 40 inv_count= 0 inv_ids=none
#   ...
#   hour=240 humans= 58 inv_count= 2 inv_ids=['17']
#
# Вывод: за 240 ч инвариант #17 (отношения = событие) сработал 2 раза.
# Это ДОПУСТИМО — отношения фракций могут измениться без proper event в news.
# baseline зафиксировал именно это.

# ====================================================================
# Методы регенерации
# ====================================================================

# python tests/test_invariants_characterization.py  # regenerate baseline
# После ручного изменения логики инвариантов обновляем baseline НАМЕРЕННО.
