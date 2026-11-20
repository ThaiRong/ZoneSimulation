# Карта методов SimulationEngine

Этап 3, Промпт 3.3: полная инвентаризация всех методов движка для последующего
извлечения фаз и сервисов (§20.2 ТЗ).

**Файл:** `src/zonesim/simulation/engine.py` (4307 строк)
**Всего методов:** 133

---

## 1. Инициализация и управление жизненным циклом

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 1 | `__init__` | 132 | core | Конструктор: создаёт state, context, save_manager, генерирует мир | оставить в engine |
| 2 | `from_state` | 151 | core | Classmethod: создать engine из готового состояния | оставить в engine |
| 3 | `load` | 169 | core | Classmethod: загрузить сохранение из файла | оставить в engine |
| 4 | `save` | 173 | core | Сохранить состояние в слот | оставить в engine |
| 5 | `_generate_world` | 178 | worldgen | Генерация мира по seed и config | `generation/worldgen.py` |
| 6 | `_init_trader_stock` | 280 | economy | Стартовый запас торговцев | `economy/trader.py` |
| 7 | `_init_trails` | 296 | world | Инициализация троп-рёбер графа | `world/trails.py` |
| 8 | `_init_shelters` | 327 | world | Стационарные укрытия: 8 шт, по секторам | `world/shelters.py` |

---

## 2. Публичный интерфейс

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 9 | `simulate_hour` | 1859 | core | **Главный почасовой цикл** — 11 фаз | оставить в engine (оркестратор) |
| 10 | `trade_price` | 1338 | economy | Цена покупки у торговца | `economy/pricing.py` |
| 11 | `get_state_summary` | 4289 | core | Сводка состояния для UI/журнала | `core/summary.py` |

---

## 3. Фазовые методы (simulate_hour → _phase*)

### Фаза 0: Проверка состояния

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 12 | `_phase0_check` | 1943 | phase0 | Точка входа фазы 0 | `simulation/phases/phase0_check.py` |
| 13 | `_sync_human_groups` | 1952 | world | Убрать выбывших, удалить пустые группы, выбрать лидеров | `world/groups_sync.py` |
| 14 | `_sync_monster_groups` | 211 | world | Синхронизация групп монстров | `world/groups_sync.py` |
| 15 | `_expire_findings` | 1047 | knowledge | Истечение сведений (finding expiry) | `knowledge/expiry.py` |
| 16 | `_update_shelter_participants` | 394 | shelter | Обновление участников укрытий | `shelter/occupancy.py` |

### Фаза 1: Запланированные события

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 17 | `_phase1_scheduled` | 1969 | phase1 | Точка входа фазы 1 | `simulation/phases/phase1_scheduled.py` |
| 18 | `_process_emission_schedule` | 639 | anomaly/эmission | Расписание выбросов аномалий | `anomalies/emission_schedule.py` |
| 19 | `_apply_emission_exposure` | 802 | anomaly/эmission | Урон группам при выбросе | `anomalies/emission_damage.py` |
| 20 | `_process_shelter_occupation` | 855 | shelter | Занятие укрытий монстрами | `shelter/occupation.py` |
| 21 | `_create_shelter_occupied_knowledge` | 906 | shelter/knowledge | Знание: "убежище занято монстрами" | `shelter/knowledge.py` |
| 22 | `_process_emission_shelter_assault` | 927 | shelter/anomaly | Штурм людьми убежищ монстров | `shelter/assault.py` |
| 23 | `_process_guard_rotation` | 1208 | guards | Смена охранников базы | `guards/rotation.py` |
| 24 | `_spawn_guard` | 1322 | guards | Создание NPC-охранника | `guards/spawn.py` |
| 25 | `_equip_guard` | 1174 | guards | Экипировка охранника | `guards/equip.py` |
| 26 | `_process_conditional_trader_schedule` | 501 | economy/trader | Расписание ситуативного торговца | `economy/conditional_trader.py` |
| 27 | `_broadcast_conditional_trader_info` | 526 | economy/trader | Знания о торговце | `economy/conditional_trader.py` |
| 28 | `_spawn_conditional_trader` | 562 | economy/trader | Спавн NPC-торговца | `economy/conditional_trader.py` |
| 29 | `_expire_conditional_trader_if_expired` | 598 | economy/trader | Удаление истёкшего торговца | `economy/conditional_trader.py` |
| 30 | `_process_distress_signals` | 1066 | signals | Обработка сигналов бедствия | `signals/distress.py` |
| 31 | `_active_distress_for` | 1107 | signals | Самый свежий сигнал для группы | `signals/distress.py` |

