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


def blocked_trail_map(state) -> dict[tuple[int, int], "AnomalyEntity"]:
    """Карта блокированных троп: edge -> аномалия. (§10.5)"""
    from zonesim.anomalies.core import AnomalyStatus

    mapping: dict[tuple[int, int], "AnomalyEntity"] = {}
    for anomaly in state.anomalies.values():
        if anomaly.status == AnomalyStatus.ACTIVE and anomaly.blocks_trail:
            mapping[edge_key(anomaly.blocks_trail[0], anomaly.blocks_trail[1])] = anomaly
    return mapping


def group_has_passage(state, group: "HumanGroup", anomaly) -> bool:
    """Проверяет, имеет ли группа проход через блокированную аномалию. (§10.5)"""
    from zonesim.knowledge.fact import KnowledgeType

    edge = list(anomaly.blocks_trail)
    humans = {npc.id: npc for npc in state.humans}
    for member_id in group.members:
        npc = humans.get(member_id)
        if npc is None:
            continue
        kb = state.knowledge_bases.get(npc.id)
        if kb is None:
            continue
        for fact in kb.get_facts(KnowledgeType.SAFE_PATH, subject_id=anomaly.id):
            if fact.payload.get("edge") == edge:
                return True
    return False


def init_trails(state) -> None:
    """Тропы: около 40% рёбер графа. (§10.4)"""
    edges = {
        edge_key(sid, nid)
        for sid, sector in state.sectors.items()
        for nid in sector.neighbors
    }
    trails = [list(edge) for edge in sorted(edges) if state.rng.random() < 0.4]
    state.trails = trails
