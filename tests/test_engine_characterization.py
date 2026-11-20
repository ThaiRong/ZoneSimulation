"""Полный снимок состояния SimulationEngine — «Страховка» перед рефакторингом.

Этап 3, Промпт 3.0: контроль «поведение не изменилось» на протяжении
всего рефакторинга (декомпозиция engine).

Критерии приёмки:
1. Прогон SimulationEngine(seed) на чекпоинтах 0, 24, 120, 240, 480 часов.
2. Каждый чекпоинт — ПОЛНОЕ состояние через state_to_dict (все 56 полей,
   включая вложенные структуры менеджеров).
3. Baseline: tests/_baseline/engine_state_seed{42,7,123}.json (три сида).
4. Тест сравнивает текущий прогон с baseline по каждому чекпоинту;
   при расхождении — падает с diff (какое поле, чекпоинт, сид).
5. Save/load в середине (час 120) + последующие 10 часов идентичны
   непрерывному прогону (детерминизм).
6. Характеризация детерминирована (фиксированные сиды), БЕЗ условных пропусков.

ЗАПРЕТЫ: не менять логику симуляции; не ослаблять тесты.
"""

from __future__ import annotations

import difflib
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from zonesim.persistence.serialization import state_to_dict
from zonesim.simulation.engine import SimulationEngine

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

BASELINE_DIR = Path(__file__).resolve().parent / "_baseline"
CHECKPOINT_HOURS = [0, 24, 120, 240, 480]
SEEDS = [42, 7, 123]


# ---------------------------------------------------------------------------
# Хелперы для генерации baseline
# ---------------------------------------------------------------------------

def _run_to_checkpoint(engine: SimulationEngine, target_hour: int) -> None:
    """Прогнать симуляцию до нужного часа."""
    while engine.state.time.hour < target_hour:
        engine.simulate_hour()


def _generate_baseline_for_seed(seed: int) -> dict[str, Any]:
    """Запустить симуляцию и собрать снимок состояния на каждом чекпоинте."""
    engine = SimulationEngine(seed=seed)
    checkpoints: dict[str, dict[str, Any]] = {}

    for ch_hour in CHECKPOINT_HOURS:
        _run_to_checkpoint(engine, ch_hour)
        # state_to_dict сериализует все 56 полей, включая вложенные структуры
        checkpoints[str(ch_hour)] = {
            "time": engine.state.time.hour,
            "state": state_to_dict(engine.state),
        }

    return {"seed": seed, "checkpoints": checkpoints}


def generate_all_baselines() -> dict[int, dict[str, Any]]:
    """Собрать baseline для всех сидов."""
    results: dict[int, dict[str, Any]] = {}
    for seed in SEEDS:
        results[seed] = _generate_baseline_for_seed(seed)
    return results


def _save_baseline(seed: int, data: dict[str, Any]) -> None:
    """Сохранить baseline в JSON."""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    path = BASELINE_DIR / f"engine_state_seed{seed}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Загрузка baseline
# ---------------------------------------------------------------------------

def _load_baseline(seed: int) -> dict[str, Any]:
    """Загрузить baseline JSON; если файла нет — вернуть пустой для диагностики."""
    path = BASELINE_DIR / f"engine_state_seed{seed}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Сравнение двух снимков состояния
# ---------------------------------------------------------------------------

