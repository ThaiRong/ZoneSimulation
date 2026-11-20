# Карта методов SimulationEngine

Этап 3, Промпт 3.3 (корректировка): полная инвентаризация всех уникальных
методов SimulationEngine для последующего извлечения фаз и сервисов (§20.2 ТЗ).

**Файл:** `src/zonesim/simulation/engine.py` (4307 строк, 132 метода)
**Покрытие:** 100% уникальных методов (по одному разу каждый)

## Таблица методов

| # | Метод | Строка | Домен | Назначение | Целевой модуль | Фаза |
|---|-------|--------|-------|-----------|---------------|------|
| 1 | __init__ | 134 | core/lifecycle | Конструктор: создаёт state, context, save_manager, генерирует мир | engine.py | init |
| 2 | from_state | 151 | core/lifecycle | Classmethod: создать engine из готового состояния | engine.py | init |
| 3 | load | 169 | core/lifecycle | Classmethod: загрузить сохранение из файла | engine.py | init |
| 4 | save | 173 | core/lifecycle | Сохранить состояние в слот | engine.py | init |
| 5 | _generate_world | 178 | worldgen | Генерация мира по seed и config | generation/worldgen.py | init |
| 6 | _sync_monster_groups | 211 | world/groups | Синхронизация групп монстров | world/groups.py | 0, 1 |
| 7 | _monster_group_members | 257 | world/groups | Члены группы монстров | world/groups.py | 4, 6 |
| 8 | _init_trader_stock | 280 | economy/trader | Стартовый запас торговцев | economy/trader.py | init |
| 9 | _init_trails | 296 | world/trails | Инициализация троп-рёбер графа | world/trails.py | init |
| 10 | _trail_set | 307 | world/trails | Свойство: множество троп | world/trails.py | 5 |
| 11 | _roll_trail_blockage | 310 | world/trails | Проверка перекрытия тропы | world/trails.py | 8 |
| 12 | _roll_trail_blockages | 323 | world/trails | Проверка всех троп | world/trails.py | init |
| 13 | _init_shelters | 327 | world/shelter | Стационарные укрытия: 8 шт, по секторам | world/shelter.py | init |
| 14 | _conditional_trader_is_active | 371 | economy/trader | Статус торговца | economy/trader.py | 1 |
| 15 | _conditional_trader_can_sleep | 381 | economy/trader | Можно ли торговцу спать | economy/trader.py | 4 |
| 16 | _conditional_trader_base_sector | 385 | economy/trader | База торговца | economy/trader.py | 4 |
| 17 | _group_in_shelter | 391 | world/shelter | Группа в укрытии? | world/shelter.py | 4 |
| 18 | _update_shelter_participants | 394 | world/shelter | Обновление участников укрытий | world/shelter.py | 0 |
| 19 | _shelter_sector_ids | 453 | world/shelter | Сектора, дающие защиту | world/shelter.py | 1, 5 |
| 20 | _emission_active | 475 | anomalies/emission | Проверка активного выброса | anomalies/emission.py | 1, 5, 7 |
| 21 | _emission_known | 480 | anomalies/emission | Проверка известного выброса | anomalies/emission.py | 4 |
| 22 | _shelter_targets | 483 | world/shelter | Цели для укрытия | world/shelter.py | 5 |
| 23 | _schedule_conditional_trader | 493 | economy/trader | Расписание ситуативного торговца | economy/trader.py | 1 |
| 24 | _process_conditional_trader_schedule | 501 | economy/trader | Проверка создания торговца | economy/trader.py | 1 |
| 25 | _broadcast_conditional_trader_info | 526 | economy/trader | Знания о торговце | economy/trader.py | 1 |
| 26 | _spawn_conditional_trader | 562 | economy/trader | Спавн NPC-торговца | economy/trader.py | 1 |
| 27 | _expire_conditional_trader_if_expired | 598 | economy/trader | Удаление истёкшего торговца | economy/trader.py | 1 |
| 28 | _process_emission_schedule | 639 | anomalies/emission | Расписание выбросов аномалий | anomalies/emission.py | 1 |
| 29 | _broadcast_emission_warning | 677 | anomalies/emission | Оповещение о выбросе | anomalies/emission.py | 1 |
| 30 | _anomaly_move_candidates | 700 | anomalies/migration | Возможные цели для аномалии | anomalies/migration.py | 8 |
| 31 | _move_all_anomalies | 706 | anomalies/migration | Перемещение всех аномалий | anomalies/migration.py | 1 |
| 32 | _emission_safe_sectors | 730 | anomalies/emission | Сектора защиты от выброса | anomalies/emission.py | 5 |
| 33 | _is_group_emission_sheltered | 751 | anomalies/emission | Группа укрыта от выброса | anomalies/emission.py | 5 |
| 34 | _mark_group_emission_exposed | 759 | anomalies/emission | Регистрация экспозиции группы | anomalies/emission.py | 1 |
| 35 | _apply_emission_exposure | 802 | anomalies/emission | Урон группам при выбросе | anomalies/emission.py | 1, 7 |
| 36 | _emergency_medkit | 820 | combat/medkit | Экстренная аптечка на ходу | combat/medkit.py | 7 |
| 37 | _free_emptied_shelters | 839 | world/shelter | Освобождение пустых укрытий | world/shelter.py | 0, 1, 7 |
| 38 | _process_shelter_occupation | 855 | world/shelter | Занятие укрытий монстрами | world/shelter.py | 1 |
| 39 | _create_shelter_occupied_knowledge | 906 | world/shelter | Знание: убежище занято монстрами | world/shelter.py | 1 |
| 40 | _process_emission_shelter_assault | 927 | world/shelter | Штурм людьми убежищ монстров | world/shelter.py | 1, 6 |
| 41 | _expire_findings | 1047 | knowledge/expiry | Истечение сведений | knowledge/expiry.py | 0 |
| 42 | _process_distress_signals | 1066 | actions/signals | Обработка сигналов бедствия | actions/signals.py | 1, 7 |
| 43 | _active_distress_for | 1107 | actions/signals | Самый свежий сигнал для группы | actions/signals.py | 1, 4, 5, 7 |
| 44 | _aid_distress_group | 1130 | actions/signals | Помощь группе сигнала бедствия | actions/signals.py | 7 |
| 45 | _equip_guard | 1174 | relations/guards | Экипировка охранника | relations/guards.py | 1 |
| 46 | _process_guard_rotation | 1208 | relations/guards | Смена охранников базы | relations/guards.py | 1 |
| 47 | _spawn_guard | 1322 | relations/guards | Создание NPC-охранника | relations/guards.py | 1 |
| 48 | trade_price | 1338 | economy/pricing | Цена покупки у торговца | economy/pricing.py | 2, 7 |
| 49 | _find_trader_for_item | 1360 | economy/trader | Поиск торговца по товару | economy/trader.py | 7 |
| 50 | _purchase_plan | 1377 | economy/trader | План покупок группы | economy/trader.py | 7 |
| 51 | _sell_loot | 1460 | economy/trader | Скупка ценностей | economy/trader.py | 7 |
| 52 | _use_medkit_charge | 1484 | combat/medkit | Применение аптечки | combat/medkit.py | 7 |
| 53 | _rest_heal | 1492 | needs/healing | Лечение в час отдыха | needs/healing.py | 7 |
| 54 | _group_can_create_shelter | 1522 | world/shelter | Проверка набора для убежища | world/shelter.py | 7 |
| 55 | _process_create_shelter | 1543 | world/shelter | Создание временного убежища | world/shelter.py | 7 |
| 56 | _process_rest_trade | 1588 | economy/trader | Торговля во время отдыха | economy/trader.py | 7 |
| 57 | _process_rest_exchanges | 1628 | world/trade | Обмены между отдыхающими группами | world/trade.py | 7 |
| 58 | _group_faction | 1660 | world/faction | Фракция группы | world/faction.py | 4 |
| 59 | _exchange_knowledge | 1665 | knowledge/exchange | Обмен знаниями между группами | knowledge/exchange.py | 7 |
| 60 | _barter_groups | 1686 | world/trade | Меновая торговля | world/trade.py | 7 |
| 61 | _create_item | 1724 | world/items | Создание предмета | world/items.py | init |
| 62 | _give_starting_equipment | 1751 | world/items | Стартовая экипировка NPC | world/items.py | 1 |
| 63 | _spawn_catalog_item | 1770 | world/items | Спавн предмета из каталога | world/items.py | init |
| 64 | _sync_npc_from_items | 1781 | world/items | Синхронизация NPC → предметы | world/items.py | 7 |
| 65 | _sync_items_from_npc | 1804 | world/items | Синхронизация предметы → NPC | world/items.py | 7 |
| 66 | _save_relation_snapshot | 1824 | relations/snapshot | Снимок отношений перед шагом | relations/snapshot.py | 1 |
| 67 | _log_relation_change | 1832 | relations/journal | Запись изменения в журнал | relations/journal.py | 1 |
| 68 | _check_and_journal_relations | 1845 | relations/journal | Проверка и запись изменений | relations/journal.py | 1 |
| 69 | simulate_hour | 1859 | core/orchestrator | Главный почасовой цикл — 11 фаз | engine.py | 0-10 |
| 70 | _phase0_check | 1943 | phase/0_check | Точка входа фазы 0: проверка состояния | phases/phase0_check.py | 0 |
| 71 | _sync_human_groups | 1952 | world/groups | Убрать выбывших, удалить пустые группы, выбрать лидеров | world/groups.py | 0, 9 |
| 72 | _phase1_scheduled | 1969 | phase/1_scheduled | Точка входа фазы 1: запланированные события | phases/phase1_scheduled.py | 1 |
| 73 | _phase2_environment | 2033 | phase/2_environment | Точка входа фазы 2: окружающая среда и торговля | phases/phase2_environment.py | 2 |
| 74 | _phase3_knowledge | 2050 | phase/3_knowledge | Точка входа фазы 3: обнаружение и сведения | phases/phase3_knowledge.py | 3 |
| 75 | _phase4_intentions | 2090 | phase/4_intentions | Точка входа фазы 4: выбор намерений | phases/phase4_intentions.py | 4 |
| 76 | _phase4_monster_intentions | 2242 | ai/intentions | Намерения групп монстров | ai/intentions.py | 4 |
| 77 | _group_kit | 2281 | world/groups | Комплект в инвентарях группы | world/groups.py | 4 |
| 78 | _capture_target | 2292 | actions/capture | Цель для захвата (монстр ≤35%) | actions/capture.py | 4 |
| 79 | _group_can_capture | 2312 | actions/capture | Проверка возможности захвата | actions/capture.py | 4 |
| 80 | _group_can_destroy | 2322 | actions/destroy | Проверка возможности уничтожения аномалии | actions/destroy.py | 4 |
| 81 | _group_detector_bonus | 2338 | knowledge/detection | Бонус обнаружения от детекторов | knowledge/detection.py | 4 |
| 82 | _active_members | 2360 | world/groups | Активные члены группы | world/groups.py | 4, 5 |
| 83 | _group_leader | 2367 | world/groups | Лидер группы | world/groups.py | 4 |
| 84 | _consume_item | 2370 | world/items | Расход предмета | world/items.py | 7 |
| 85 | _phase5_movement | 2381 | phase/5_movement | Точка входа фазы 5: перемещение | phases/phase5_movement.py | 5 |
| 86 | _walk | 2454 | world/movement | Построение пути через рёбра графа | world/movement.py | 5 |
| 87 | _apply_human_move | 2481 | world/movement | Применение перемещения группы | world/movement.py | 5 |
| 88 | _blocked_trail_map | 2507 | world/trails | Карта перекрытых троп | world/trails.py | 5 |
| 89 | _group_has_passage | 2514 | world/trails | Есть ли проход через аномалию | world/trails.py | 5 |
| 90 | _check_blocked_trails | 2529 | world/trails | Проверка перекрытых троп | world/trails.py | 5 |
| 91 | _move_monster_groups | 2589 | monsters/movement | Перемещение групп монстров | monsters/movement.py | 5 |
| 92 | _phase6_detections | 2660 | phase/6_detections | Точка входа фазы 6: обнаружение | phases/phase6_detections.py | 6 |
| 93 | _check_monster_anomaly_contacts | 2728 | anomalies/contact | Контакт монстров с аномалией | anomalies/contact.py | 6 |
| 94 | _schedule_encounters | 2771 | combat/encounters | Запланировать боевые встречи | combat/encounters.py | 6 |
| 95 | _schedule_monster_attack | 2917 | combat/encounters | Запланировать атаку монстров | combat/encounters.py | 6 |
| 96 | _monster_group_power | 2946 | combat/power | Сила группы монстров | combat/power.py | 6 |
| 97 | _resolve_feeding_competition | 2956 | monsters/feeding | Разрешение конкуренции за корм | monsters/feeding.py | 6 |
| 98 | _base_guards | 2997 | combat/guards | Охранники сектора фракции | combat/guards.py | 6 |
| 99 | _squad_power | 3007 | combat/power | Боевая сила отряда | combat/power.py | 6 |
| 100 | _monsters_attack | 3029 | combat/execution | Атака монстров | combat/execution.py | 6 |
| 101 | _resolve_zero_health | 3064 | combat/results | Здоровье 0 → бессознательность/смерть | combat/results.py | 6, 7 |
| 102 | _home_sector_id | 3078 | world/faction | Домашняя база фракции | world/faction.py | 4, 5 |
| 103 | _distance_to_border | 3088 | world/faction | До границы в рёбрах | world/faction.py | 4 |
| 104 | _known_anomaly_sectors | 3104 | knowledge/anomaly_sectors | Известные аномалии NPC | knowledge/anomaly_sectors.py | 5 |
| 105 | _sector_humans | 3110 | world/sectors | NPC в секторе | world/sectors.py | 6 |
| 106 | _sleep_tick | 3117 | needs/sleep | Восстановление выносливости (сон) | needs/sleep.py | 7 |
| 107 | _unconscious_tick | 3132 | needs/unconscious | Обработка бессознательных состояний | needs/unconscious.py | 7 |
| 108 | _rest_tick | 3181 | needs/rest | Отдых: восстановление при комфорте | needs/rest.py | 7 |
| 109 | _base_heal_tick | 3199 | needs/healing | Лечение на базе фракции | needs/healing.py | 7 |
| 110 | _research_tick | 3215 | needs/research | Исследование аномалий | needs/research.py | 7 |
| 111 | _give_artifact | 3273 | needs/artifact | Получение артефакта после исследования | needs/artifact.py | 7 |
| 112 | _process_artifact_sales | 3291 | economy/trader | Продажа артефактов NPC | economy/trader.py | 7 |
| 113 | _exit_tick | 3357 | needs/exit | Попытка покинуть Зону | needs/exit.py | 7 |
| 114 | _set_unconscious_or_dead | 3373 | combat/results | Установка состояния смерть/бессознательность | combat/results.py | 7 |
| 115 | _execute_battles | 3385 | combat/execution | Выполнение запланированных боёв | combat/execution.py | 7 |
| 116 | _apply_battle_result | 3441 | combat/results | Применение результата боя | combat/results.py | 7 |
| 117 | _stale_shelter_occupied_knowledge | 3650 | world/shelter | Устаревание знания об укрытии | world/shelter.py | 7 |
| 118 | _damage_carried_valuables | 3672 | combat/loot | Порча ценностей при бою | combat/loot.py | 7 |
| 119 | _create_corpse | 3692 | combat/loot | Создание трупа | combat/loot.py | 7 |
| 120 | _process_corpse_action | 3716 | combat/loot | Действия с трупами | combat/loot.py | 7 |
| 121 | _process_monster_feeding | 3758 | monsters/feeding | Кормление монстров | monsters/feeding.py | 7 |
| 122 | _process_monster_rest | 3783 | monsters/rest | Отдых монстров после еды | monsters/rest.py | 7 |
| 123 | _process_destroy_anomaly | 3824 | actions/destroy | Уничтожение аномалии | actions/destroy.py | 7 |
| 124 | _process_capture_monster | 3914 | actions/capture | Захват монстра | actions/capture.py | 7 |
| 125 | _has_strict_comfort | 3999 | needs/comfort | Strict comfort для invariant | needs/comfort.py | 4, 7 |
| 126 | _phase7_actions | 4049 | phase/7_actions | Точка входа фазы 7: основные действия | phases/phase7_actions.py | 7 |
| 127 | _phase8_environment | 4161 | phase/8_environment | Точка входа фазы 8: воздействие среды | phases/phase8_environment.py | 8 |
| 128 | _process_artifact_formations | 4191 | anomalies/artifact | Образование артефактов | anomalies/artifact.py | 2 |
| 129 | _phase9_consequences | 4215 | phase/9_consequences | Точка входа фазы 9: последствия | phases/phase9_consequences.py | 9 |
| 130 | _process_daily_export | 4227 | economy/export | Ежедневный экспорт артефактов | economy/export.py | 9 |
| 131 | _phase10_report | 4275 | phase/10_report | Автосохранение + отчёт | phases/phase10_report.py | 10 |
| 132 | get_state_summary | 4289 | core/summary | Сводка состояния для UI/журнала | engine.py | 10 |

