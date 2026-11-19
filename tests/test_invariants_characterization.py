"""Characterization-тест инвариантов (§22).

Golden-baseline: фиксирует ТЕКУЩЕЕ поведение assert_world_invariants
на 240 ч (seed 42). Снимки на чекпоинтах: 0,24,48,...,240.

Fingerprint = { invariant_id: counter } + { world_metric: value }
на каждом чекпоинте.

ПРИ РЕФАКТОРЕ: fingerprint должен СОВПАДАТЬ с baseline.
ПРИ ИЗМЕНЕНИИ ПОВЕДЕНИЯ: baseline ОБНОВЛЯЕТСЯ НАМЕРЕННО через
  python tests/regenerate_baseline.py
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any

import pytest

from zonesim.simulation.engine import SimulationEngine


# ====================================================================
# Golden-baseline
# ====================================================================

BASELINE_DIR = Path(__file__).parent / "_baseline"
BASELINE_FILE = BASELINE_DIR / "invariants_240h_seed42.json"


def _compute_fingerprint(state) -> dict[str, Any]:
    """Вычисляет fingerprint состояния инвариантов на конкретном часе.

    Состоит из:
    1. invariant_counts: сколько раз каждый # инварианта сработал в последний вызов
    2. world_metrics: ключевые метрики мира

    НБ: НЕ полный хэш сейва (хрупко к формату), а СЕМАНТИЧЕСКИЙ fingerprint.
    """
    from zonesim.simulation.invariants import assert_world_invariants

    # Получаем текущие нарушения
    errors = assert_world_invariants(state)

    # Считаем нарушения по #
    invariant_counts: dict[str, int] = {}
    for err in errors:
        # Format: "Инвариант #12 (ч. 5): ..."
        if "Инвариант #" in err:
            idx = err.index("Инвариант #") + len("Инвариант #")
            dash = err.index(" ", idx)
            inv_id = err[idx:dash]
            invariant_counts[inv_id] = invariant_counts.get(inv_id, 0) + 1

    # Ключевые метрики мира
    world_metrics = {
        "time_hour": state.time.hour,
        "time_day": state.time.day,
        "time_phase": state.time.phase if hasattr(state.time, 'phase') else None,
        "num_humans": len(state.humans),
        "num_monsters": len(state.monsters),
        "num_human_groups": len(state.human_groups),
        "num_monster_groups": len(state.monster_groups),
        "num_anomalies": len(state.anomalies),
        "num_items": len(state.items),
        "num_artifacts": len(state.artifacts.artifacts),
        "num_shelters": len(state.shelters),
        "num_stations": len(state.stationary_humans),
        "next_human_id": state.next_human_id if hasattr(state, 'next_human_id') else None,
        "next_monster_id": state.next_monster_id if hasattr(state, 'next_monster_id') else None,
        "next_item_id": state.next_item_id if hasattr(state, 'next_item_id') else None,
        "next_group_id": state.next_group_id if hasattr(state, 'next_group_id') else None,
        "next_anomaly_id": state.next_anomaly_id if hasattr(state, 'next_anomaly_id') else None,
        "num_knowledge_bases": len(state.knowledge_bases),
        "num_factions": len(state.faction_relations._relations) if hasattr(state.faction_relations, '_relations') else 0,
    }

    return {
        "invariant_counts": invariant_counts,
        "world_metrics": world_metrics,
    }


def _generate_baseline() -> dict[str, Any]:
    """Генерирует golden-baseline.

    Запуск:
      python tests/regenerate_baseline.py
    """
    engine = SimulationEngine(seed=42)

    checkpoints: dict[int, dict[str, Any]] = {}

    # Чекпоинт 0 (initial state)
    checkpoints[0] = _compute_fingerprint(engine.state)

    # Прогон 240 ч
    for _ in range(240):
        engine.simulate_hour()
        current_hour = engine.state.time.hour
        if current_hour % 24 == 0:
            checkpoints[current_hour] = _compute_fingerprint(engine.state)

    # JSON сериализует int-ключи как строки — конвертируем
    checkpoints_str: dict[str, dict[str, Any]] = {
        str(k): v for k, v in checkpoints.items()
    }

    return {
        "version": 1,
        "seed": 42,
        "hours": 240,
        "checkpoint_interval": 24,
        "num_checkpoints": len(checkpoints),
        "checkpoints": checkpoints_str,
    }


@pytest.fixture(scope="session")
def golden_baseline() -> dict[str, Any]:
    """Golden-baseline инвариантов на 240 ч (seed 42)."""
    if not BASELINE_FILE.exists():
        # Генерируем baseline
        baseline = _generate_baseline()
        BASELINE_DIR.mkdir(exist_ok=True)
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2, default=str)

    with open(BASELINE_FILE, "r", encoding="utf-8") as f:
        bp = json.load(f)
        # JSON сериализует ключи как строки — конвертируем обратно
        int_checkpoints: dict[int, dict[str, Any]] = {}
        for k, v in bp["checkpoints"].items():
            int_checkpoints[int(k)] = v
        bp["checkpoints"] = int_checkpoints
        return bp


# ====================================================================
# Characterization test
# ====================================================================


def test_characterization_240h_seed42(golden_baseline: dict[str, Any]) -> None:
    """Characterization: поведение инвариантов на 240 ч (seed 42) совпадает с baseline.

    При рефакторинге (Части 3–5) fingerprint должен совпасть.
    При намеренном изменении логики — baseline обновляется вручную.
    """
    engine = SimulationEngine(seed=42)

    expected_checkpoints = golden_baseline["checkpoints"]
    expected_interval = golden_baseline["checkpoint_interval"]

    mismatches: list[str] = []
    seen_checkpoints: set[int] = set()

    # Проверяем чекпоинт 0 (initial)
    fp0 = _compute_fingerprint(engine.state)
    bp0 = expected_checkpoints.get(0)
    if bp0:
        if fp0["invariant_counts"] != bp0["invariant_counts"]:
            mismatches.append(
                f"Час 0: invariant_counts differ:\n"
                f"  Current:   {fp0['invariant_counts']}\n"
                f"  Baseline:  {bp0['invariant_counts']}"
            )
        if fp0["world_metrics"] != bp0["world_metrics"]:
            mismatches.append(
                f"Час 0: world_metrics differ:\n"
                f"  Current:   {fp0['world_metrics']}\n"
                f"  Baseline:  {bp0['world_metrics']}"
            )
        seen_checkpoints.add(0)

    # Прогон 240 ч
    for _ in range(240):
        engine.simulate_hour()
        current_hour = engine.state.time.hour

        if current_hour % expected_interval == 0:
            fp = _compute_fingerprint(engine.state)
            bp = expected_checkpoints.get(current_hour)
            if bp is None:
                mismatches.append(f"Час {current_hour}: отсутствует в baseline")
                continue

            if fp["invariant_counts"] != bp["invariant_counts"]:
                mismatches.append(
                    f"Час {current_hour}: invariant_counts differ:\n"
                    f"  Current:   {fp['invariant_counts']}\n"
                    f"  Baseline:  {bp['invariant_counts']}"
                )
            if fp["world_metrics"] != bp["world_metrics"]:
                mismatches.append(
                    f"Час {current_hour}: world_metrics differ:\n"
                    f"  Current:   {fp['world_metrics']}\n"
                    f"  Baseline:  {bp['world_metrics']}"
                )
            seen_checkpoints.add(current_hour)

    assert not mismatches, (
        f"Characterization-тест ПРОВАЛЕН: {len(mismatches)} расхождений\n\n"
        + "\n\n".join(mismatches)
    )


# ====================================================================
# Regenerate baseline (для разработчиков)
# ====================================================================

if __name__ == "__main__":
    """
    Regenerate golden-baseline.

    Использование:
      cd ZoneSimulation
      python tests/test_invariants_characterization.py

    Это перезапишет tests/_baseline/invariants_240h_seed42.json.
    """
    print("Generating golden-baseline...")
    baseline = _generate_baseline()
    BASELINE_DIR.mkdir(exist_ok=True)
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2, default=str)
    print(f"Baseline written to: {BASELINE_FILE}")
    print(f"Checkpoints: {baseline['num_checkpoints']}")
    # Convert string keys back to int for display
    int_checkpoints = {int(k): v for k, v in baseline["checkpoints"].items()}
    for h, fp in sorted(int_checkpoints.items()):
        invs = fp["invariant_counts"]
        humans = fp["world_metrics"]["num_humans"]
        inv_str = sorted(invs.keys()) if invs else "none"
        print(f"  hour={h:3d} humans={humans:3d} inv_count={sum(invs.values()):2d} "
              f"inv_ids={inv_str}")