### Фаза 2: Окружающая среда

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 32 | `_phase2_environment` | 2033 | phase2 | Точка входа фазы 2 | `simulation/phases/phase2_environment.py` |
| 33 | `_process_artifact_formations` | 4191 | anomaly/artifact | Образование артефактов | `anomalies/artifact_formation.py` |

### Фаза 3: Знания

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 34 | `_phase3_knowledge` | 2050 | phase3 | Точка входа фазы 3 | `simulation/phases/phase3_knowledge.py` |
| 35 | `_check_anomaly_detection` | (out) | knowledge | Проверка обнаружения аномалий NPC | `knowledge/detection.py` |

### Фаза 4: Намерения

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 36 | `_phase4_intentions` | 2090 | phase4 | Точка входа фазы 4 | `simulation/phases/phase4_intentions.py` |
| 37 | `_phase4_monster_intentions` | 2242 | phase4/monsters | Намерения групп монстров | `simulation/phases/phase4_intentions.py` |
| 38 | `_group_kit` | 2281 | world | Комплект в инвентарях группы | `world/kit.py` |
| 39 | `_capture_target` | 2292 | capture | Цель для захвата (монстр ≤35%) | `capture/selection.py` |
| 40 | `_group_can_capture` | 2312 | capture | Проверка возможности захвата | `capture/checks.py` |
| 41 | `_group_can_destroy` | 2322 | destroy | Проверка возможности уничтожения аномалии | `destroy/checks.py` |
| 42 | `_group_detector_bonus` | 2338 | knowledge | Бонус обнаружения от детекторов | `knowledge/detector_bonus.py` |
| 43 | `_active_members` | 2360 | world | Активные члены группы | `world/groups_sync.py` |
| 44 | `_group_leader` | 2367 | world | Лидер группы | `world/groups_sync.py` |
| 45 | `_group_faction` | 1660 | faction | Фракция группы | `faction/relations.py` |

### Фаза 5: Перемещение

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 46 | `_phase5_movement` | 2381 | phase5 | Точка входа фазы 5 | `simulation/phases/phase5_movement.py` |
| 47 | `_walk` | 2454 | world/movement | Построение пути через рёбра графа | `world/movement.py` |
| 48 | `_apply_human_move` | 2481 | world/movement | Применение перемещения группы | `world/movement.py` |
| 49 | `_blocked_trail_map` | 2507 | world/trails | Карта перекрытых троп | `world/trails.py` |
| 50 | `_group_has_passage` | 2514 | world/trails | Есть ли проход через аномалию | `world/trails.py` |
| 51 | `_check_blocked_trails` | 2529 | world/trails | Проверка перекрытых троп | `world/trails.py` |
| 52 | `_move_monster_groups` | 2589 | world/movement | Перемещение групп монстров | `world/movement.py` |
| 53 | `_shelter_targets` | 483 | shelter | Цели для укрытия | `shelter/targets.py` |
| 54 | `_emission_safe_sectors` | 730 | anomaly/эmission | Сектора, защищающие от выброса | `anomalies/emission_safety.py` |
| 55 | `_is_group_emission_sheltered` | 751 | anomaly/эmission | Проверка укрытия от выброса | `anomalies/emission_safety.py` |

### Фаза 6: Обнаружение

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 56 | `_phase6_detections` | 2660 | phase6 | Точка входа фазы 6 | `simulation/phases/phase6_detections.py` |
| 57 | `_check_monster_anomaly_contacts` | 2728 | anomaly | Контакт монстров с аномалией | `anomalies/contact.py` |
| 58 | `_schedule_encounters` | 2771 | combat | Запланировать боевые встречи | `combat/encounters.py` |
| 59 | `_process_emission_shelter_assault` | 927 | combat/shelter | Штурм убежищ в выбросе | `combat/shelter_assault.py` |

