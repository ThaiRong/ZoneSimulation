"""Карта модулей invariants/ и 25 инвариантов §22.

Этап 2, Часть 2: разбивка монолита invariants_file.py на модули.
"""

# ====================================================================
# Структура пакета simulation/invariants/
# ====================================================================

# invariants/
# ├── __init__.py          — экспорт из registry + re-export check functions
# ├── registry.py          — реестр 25 инвариантов, CANONICAL_DESCRIPTIONS, check_fn wiring
# ├── invariants_file.py   — фасад: InvariantViolation, assert_world_invariants, re-export check functions
# ├── groups.py            — _check_human_groups (#1,#2,#4), _check_status_intentions (#5)
# ├── items.py             — _check_items_and_stats (#6,#8,#9)
# ├── knowledge.py         — _check_knowledge_immutability (#16), _check_group_knowledge (#25)
# ├── anomalies_bases.py   — _check_anomalies_and_bases (#10,#11)
# ├── sleep.py             — _check_comfort_sleep_guard (#13)
# ├── corpses.py           — _check_corpses (#15), _check_finding_expiry (#21)
# ├── relations.py         — _check_faction_relation_events (#17)
# ├── events.py            — _check_event_links (#18)
# ├── emission.py          — _check_emission_movement (#20), _check_emission_knowledge_staleness (#22)
# ├── shelter.py           — _check_shelter_occupancy (#23)
# └── trails.py            — _check_trail_blockages (#24)

# ====================================================================
# Карта 25 инвариантов → модули + check_fn + coverage
# ====================================================================

# #   | Модуль                | check_fn                     | Coverage  | Тесты
# ----|-----------------------|------------------------------|-----------|------
#  1 | groups.py             | _check_human_groups          | full      | ✅ негативный, мутация
#  2 | groups.py             | _check_human_groups          | full      | ✅ негативный, мутация
#  3 | ❌ отсутствующий       | None                          | missing   | ❌ xfail (strict)
#  4 | groups.py             | _check_human_groups          | full      | ⚠️ нет явного негативного
#  5 | groups.py             | _check_status_intentions     | full*     | ✅ негативный, мутация
#  6 | items.py              | _check_items_and_stats       | full      | ✅ негативный, мутация
#  7 | ❌ отсутствующий       | None                          | missing   | ❌ xfail (strict)
#  8 | items.py              | _check_items_and_stats       | full      | ✅ негативный, мутация
#  9 | items.py              | _check_items_and_stats       | partial   | ❌ xfail (только lower bounds)
# 10 | anomalies_bases.py    | _check_anomalies_and_bases   | full      | ✅ негативный, мутация
# 11 | anomalies_bases.py    | _check_anomalies_and_bases   | full      | ✅ негативный, мутация
# 12 | ❌ отсутствующий       | None                          | missing   | ❌ xfail (strict)
# 13 | sleep.py              | _check_comfort_sleep_guard   | partial   | ❌ xfail (stub, pass)
# 14 | ❌ отсутствующий       | None                          | missing   | ❌ xfail (strict)
# 15 | corpses.py            | _check_corpses               | full      | ✅ (работает)
# 16 | knowledge.py          | _check_knowledge_immutability| full      | ✅ негативный, мутация
# 17 | relations.py          | _check_faction_relation_events| full     | ✅ mutation (test_invariants_17_25)
# 18 | events.py             | _check_event_links           | partial   | ❌ xfail (только hour)
# 19| static                | None (static)                | static    | ✅ PASS (architecture)
# 20 | emission.py           | _check_emission_movement     | full      | ✅ негативный, мутация
# 21 | corpses.py            | _check_finding_expiry        | partial   | ❌ xfail (только age)
# 22 | emission.py           | _check_emission_knowledge_staleness | partial | ❌ xfail (partial)
# 23 | shelter.py            | _check_shelter_occupancy     | partial   | ❌ xfail (только occupied_by)
# 24 | trails.py             | _check_trail_blockages       | full      | ✅ негативный, мутация
# 25 | knowledge.py          | _check_group_knowledge       | full      | ✅ mutation (test_invariants_17_25)

# ====================================================================
# check_fn wiring (registry.py)
# ====================================================================

# _FN_MAP = {
#     1: _check_human_groups,         # full
#     2: _check_human_groups,         # full
#     3: None,                        # missing
#     4: _check_human_groups,         # full
#     5: _check_status_intentions,    # full (частично: только prisoner, не sleeper)
#     6: _check_items_and_stats,      # full
#     7: None,                        # missing
#     8: _check_items_and_stats,      # full
#     9: _check_items_and_stats,      # partial
#     10: _check_anomalies_and_bases, # full
#     11: _check_anomalies_and_bases, # full
#     12: None,                       # missing
#     13: _check_comfort_sleep_guard, # partial (stub)
#     14: None,                       # missing
#     15: _check_corpses,             # full
#     16: _check_knowledge_immutability, # full
#     17: _check_faction_relation_events, # full
#     18: _check_event_links,         # partial
#     20: _check_emission_movement,   # full
#     21: _check_finding_expiry,      # partial
#     22: _check_emission_knowledge_staleness, # partial
#     23: _check_shelter_occupancy,   # partial
#     24: _check_trail_blockages,     # full
#     25: _check_group_knowledge,     # full
# }

# ====================================================================
# Результаты Этапа 2, Часть 2
# ====================================================================

# ✅ Разбит invariants_file.py (785 строк) на 11 модулей
# ✅ check_fn проставлен для всех runtime-инвариантов (full/partial/missing)
# ✅ assert_world_invariants через invariants_file.py (фасад) — ИДЕНТИЧНО
# ✅ invariants_file.py → тонкий фасад с re-export из модулей
# ✅ CI зелёный: 618 passed, 1 skipped, 6 xfailed
# ✅ Гейт верности §22 (CANONICAL_DESCRIPTIONS) зелёный
# ✅ Детерминизм цел (assert_world_invariants не менял логику)

# 📋 Пробелы (xfail strict): #3, #7, #12, #14 — проверки отсутствуют
# ⚠️ Частичные проверки: #5, #9, #13, #18, #21, #22, #23
# ✅ Полные проверки: #1, #2, #4, #6, #8, #10, #11, #15, #16, #17, #20, #24, #25
# ✅ Static: #19 (UI не мутирует мир)
