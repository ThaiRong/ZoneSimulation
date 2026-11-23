# Инвентарь метода _phase7_actions

Этап 3, Промпт 3.7A: полная карта тела метода `_phase7_actions` для подготовки извлечения в standalone-фазу. Код НЕ менялся.

---

## 1. СИГНАТУРА И ГАБАРИТЫ

```python
def _phase7_actions(self, hour: int, is_night: bool) -> None:
```

- **Строка начала:** 3637
- **Строка конца:** 3748 (включительно)
- **Номер следующей строки:** 3749 (`def _phase8_environment`)
- **Количество строк метода:** 112 (включая сигнатуру и docstring)
- **Количество строк тела:** 109 (строки 3640–3748)

---

## 2. УПОРЯДОЧЕННЫЙ СПИСОК БЛОКОВ

Блоки идут в точном порядке исходного кода. Каждый блок описан с указанием, что делает, диапазон строк и условие входа.

### Блок 1: Бои
- **Строки:** 3640
- **Что делает:** Вызывает `_execute_battles(hour)` для исполнения боёв, спланированных в фазе 6. Заполняет `self._pending_battles` (список боёв), `self._combat_human_ids`, `self._combat_monster_ids`.
- **Условие входа:** Всегда.

### Блок 2: Кормление монстров
- **Строки:** 3641
- **Что делает:** Вызывает `_process_monster_feeding(hour)`, который обрабатывает монстров с намерением `feed`. Возвращает множество `fed_monster_groups` — IDs групп, которые уже покормились.
- **Условие входа:** Всегда.
- **Важно:** `fed_monster_groups` накапливается и используется в блоке 16.

### Блок 3: Обработка трупов ( corpse_action )
- **Строки:** 3642–3644
- **Что делает:** Проходит по всем human_groups. Для каждой группы вызывает `_process_corpse_action(group, hour)`. Если действие совершено, добавляет `group.id` в `acted_groups`.
- **Условие входа:** `for group in self.state.human_groups.values()`.
- **Накопительная переменная:** `acted_groups = set()` — множества групп, уже совершивших действие в этой фазе. Используется далее как фильтр `if group.id in acted_groups`.

### Блок 4: Уничтожение аномалий и захват монстров
- **Строки:** 3645–3654
- **Что делает:** Проходит по human_groups. Пропускает группы из `acted_groups` и группы с намерением ≠ `DESTROY` или `CAPTURE`. Для `DESTROY` вызывает `_process_destroy_anomaly`, для `CAPTURE` — `_process_capture_monster`. Совершивших действие добавляет в `acted_groups`.
- **Условие входа:** `if group.id in acted_groups or group.intention not in (DESTROY, CAPTURE): continue`

### Блок 5: Обмен отдыхающими (rest exchanges)
- **Строки:** 3656–3660
- **Что делает:** Выбирает все группы с `intention == REST` в `resting_groups`. Вызывает `_process_rest_exchanges(hour, resting_groups)` и `_process_rest_trade(hour, resting_groups)`.
- **Условие входа:** Всегда.

### Блок 6: Создание убежищ
- **Строки:** 3661–3665
- **Что делает:** Проходит по human_groups. Для групп с `intention == CREATE_SHELTER` вызывает `_process_create_shelter(group, hour)`. При успехе добавляет в `acted_groups` и меняет намерение на `REST`.
- **Условие входа:** `if group.intention != CREATE_SHELTER: continue`

### Блок 7: Помощь в беде (HELP)
- **Строки:** 3666–3674
- **Что делает:** Проходит по human_groups. Пропускает из `acted_groups` и группы без `HELP`. Проверяет наличие активного distress-сигнала для группы. Если группа на месте distress — вызывает `_aid_distress_group(group, members, distress, hour)` и добавляет в `acted_groups`.
- **Условие входа:** `if group.id in acted_groups or group.intention != HELP: continue`
- **Локальные переменные:** `distress`, `members`.

### Блок 8: Обработка отдельных людей (humans)
- **Строки:** 3676–3729
- **Что делает:** Проходит по каждому `npc in self.state.humans`. Для каждого — цепочка проверок статуса и намерений.
- **Условие входа:** `for npc in self.state.humans:`

