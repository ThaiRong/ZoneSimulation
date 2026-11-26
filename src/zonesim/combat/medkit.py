"""Экстренное лечение и использование аптечек. Основано на §14.3 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zonesim.world.item import ItemType, consume_item

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState
    from zonesim.world.entity import HumanNPC
    from zonesim.world.item import Item


def use_medkit_charge(state, medkit: Item, members: list[HumanNPC]) -> None:
    """Расходует один заряд аптечки; пустую аптечку удаляет."""
    charges = medkit.properties.get("charges", medkit.quantity)
    if charges > 1:
        medkit.properties["charges"] = charges - 1
    else:
        consume_item(state, medkit, members)


def emergency_medkit(state, npc: HumanNPC, members: list[HumanNPC]) -> None:
    """Экстренное применение на ходу: половина эффекта, без часа действия. (§14.3)"""
    for other in members:
        for item_id in other.inventory:
            item = state.items.get(item_id)
            if (
                item is not None
                and item.type is ItemType.MEDICINE
                and item.properties.get("charges", 0) > 0
            ):
                npc.health = min(
                    npc.max_health,
                    npc.health + item.properties.get("heal_amount", 30) // 2,
                )
                use_medkit_charge(state, item, members)
                return
