"""Фаза 3: Наблюдение и распространение сведений.

Этап 3, Промпт 3.5: тело перенесено из engine.py в standalone функцию.
Работает с SimulationContext, вспомогательные методы вызываются через ctx.engine_ref.
"""

from __future__ import annotations

from zonesim.actions.detection import check_anomaly_detection
from zonesim.anomalies.core import AnomalyStatus
from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType
from zonesim.simulation.context import SimulationContext
from zonesim.world.entity import EntityStatus


def run_phase3_knowledge(ctx: SimulationContext) -> None:
    """Фаза 3: Наблюдение и распространение сведений.

    Бодрствующие NPC получают знания об аномалиях своего сектора только
    при успешной проверке обнаружения (§10.3, §5.1).
    """
    state = ctx.state
    hour = ctx.hour
    is_night = ctx.is_night

    for npc in state.humans:
        if npc.status != EntityStatus.ACTIVE:
            continue

        sector = state.sectors.get(npc.sector_id)
        terrain_concealment = sector.concealment if sector else 50

        for anomaly in state.anomalies.values():
            if anomaly.sector_id != npc.sector_id or anomaly.status != AnomalyStatus.ACTIVE:
                continue

            detected = check_anomaly_detection(
                observer_att=npc.attentiveness,
                anomaly_concealment=anomaly.concealment,
                terrain_concealment=terrain_concealment,
                is_night=is_night,
                rng_value=state.rng.random(),
            )
            if not detected:
                continue

            kb = state.knowledge_bases.setdefault(npc.id, KnowledgeBase())
            kb.add_manual(
                npc_id=npc.id,
                fact_type=KnowledgeType.ANOMALY,
                subject_id=anomaly.id,
                payload={
                    "sector_id": anomaly.sector_id,
                    "anomaly_type": anomaly.anomaly_type.value,
                    "concealment": anomaly.concealment,
                },
                hour=hour,
            )