#### Блок 8a: Пропуск комбатантов и acted-групп
- **Строки:** 3677
- **Условие:** `if npc.id in self._combat_human_ids or npc.group_id in acted_groups: continue`

#### Блок 8b: SLEEPING статус — проверка комфорта и будим
- **Строки:** 3678–3700
- **Условие:** `if npc.status == EntityStatus.SLEEPING:`
- **Вложенная логика:** Если `npc.group_id` принадлежит группе с `comfort=True`, проверяет `self._has_strict_comfort(...)`. Если комфорт не подтверждён — будит всех SLEEPING членов группы (устанавливает `group.comfort = False`, меняет `m.status = EntityStatus.ACTIVE`, `m.intention = REST`).
- **После:** Если `not getattr(npc, "on_treatment", False)` — вызывает `self._sleep_tick(npc)`.
- **continue** на строке 3700.

#### Блок 8c: UNCONSCIOUS статус
- **Строки:** 3701–3703
- **Условие:** `if npc.status == EntityStatus.UNCONSCIOUS:`
- **Действие:** Вызывает `self._unconscious_tick(npc, hour)`.
- **continue** на строке 3703.

#### Блок 8d: Не ACTIVE статус
- **Строки:** 3704–3705
- **Условие:** `if npc.status != EntityStatus.ACTIVE:`
- **Действие:** `continue`.

#### Блок 8e: Базовый расход выносливости
- **Строки:** 3707–3710
- **Действие:** `update_stamina(npc, STAMINA_COST_AWAKE, "awake", self.state.time)`.
- **Результат:** Может изменить `npc.status` на `UNCONSCIOUS` (строка 3701).
- **Пропуск:** `if npc.status != EntityStatus.ACTIVE: continue` на строке 3710.

#### Блок 8f: Намерение SLEEP
- **Строки:** 3712–3724
- **Условие:** `if npc.intention == SLEEP:`
- **Вложенная логика:** Проверяет `self._has_strict_comfort(...)` через `group.comfort`. Если не подтверждён — отменяет сон (`npc.intention = REST`, `group.comfort = False`).
- **При подтверждённом сне:** `npc.status = EntityStatus.SLEEPING`, `npc.intention = SLEEP`.
- **continue** неявный (блок elif).

#### Блок 8g: Намерение REST
- **Строки:** 3725–3726
- **Условие:** `elif npc.intention == REST:`
- **Действие:** `self._rest_tick(npc)`.

#### Блок 8h: Намерение RESEARCH / ARTIFACT_SEARCH
- **Строки:** 3727–3728
- **Условие:** `elif npc.intention in (RESEARCH, ARTIFACT_SEARCH):`
- **Действие:** `self._research_tick(npc, hour)`.

#### Блок 8i: Намерение EXIT
- **Строки:** 3729
- **Условие:** `elif npc.intention == EXIT:`
- **Действие:** `self._exit_tick(npc, hour)`.

### Блок 9: Отдых монстров
- **Строки:** 3731–3732
- **Что делает:** Вызывает `_process_monster_rest(fed_monster_groups, is_night)`. Передаёт `fed_monster_groups` (накопленный в блоке 2).
- **Условие входа:** Всегда.

---

## 3. ВЫЗОВЫ ВСПОМОГАТЕЛЬНЫХ МЕТОДОВ

