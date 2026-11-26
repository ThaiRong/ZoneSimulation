"""Захват монстров группами. Основано на §16.8 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zonesim.world.entity import EntityStatus
from zonesim.world.item import ItemType
from zonesim.monsters.behavior import species_value

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState
    from zonesim.world.group import HumanGroup


def capture_target(state, group: HumanGroup):
    """Ослабленный монстр в секторе группы. (§16.8: здоровье ≤ 35%)"""
    candidates = [
        monster for monster in state.monsters
        if monster.sector_id == group.sector_id
        and monster.status in (EntityStatus.ACTIVE, EntityStatus.UNCONSCIOUS)
        and monster.health_share <= 0.35
    ]
    if not candidates:
        return None
    # активное сопротивление других монстров рядом запрещает захват
    resisting = any(
        monster.status == EntityStatus.ACTIVE
        for monster in state.monsters
        if monster.sector_id == group.sector_id and monster not in candidates
    )
    if resisting:
        return None
    return min(candidates, key=lambda monster: monster.health_share)


def group_can_capture(state, group: HumanGroup, members) -> bool:
    """Проверяет возможность захвата группы. (§16.8)"""
    from zonesim.world.groups import group_kit

    target = capture_target(state, group)
    if target is None:
        return False
    _, kit = group_kit(
        state,
        members, ItemType.CAPTURE_KIT,
        lambda item: item.properties.get("target_species") == species_value(target),
    )
    return kit is not None
