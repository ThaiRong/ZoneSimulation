# Инвентарь методов _phase8_environment, _phase9_consequences, _phase10_report

Этап 3, Промпт 3.8A: полная карта трёх оставшихся точек входа фаз. Код НЕ менялся.

---

## 1. СИГНАТУРА И ГАБАРИТЫ

### _phase8_environment
```python
def _phase8_environment(self, hour: int) -> None:
```
- **Строка начала:** 3638
- **Строка конца:** 3666 (включительно)
- **Номер следующей строки:** 3668 (`def _process_artifact_formations`)
- **Количество строк метода:** 29 (3638–3666)
- **Количество строк тела:** 27 (3641–3667)
- **Тип возврата:** None

### _phase9_consequences
```python
def _phase9_consequences(self, hour: int) -> None:
```
- **Строка начала:** 3692
- **Строка конца:** 3702 (включительно)
- **Номер следующей строки:** 3704 (`def _process_daily_export`)
- **Количество строк метода:** 11 (3692–3702)
- **Количество строк тела:** 9 (3695–3703)
- **Тип возврата:** None

### _phase10_report
```python
def _phase10_report(self, hour: int) -> None:
```
- **Строка начала:** 3705
- **Строка конца:** 3722 (включительно)
- **Номер следующей строки:** 3724 (`def get_state_summary`)
- **Количество строк метода:** 18 (3705–3722)
- **Количество строк тела:** 16 (3708–3723)
- **Тип возврата:** None

---

## 2. РАЗГРАНИЧЕНИЕ «ТЕЛО ФАЗЫ» vs «simulate_hour» — КЛЮЧЕВОЙ РАЗДЕЛ

### simulate_hour (строки 1859–1958)

Вызовы фаз в simulate_hour идут в порядке:

```
# строка 1919
run_phase0_check(self.context)       # извлечена
# строка 1922
run_phase1_scheduled(self.context)   # извлечена
# строка 1925
run_phase2_environment(self.context)  # извлечена
# строка 1928
run_phase3_knowledge(self.context)    # извлечена
# строка 1931
run_phase4_intentions(self.context)   # извлечена
# строка 1934
run_phase5_movement(self.context)     # извлечена
# строка 1937
run_phase6_detections(self.context)   # извлечена
# строка 1940
run_phase7_actions(self.context)      # извлечена
# строка 1943
self._phase8_environment(hour)        # ← НЕ извлечена (текущая цель)
# строка 1946
self._phase9_consequences(hour)       # ← НЕ извлечена (текущая цель)
# строка 1949
self._free_emptied_shelters(hour)     # ← НЕ фаза, вызов из simulate_hour
# строка 1952
errors = assert_world_invariants(self.state)   # ← НЕ фаза, проверка инвариантов
# строка 1960
self.state.time.advance()             # ← НЕ фаза, продвижение времени
# строка 1961
self._phase10_report(hour)            # ← НЕ извлечена (текущая цель)
# строки 1963–1967
events = [e.to_dict() for e in ...]  # ← НЕ фаза, формирование событий
# строки 1969–1976
return { ... }                        # ← НЕ фаза, возвращаемая сводка
```

### Что НЕ переносится (живёт в simulate_hour):

| Строка | Что | Почему |
|--------|-----|--------|
| 1949 | `self._free_emptied_shelters(hour)` | Вызов между фазами 9 и проверкой инвариантов — координационный вызов, не часть тела фазы 9 |
| 1952–1956 | `errors = assert_world_invariants(...); if errors: raise ...` | Проверка инвариантов — логика simulate_hour, а не фазы |
| 1960 | `self.state.time.advance()` | Продвижение времени — orchestration, не часть фазы |
| 1963–1967 | `events = [e.to_dict() for e in ...]` | Формирование сводки — логика simulate_hour |
| 1969–1976 | `return { ... }` | Возврат из simulate_hour — метод возвращает dict |

