"""Утилиты для работы с знаниями (KnowledgeBase)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState
    from zonesim.world.group import HumanGroup
    from zonesim.world.item import Item, ItemType


def group_detector_bonus(state) -> dict[int, int]:
    """Бонус детекторов аномалий по группам (лучший исправный детектор)."""
    from zonesim.world.item import ItemType

    humans = {npc.id: npc for npc in state.humans}
    bonuses: dict[int, int] = {}
    for group in state.human_groups.values():
        best = 0
        for member_id in group.members:
            npc = humans.get(member_id)
            if npc is None:
                continue
            for item_id in npc.inventory:
                item = state.items.get(item_id)
                if (
                    item is not None
                    and item.type is ItemType.DETECTOR
                    and item.condition > 0
                ):
                    best = max(best, item.properties.get("anomaly_detection_bonus", 0))
        if best:
            bonuses[group.id] = best
    return bonuses