### Фаза 7: Основные действия

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 60 | `_phase7_actions` | 4049 | phase7 | Точка входа фазы 7 | `simulation/phases/phase7_actions.py` |
| 61 | `_execute_battles` | 3385 | combat | Выполнение запланированных боёв | `combat/execution.py` |
| 62 | `_apply_battle_result` | 3441 | combat | Применение результата боя | `combat/results.py` |
| 63 | `_process_monster_feeding` | 3758 | monsters/feeding | Кормление монстров | `monsters/feeding.py` |
| 64 | `_process_monster_rest` | 3783 | monsters/rest | Отдых монстров после еды | `monsters/rest.py` |
| 65 | `_process_corpse_action` | 3716 | combat/loot | Действия с трупами (ограбление) | `combat/loot.py` |
| 66 | `_process_destroy_anomaly` | 3824 | destroy | Уничтожение аномалии | `destroy/execute.py` |
| 67 | `_process_capture_monster` | 3914 | capture | Захват монстра | `capture/execute.py` |
| 68 | `_process_rest_exchanges` | 1628 | world/trade | Обмены между отдыхающими группами | `world/trade.py` |
| 69 | `_barter_groups` | 1686 | world/trade | Меновая торговля | `world/trade.py` |
| 70 | `_exchange_knowledge` | 1665 | knowledge | Обмен знаниями между группами | `knowledge/exchange.py` |
| 71 | `_process_rest_trade` | 1588 | world/trade | Торговля во время отдыха | `world/trade.py` |
| 72 | `_process_create_shelter` | 1543 | shelter | Создание временного убежища | `shelter/creation.py` |
| 73 | `_aid_distress_group` | 1130 | signals | Помощь группе сигнала бедствия | `signals/rescue.py` |
| 74 | `_apply_emission_exposure` | 802 | anomaly/эmission | Урон при выбросе | `anomalies/emission_damage.py` |
| 75 | `_sleep_tick` | 3117 | needs/sleep | Восстановление выносливости (сон) | `needs/sleep.py` |
| 76 | `_unconscious_tick` | 3132 | needs/unconscious | Обработка бессознательных состояний | `needs/unconscious.py` |
| 77 | `_rest_tick` | 3181 | needs/rest | Отдых: восстановление при комфорте | `needs/rest.py` |
| 78 | `_base_heal_tick` | 3199 | needs/healing | Лечение на базе фракции | `needs/healing.py` |
| 79 | `_research_tick` | 3215 | needs/research | Исследование аномалий | `needs/research.py` |
| 80 | `_give_artifact` | 3273 | needs/artifact | Получение артефакта после исследования | `needs/artifact.py` |
| 81 | `_process_artifact_sales` | 3291 | economy/trade | Продажа артефактов NPC | `economy/artifact_trade.py` |
| 82 | `_exit_tick` | 3357 | needs/exit | Попытка покинуть Зону | `needs/exit.py` |

### Фаза 8: Воздействие окружающей среды

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 83 | `_phase8_environment` | 4161 | phase8 | Точка входа фазы 8 | `simulation/phases/phase8_environment.py` |
| 84 | `check_anomaly_migration` | (out) | anomaly/migration | Миграция аномалий | `anomalies/migration.py` |
| 85 | `_anomaly_move_candidates` | 700 | anomaly/migration | Возможные цели перемещения аномалии | `anomalies/migration.py` |
| 86 | `_roll_trail_blockage` | 310 | world/trails | Проверка перекрытия тропы | `world/trails.py` |

### Фаза 9: Последствия

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 87 | `_phase9_consequences` | 4215 | phase9 | Точка входа фазы 9 | `simulation/phases/phase9_consequences.py` |
| 88 | `_process_daily_export` | 4227 | economy/export | Ежедневный экспорт артефактов | `economy/export.py` |

### Фаза 10: Отчёт

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 89 | `_phase10_report` | 4275 | phase10 | Автосохранение + отчёт | `simulation/phases/phase10_report.py` |

---

