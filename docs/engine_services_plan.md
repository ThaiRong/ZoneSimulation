# План выноса доменных сервисов из engine.py

**Этап 3, Промпт 3.9A.** Создание полного графа вызовов, классификация,
конвенции и план батчей для извлечения сервисных методов из SimulationEngine.

**Файл:** `src/zonesim/simulation/engine.py` (3612 строк, 106 методов после B1)
**До после B1:** 3730 → 3612 строк, −118 строк, 7 методов вынесено.
**Охват:** Все 106 оставшихся методов, кроме lifecycle (`__init__`, `from_state`, `load`, `save`),
orchestrator (`simulate_hour`, `get_state_summary`) и 7 уже вынесенных (B1).

---

## 1. ГРАФ ВЫЗОВОВ

Для каждого метода указаны:
- **calls** — вызовы других хелперов (`self._xxx`), внешних функций, state.rng
- **reads** — чтение атрибутов движка (`self.state.xxx`, `self._xxx`)
- **mutates** — мутация атрибутов движка (`.append`, `.add`, `.clear`, присваивание)
- **nested_def** — вложенные `def`/`lambda`
- **property** — `True` если метод декорирован `@property`

### 1.1 Методы — не вызывают других хелперов (листья)

Эти методы НЕ вызывают `self._xxx` и являются «чистыми» кандидатами для выноса.

| Метод | Строка | Домен | Reads | Mutates | external_calls | nested_def |
|-------|--------|-------|-------|---------|----------------|------------|
| `_conditional_trader_is_active` | 389 | economy/trader | state.conditional_trader_* | — | — | — |
| `_emission_active` | 493 | anomalies/emission | state.emission_start/end | — | is_emission_active() | — |
| `_emission_known` | 498 | anomalies/emission | state.emission_warning_hour | — | is_emission_known() | — |
| `_emission_safe_sectors` | 748 | anomalies/emission | state.shelters/sectors/stationary | — | — | — |
| `_active_distress_for` | 1125 | actions/signals | state.humans/knowledge_bases | — | KnowledgeType | — |
| `_find_trader_for_item` | 1378 | economy/trader | state.stationary_humans | — | EntityStatus | — |
| `_group_kit` | 2012 | world/groups | state.items | — | ItemType | — |
| `_capture_target` | 2023 | actions/capture | state.monsters | — | EntityStatus, species_value() | — |
| `_active_members` | 2091 | world/groups | state.humans | — | EntityStatus | — |
| `_group_leader` | 2098 | world/groups | group.leader_id, members | — | — | — |
| `_monster_group_members` | 275 | world/groups | state.monsters | — | EntityStatus, species_value() | — |
| `_base_guards` | 2577 | combat/guards | state.sectors/stationary_humans | — | EntityStatus | — |
| `_monsters_attack` | 2586 | combat/execution | state.sectors, state.items | — | squad_power(), calculate_hunt_chance(), species_value() | — |
| `_resolve_zero_health` | 2621 | combat/results | state.rng, npc.max_health | npc.status, npc.unconscious_* | calculate_unconscious_chance(), resolve_unconscious_check() | — |
| `_known_anomaly_sectors` | 2635 | knowledge/anomaly_sectors | state.knowledge_bases | — | known_anomaly_sectors() | — |
| `_blocked_trail_map` | 2165 | world/trails | state.anomalies | — | AnomalyStatus | — |
| `_group_has_passage` | 2172 | world/trails | state.humans/knowledge_bases | — | KnowledgeType | — |
| `_exit_tick` | 2881 | needs/exit | state.sectors, state.exile_manager | — | EntityStatus | — |
| `_expire_conditional_trader_if_expired` | 616 | economy/trader | state.conditional_trader_*, state.humans, state.news_manager | npc.status, conditional_trader_* | EntityStatus, _schedule_conditional_trader() | — |
| `_schedule_conditional_trader` | 511 | economy/trader | state.next_conditional_spawn_hour, state.rng | next_conditional_spawn_hour | — | — |
| `_conditional_trader_can_sleep` | 399 | economy/trader | — | — | _conditional_trader_is_active() | — |
| `_conditional_trader_base_sector` | 403 | economy/trader | state.conditional_trader_sector | — | _conditional_trader_is_active() | — |
| `_expire_findings` | 1065 | knowledge/expiry | state.corpses/items/news_manager | state.items.pop(), state.corpses | EntityStatus | — |
| `_sync_npc_from_items` | 1794 | world/items | state.items | npc.weapon_condition/damage, armor_condition/value, ammo, medicines | EquipmentManager.get_armor_effectiveness() | — |
| `_sync_items_from_npc` | 1817 | world/items | state.items, npc.inventory | item.condition, item.quantity | — | — |
| `_consume_item` | 2101 | world/items | state.items, members | owner.inventory, equipped_*, items.pop | give_item() | — |
| `_save_relation_snapshot` | 1837 | relations/snapshot | state.faction_relations._relations | state.prev_relation_snapshot | — | — |
| `_log_relation_change` | 1845 | relations/journal | — | state.relation_change_journal.append | — | — |
| `_stale_shelter_occupied_knowledge` | 3174 | world/shelter | state.knowledge_bases, state.news_manager | fact.valid_until, fact.payload | KnowledgeType | — |
| `_check_and_journal_relations` | 1858 | relations/journal | state.faction_relations._relations, state.prev_relation_snapshot | — | _log_relation_change() | — |
| `_schedule_monster_attack` | 2507 | combat/encounters | state.rng, state.time | monster.target_id, target_memory_hour | select_weakest_target() | — |
| `_base_guards` | 2577 | combat/guards | state.sectors, state.stationary_humans | — | EntityStatus | — |
| `_process_daily_export` | 3547 | economy/export | state.time, state.humans, state.import_export | import_export.export_records, daily_export_totals | ExportRecord | — |
| `_process_artifact_formations` | 3523 | anomalies/artifact | state.anomalies, state.artifacts, state.rng, state.news_manager | art.discovered | _emission_active(), EMISSION_ARTIFACT_ACCELERATION | — |
| `_process_monster_rest` | 3307 | monsters/rest | fed_groups, state.monster_groups, state.rng, _combat_monster_ids | monster.health/stamina/status | _monster_group_members(), MONSTER_HEALTH_REGEN_* | — |
| `_roll_trail_blockages` | 341 | world/trails | state.anomalies | — | _roll_trail_blockage() | — |
| `_sync_human_groups` | 1956 | world/groups | state.humans, state.human_groups | group.members/sector_id/leader_id, npc.group_id, human_groups.del | EntityStatus, HumanGroup | — |
| `_group_in_shelter` | 409 | world/shelter | — | — | _shelter_sector_ids() | — |
| `_shelter_targets` | 501 | world/shelter | state.shelters, state.time | — | _shelter_sector_ids() | — |
| `_roll_trail_blockage` | 328 | world/trails | state.rng, _trail_set, state.sectors, state.anomalies | anomaly.blocks_trail | EMISSION_TRAIL_BLOCK_CHANCE | — |
| `_damage_carried_valuables` | 3196 | combat/loot | npc.inventory, state.items, state.rng, result.battle_log | item.condition | EquipmentManager.check_value_damage() | — |
| `_is_group_emission_sheltered` | 769 | anomalies/emission | group.sector_id | — | _emission_safe_sectors() | — |