| Метод | Блок (номер) | Аргументы |
|-------|-------------|-----------|
| `_execute_battles` | 1 | `(hour)` |
| `_process_monster_feeding` | 2 | `(hour)` |
| `_process_corpse_action` | 3 | `(group, hour)` — вызывается в цикле |
| `_process_destroy_anomaly` | 4 | `(group, hour, is_night)` |
| `_process_capture_monster` | 4 | `(group, hour)` |
| `_process_rest_exchanges` | 5 | `(hour, resting_groups)` |
| `_process_rest_trade` | 5 | `(hour, resting_groups)` |
| `_process_create_shelter` | 6 | `(group, hour)` — вызывается в цикле |
| `_active_distress_for` | 7 | `(group, hour)` |
| `_active_members` | 7 | `(group)` |
| `_aid_distress_group` | 7 | `(group, members, distress, hour)` |
| `_has_strict_comfort` | 8b, 8f | `(group, {m.id: m for m in self.state.humans}, {n.id: n for n in self.state.stationary_humans}, self.state.shelters, self.state.temp_shelters, self.state.sectors, npc.sector_id, npc.faction)` |
| `_sleep_tick` | 8b | `(npc)` — вызывается в цикле |
| `_unconscious_tick` | 8c | `(npc, hour)` |
| `update_stamina` | 8e | `(npc, STAMINA_COST_AWAKE, "awake", self.state.time)` |
| `_rest_tick` | 8g | `(npc)` |
| `_research_tick` | 8h | `(npc, hour)` |
| `_exit_tick` | 8i | `(npc, hour)` |
| `_process_monster_rest` | 9 | `(fed_monster_groups, is_night)` |

---

## 4. ИЗМЕНЯЕМЫЕ АТРИБУТЫ ДВИЖКА

### (a) МУТАЦИЯ на месте (.append/.add/.update/[key]=…)