## 4. Комбат (бои, встречи, лут)

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 90 | `_schedule_encounters` | 2771 | combat | Запланировать боевые встречи | `combat/encounters.py` |
| 91 | `_schedule_monster_attack` | 2917 | combat | Запланировать атаку монстров | `combat/encounters.py` |
| 92 | `_monster_group_power` | 2946 | combat | Сила группы монстров | `combat/power.py` |
| 93 | `_resolve_feeding_competition` | 2956 | combat/feeding | Разрешение конкуренции за корм | `combat/feeding.py` |
| 94 | `_base_guards` | 2997 | combat | Охранники сектора фракции | `combat/guards.py` |
| 95 | `_squad_power` | 3007 | combat | Боевая сила отряда | `combat/power.py` |
| 96 | `_monsters_attack` | 3029 | combat | Атака монстров | `combat/execution.py` |
| 97 | `_resolve_zero_health` | 3064 | combat | Здоровье 0 → бессознательность/смерть | `combat/results.py` |
| 98 | `_execute_battles` | 3385 | combat | Выполнение боёв | `combat/execution.py` |
| 99 | `_apply_battle_result` | 3441 | combat | Применение результата | `combat/results.py` |
| 100 | `_damage_carried_valuables` | 3672 | combat/loot | Порча ценностей при бою | `combat/loot.py` |
| 101 | `_create_corpse` | 3692 | combat/loot | Создание трупа | `combat/loot.py` |
| 102 | `_process_corpse_action` | 3716 | combat/loot | Действия с трупами | `combat/loot.py` |
| 103 | `_use_medkit_charge` | 1484 | combat/medkit | Применение аптечки | `combat/medkit.py` |
| 104 | `_emergency_medkit` | 820 | combat/medkit | Экстренная аптечка на ходу | `combat/medkit.py` |
| 105 | `_rest_heal` | 1492 | combat/medkit | Лечение в час отдыха | `combat/medkit.py` |
| 106 | `_consume_item` | 2370 | world/items | Расход предмета | `world/items.py` |
| 107 | `_set_unconscious_or_dead` | 3373 | combat | Установка состояния смерть/бессознательность | `combat/results.py` |
| 108 | `_create_item` | 1724 | world/items | Создание предмета | `world/items.py` |
| 109 | `_spawn_catalog_item` | 1770 | world/items | Спавн предмета из каталога | `world/items.py` |
| 110 | `_sync_npc_from_items` | 1781 | world/items | Синхронизация NPC → предметы | `world/items.py` |
| 111 | `_sync_items_from_npc` | 1804 | world/items | Синхронизация предметы → NPC | `world/items.py` |
| 112 | `_give_starting_equipment` | 1751 | world/items | Стартовая экипировка NPC | `world/items.py` |

---

## 5. Эмиссии (выбросы, экспозиция, аномалии)

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 113 | `_emission_active` | 475 | anomaly/emission | Проверка активного выброса | `anomalies/emission.py` |
| 114 | `_emission_known` | 480 | anomaly/emission | Проверка известного выброса | `anomalies/emission.py` |
| 115 | `_emission_safe_sectors` | 730 | anomaly/emission | Сектора защиты от выброса | `anomalies/emission.py` |
| 116 | `_is_group_emission_sheltered` | 751 | anomaly/emission | Группа укрыта от выброса | `anomalies/emission.py` |
| 117 | `_mark_group_emission_exposed` | 759 | anomaly/emission | Регистрация экспозиции группы | `anomalies/emission.py` |
| 118 | `_apply_emission_exposure` | 802 | anomaly/emission | Применение урона экспозиции | `anomalies/emission.py` |
| 119 | `_move_all_anomalies` | 706 | anomaly/migration | Перемещение всех аномалий | `anomalies/migration.py` |
| 120 | `_anomaly_move_candidates` | 700 | anomaly/migration | Возможные цели для аномалии | `anomalies/migration.py` |
| 121 | `_check_monster_anomaly_contacts` | 2728 | anomaly/contact | Контакт монстров-аномалий | `anomalies/contact.py` |
| 122 | `_process_artifact_formations` | 4191 | anomaly/artifact | Образование артефактов | `anomalies/artifact.py` |

---

## 6. Убежища

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 123 | `_update_shelter_participants` | 394 | shelter | Обновление участников | `shelter/occupancy.py` |
| 124 | `_shelter_sector_ids` | 453 | shelter | Сектора-укрытия | `shelter/sectors.py` |
| 125 | `_shelter_targets` | 483 | shelter | Цели укрытия для группы | `shelter/targets.py` |
| 126 | `_process_shelter_occupation` | 855 | shelter | Занятие укрытий монстрами | `shelter/occupation.py` |
| 127 | `_create_shelter_occupied_knowledge` | 906 | shelter/knowledge | Знание "занято монстрами" | `shelter/knowledge.py` |
| 128 | `_stale_shelter_occupied_knowledge` | 3650 | shelter/knowledge | Устаревание знания | `shelter/knowledge.py` |
| 129 | `_process_emission_shelter_assault` | 927 | shelter/assault | Штурм убежищ монстрами | `shelter/assault.py` |
| 130 | `_process_create_shelter` | 1543 | shelter/creation | Создание временного убежища | `shelter/creation.py` |
| 131 | `_group_can_create_shelter` | 1522 | shelter/creation | Проверка набора для убежища | `shelter/creation.py` |
| 132 | `_free_emptied_shelters` | 839 | shelter | Освобождение пустых укрытий | `shelter/occupancy.py` |