### 1.2 Методы — вызывают 1 хелпер

| Метод | Вызывает | Строка |
|-------|----------|--------|
| `_conditional_trader_can_sleep` | `_conditional_trader_is_active` | 399 |
| `_conditional_trader_base_sector` | `_conditional_trader_is_active` | 403 |
| `_emergency_medkit` | `_use_medkit_charge` | 838 |
| `_rest_heal` | `_use_medkit_charge` | 1510 |
| `_use_medkit_charge` | `_consume_item` | 1502 |
| `_check_and_journal_relations` | `_log_relation_change` | 1858 |
| `_sell_loot` | `_consume_item` | 1478 |
| `_give_artifact` | `_create_item` | 2797 |
| `_set_unconscious_or_dead` | `_resolve_zero_health` | 2897 |
| `_execute_battles` | `_sync_npc_from_items`, `_shelter_sector_ids` | 2909 |
| `_stale_shelter_occupied_knowledge` | (none, but uses state.news_manager) | 3174 |
| `_group_in_shelter` | `_shelter_sector_ids` | 409 |
| `_shelter_targets` | `_shelter_sector_ids` | 501 |
| `_process_emission_shelter_assault` | `_emission_active`, `_emission_safe_sectors` | 945 |
| `_mark_group_emission_exposed` | `_active_members`, `_emergency_medkit`, `_set_unconscious_or_dead` | 777 |
| `_expire_conditional_trader_if_expired` | `_schedule_conditional_trader` | 616 |
| `_group_can_capture` | `_capture_target`, `_group_kit` | 2043 |
| `_group_can_destroy` | `_group_kit` | 2053 |
| `_process_create_shelter` | `_active_members`, `_group_leader` | 1561 |
| `_apply_battle_result` | `_emission_active`, `_is_group_emission_sheltered`, `_mark_group_emission_exposed`, `_stale_shelter_occupied_knowledge`, `_create_corpse`, `_sync_items_from_npc`, `_damage_carried_valuables` | 2965 |
| `_unconscious_tick` | `_use_medkit_charge`, `_sync_npc_from_items` | 2656 |
| `_rest_tick` | `_base_heal_tick` | 2705 |
| `_base_heal_tick` | `_sync_npc_from_items`, `trade_price` | 2723 |
| `_process_rest_exchanges` | `_exchange_knowledge`, `_barter_groups`, `_log_relation_change` | 1646 |
| `_apply_emission_exposure` | `_active_members`, `_is_group_emission_sheltered`, `_mark_group_emission_exposed` | 820 |
| `_aid_distress_group` | `_active_members`, `_use_medkit_charge` | 1148 |
| `_process_distress_signals` | `_active_members` | 1084 |
| `_roll_trail_blockages` | `_roll_trail_blockage` | 341 |
| `_apply_human_move` | `_check_blocked_trails` | 2139 |
| `_buy_price` / `trade_price` | `_find_trader_for_item` | 1365 |
| `_process_rest_trade` | `_active_members`, `_rest_heal`, `_group_leader`, `_sell_loot`, `_purchase_plan`, `trade_price`, `_sync_npc_from_items` | 1606 |

### 1.3 Методы — вызывают 2+ хелперов (зависимые)