### Что переносится:

| Фаза | Что | Строки тела |
|------|-----|-------------|
| 8 | Тело `_phase8_environment` (миграция аномалий) | 3641–3666 |
| 9 | Тело `_phase9_consequences` (синхронизация групп, экспорт) | 3695–3702 |
| 10 | Тело `_phase10_report` (автосохранение) | 3708–3722 |

### Важное наблюдение:

**Фаза 10 НЕ возвращает значение.** Она `return None` (пустой return или нет return). В simulate_hour результат вызова `_phase10_report` не используется:
```python
self._phase10_report(hour)  # результат не присваивается, не используется
```

**Порядок критичен:**
```
_phase8(hour) → _phase9(hour) → _free_emptied_shelters → assert_invariants → time.advance() → _phase10(hour)
```

---

## 3. УПОРЯДОЧЕННЫЕ БЛОКИ КАЖДОЙ ФАЗЫ

### Фаза 8: _phase8_environment (строки 3638–3667)

#### Блок 8.1: Условие миграции
- **Строки:** 3641–3642
- **Что делает:** `if hour % 48 == 0:` — проверка каждые 48 часов
- **Условие входа:** `hour % 48 == 0` (каждый второй день на часе)

#### Блок 8.2: Подстановка start_ids
- **Строки:** 3643
- **Что делает:** `start_ids = {s.id for s in self.state.sectors.values() if s.is_faction_start}` — сет ID базовых секторов
- **Условие входа:** Всегда внутри блока 8.1

#### Блок 8.3: Цикл по аномалиям
- **Строки:** 3644–3666
- **Что делает:** Для каждой активной аномалии:
  - 3645: `if anomaly.status == AnomalyStatus.ACTIVE:` — фильтр активных
  - 3646: `rng_val = self.state.rng.random()` — генерация случайного числа
  - 3647–3651: `migration = check_anomaly_migration(...)` — вызов функции миграции с параметрами
    - `anomaly` — сама аномалия
    - `hour` — час
    - `sector_ids=self._anomaly_move_candidates(anomaly)` — кандидаты на перемещение
    - `faction_start_ids=start_ids` — ID баз
    - `rng_value=rng_val` — предвычисленное случайное число
  - 3652–3665: `if migration["moved"]:` — если переместила:
    - 3653: `self._roll_trail_blockage(anomaly)` — проверка перекрытия тропы
    - 3654–3665: `self.state.news_manager.create_event(...)` — запись события в ленту новостей

### Фаза 9: _phase9_consequences (строки 3692–3703)

#### Блок 9.1: Синхронизация групп
- **Строки:** 3695
- **Что делает:** `self._sync_human_groups()` — убирает выбывших, удаляет пустые группы, выбирает лидеров
- **Условие входа:** Всегда

#### Блок 9.2: Ежедневный экспорт
- **Строки:** 3697–3701
- **Что делает:** `if self.state.time.hour % 24 == 7:` — проверка каждого 7-го часа дня
- **Действие:** `self._process_daily_export(hour)` — вызов ежедневного экспорта
- **Условие входа:** `self.state.time.hour % 24 == 7` (каждый день на 7-м часе)

### Фаза 10: _phase10_report (строки 3705–3723)

#### Блок 10.1: Проверка save_manager
- **Строки:** 3708–3710
- **Что делает:** `if self.save_manager is None: return` — ранний выход если менеджер не инициализирован
- **Условие входа:** Всегда

#### Блок 10.2: Чтение настроек
- **Строки:** 3711–3712
- **Что делает:** `settings = self.state.config.get("persistence", {})` и `if not settings.get("autosave_enabled", True): return`
- **Условие входа:** Если settings["autosave_enabled"] == False