---

## 7. Знания и сведения

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 133 | `_expire_findings` | 1047 | knowledge | Истечение сведений | `knowledge/expiry.py` |
| 134 | `_exchange_knowledge` | 1665 | knowledge | Обмен знаниями между группами | `knowledge/exchange.py` |
| 135 | `_known_anomaly_sectors` | 3104 | knowledge | Известные аномалии NPC | `knowledge/anomaly_sectors.py` |
| 136 | `_group_detector_bonus` | 2338 | knowledge | Бонус обнаружения | `knowledge/detector_bonus.py` |

---

## 8. Монстры

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 137 | `_sync_monster_groups` | 211 | monsters | Синхронизация групп | `world/groups_sync.py` |
| 138 | `_monster_group_members` | 257 | monsters | Члены группы монстров | `world/groups_sync.py` |
| 139 | `_move_monster_groups` | 2589 | monsters/movement | Перемещение монстров | `monsters/movement.py` |
| 140 | `_process_monster_feeding` | 3758 | monsters/feeding | Кормление монстров | `monsters/feeding.py` |
| 141 | `_process_monster_rest` | 3783 | monsters/rest | Отдых монстров | `monsters/rest.py` |
| 142 | `_monster_group_power` | 2946 | monsters/power | Сила группы | `monsters/power.py` |
| 143 | `_resolve_feeding_competition` | 2956 | monsters/feeding | Конкуренция за корм | `monsters/feeding.py` |

---

## 9. Группы и лидеры

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 144 | `_sync_human_groups` | 1952 | world/groups | Синхронизация групп | `world/groups_sync.py` |
| 145 | `_active_members` | 2360 | world/groups | Активные члены | `world/groups_sync.py` |
| 146 | `_group_leader` | 2367 | world/groups | Лидер группы | `world/groups_sync.py` |
| 147 | `_group_faction` | 1660 | world/faction | Фракция группы | `world/faction.py` |
| 148 | `_group_kit` | 2281 | world/kit | Комплект группы | `world/kit.py` |

---

## 10. Охрана и базы

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 149 | `_equip_guard` | 1174 | guards | Экипировка охранника | `guards/equip.py` |
| 150 | `_process_guard_rotation` | 1208 | guards | Смена охранников | `guards/rotation.py` |
| 151 | `_spawn_guard` | 1322 | guards | Спавн охранника | `guards/spawn.py` |

---

## 11. Сны/отдых/сознание/лечение/исследование/выход (needs)

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 152 | `_sleep_tick` | 3117 | needs/sleep | Восстановление выносливости | `needs/sleep.py` |
| 153 | `_unconscious_tick` | 3132 | needs/unconscious | Бессознательность | `needs/unconscious.py` |
| 154 | `_rest_tick` | 3181 | needs/rest | Отдых | `needs/rest.py` |
| 155 | `_base_heal_tick` | 3199 | needs/healing | Лечение на базе | `needs/healing.py` |
| 156 | `_research_tick` | 3215 | needs/research | Исследование аномалий | `needs/research.py` |
| 157 | `_give_artifact` | 3273 | needs/artifact | Получение артефакта | `needs/artifact.py` |
| 158 | `_exit_tick` | 3357 | needs/exit | Покидание Зоны | `needs/exit.py` |

---

## 12. Отношения фракций

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 159 | `_save_relation_snapshot` | 1824 | relations | Снимок отношений перед шагом | `relations/snapshot.py` |
| 160 | `_log_relation_change` | 1832 | relations | Запись изменения в журнал | `relations/journal.py` |
| 161 | `_check_and_journal_relations` | 1845 | relations | Проверка и запись изменений | `relations/journal.py` |

---

## 13. Вспомогательные и утилиты

