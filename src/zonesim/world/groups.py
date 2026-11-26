"""Группы: логика работы с комплектами и лидерами. Основано на §7.5 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zonesim.world.item import ItemType

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState
    from zonesim.world.entity import HumanNPC
    from zonesim.world.group import HumanGroup
    from zonesim.world.item import Item


def group_kit(state, members, item_type: ItemType, predicate=None):
    """Первый подходящий исправный комплект в инвентарях членов группы."""
    for npc in members:
        for item_id in npc.inventory:
            item = state.items.get(item_id)
            if item is None or item.type is not item_type or item.condition <= 0:
                continue
            if predicate is None or predicate(item):
                return npc, item
    return None, None


def active_members(state, group: HumanGroup) -> list[HumanNPC]:
    """Активные члены группы (без мёртвых/пленных/бессознательных)."""
    npcs = {npc.id: npc for npc in state.humans}
    from zonesim.world.entity import EntityStatus
    return [
        npcs[mid] for mid in group.members
        if mid in npcs and npcs[mid].status == EntityStatus.ACTIVE
    ]


def group_leader(group: HumanGroup, members: list[HumanNPC]) -> HumanNPC:
    """Лидер группы из активных членов."""
    return next((npc for npc in members if npc.id == group.leader_id), members[0])