## Сводная статистика по категориям

| Категория | Методов |
|---|---|
| world | 39 |
| economy | 16 |
| combat | 15 |
| anomalies | 12 |
| phase | 11 |
| needs | 9 |
| actions | 8 |
| core | 6 |
| relations | 6 |
| knowledge | 4 |
| monsters | 4 |
| worldgen | 1 |
| ai | 1 |
| **ИТОГО** | **132** |

## Целевая структура модулей (соответствие ТЗ §20.2)

```
src/zonesim/
├── simulation/
│   ├── engine.py          ← оркестратор + lifecycle
│   ├── context.py         ← SimulationContext
│   ├── state.py           ← SimulationState dataclass
│   └── phases/            ← все _phaseN_* методы (11 модулей)
├── combat/                ← бои, встречи, лут, медички, трупы, результаты
├── anomalies/             ← эмиссии, артефакты, миграции, контакты
├── knowledge/             ← обнаружение, обмен, истечение, детекторы
├── monsters/              ← миграция, кормление, отдых, движение, сила
├── world/                 ← группы, лидеры, предметы, тропы, movement,
│                           shelter (укрытия), faction (факции), sectors
├── needs/                 ← sleep, unconscious, rest, healing, research,
│                           artifact, exit, comfort
├── economy/               ← торговля, экспорт, conditional_trader, pricing
├── relations/             ← снимок, журнал отношений, guards (охранники)
├── actions/               ← capture (захват), destroy (уничтожение),
│                           signals (сигналы бедствия)
├── ai/                    ← намерения, выбор действий
├── generation/            ← мирген, миграция
├── news/                  ← новости
├── persistence/           ← сериализация
└── ui/                    ← интерфейс
```

## Примечания

1. **simulate_hour** — оркестратор 11 фаз + 2 вспомогательных метода.
2. Методы `_phaseN_*` — ТОЧКИ ВХОДА для извлечения в отдельные модули phases/.
3. Вспомогательные методы распределяются по целевым модулям согласно таблице.
4. Методы `from_state`, `load`, `save` — остаются в engine (lifecycle).
5. `_check_and_journal_relations` — специфичен для инварианта #17.
6. `_schedule_encounters` содержит вложенную функцию `in_combat_cooldown`.
7. Все методы из engine.py: уникальных 132 (без внешних функций).