#### Блок 10.3: Проверка интервала
- **Строки:** 3713–3716
- **Что делает:**
  - `interval = settings.get("autosave_interval", 6)` — интервал автосохранения
  - `slot_count = settings.get("autosave_slots", 3)` — количество слотов
  - `if interval <= 0 or slot_count <= 0 or self.state.time.hour % interval != 0: return`
- **Условие входа:** interval/slot_count > 0 и `time.hour % interval == 0`

#### Блок 10.4: Вычисление слота и сохранение
- **Строки:** 3717–3718
- **Что делает:**
  - `slot_index = (self.state.time.hour // interval - 1) % slot_count`
  - `self.save(f"autosave_{slot_index}")` — вызов метода save
- **Условие входа:** Всегда внутри блока (если все проверки прошли)

---

## 4. ВЫЗОВЫ ХЕЛПЕРОВ

| Метод | Блок | Аргументы |
|-------|------|-----------|
| `_anomaly_move_candidates` | 8.3 | `(anomaly)` — вызывается в цикле |
| `check_anomaly_migration` | 8.3 | `(anomaly, hour, sector_ids=..., faction_start_ids=..., rng_value=...)` |
| `_roll_trail_blockage` | 8.3 | `(anomaly)` — вызывается при перемещении |
| `state.news_manager.create_event` | 8.3 | `(hour, minute, sector_id, event_type, participants, result, importance, summary, details)` |
| `_sync_human_groups` | 9.1 | нет аргументов |
| `_process_daily_export` | 9.2 | `(hour)` |
| `state.config.get` | 10.2 | `("persistence", {})` |
| `self.save` | 10.4 | `(f"autosave_{slot_index}")` |

---

## 5. АТРИБУТЫ ДВИЖКА

### (a) МУТАЦИЯ на месте (.append/.add/[key]=v)

| Атрибут | Строка | Тип | Описание |
|---------|--------|-----|----------|
| `state.news_manager.events` | 8.3, 9.2, 10.4 | `.create_event()` | Запись событий в ленту |
| `state.import_export.export_records` | 9.2 | `.append()` | Запись экспорта (через `_process_daily_export`) |
| `state.import_export.daily_export_totals` | 9.2 | `[key] = ... + actual` | Накопление общего экспорта (через `_process_daily_export`) |

### (b) ПЕРЕПРИСВАИВАНИЕ

| Атрибут | Строка | Описание |
|---------|--------|----------|
| `start_ids` | 8.3 | локальная переменная (не attribute) |
| `migration` | 8.3 | локальная переменная (не attribute) |

**Ни одного переприсваивания `self._attr = ...` в телах трёх методов нет.**

### Чтение/запись других атрибутов

| Атрибут | Чтение | Запись |
|---------|--------|--------|
| `self.save_manager` | ✓ (строка 3708) | — |
| `self.state.config` | ✓ (строка 3711) | — |
| `self.catalog` | — | — |
| `self._home_cache` | — | — |
| `self._border_dist` | — | — |
| `self._trail_set` | — | — |
| `self.save(...)` | — | ✓ (строка 3718) — метод save вызывается внутри фазы 10 |

---

## 6. ПОЛЯ STATE, КОТОРЫЕ ФАЗЫ ПИШУТ

| Поле state | Мутация | Где |
|------------|---------|-----|
| `anomalies[].sector_id` | косвенно (через `check_anomaly_migration`) | 8.3 |
| `news_manager.events` | `.create_event()` | 8.3, 9.2 |
| `import_export.export_records` | `.append()` | 9.2 (через `_process_daily_export`) |
| `import_export.daily_export_totals` | `[key] += ...` | 9.2 (через `_process_daily_export`) |

### Прочие поля, которые ЧИТАЮТ фазы

| Поле | Где |
|------|-----|
| `anomalies` | 8.3 (цикл `.values()`) |
| `sectors` | 8.3 (через `_anomaly_move_candidates` → `_anomaly_move_candidates` читает `.values()`) |
| `time.hour` | 9.2 (`self.state.time.hour % 24`) |
| `humans` | 9.2 (через `_sync_human_groups` и `_process_daily_export`) |
| `humans[].artifacts` | 9.2 (через `_process_daily_export`) |
| `config` | 10.2 |
| `time.hour` | 10.3 |