| Метод | Вызывает | Строка |
|-------|----------|--------|
| `_update_shelter_participants` | `_shelter_sector_ids`, `_walk` | 412 |
| `_move_all_anomalies` | `_roll_trail_blockage` | 724 |
| `_process_emission_schedule` | `_emission_active`, `_move_all_anomalies`, `_broadcast_emission_warning` | 657 |
| `_process_conditional_trader_schedule` | `_schedule_conditional_trader`, `_broadcast_conditional_trader_info`, `_spawn_conditional_trader` | 519 |
| `_spawn_conditional_trader` | `_give_starting_equipment` | 580 |
| `_equip_guard` | `_spawn_catalog_item`, `_sync_npc_from_items` | 1192 |
| `_process_guard_rotation` | `_spawn_guard`, `_equip_guard` | 1226 |
| `_spawn_guard` | `_equip_guard` | 1340 |
| `_give_starting_equipment` | `_spawn_catalog_item`, `_sync_npc_from_items` | 1764 |
| `_move_monster_groups` | `_trail_set`, `_walk`, `_check_blocked_trails`, `_monster_group_members` | 2247 |
| `_check_blocked_trails` | `_blocked_trail_map`, `_group_has_passage`, `_group_detector_bonus`, `_create_corpse`, `_set_unconscious_or_dead` | 2187 |
| `_schedule_encounters` | `_monster_group_members`, `_monsters_attack`, `_schedule_monster_attack`, `_base_guards`, `_resolve_feeding_competition` | 2361 |
| `_resolve_feeding_competition` | `_monster_group_members`, `_schedule_monster_attack` | 2536 |
| `_purchase_plan` | `_capture_target`, `_group_kit`, `_group_leader`, `trade_price`, `_sync_npc_from_items` | 1395 |
| `_process_rest_trade` | 7 хелперов (см. выше) | 1606 |
| `_apply_battle_result` | 7 хелперов (см. выше) | 2965 |
| `_research_tick` | `_give_artifact`, `_set_unconscious_or_dead` | 2739 |
| `_process_destroy_anomaly` | `_active_members`, `_group_kit`, `_group_leader`, `_consume_item`, `_give_artifact`, `_set_unconscious_or_dead` | 3348 |
| `_process_capture_monster` | `_active_members`, `_capture_target`, `_group_kit`, `_group_leader`, `_consume_item`, `_create_item`, `_set_unconscious_or_dead`, `_monster_group_members` | 3438 |
| `_check_monster_anomaly_contacts` | `_monster_group_members`, `_create_corpse` | 2318 |
| `_process_shelter_occupation` | `_monster_group_members` | 873 |
| `_phase4_intentions` (через run_phase4) | `_process_distress_signals`, `_emission_known`, `_emission_active`, `_active_distress_for`, `_group_can_destroy`, `_group_can_capture`, `_group_can_create_shelter`, `_phase4_monster_intentions` | 2090 |
| `_process_rest_trade` | `_active_members`, `_rest_heal`, `_sell_loot`, `_purchase_plan`, `trade_price`, `_sync_npc_from_items` | 1606 |
| `_process_artifact_sales` | `_create_item`, `trade_price`, `_sync_npc_from_items` | 2815 |

### 1.4 `_generate_world` — инициализация (не выносить, но в графе)

| Метод | Вызывает | Строка |
|-------|----------|--------|
| `_generate_world` | `_give_starting_equipment`, `_equip_guard`, `_init_trader_stock`, `_init_trails`, `_roll_trail_blockages`, `_sync_monster_groups` | 196 |
| `_sync_monster_groups` | species_value() (внешняя) | 229 |
| `_init_trader_stock` | (без self._xxx) | 298 |
| `_init_trails` | (без self._xxx) | 314 |
| `_init_shelters` | (без self._xxx, есть lambda) | 345 |

### 1.5 Lifecycle / Orchestrator

| Метод | Вызывает | Строка |
|-------|----------|--------|
| `__init__` | `_generate_world` | 150 |
| `from_state` | (без self._xxx) | 168 |
| `load` | `SaveManager`, `from_state` | 186 |
| `save` | `save_manager.save` | 190 |
| `simulate_hour` | run_phase0-10 (все фазы) | 1885 |
| `get_state_summary` | (без self._xxx) | 3570 |

### 1.6 Особые методы

| Метод | Строка | property | nested_def |
|-------|--------|----------|------------|
| `_trail_set` | 325 | **True** | — |
| `_schedule_encounters` | 2361 | — | **`in_combat_cooldown(*groups)`** (строка ~2383) |

---

## 2. КЛАССИФИКАЦИЯ

### 2.1 Чистые (зависят только от state и аргументов, не вызывают self._xxx)

Эти методы НЕ вызывают других хелперов. Можно выносить первыми.

**Листья графа (38 методов):**

```
conditional_trader_is_active
conditional_trader_can_sleep
conditional_trader_base_sector
emission_active
emission_known
emission_safe_sectors
active_distress_for
find_trader_for_item
group_kit
capture_target
active_members
group_leader
monster_group_members
base_guards
monsters_attack
resolve_zero_health
known_anomaly_sectors
blocked_trail_map
group_has_passage
exit_tick
schedule_conditional_trader
expire_findings
sync_npc_from_items
sync_items_from_npc
consume_item
save_relation_snapshot
log_relation_change
stale_shelter_occupied_knowledge
schedule_monster_attack
process_daily_export
damage_carried_valuables
```

**Листья, но с вызовами других хелперов (1-2, можно выносить в батчах 2+):**

```
group_in_shelter → _shelter_sector_ids
shelter_targets → _shelter_sector_ids
roll_trail_blockage (использует _trail_set property)
is_group_emergency_sheltered → _emission_safe_sectors
emergency_medkit → _use_medkit_charge
rest_heal → _use_medkit_charge
use_medkit_charge → _consume_item
check_and_journal_relations → _log_relation_change
sell_loot → _consume_item
give_artifact → _create_item
set_unconscious_or_dead → _resolve_zero_health
group_can_capture → _capture_target, _group_kit
group_can_destroy → _group_kit
process_create_shelter → _active_members, _group_leader
```

### 2.2 Зависимые (вызывают другие хелперы)

**Уровень 1 (зависят от 1 метода):** 23 метода

**Уровень 2 (зависят от 2+ методов):** 18 методов

**Уровень 3 (глубокие):**
- `_process_conditional_trader_schedule` → `schedule_conditional_trader`, `broadcast_conditional_trader_info`, `spawn_conditional_trader` → `give_starting_equipment`
- `_process_guard_rotation` → `spawn_guard` → `equip_guard` → `spawn_catalog_item`, `sync_npc_from_items`
- `equip_guard` → `spawn_catalog_item`, `sync_npc_from_items`
- `give_starting_equipment` → `spawn_catalog_item`, `sync_npc_from_items`

### 2.3 Циклы / сильно связанные компоненты

**Циклов нет.** Вызовы хелперов образуют DAG (направленный ациклический граф).

**Крупные связи:**
- `_process_rest_trade` → 7 хелперов
- `_apply_battle_result` → 7 хелперов
- `_schedule_encounters` → 5 хелперов + `in_combat_cooldown` (вложенный def)
- `_process_capture_monster` → 8 хелперов
- `_process_destroy_anomaly` → 6 хелперов

---

## 3. КОНВЕНЦИЯ ВЫНОСА

### 3.1 Форма

**Модульные функции, НЕ классы-сервисы.** Каждая функция — отдельный `def` на уровне модуля.

### 3.2 Сигнатура

