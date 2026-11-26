"""Тропы и их блокировки. Основано на §10.5 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zonesim.anomalies.emission import EMISSION_TRAIL_BLOCK_CHANCE
from zonesim.ai import edge_key

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState
    from zonesim.anomalies.core import AnomalyEntity


def trail_set(state) -> set[tuple[int, int]]:
    """Множество рёбер троп (edges)."""
    return {edge_key(pair[0], pair[1]) for pair in state.trails}


def roll_trail_blockage(state, anomaly) -> None:
    """Аномалия может перекрыть тропу у своего сектора. (§10.5)"""
    anomaly.blocks_trail = None
    if state.rng.random() >= EMISSION_TRAIL_BLOCK_CHANCE:
        return
    incident = [
        edge for edge in trail_set(state)
        if anomaly.sector_id in edge
        and not any(state.sectors[s].is_faction_start for s in edge)
    ]
    if incident:
        anomaly.blocks_trail = list(state.rng.choice(sorted(incident)))


def roll_trail_blockages(state) -> None:
    """Проходит по всем аномалиям и проверяет блокировки троп."""
    for anomaly in state.anomalies.values():
        roll_trail_blockage(state, anomaly)