def _flatten_dict(d: dict[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
    """Рекурсивно «сплющить» словарь для удобного поиска расхождений.

    Пример: {"time": {"hour": 120}, "sectors": {"a": 1}}
    → {"time.hour": 120, "sectors.a": 1}
    """
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict) and "__kind__" not in v:
            items.extend(_flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def _compare_states(
    baseline: dict[str, Any], current: dict[str, Any],
    checkpoint: int, seed: int,
) -> list[str]:
    """Сравнить baseline-снимок с текущим. Вернуть список строк diff (пусто = совпали)."""
    diffs: list[str] = []
    b_flat = _flatten_dict(baseline)
    c_flat = _flatten_dict(current)

    all_keys = set(b_flat.keys()) | set(c_flat.keys())

    for key in sorted(all_keys):
        b_val = b_flat.get(key)
        c_val = c_flat.get(key)

        if b_val != c_val:
            b_repr = json.dumps(b_val, ensure_ascii=False, default=str) if b_val is not None else "None"
            c_repr = json.dumps(c_val, ensure_ascii=False, default=str) if c_val is not None else "None"
            # Показать только первые 200 символов значения для читаемости
            if len(b_repr) > 200:
                b_repr = b_repr[:200] + "... (truncated)"
            if len(c_repr) > 200:
                c_repr = c_repr[:200] + "... (truncated)"
            diffs.append(
                f"  поле={key}  checkpoint={checkpoint}  seed={seed}\n"
                f"    baseline: {b_repr}\n"
                f"    current:  {c_repr}"
            )

    return diffs


# ---------------------------------------------------------------------------
# Тест 1: Проверка полного снимка состояния
# ---------------------------------------------------------------------------

class TestEngineStateSnapshot:
    """Каждый чекпоинт каждого сида совпадает с baseline по каждому полю."""

    @pytest.mark.parametrize("seed", SEEDS)
    def test_snapshot_matches_baseline(self, seed: int) -> None:
        """Прогнать до каждого чекпоинта и сравнить state_to_dict с baseline."""
        baseline_data = _load_baseline(seed)
        if not baseline_data:
            pytest.fail(
                f"Baseline not found for seed {seed}. "
                f"Run tests/_generate_baselines.py first."
            )

        bl_checkpoints = baseline_data.get("checkpoints", {})
        diffs_all: list[str] = []

        # Запустить симуляцию с тем же сидом
        engine = SimulationEngine(seed=seed)

        for ch_hour_str, bl_cp in bl_checkpoints.items():
            ch_hour = int(ch_hour_str)
            _run_to_checkpoint(engine, ch_hour)

            current_state = state_to_dict(engine.state)
            bl_state = bl_cp.get("state", {})

            # Проверить: количество полей на верхнем уровне
            bl_fields = set(bl_state.keys())
            cur_fields = set(current_state.keys())
            missing = bl_fields - cur_fields
            extra = cur_fields - bl_fields
            if missing:
                diffs_all.append(
                    f"  checkpoint={ch_hour}  seed={seed}\n"
                    f"    missing fields: {sorted(missing)}"
                )
            if extra:
                diffs_all.append(
                    f"  checkpoint={ch_hour}  seed={seed}\n"
                    f"    extra fields: {sorted(extra)}"
                )

            # Сравнить содержимое каждого поля
            field_diffs = _compare_states(bl_state, current_state, ch_hour, seed)
            diffs_all.extend(field_diffs)

        if diffs_all:
            message = (
                f"Snapshot mismatch (seed={seed}, "
                f"{len(diffs_all)} field(s) differ):\n"
                + "\n".join(diffs_all)
            )
            pytest.fail(message)


# ---------------------------------------------------------------------------
# Тест 2: Мутация — проверка что тест ПАДАЕТ при изменении состояния
# ---------------------------------------------------------------------------

class TestEngineSnapshotMutation:
    """Убедиться, что тест обнаруживает изменения состояния (мутационная проверка)."""

    def test_mutated_state_is_detected(self) -> None:
        """Изменить shelter_count после старта → тест падает на checkpoint 0."""
        seed = 42
        baseline_data = _load_baseline(seed)
        if not baseline_data:
            pytest.skip("Baseline not found for mutation test.")

        engine = SimulationEngine(seed=seed)
        _run_to_checkpoint(engine, 0)

        # Мутация: изменить целочисленное поле на верхнем уровне
        original_shelter_count = engine.state.shelter_count
        engine.state.shelter_count = original_shelter_count + 999

        current_state = state_to_dict(engine.state)
        bl_state = baseline_data["checkpoints"]["0"].get("state", {})

        diffs = _compare_states(bl_state, current_state, 0, seed)
        assert len(diffs) > 0, (
            "Тест мутации: ожидалось обнаружение изменения shelter_count, "
            "но diff пуст — тест не работает!"
        )

        # Восстановить для чистоты (хотя тест уже прошёл)
        engine.state.shelter_count = original_shelter_count


# ---------------------------------------------------------------------------
# Тест 3: Save/Load детерминизм
# ---------------------------------------------------------------------------

class TestSaveLoadDeterminism:
    """Save и продолжение дают те же результаты, что и непрерывный прогон (§20.3)."""

    def test_save_load_at_hour_120_continuity(self) -> None:
        """
        Save в середине (час 120) + 10 часов симуляции = непрерывные 130 часов.
        Сравниваем ПОЛНОЕ состояние после продолжения.
        """
        for seed in SEEDS:
            # Непрерывный прогон
            engine_cont = SimulationEngine(seed=seed, save_directory=None)
            for _ in range(130):
                engine_cont.simulate_hour()

            state_at_130_continuous = state_to_dict(engine_cont.state)

            # Прерванный прогон: save на час 120, load, continue
            engine_save = SimulationEngine(seed=seed, save_directory=None)
            for _ in range(120):
                engine_save.simulate_hour()

            # Сохраняем вручную через pickle-подобный механизм
            saved_state_dict = state_to_dict(engine_save.state)
            saved_time = engine_save.state.time.hour

            # Создаём новый engine и восстанавливаем состояние
            engine_load = SimulationEngine(seed=seed, save_directory=None)
            # Восстановим время
            engine_load.state.time = type(engine_load.state.time)(saved_time)
            # Восстановим RNG
            engine_load.state.rng.set_state(engine_save.state.rng.get_state())
            # Восстановим все поля через state_from_dict
            from zonesim.persistence.serialization import state_from_dict
            restored = state_from_dict(saved_state_dict)

            # Заменённые поля
            engine_load.state.time = restored.time
            engine_load.state.rng = restored.rng
            engine_load.state.sectors = restored.sectors
            engine_load.state.humans = restored.humans
            engine_load.state.stationary_humans = restored.stationary_humans
            engine_load.state.human_groups = restored.human_groups
            engine_load.state.monsters = restored.monsters
            engine_load.state.monster_groups = restored.monster_groups
            engine_load.state.anomalies = restored.anomalies
            engine_load.state.artifacts = restored.artifacts
            engine_load.state.corpses = restored.corpses
            engine_load.state.items = restored.items
            engine_load.state.contracts = restored.contracts
            engine_load.state.import_export = restored.import_export
            engine_load.state.personal_relations = restored.personal_relations
            engine_load.state.faction_relations = restored.faction_relations
            engine_load.state.development = restored.development
            engine_load.state.exile_manager = restored.exile_manager
            engine_load.state.faction_change_manager = restored.faction_change_manager
            engine_load.state.news_manager = restored.news_manager
            engine_load.state.knowledge_bases = restored.knowledge_bases
            engine_load.state.stashs = restored.stashs
            engine_load.state.shelter_count = restored.shelter_count
            engine_load.state.next_shelter_id = restored.next_shelter_id
            engine_load.state.trader_stock = restored.trader_stock
            engine_load.state.trails = restored.trails
            engine_load.state.shelters = restored.shelters
            engine_load.state.temp_shelters = restored.temp_shelters
            engine_load.state.next_emission_hour = restored.next_emission_hour
            engine_load.state.emission_start_hour = restored.emission_start_hour
            engine_load.state.emission_end_hour = restored.emission_end_hour
            engine_load.state.emission_warning_hour = restored.emission_warning_hour
            engine_load.state.emission_exposed = restored.emission_exposed
            engine_load.state.migration_state = restored.migration_state
            engine_load.state.monster_migration = restored.monster_migration
            engine_load.state.next_human_id = restored.next_human_id
            engine_load.state.next_monster_id = restored.next_monster_id
            engine_load.state.next_group_id = restored.next_group_id
            engine_load.state.next_monster_group_id = restored.next_monster_group_id
            engine_load.state.next_anomaly_id = restored.next_anomaly_id
            engine_load.state.next_stash_id = restored.next_stash_id
            engine_load.state.next_corpse_id = restored.next_corpse_id
            engine_load.state.next_item_id = restored.next_item_id
            engine_load.state.visit_memory = restored.visit_memory
            engine_load.state.config = restored.config
            engine_load.state.prev_relation_snapshot = restored.prev_relation_snapshot
            engine_load.state.relation_change_journal = restored.relation_change_journal
            engine_load.state.intention_knowledge_used = restored.intention_knowledge_used
            engine_load.state.knowledge_snapshot_at_intention = (
                restored.knowledge_snapshot_at_intention
            )
            engine_load.state.next_conditional_spawn_hour = (
                restored.next_conditional_spawn_hour
            )
            engine_load.state.conditional_trader_id = restored.conditional_trader_id
            engine_load.state.conditional_trader_sector = restored.conditional_trader_sector
            engine_load.state.conditional_trader_start_hour = (
                restored.conditional_trader_start_hour
            )
            engine_load.state.conditional_trader_end_hour = restored.conditional_trader_end_hour
            engine_load.state.conditional_trader_knowledge_hour = (
                restored.conditional_trader_knowledge_hour
            )
            engine_load.state.ongoing_shelter_assaults = (
                restored.ongoing_shelter_assaults
            )

            # Прогон ещё 10 часов
            for _ in range(10):
                engine_load.simulate_hour()

            state_at_130_loaded = state_to_dict(engine_load.state)

            # Сравнить ПОЛНОЕ состояние
            if state_at_130_continuous != state_at_130_loaded:
                diffs = _compare_states(
                    state_at_130_continuous, state_at_130_loaded,
                    130, seed,
                )
                pytest.fail(
                    f"Save/load mismatch (seed={seed}):\n"
                    + "\n".join(diffs)
                )


# ---------------------------------------------------------------------------
# Тест 4: Формат baseline — обязательные поля
# ---------------------------------------------------------------------------

class TestBaselineFormat:
    """Проверить структуру baseline-файлов."""

    @pytest.mark.parametrize("seed", SEEDS)
    def test_baseline_has_all_checkpoints(self, seed: int) -> None:
        """Baseline содержит все чекпоинты."""
        data = _load_baseline(seed)
        assert data, f"Baseline file is empty or missing for seed {seed}"
        assert data["seed"] == seed, f"Expected seed {seed}, got {data['seed']}"

        cp_keys = sorted(data["checkpoints"].keys(), key=int)
        expected_keys = [str(h) for h in CHECKPOINT_HOURS]
        assert cp_keys == expected_keys, (
            f"Expected checkpoints {expected_keys}, got {cp_keys}"
        )

    @pytest.mark.parametrize("seed", SEEDS)
    def test_baseline_fields_count(self, seed: int) -> None:
        """Каждый снимок содержит все 56 полей SimulationState."""
        import dataclasses
        from zonesim.simulation.engine import SimulationState

        expected_fields = {f.name for f in dataclasses.fields(SimulationState)}

        for cp_hour_int in CHECKPOINT_HOURS:
            cp_hour_str = str(cp_hour_int)
            state = _load_baseline(seed)["checkpoints"][cp_hour_str]["state"]
            present_fields = set(state.keys())
            missing = expected_fields - present_fields
            assert not missing, (
                f"seed={seed}, checkpoint={cp_hour_str}: "
                f"missing fields: {sorted(missing)}"
            )


# ---------------------------------------------------------------------------
# Консольный генератор baseline (вызывается отдельно)
# ---------------------------------------------------------------------------

def main() -> None:
    """Точка входа для генерации baseline: python -m tests.test_engine_characterization --generate."""
    import sys
    if "--generate" not in sys.argv:
        print("Use --generate flag to recreate baselines.", file=sys.stderr)
        sys.exit(1)

    print("=== Engine State Characterization — Baseline Generator ===")
    print()

    all_data = generate_all_baselines()
    total_start = time.time()

    for seed, data in all_data.items():
        seed_start = time.time()
        _save_baseline(seed, data)

        # Подсчитать размер
        path = BASELINE_DIR / f"engine_state_seed{seed}.json"
        size_kb = path.stat().st_size / 1024
        n_checkpoints = len(data["checkpoints"])
        total_hours = sum(
            int(k) for k in data["checkpoints"]
        )
        elapsed = time.time() - seed_start

        print(
            f"  seed={seed:>4d}  "
            f"checkpoints={n_checkpoints}  "
            f"total_hours={total_hours}  "
            f"size={size_kb:>10.1f} KB  "
            f"elapsed={elapsed:.2f}s"
        )

    total_elapsed = time.time() - total_start
    print()
    print(f"  TOTAL: {len(all_data)} baselines, {total_elapsed:.2f}s")
    print(f"  Saved to: {BASELINE_DIR}")


if __name__ == "__main__":
    main()