```python
def helper_name(state, ...явные_аргументы) -> ReturnType:
    """Документация — копия docstring из engine."""
```

- `state` — первый параметр (SimulationState)
- Далее — исходные аргументы метода в исходном порядке
- `rng` брать из `state.rng`, отдельным параметром не передавать

### 3.3 Кэши движка

Кэши движка (`_home_cache`, `_border_dist`) остаются на движке. Если функция их использует —
передавать явным параметром с дефолтом `None`:

```python
def home_sector_id(state, faction: str, home_cache: dict | None = None) -> int | None:
    cache = home_cache if home_cache is not None else {}  # для вызовов вне engine
    ...
```

### 3.4 Коллекции движка

Коллекции (`_pending_battles`, `_combat_*_ids`, `_feeding_claims`) передаются явным параметром:

```python
def schedule_encounters(state, is_night: bool, hour: int,
                        pending_battles: list[dict],
                        combat_human_ids: set[int],
                        combat_monster_ids: set[int],
                        feeding_claims: dict[int, int],
                        ...):
```

### 3.5 Мутация vs Переприсваивание

**ЗАПРЕЩЕНО** переприсваивание коллекций внутри вынесенной функции:

```python
# ❌ ЗАПРЕЩЕНО — вызывающая сторона не увидит замену
def bad(pending_battles):
    pending_battles = []  # потеряно!

# ✅ ТОЛЬКО мутация на месте
def good(pending_battles):
    pending_battles.clear()  # видно вызывающей
    pending_battles.append(...)
```

Для методов, которые переприсваивают коллекцию (например `_schedule_encounters` делает
`self._pending_battles = []`), в вынесенной функции делать так:

```python
def schedule_encounters(..., pending_battles, combat_human_ids, ...):
    pending_battles.clear()  # мутация, видно вызывающей
    combat_human_ids.clear()
    ...
```

### 3.6 Зависимости между модулями

- Доменные модули НЕ импортируют `engine` и НЕ импортируют `simulation.engine`
- `SimulationState` — только под `TYPE_CHECKING`
- Если функция вызывает другую вынесенную функцию — импортировать её из целевого модуля
- Вложенные def/lambda остаются в engine, если вызывают ещё не вынесенные хелперы

---

## 4. ПЛАН БАТЧЕЙ

Принцип: вызовы идут ТОЛЬКО назад — к уже вынесенным модулям или к чистым внешним функциям.

### Батч 1: Чистые листья (0 зависимостей от self._xxx)

**Методы (19):**

```
conditional_trader_is_active      → economy/trader.py
conditional_trader_can_sleep      → economy/trader.py
conditional_trader_base_sector    → economy/trader.py
emission_active                    → anomalies/emission.py
emission_known                     → anomalies/emission.py
emission_safe_sectors              → anomalies/emission.py
active_distress_for                → actions/signals.py
find_trader_for_item               → economy/trader.py
group_kit                          → world/groups.py
capture_target                     → actions/capture.py
active_members                     → world/groups.py
group_leader                       → world/groups.py
monster_group_members              → world/groups.py
base_guards                        → combat/guards.py
resolve_zero_health                → combat/results.py
known_anomaly_sectors              → knowledge/anomaly_sectors.py
blocked_trail_map                  → world/trails.py
group_has_passage                  → world/trails.py
exit_tick                          → needs/exit.py
schedule_conditional_trader        → economy/trader.py
expire_findings                    → knowledge/expiry.py
sync_npc_from_items                → world/items.py
sync_items_from_npc                → world/items.py
consume_item                       → world/items.py
save_relation_snapshot             → relations/snapshot.py
log_relation_change                → relations/journal.py
stale_shelter_occupied_knowledge   → world/shelter.py
schedule_monster_attack            → combat/encounters.py
process_daily_export               → economy/export.py
damage_carried_valuables           → combat/loot.py
```

**Ожидаемое уменьшение engine.py:** ~180 строк

**Риски:** Методы `monsters_attack` и `resolve_zero_health` зависят от внешних модулей
(`squad_power`, `calculate_hunt_chance`, `calculate_unconscious_chance`, `resolve_unconscious_check`) — уже вынесены или доступны из модулей.

### Батч 2: Уровень 1 (зависят от батча 1)

**Методы (14):**

```
emergency_medkit               → combat/medkit.py    (_use_medkit_charge)
rest_heal                      → needs/healing.py    (_use_medkit_charge)
use_medkit_charge              → combat/medkit.py    (_consume_item)
sell_loot                      → economy/trader.py   (_consume_item)
give_artifact                  → needs/artifact.py   (_create_item)
set_unconscious_or_dead        → combat/results.py   (_resolve_zero_health)
group_can_capture              → actions/capture.py  (_capture_target, _group_kit)
group_can_destroy              → actions/destroy.py  (_group_kit)
process_create_shelter         → world/shelter.py    (_active_members, _group_leader)
check_and_journal_relations    → relations/journal.py (_log_relation_change)
roll_trail_blockages           → world/trails.py     (_roll_trail_blockage)
group_in_shelter               → world/shelter.py    (_shelter_sector_ids)
shelter_targets                → world/shelter.py    (_shelter_sector_ids)
is_group_emission_sheltered    → anomalies/emission.py (_emission_safe_sectors)
```

**Ожидаемое уменьшение:** ~130 строк

**Риски:** `_use_medkit_charge` → `_consume_item` — порядок важен, обе в одном батче.

---

## 4.1 Батч 2 — фактический состав (3.9-B2)

**Дата фиксации:** 5b48afb (pre-batch)
**Fork критерий:** метод вызывает ТОЛЬКО `self._<уже вынесенные>` или чистые внешние функции.
**Вызовов `self._<ещё не вынесенный хелпер>`** — 0 (все зависимости включены в батч).

### Фактический состав (18 методов: 14 B2 + 4 зависимости)