| # | Метод | Строка | Домен | Назначение | Предложение |
|---|-------|--------|-------|-----------|-------------|
| 162 | `_trail_set` | 307 | world/trails | Property: множество троп | `world/trails.py` |
| 163 | `_roll_trail_blockages` | 323 | world/trails | Проверка всех троп | `world/trails.py` |
| 164 | `_conditional_trader_is_active` | 371 | economy/trader | Статус торговца | `economy/conditional_trader.py` |
| 165 | `_conditional_trader_can_sleep` | 381 | economy/trader | Можно ли торговцу спать | `economy/conditional_trader.py` |
| 166 | `_conditional_trader_base_sector` | 385 | economy/trader | База торговца | `economy/conditional_trader.py` |
| 167 | `_group_in_shelter` | 391 | shelter | Группа в укрытии? | `shelter/checks.py` |
| 168 | `_find_trader_for_item` | 1360 | economy/trader | Поиск торговца по товару | `economy/trader.py` |
| 169 | `_purchase_plan` | 1377 | economy/trader | План покупок группы | `economy/trader.py` |
| 170 | `_sell_loot` | 1460 | economy/trader | Скупка ценностей | `economy/trader.py` |
| 171 | `_home_sector_id` | 3078 | world/faction | Домашняя база фракции | `world/faction.py` |
| 172 | `_distance_to_border` | 3088 | world/faction | До границы | `world/faction.py` |
| 173 | `_sector_humans` | 3110 | world | NPC в секторе | `world/sectors.py` |
| 174 | `_process_daily_export` | 4227 | economy/export | Экспорт артефактов | `economy/export.py` |
| 175 | `_has_strict_comfort` | 3999 | needs/comfort | Strict comfort для invariant | `needs/comfort.py` |

---

## Сводная статистика по категориям

| Категория | Методов | % |
|---|---|---|
| Фазовые методы (phase0–10) | 11 | 8.3% |
| Публичный интерфейс | 3 | 2.3% |
| Комбат (бои, встречи, лут) | 25 | 18.8% |
| Аномалии (эмиссии, артефакты) | 14 | 10.5% |
| Убежища | 12 | 9.0% |
| Знания и сведения | 6 | 4.5% |
| Монстры | 7 | 5.3% |
| Группы и лидеры | 5 | 3.8% |
| Охрана и базы | 4 | 3.0% |
| Needs (сны/отдых/лечение) | 11 | 8.3% |
| Отношения фракций | 3 | 2.3% |
| Экономика (торговля, экспорт) | 12 | 9.0% |
| Мировые (движение, тропы, предметы) | 23 | 17.3% |
| Вспомогательные утилиты | 14 | 10.5% |
| **ИТОГО** | **133** | **100%** |

---

## Целевая структура модулей (§20.2 ТЗ)

```
src/zonesim/
├── simulation/
│   ├── engine.py          ← оркестратор (simulate_hour, lifecycle)
│   ├── context.py         ← SimulationContext
│   ├── state.py           ← SimulationState dataclass
│   └── phases/            ← все _phaseN_* методы
│       ├── phase0_check.py
│       ├── phase1_scheduled.py
│       ├── phase2_environment.py
│       ├── phase3_knowledge.py
│       ├── phase4_intentions.py
│       ├── phase5_movement.py
│       ├── phase6_detections.py
│       ├── phase7_actions.py
│       ├── phase8_environment.py
│       ├── phase9_consequences.py
│       └── phase10_report.py
├── combat/                ← бои, встречи, лут, медички
├── anomalies/             ← эмиссии, артефакты, миграции, контакты
├── shelter/               ← все укрытия
├── knowledge/             ← обнаружение, обмен, истечение
├── monsters/              ← миграция, кормление, отдых, движение
├── world/                 ├── группы, лидеры, предметы, тропы, movement
│                           └── факции, базы, comfort
├── needs/                 ├── sleep, unconscious, rest, healing
│                           ├── research, artifact, exit
├── economy/               ├── торговля, экспорт, conditional_trader
├── guards/                ├── экипировка, ротация, спавн
├── relations/             ├── снимок, журнал отношений
├── capture/               ├── захват монстров
├── destroy/               ├── уничтожение аномалий
├── signals/               ├── сигналы бедствия, спасение
└── generation/            ← мирген, миграция (уже есть)
```

---

## Примечания

1. **simulate_hour** — 11 фазовых вызовов + 2 вспомогательных (_free_emptied_shelters, _save_relation_snapshot).
2. Методы `_phaseN_*` — ТОЧКИ ВХОДА для извлечения в отдельные модули.
3. Вспомогательные методы (`_sync_*`, `_process_*`, `_*tick`) — распределяются по целевым модулям.
4. Методы `from_state`, `load`, `save` — остаются в engine (lifecycle).
5. `_check_and_journal_relations` — специфичен для инварианта #17, остаётся в engine.
6. `_schedule_encounters` содержит вложенную функцию `in_combat_cooldown` — вынести в `combat/encounters.py`.
7. Импорты `from zonesim.simulation.state import SimulationState` обновлены в Промпте 3.1.
8. `SimulationContext` подключён в Промпте 3.2, но пока не используется фазовыми методами — следующая итерация.