| Атрибут | Строка | Тип мутации | Описание |
|---------|--------|-------------|----------|
| `acted_groups` | 3642 | `= set()` | ПЕРЕПРИСВАИВАНИЕ — создание нового пустого множества |
| `acted_groups` | 3643, 3653, 3664, 3673 | `.add(...)` | Добавление ID группы |
| `self._pending_battles` | 3640 (через `_execute_battles`) | `.clear()` или `= []` | Зависит от реализации `_execute_battles` |
| `self._combat_human_ids` | 3640 (через `_execute_battles`) | `.clear()` или `= set()` | Зависит от реализации `_execute_battles` |
| `self._feeding_claims` | 3641 (через `_process_monster_feeding`) | Зависит от реализации |
| `group.intention` | 3664 | `[key]=...` | Изменение на `REST` после создания убежища |
| `group.comfort` | 3690, 3719 | `[key]=...` | Установка `False` при отмене комфорта |
| `m.status` | 3691 | `[key]=...` | Будим NPC: `EntityStatus.ACTIVE` |
| `m.intention` | 3692 | `[key]=...` | Будим NPC: `REST` |
| `npc.intention` | 3719 | `[key]=...` | Отмена сна → `REST` |
| `npc.status` | 3721 | `[key]=...` | Переход в `SLEEPING` |
| `npc.intention` | 3722 | `[key]=...` | `SLEEP` (инвариант #5) |

### (b) ПЕРЕПРИСВАИВАНИЕ (локальный алиас НЕ сработает — нужно `engine._attr`)

| Атрибут | Строка | Тип | Описание |
|---------|--------|-----|----------|
| `acted_groups` | 3642 | `= set()` | КРИТИЧНО: создаётся новое пустое множество, которое накапливает ID acted-групп. При переносе — `engine._act_groups = set()` или `engine.acted_groups.clear()`. |

### Чтение/запись других атрибутов

| Атрибут | Чтение | Запись |
|---------|--------|--------|
| `_combat_human_ids` | ✓ (строка 3677) | через `_execute_battles` |
| `_moved_human_ids` | — | — |
| `_moved_monster_ids` | — | — |
| `_home_cache` | — | — |
| `_border_dist` | — | — |
| `catalog` | — | — |
| `save_manager` | — | — |

---

## 5. ПОЛЯ STATE, КОТОРЫЕ ФАЗА ПИШЕТ

| Поле state | Мутация | Где |
|------------|---------|-----|
| `humans[].status` | `[key]=...` | Блоки 8b, 8e, 8f (SLEEPING, UNCONSCIOUS, DEAD) |
| `humans[].intention` | `[key]=...` | Блоки 8b, 8f, 8g–i |
| `humans[].stamina` / `stamina_share` | — (через `update_stamina`) | Блок 8e |
| `news_manager.events` | `.append()` | В хелперах (`_execute_battles`, `_unconscious_tick`, `_research_tick`, `_exit_tick`, `_sleep_tick`, `_rest_tick`, `_process_monster_feeding`, `_process_monster_rest`) |
| `corpses` | `.append()`/`.remove()` | В хелперах (`_create_corpse` из `_unconscious_tick`, `_process_monster_feeding`) |
| `items` | `.pop()`/`[key]=...` | В хелперах (`_consume_item`) |
| `knowledge_bases` | `.add()`/`.update()` | В хелперах (`_exchange_knowledge`, `_stale_shelter_occupied_knowledge`) |
| `temp_shelters` | `.remove()`/`.pop()` | В хелперах (`_process_create_shelter`) |
| `human_groups[].intention` | `[key]=...` | Блоки 4, 6, 7, 8f–i |
| `human_groups[].comfort` | `[key]=...` | Блоки 8b, 8f |
| `human_groups[].id` (через acted_groups) | — | Блок 3, 4, 6, 7 |

---

## 6. ЛОКАЛЬНЫЕ ПЕРЕМЕННЫЕ

| Имя | Где инициализируется | Где используется | Накопительная? |
|-----|---------------------|------------------|---------------|
| `hour` | Параметр метода | Строки 3640–3644, 3647, 3653, 3656, 3664, 3669, 3701, 3707, 3727, 3729 | Нет (параметр) |
| `is_night` | Параметр метода | Строки 3647, 3732 | Нет (параметр) |
| `acted_groups` | 3642: `= set()` | Строки 3643, 3646, 3653, 3664, 3667, 3677, 3733 | **Да** — накапливает ID групп, совершивших действие |
| `group` | Циклы | Множество блоков | Нет (итерационная) |
| `done` | 3647, 3653: результат хелпера | 3652, 3654 | Нет |
| `resting_groups` | 3656–3658: список групп с REST | 3659–3660 | Нет (срез) |
| `npc` | Цикл `for npc in self.state.humans:` | Блоки 8a–8i | Нет (итерационная) |
| `group` (в блоке 8b) | 3681: `self.state.human_groups.get(npc.group_id)` | 3682–3692 | Нет |
| `mid` | 3689: `for mid in group.members` | 3690–3692 | Нет |
| `m` | 3690: `for m in self.state.humans` | 3691–3692 | Нет |
| `distress` | 3669: `_active_distress_for(group, hour)` | 3670–3673 | Нет |
| `members` | 3670: `_active_members(group)` | 3671–3673 | Нет |
| `fed_monster_groups` | 3641: возврат `_process_monster_feeding` | 3731–3732 | **Да** — накапливает ID покормленных групп |

---

## 7. ВЛОЖЕННЫЕ ФУНКЦИИ И ЗАМЫКАНИЯ

**Внутри тела `_phase7_actions` вложенных функций `def` и `lambda` НЕТ.**

Всевозможные замыкания (на `self`, `group`, `npc`, `hour`, `is_night`) формируются только внутри вызываемых хелперов (`_execute_battles`, `_has_strict_comfort`, `_sleep_tick` и др.), но не в самом теле фазы 7.

Это упрощает перенос: нет risk потери замыканий при замене `self.*` на `engine.*`.

---

## 8. ТОЧКИ ПОТРЕБЛЕНИЯ RNG

Фаза 7 сама по себе **не вызывает** `self.state.rng.*` напрямую. Все обращения к RNG делегируются через хелперы:

1. `_execute_battles(hour)` → CombatSystem → RNG внутри боёв
2. `_process_monster_feeding(hour)` → RNG при распределении кормлений
3. `_process_corpse_action(group, hour)` → RNG при выборе целей
4. `_process_destroy_anomaly(group, hour, is_night)` → RNG
5. `_process_capture_monster(group, hour)` → RNG
6. `_aid_distress_group(...)` → RNG
7. `_sleep_tick(npc)` → RNG (пробуждение)
8. `_unconscious_tick(npc, hour)` → RNG (возрождение)
9. `_rest_tick(npc)` → RNG (лечение)
10. `_research_tick(npc, hour)` → RNG (исследование)
11. `_exit_tick(npc, hour)` → RNG (уход)
12. `_process_monster_rest(fed_monster_groups, is_night)` → RNG (отдых монстров)

**Порядок детерминирован порядком вызовов в блоках 1–9.** Порядок критичен для воспроизводимости.

---

## 9. РАННИЕ ВЫХОДЫ И УПРАВЛЕНИЕ ПОТОКОМ

| Тип | Строка | Условие | Описание |
|-----|--------|---------|----------|
| `continue` | 3677 | `npc.id in self._combat_human_ids or npc.group_id in acted_groups` | Пропуск комбатантов |
| `continue` | 3700 | `npc.status == SLEEPING` + `on_treatment` | Пропуск после сна |
| `continue` | 3703 | `npc.status == UNCONSCIOUS` | Пропуск после бессознательности |
| `continue` | 3705 | `npc.status != ACTIVE` | Пропуск неактивных |
| `continue` | 3710 | `npc.status != ACTIVE` | Пропуск после exhaustion |
| **Нет `return`** | — | — | Фаза 7 не содержит `return`; полный проход всех блоков |
| Нет `break` | — | — | Нет прерываний циклов |

**Семантика при переносе:** функция `run_phase7_actions(ctx)` будет вызываться как statement (без ожидания возврата), что идентично текущему поведению.

---

## 10. ПРЯМЫЕ ВЫЗОВЫ ФАЗЫ 7 В ТЕСТАХ

### Все вызовы `_phase7_actions` (grep по всему проекту)

| Файл | Строка | Код |
|------|--------|-----|
| `src/zonesim/simulation/engine.py` | 1917 | `self._phase7_actions(hour, is_night)` — из `simulate_hour()` |
| `tests/test_combat_integration.py` | 138 | `engine._phase7_actions(engine.state.time.hour, is_night=False)` |
| `tests/test_guards.py` | 157 | `engine._phase7_actions(engine.state.time.hour, is_night=False)` |
| `tests/test_items_loot.py` | 154 | `engine._phase7_actions(engine.state.time.hour, is_night=False)` |

**Итого:** 4 вызова (1 в production, 3 в тестах).

---

## 11. РИСКИ ПЕРЕНОСА

1. **`acted_groups = set()` (строка 3642)** — создание нового множества. При переносе это должно быть `engine._acted_groups = set()` или `engine._acted_groups.clear()`, иначе локальная переменная не запишет результат. Это **самый критичный риск** — `acted_groups` — аккумулятор между блоками.

2. **`update_stamina(..., self.state.time)` (строка 3707)** — передача `self.state.time`, а не `self.state.time.hour`. Хелпер `update_stamina` принимает объект `GameTime`. При переносе нужно: `engine.update_stamina(npc, STAMINA_COST_AWAKE, "awake", ctx.state.time)` или через `engine.state.time`.

3. **`_has_strict_comfort` вызывается 2 раза (блоки 8b, 8f) с одним и тем же сложным набором аргументов** — включая `{m.id: m for m in self.state.humans}`. Каждый раз пересоздаётся словарь. При переносе нужно передать через `engine.*`.

4. **Просыпание всей группы (блоки 8b, строки 3689–3692)** — двойной цикл `for mid in group.members` + `for m in self.state.humans`. Мутирует `m.status`, `m.intention`, `group.comfort`. Семантика: будит ВСЕХ SLEEPING членов группы, а не только проверяемый `npc`.

5. **`fed_monster_groups` передаётся из блока 2 в блок 9** — накопительная переменная между блоками. При переносе должна стать полем engine или передаваться как аргумент.

6. **Двойная проверка `npc.status != EntityStatus.ACTIVE`** (строки 3705 и 3710) — после `update_stamina` на строке 3707 NPC мог перейти в UNCONSCIOUS. Это **не баг**, а защита от изменения статуса в середине блока.

7. **Параметр `is_night` используется только в блоках 4 (`_process_destroy_anomaly`) и 9 (`_process_monster_rest`)**. В остальной части фазы не нужен. Но его передача обязательна для корректности.

8. **`group.comfort = False` (строки 3690, 3719)** — мутация группы, которая затем читается вложенной логикой просыпания. Порядок критичен.