| Метод | Целевой модуль | Новая сигнатура | Зависимости (self._xxx) |
|-------|----------------|-----------------|------------------------|
| `_emergency_medkit` | combat/medkit.py | `emergency_medkit(state, npc, members)` | `_use_medkit_charge` (в батче) |
| `_rest_heal` | needs/healing.py | `rest_heal(state, group, members)` | `_use_medkit_charge` (в батче), `_sync_npc_from_items` (в батче) |
| `_use_medkit_charge` | combat/medkit.py | `use_medkit_charge(state, item, members)` | `_consume_item` (B1 ✓) |
| `_sell_loot` | economy/trader.py | `sell_loot(state, leader, trader)` | `_consume_item` (B1 ✓) |
| `_give_artifact` | needs/artifact.py | `give_artifact(state, npc, anomaly, hour)` | `_create_item` (в батче) |
| `_set_unconscious_or_dead` | combat/results.py | `set_unconscious_or_dead(state, npc, start_health, hour, cause)` | `_resolve_zero_health` (B1 ✓) |
| `_group_can_capture` | actions/capture.py | `group_can_capture(state, group, members)` | `_capture_target` (B1 ✓), `_group_kit` (B1 ✓) |
| `_group_can_destroy` | actions/destroy.py | `group_can_destroy(state, group, members)` | `_group_kit` (B1 ✓) |
| `_process_create_shelter` | world/shelter.py | `process_create_shelter(state, group, hour)` | `_active_members` (B1 ✓), `_group_leader` (B1 ✓) |
| `_check_and_journal_relations` | relations/journal.py | `check_and_journal_relations(state, hour)` | `_log_relation_change` (B1 ✓) |
| `_roll_trail_blockages` | world/trails.py | `roll_trail_blockages(state)` | `_roll_trail_blockage` (в батче) |
| `_group_in_shelter` | world/shelter.py | `group_in_shelter(state, group)` | `_shelter_sector_ids` (в батче) |
| `_shelter_targets` | world/shelter.py | `shelter_targets(state, group, hour)` | `_shelter_sector_ids` (в батче) |
| `_is_group_emission_sheltered` | anomalies/emission.py | `is_group_emission_sheltered(state, group)` | `_emission_safe_sectors` (B1 ✓) |
| **_create_item** (зависимость) | world/items.py | `create_item(state, catalog, item_type, name, base_value, owner_id, quantity, properties)` | — (чистый, extern `give_item`) |
| **_roll_trail_blockage** (зависимость) | world/trails.py | `roll_trail_blockage(state, anomaly)` | — (чистый, extern `EMISSION_TRAIL_BLOCK_CHANCE`) |
| **_shelter_sector_ids** (зависимость) | world/shelter.py | `shelter_sector_ids(state)` | — (чистый, читает state) |
| **_sync_npc_from_items** (зависимость) | world/items.py | `sync_npc_from_items(state, npc)` | — (чистый, читает state.items) |

**Замечания:**
- План указал 14 методов, фактический состав — 18 (14 + 4 зависимости).
- Зависимости `_create_item`, `_roll_trail_blockage`, `_shelter_sector_ids`, `_sync_npc_from_items` — все чистые (0 `self._xxx` вызовов), включены в батч.
- `_sync_npc_from_items` добавлен т.к. `_rest_heal` вызывает его на строке 1538.

### Вызывающие стороны (фактические места замены)

**Фазы:**
| Вызов | Файл:строка | Станет |
|-------|-------------|--------|
| `engine._group_can_destroy` | `phases/phase04_intentions.py:119` | `group_can_destroy(state, group, members)` |
| `engine._group_can_capture` | `phases/phase04_intentions.py:120` | `group_can_capture(state, group, members)` |
| `engine._shelter_targets` | `phases/phase05_movement.py:88` | `shelter_targets(state, group, hour)` |
| `engine._process_create_shelter` | `phases/phase07_actions.py:63` | `process_create_shelter(state, group, hour)` |
| `engine._roll_trail_blockage` | `phases/phase08_environment.py:33` | `roll_trail_blockage(state, anomaly)` |

**engine.py (self._xxx вызовы):**
| Вызов | Строки | Станет |
|-------|--------|--------|
| `self._roll_trail_blockages()` | 225 | `roll_trail_blockages(state)` |
| `self._roll_trail_blockage(a)` | 343, 737 | `roll_trail_blockage(state, a)` |
| `self._group_in_shelter` | 410 | `group_in_shelter(state, group)` |
| `self._shelter_sector_ids()` | 410, 442, 508, 509, 2952 | `shelter_sector_ids(state)` |
| `self._shelter_targets(g, h)` | 508-509 | `shelter_targets(state, g, h)` |
| `self._is_group_emission_sheltered(g)` | 775, 3027 | `is_group_emission_sheltered(state, g)` |
| `self._mark_group_emission_exposed(g, h)` → `self._emergency_medkit` | 791 | `emergency_medkit(state, npc, members)` |
| `self._mark_group_emission_exposed(g, h)` → `self._set_unconscious_or_dead` | 797 | `set_unconscious_or_dead(state, npc, start, hour, cause="emission")` |
| `self._emergency_medkit(npc, members)` | 852 | `emergency_medkit(state, item, members)` |
| `self._use_medkit_charge(item, members)` | 852 | `use_medkit_charge(state, item, members)` |
| `self._sell_loot(leader, trader)` | 1492 | `sell_loot(state, leader, trader)` |
| `self._use_medkit_charge(medkit, members)` | 1508 | `use_medkit_charge(state, medkit, members)` |
| `self._rest_heal(group, members)` | 1537 | `rest_heal(state, group, members)` |
| `self._use_medkit_charge(kit, members)` | 1537 | `use_medkit_charge(state, kit, members)` |
| `self._sync_npc_from_items(patient)` | 1538 | `sync_npc_from_items(state, patient)` |
| `self._give_artifact(npc, target, hour)` | 2802 | `give_artifact(state, npc, target, hour)` |
| `self._set_unconscious_or_dead(...)` | 2899 | `set_unconscious_or_dead(state, npc, start_health, hour, cause)` |
| `self._sync_npc_from_items(entity)` | 2913 | `sync_npc_from_items(state, entity)` |
| `self._give_artifact(npc, target, hour)` | 3407 | `give_artifact(state, npc, target, hour)` |

