"""Получение артефактов из аномалий. Основано на §15 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zonesim.world.item import ItemType, create_item

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState
    from zonesim.world.entity import HumanNPC


def give_artifact(state, npc: HumanNPC, anomaly, hour: int) -> None:
    """Выдаёт артефакт из аномалии NPC. (§15)"""
    for art in state.artifacts.artifacts:
        if art.anomaly_id == anomaly.id and not art.discovered:
            art.discovered = True
            npc.artifacts.append(art.id)
            create_item(
                state, ItemType.ARTIFACT, f"Артефакт ({art.rarity})", art.value, npc.id,
                properties={"artifact_id": art.id},
            )
            state.news_manager.create_event(
                hour=hour, minute=45, sector_id=npc.sector_id,
                event_type="artifact_found", participants=[npc.id], result="picked_up",
                importance=30,
                summary=f"NPC {npc.id} извлёк артефакт из аномалии {anomaly.id}",
                details={"artifact_id": art.id, "rarity": art.rarity, "value": art.value},
            )
            return