---

## 7. ЛОКАЛЬНЫЕ ПЕРЕМЕННЫЕ И ВОЗВРАТ

| Имя | Где инициализируется | Где используется |
|-----|---------------------|------------------|
| `hour` | Параметр метода | Все блоки (передаётся в хелперы) |
| `start_ids` | 8.3: `{s.id for s in self.state.sectors.values() if s.is_faction_start}` | 8.3: передаётся в `check_anomaly_migration` |
| `rng_val` | 8.3: `self.state.rng.random()` | 8.3: передаётся в `check_anomaly_migration` |
| `migration` | 8.3: `check_anomaly_migration(...)` | 8.3: проверка `migration["moved"]`, `migration["to_sector"]`, `details=migration` |
| `settings` | 10.2: `self.state.config.get("persistence", {})` | 10.2–10.4: чтение `autosave_enabled`, `autosave_interval`, `autosave_slots` |
| `interval` | 10.3: `settings.get("autosave_interval", 6)` | 10.3–10.4: проверка, вычисление slot_index |
| `slot_count` | 10.3: `settings.get("autosave_slots", 3)` | 10.3–10.4: вычисление slot_index |
| `slot_index` | 10.4: `(self.state.time.hour // interval - 1) % slot_count` | 10.4: строка аргумента `self.save(f"autosave_{slot_index}")` |

### Возврат

Все три метода **возвращают None** (явно или неявно). В simulate_hour результат не используется:
```python
self._phase8_environment(hour)     # результат игнорируется
self._phase9_consequences(hour)    # результат игнорируется
self._phase10_report(hour)         # результат игнорируется
```

---

## 8. ВЛОЖЕННЫЕ ФУНКЦИИ / ЗАМЫКАНИЯ

**Внутри тел всех трёх методов вложенных функций `def` и `lambda` НЕТ.**

Все замыкания формируются внутри хелперов (`_anomaly_move_candidates`, `check_anomaly_migration`, `_roll_trail_blockage`, `_sync_human_groups`, `_process_daily_export`), но не в самом теле фаз.

Это упрощает перенос: нет risk потери замыканий при замене `self.*` на `engine.*`.

---

## 9. ТОЧКИ ПОТРЕБЛЕНИЯ RNG — В ПОРЯДКЕ СЛЕДОВАНИЯ

| # | Строка | Обращение | Хелпер |
|---|--------|-----------|--------|
| 1 | 8.3 | `self.state.rng.random()` | `rng_val = ...` для `check_anomaly_migration` |
| 2 | 9.2 | (нет прямых) | `check_anomaly_migration` уже получил RNG |
| 3 | 10.4 | (нет) | save — не использует RNG |

**Полный поток RNG (включая хелперов, которые тянут RNG):**

1. `check_anomaly_migration` (через `rng_value=rng_val`) — миграция аномалий
2. `_roll_trail_blockage` — может проверять блокировку (через RNG внутри)
3. `check_artifact_formation` (через `state.artifacts.check_artifact_formation`) — но это в `_process_artifact_formations`, который НЕ в фазе 8, а в phase2

**Важно:** фаза 8 сама содержит ровно ОДНО прямое обращение к RNG: `self.state.rng.random()` на строке 3646.

---

## 10. РАННИЕ ВЫХОДЫ

### _phase8_environment
- **Нет `return`, `continue`, `break` внутри тела.**
- Условный блок `if hour % 48 == 0` — это не выход, а пропуск логики.
- Внутри `if migration["moved"]:` — не выход, а условное действие.

### _phase9_consequences
- **Нет `return`, `continue`, `break` внутри тела.**