**Тесты:**
| Вызов | Файл:строки | Станет |
|-------|-------------|--------|
| `engine._group_can_capture(group, [npc])` | `tests/test_actions_integration.py:169,171,173,175,186` | `group_can_capture(state, group, [npc])` |
| `engine._group_can_destroy(group, [npc])` | `tests/test_actions_integration.py:90,92,94,96,99` | `group_can_destroy(state, group, [npc])` |
| `engine._create_item(...)` | `tests/test_actions_integration.py:295` | `create_item(engine.state, catalog, ...)` |
| `engine._create_item(...)` | `tests/test_monster_integration.py:95` | `create_item(engine.state, catalog, ...)` |
| `engine._create_item(...)` | `tests/test_items_loot.py:70` | `create_item(engine.state, catalog, ...)` |
| `engine._create_item(...)` | `tests/test_mechanics04.py:239` | `create_item(engine.state, catalog, ...)` |
| `engine._create_item(...)` | `tests/test_rest_trade.py:112,184,199` | `create_item(engine.state, catalog, ...)` |

**Ожидаемое уменьшение engine.py:** ~180 строк (18 методов × ~10 строк среднее)

**Методы (12):**

```
aid_distress_group             → actions/signals.py    (_active_members, _use_medkit_charge)
process_distress_signals       → actions/signals.py    (_active_members)
apply_emission_exposure        → anomalies/emission.py (_active_members, _is_group_emission_sheltered, _mark_group_emission_exposed)
mark_group_emission_exposed    → anomalies/emission.py (_active_members, _emergency_medkit, _set_unconscious_or_dead)
process_emission_shelter_assault → world/shelter.py   (_emission_active, _emission_safe_sectors)
apply_battle_result            → combat/results.py     (7 хелперов)
unconscious_tick               → needs/unconscious.py  (_use_medkit_charge, _sync_npc_from_items)
rest_tick                      → needs/rest.py         (_base_heal_tick)
base_heal_tick                 → needs/healing.py      (_sync_npc_from_items, trade_price)
process_rest_exchanges         → world/trade.py        (_exchange_knowledge, _barter_groups, _log_relation_change)
roll_trail_blockage            → world/trails.py       (property _trail_set)
```

**Ожидаемое уменьшение:** ~220 строк

**Риски:** `apply_battle_result` вызывает 7 хелперов — все из батчей 1-2. `apply_emission_exposure` → `mark_group_emission_exposed` — взаимная зависимость внутри батча.

### Батч 4: Шелтеры, трейды, эмитсии

**Методы (10):**

```
init_shelters                    → world/shelter.py    (lambda)
update_shelter_participants       → world/shelter.py    (_shelter_sector_ids, _walk)
move_all_anomalies                → anomalies/migration.py (_roll_trail_blockage)
process_emission_schedule         → anomalies/emission.py (_emission_active, _move_all_anomalies, _broadcast_emission_warning)
broadcast_conditional_trader_info → economy/trader.py   (state mutations)
spawn_conditional_trader          → economy/trader.py   (_give_starting_equipment)
expire_conditional_trader_if_expired → economy/trader.py (_schedule_conditional_trader)
process_conditional_trader_schedule → economy/trader.py (3 вызова)
broadcast_emission_warning        → anomalies/emission.py (state.knowledge_bases)
conditional_trader_is_active     → already in batch 1
```

**Ожидаемое уменьшение:** ~160 строк

**Риски:** `process_conditional_trader_schedule` вызывает `spawn_conditional_trader` который вызывает `give_starting_equipment`. `give_starting_equipment` ещё не вынесен → техдолг.

### Батч 5: Инит-хелперы, экипировка

**Методы (6):**

```
generate_world                 → worldgen (не выносить, orchestrator)
sync_monster_groups            → world/groups.py
init_trader_stock              → economy/trader.py
init_trails                    → world/trails.py
give_starting_equipment        → world/items.py (_spawn_catalog_item, _sync_npc_from_items)
spawn_catalog_item             → world/items.py
equip_guard                    → relations/guards.py (_spawn_catalog_item, _sync_npc_from_items)
spawn_guard                    → relations/guards.py (_equip_guard)
process_guard_rotation         → relations/guards.py (_spawn_guard, _equip_guard)
```

**Ожидаемое уменьшение:** ~170 строк

**Риски:** Цепочка: `process_guard_rotation` → `spawn_guard` → `equip_guard` → `spawn_catalog_item`. Все в одном батче — без зависимостей вперёд.

### Батч 6: Движение

**Методы (6):**

```
walk                           → world/movement.py    (_trail_set property)
apply_human_move               → world/movement.py    (_check_blocked_trails)
check_blocked_trails           → world/trails.py      (_blocked_trail_map, _group_has_passage, _group_detector_bonus, _create_corpse, _set_unconscious_or_dead)
move_monster_groups            → monsters/movement.py (_trail_set, _walk, _check_blocked_trails, _monster_group_members)
```

**Ожидаемое уменьшение:** ~170 строк

**Риски:** `check_blocked_trails` вызывает `_create_corpse` и `_set_unconscious_or_dead` — уже из батчей 2-3. `move_monster_groups` вызывает `walk` и `check_blocked_trails`.

### Батч 7: Бой — планирование

**Методы (4):**

```
schedule_encounters            → combat/encounters.py (_monster_group_members, _monsters_attack, _schedule_monster_attack, _base_guards, _resolve_feeding_competition)
resolve_feeding_competition    → monsters/feeding.py  (_monster_group_members, _schedule_monster_attack)
monsters_attack                → combat/execution.py  (squad_power, calculate_hunt_chance)
```

**Ожидаемое уменьшение:** ~210 строк

**Риски:** `schedule_encounters` содержит `in_combat_cooldown` (вложенный def) → техдолг, перенести def в отдельный хелпер. `resolve_feeding_competition` вызывает `_schedule_monster_attack` (батч 1) и `monster_group_power` (уже вынесен в B1).

### Батч 8: Бой — результаты

**Методы (4):**

