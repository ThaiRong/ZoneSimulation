"""Стартовые стражи (guards) на базах. Основано на §15.1 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState
    from zonesim.world.entity import HumanNPC


def base_guards(state, sector_id: int, faction: str) -> list["HumanNPC"]:
    """Возвращает список стражей в секторе. (§15.1)"""
    from zonesim.world.entity import EntityStatus

    sector = state.sectors[sector_id]
    if not sector.is_faction_start or sector.controller_faction != faction:
        return []
    return [
        npc for npc in state.stationary_humans
        if npc.sector_id == sector_id and npc.stationary_role == "guard"
        and npc.status == EntityStatus.ACTIVE
    ]