### _phase10_report
- **Строка 3708:** `if self.save_manager is None: return` — ранний выход при отсутствии save_manager
- **Строка 3712:** `if not settings.get("autosave_enabled", True): return` — ранний выход если автосохранение отключено
- **Строка 3716:** `if interval <= 0 or slot_count <= 0 or self.state.time.hour % interval != 0: return` — ранний выход если не время сохранять

**Все три `return` прерывают выполнение ТОЛЬКО внутри функции `_phase10_report`, не затрагивая simulate_hour.**

---

## 11. ПРЯМЫЕ ВЫЗОВЫ В ТЕСТАХ

### Найденные вызовы `_phase9_consequences`

| Файл | Строка | Код |
|------|--------|-----|
| `tests/test_groups.py` | 131 | `engine._phase9_consequences(engine.state.time.hour)` |

### Найденные вызовы `_phase8_environment`

**Не найдено.**

### Найденные вызовы `_phase10_report`

**Не найдено.**

### Найденные вызовы в src/

| Файл | Строка | Код |
|------|--------|-----|
| `src/zonesim/simulation/engine.py` | 1943 | `self._phase8_environment(hour)` — из `simulate_hour` |
| `src/zonesim/simulation/engine.py` | 1946 | `self._phase9_consequences(hour)` — из `simulate_hour` |
| `src/zonesim/simulation/engine.py` | 1961 | `self._phase10_report(hour)` — из `simulate_hour` |

**Итого:** 4 вызова (3 в production, 1 в тесте).

---

## 12. РИСКИ ПЕРЕНОСА

1. **Вызов `self.save()` в фазе 10 (строка 3718).** Это публичный метод engine для сохранения состояния. При переносе нужно: `engine.save(f"autosave_{slot_index}")`. **Не безопасно** — метод `save` может иметь побочные эффекты. Проверить: save — это чистая сериализация или что-то ещё?

2. **Вызов `self.state.time.hour % 24 == 7` в фазе 9 (строка 3697).** Использует `self.state.time`, а не `ctx.hour`. При переносе: `state.time.hour % 24 == 7` или `hour % 24 == 7` (поскольку `hour` параметр метода). **Важно:** `hour` параметр — это `self.state.time.hour` ДО advance(), так что проверка `hour % 24 == 7` корректна.

3. **Двойное использование `hour` vs `self.state.time.hour`.** В фазе 8 `hour` параметр используется для проверки `hour % 48 == 0`. В фазе 9 `self.state.time.hour` используется для проверки `hour % 24 == 7`. При переносе: оба варианта дают одинаковый результат (поскольку `hour` — это `state.time.hour` до advance), но нужно быть последовательным.

4. **`.create_event` — мутация state.news_manager.** Это чистая мутация через `state.`, не через `engine._helper`. При переносе: `state.news_manager.create_event(...)` — работает корректно.

5. **Вызов `self._process_daily_export(hour)` из фазы 9.** Это НЕ хелпер фазы 9 — это отдельный метод в engine.py (строки 3704–3751). При переносе: `engine._process_daily_export(hour)` — метод остаётся в engine.

6. **Соблазн захватить `assert_world_invariants` или `time.advance()`** — это НЕ часть фаз 8/9/10, а orchestration simulate_hour. Строго исключить из переноса.

7. **`_free_emptied_shelters(hour)` вызывается ПОСЛЕ фазы 9 в simulate_hour.** Это координационный вызов, не часть тела фазы 9. Не переносить.

8. **Порядок `time.advance()` перед фазой 10.** В simulate_hour:
   ```
   _phase8(hour) → _phase9(hour) → _free_emptied_shelters → assert_invariants → time.advance() → _phase10(hour)
   ```
   Фаза 10 читает `self.state.time.hour` для вычисления `slot_index`. После `time.advance()` `hour` уже следующий. Это КРИТИЧНО: фаза 10 работает с УЖЕ продвинутым временем.