```
execute_battles                → combat/execution.py  (_sync_npc_from_items, _shelter_sector_ids)
create_corpse                  → combat/loot.py
process_corpse_action          → combat/loot.py
```

**Ожидаемое уменьшение:** ~130 строк

**Риски:** `execute_battles` → `_shelter_sector_ids` (батч 2). `create_corpse` → внешние `LootManager`, `Corpse`.

### Батч 9: Трейды, знания, рест-тик

**Методы (9):**

```
trade_price                    → economy/pricing.py    (_find_trader_for_item)
purchase_plan                  → economy/trader.py     (_capture_target, _group_kit, _group_leader, trade_price, _sync_npc_from_items)
process_rest_trade             → economy/trader.py     (7 хелперов)
process_rest_exchanges         → уже в батче 3
exchange_knowledge             → knowledge/exchange.py (state mutations)
barter_groups                  → world/trade.py        (give_item, state mutations)
process_artifact_sales         → economy/trader.py     (_create_item, trade_price, _sync_npc_from_items)
research_tick                  → needs/research.py     (_give_artifact, _set_unconscious_or_dead)
```

**Ожидаемое уменьшение:** ~250 строк

**Риски:** `process_rest_trade` вызывает 7 хелперов — все из батчей 1-3. `purchase_plan` → `_group_can_capture` (батч 2).

### Батч 10: Остальные действия, монстры, знания

**Методы (13):**

```
check_monster_anomaly_contacts  → anomalies/contact.py (_monster_group_members, _create_corpse)
phase4_monster_intentions       → ai/intentions.py     (_monster_group_members)
process_monster_feeding         → monsters/feeding.py  (_monster_group_members, _feed_manager.consume)
process_monster_rest            → monsters/rest.py     (_monster_group_members)
process_destroy_anomaly         → actions/destroy.py   (6 хелперов)
process_capture_monster         → actions/capture.py   (8 хелперов)
```

**Ожидаемое уменьшение:** ~230 строк

**Риски:** `process_capture_monster` → 8 хелперов, все из батчей 1-9. `process_destroy_anomaly` → 6 хелперов.

---

## 5. СЛАБО СВЯЗАННЫЕ КОМПОНЕНТЫ (техдолг)

При корректном порядке батчей прямых зависимостей вперёд **нет**.
Однако есть временные обходные пути, требующие явного параметра `host`:

| Метод | Зависит от | Батч | Решение |
|-------|-----------|------|---------|
| `process_conditional_trader_schedule` | `spawn_conditional_trader` → `give_starting_equipment` | 4/5 | `give_starting_equipment` в батче 5 → батч 4 зависит вперёд. **Решение:** батч 4 → батч 5, поменять местами |
| `apply_battle_result` | 7 хелперов | 3 | Все из батчей 1-2 — **нет проблемы** |
| `schedule_encounters` | `_resolve_feeding_competition` | 7 | В одном батче — **нет проблемы** |

**Корректировка порядка батчей 4 ↔ 5:**
- Батч 5 (инит-хелперы, экипировка) → выносим ПЕРВЫМ
- Батч 4 (условный торговец) → зависит от `give_starting_equipment` из батча 5

---

## 6. СПИСОК ТЕСТОВЫХ ВЫЗОВОВ

**Всего:** 127 вызовов `engine._method(...)` в 11 файлах, 35 уникальных методов.

### test_guards.py (16 вызовов, 5 методов)

| файл:строка | Метод |
|-------------|-------|
| `test_guards.py:70` | `_process_guard_rotation` |
| `test_guards.py:88` | `_process_guard_rotation` |
| `test_guards.py:99` | `_process_guard_rotation` |
| `test_guards.py:105` | `_process_guard_rotation` |
| `test_guards.py:107` | `_process_guard_rotation` |
| `test_guards.py:116` | `_process_guard_rotation` |
| `test_guards.py:117` | `_process_guard_rotation` |
| `test_guards.py:141` | `_process_guard_rotation` |
| `test_guards.py:156` | `_process_guard_rotation` |
| `test_guards.py:200` | `_schedule_monster_attack` |
| `test_guards.py:203` | `_execute_battles` |
| `test_guards.py:241` | `_schedule_monster_attack` |
| `test_guards.py:244` | `_execute_battles` |
| `test_guards.py:259` | `_sync_monster_groups` |
| `test_guards.py:274` | `_monsters_attack` |
| `test_guards.py:290` | `_monsters_attack` |
| `test_guards.py:295` | `_squad_power` (уже в B1) |
| `test_guards.py:298` | `_squad_power` (уже в B1) |

### test_actions_integration.py (21 вызов, 8 методов)

| файл:строка | Метод |
|-------------|-------|
| `test_actions_integration.py:32` | `_sync_human_groups` |
| `test_actions_integration.py:51` | `_sync_monster_groups` |
| `test_actions_integration.py:90-96` | `_group_can_destroy` (×5) |
| `test_actions_integration.py:111` | `_process_destroy_anomaly` |
| `test_actions_integration.py:131` | `_process_destroy_anomaly` |
| `test_actions_integration.py:169-175` | `_group_can_capture` (×5) |
| `test_actions_integration.py:185` | `_sync_monster_groups` |
| `test_actions_integration.py:186` | `_group_can_capture` |
| `test_actions_integration.py:194` | `_process_capture_monster` |
| `test_actions_integration.py:206` | `_sync_monster_groups` |
| `test_actions_integration.py:219` | `_process_capture_monster` |
| `test_actions_integration.py:269` | `_process_rest_trade` |
| `test_actions_integration.py:295` | `_create_item` |
| `test_actions_integration.py:298` | `_process_rest_trade` |

### test_balance.py (6 вызовов, 4 метода)

| файл:строка | Метод |
|-------------|-------|
| `test_balance.py:113` | `_sync_monster_groups` |
| `test_balance.py:130,136` | `_check_monster_anomaly_contacts` (×2) |
| `test_balance.py:156` | `_process_rest_trade` |
| `test_balance.py:184` | `_unconscious_tick` |
| `test_balance.py:203` | `_unconscious_tick` |

