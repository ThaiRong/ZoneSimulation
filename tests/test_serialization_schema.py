"""Schema-driven сериализация: гейты полноты и истинный round-trip (§21 ТЗ).

Production-код НЕ изменяется — только тесты. Четыре поля
(intention_knowledge_used, knowledge_snapshot_at_intention,
prev_relation_snapshot, relation_change_journal) намеренно не
сериализуются, поэтому тесты помечены xfail(strict=True).
"""

from __future__ import annotations

import dataclasses
import shutil

import pytest

from zonesim.persistence.serialization import state_from_dict, state_to_dict
from zonesim.simulation.engine import SimulationEngine, SimulationState


# ---------------------------------------------------------------------------
# 1. Гейт полноты: все поля SimulationState присутствуют в словаря serialization
# ---------------------------------------------------------------------------

def test_serialization_completeness_gate(controlled_state: SimulationState,
                                         full_field_names: set[str]) -> None:
    """set(state_to_dict(s)) должен содержать ключи для ВСЕХ 56 полей."""
    serialized_keys = set(state_to_dict(controlled_state).keys())
    assert serialized_keys == full_field_names, (
        f"Отсутствуют поля: {full_field_names - serialized_keys}"
    )


# ---------------------------------------------------------------------------
# 2. Истинный round-trip: поле-за-полем совпадает оригинал и restored state
# ---------------------------------------------------------------------------

def _compare_state_field_by_field(original: SimulationState,
                                  restored: SimulationState) -> list[str]:
    """Сравнивает два SimulationState поле-за-полем, возвращает список差异."""
    diffs: list[str] = []
    for field in dataclasses.fields(original):
        fname = field.name
        orig_val = getattr(original, fname)
        rest_val = getattr(restored, fname)
        if orig_val != rest_val:
            diffs.append(fname)
    return diffs


@pytest.mark.xfail(strict=True, reason="4 поля не выживают при round-trip")
def test_true_roundtrip_field_by_field(controlled_state: SimulationState) -> None:
    """state_from_dict(state_to_dict(s)) == s по ВСЕМ 56 полям."""
    d = state_to_dict(controlled_state)
    restored = state_from_dict(d)
    diffs = _compare_state_field_by_field(controlled_state, restored)
    assert diffs == [], f"Поля с расхождениями: {diffs}"


# ---------------------------------------------------------------------------
# 3. Характеризация: save/load в середине прогона + 10 ч vs непрерывный
# ---------------------------------------------------------------------------

def test_save_load_mid_run_continuation(tmp_path: pytest.TempPath) -> None:
    """Save/load в середине прогона не ломает детерминизм: 10 последующих часов идентичны."""
    # --- Непрерывный прогон -----------------------------------------------
    engine_continuous = SimulationEngine(seed=777)
    for _ in range(20):
        engine_continuous.simulate_hour()

    for _ in range(10):
        engine_continuous.simulate_hour()
    state_continuous_final = engine_continuous.state

    # --- Прерванный прогон (save after 20h, load, continue 10h) ------------
    engine_break = SimulationEngine(seed=777)
    for _ in range(20):
        engine_break.simulate_hour()

    save_dir = tmp_path / "break_save"
    save_dir.mkdir()
    from zonesim.persistence import SaveManager
    SaveManager(save_dir).save("mid", engine_break.state)

    engine_break_restored = SimulationEngine.load("mid", save_dir)

    for _ in range(10):
        engine_break_restored.simulate_hour()
    state_break_final = engine_break_restored.state

    # --- Сравнение через state_to_dict (как в существующих тестах проекта) ---
    # relation_change_journal не сериализуется, поэтому исключаем из сравнения
    dict_continuous = state_to_dict(state_continuous_final)
    dict_break = state_to_dict(state_break_final)
    dict_continuous.pop("relation_change_journal", None)
    dict_break.pop("relation_change_journal", None)
    assert dict_continuous == dict_break