### test_base_healing.py (7 вызовов, 1 метод)

| файл:строка | Метод |
|-------------|-------|
| `test_base_healing.py:39,44,57,60,69,83,91` | `_rest_tick` (×7) |

### test_combat_integration.py (4 вызова, 3 метода)

| файл:строка | Метод |
|-------------|-------|
| `test_combat_integration.py:89` | `_home_sector_id` (уже в B1) |
| `test_combat_integration.py:99` | `_sync_human_groups` |
| `test_combat_integration.py:124` | `_sync_monster_groups` |

### test_ai.py (4 вызова, 2 метода)

| файл:строка | Метод |
|-------------|-------|
| `test_ai.py:186,205` | `_sync_monster_groups` (×2) |
| `test_ai.py:192,211` | `_sync_human_groups` (×2) |

### test_emission_shelter_assault.py (9 вызовов, 5 методов)

| файл:строка | Метод |
|-------------|-------|
| `test_emission_shelter_assault.py:137` | `_emission_safe_sectors` |
| `test_emission_shelter_assault.py:293,469` | `_process_emission_shelter_assault` (×2) |
| `test_emission_shelter_assault.py:330` | `_apply_emission_exposure` |
| `test_emission_shelter_assault.py:359` | `_create_shelter_occupied_knowledge` |
| `test_emission_shelter_assault.py:388,410,431` | `_create_shelter_occupied_knowledge` (×3) |
| `test_emission_shelter_assault.py:438` | `_stale_shelter_occupied_knowledge` |

### test_monster_integration.py (24 вызова, 10 методов)

| файл:строка | Метод |
|-------------|-------|
| `test_monster_integration.py:36,46` | `_sync_monster_groups` (×2) |
| `test_monster_integration.py:95` | `_create_item` |
| `test_monster_integration.py:166` | `_schedule_encounters` |
| `test_monster_integration.py:188,208` | `_monsters_attack` (×2) |
| `test_monster_integration.py:248,279` | `_move_monster_groups` (×2) |
| `test_monster_integration.py:319,328,391,433,533` | `_phase4_monster_intentions` (×5) |
| `test_monster_integration.py:324,363,364` | `_schedule_monster_attack`, `_execute_battles` (×2) |
| `test_monster_integration.py:393,397,434,466,501,508,536` | `_schedule_encounters`, `_process_monster_feeding` (×7) |
| `test_monster_integration.py:573` | `_check_monster_anomaly_contacts` |

### test_mechanics04.py (17 вызовов, 11 методов)

| файл:строка | Метод |
|-------------|-------|
| `test_mechanics04.py:50,62,64,77` | `_walk` (×4) |
| `test_mechanics04.py:99,125` | `_apply_human_move` (×2) |
| `test_mechanics04.py:145,151` | `_process_shelter_occupation` (×2) |
| `test_mechanics04.py:185,189,202` | `_apply_emission_exposure` (×3) |
| `test_mechanics04.py:210` | `_move_all_anomalies` |
| `test_mechanics04.py:224,229` | `_process_emission_schedule` (×2) |
| `test_mechanics04.py:237,250` | `_create_corpse` (×2) |
| `test_mechanics04.py:239` | `_create_item` |
| `test_mechanics04.py:244,252` | `_expire_findings` (×2) |
| `test_mechanics04.py:278` | `_process_distress_signals` |
| `test_mechanics04.py:288` | `_aid_distress_group` |

### test_items_loot.py (5 вызовов, 3 метода)

| файл:строка | Метод |
|-------------|-------|
| `test_items_loot.py:70` | `_create_item` |
| `test_items_loot.py:73` | `_create_corpse` |
| `test_items_loot.py:124` | `_process_corpse_action` |
| `test_items_loot.py:178` | `_create_corpse` |
| `test_items_loot.py:202` | `_create_corpse` |

### test_rest_trade.py (11 вызовов, 5 методов)

| файл:строка | Метод |
|-------------|-------|
| `test_rest_trade.py:77,91` | `_rest_tick` (×2) |
| `test_rest_trade.py:99` | `_sleep_tick` |
| `test_rest_trade.py:112,184,199` | `_create_item` (×3) |
| `test_rest_trade.py:122,140` | `_process_rest_trade` (×2) |
| `test_rest_trade.py:161,176,188,202` | `_process_rest_exchanges` (×4) |

### Файлы БЕЗ вызовов `engine._method`

```
test_phase*.py (все)
test_groups.py
conftest.py
test_core.py
test_240h_determinism.py
test_artifact_manager_regression.py
test_catalog.py
test_engine_characterization.py
test_generation.py
test_invariants*.py
test_model_consistency.py
test_persistence.py
test_schema*.py
test_serialization*.py
test_type_fidelity_smoke.py
test_ui.py
```

---

## 7. СВОДКА

### Статистика

| Категория | Методов | Строк (оц.) |
|-----------|---------|-------------|
| Чистые листья (батч 1) | 30 | ~180 |
| Уровень 1 (батч 2) | 14 | ~130 |
| Уровень 2 (батч 3) | 12 | ~220 |
| Шелтеры/трейды/эмитсии (батч 4) | 10 | ~160 |
| Инит-хелперы/экипировка (батч 5) | 6 | ~170 |
| Движение (батч 6) | 4 | ~170 |
| Бой — планирование (батч 7) | 4 | ~210 |
| Бой — результаты (батч 8) | 4 | ~130 |
| Трейды/знания/рест (батч 9) | 9 | ~250 |
| Действия/монстры/знания (батч 10) | 13 | ~230 |
| **ИТОГО** | **110** | **~1860** |

### Техдолг (ожидаемо — нет для чистых батчей)

При корректировке порядка батчей 4↔5 прямых зависимостей вперёд **нет**.
Все батчи выносят методы, чьи зависимости уже вынесены.

### Проверка приёмки

```
git status --porcelain         # только docs/engine_services_plan.md
wc -l engine.py = 3612         # не менять (это подготовка, не код)
pytest tests/test_engine_characterization.py -q → 12 passed
```
