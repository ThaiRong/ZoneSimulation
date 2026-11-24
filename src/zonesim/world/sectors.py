"""Сектора: запросы по людям в секторах. Основано на §7.2 ТЗ."""

from __future__ import annotations

from typing import Any

from zonesim.world.entity import HumanNPC


def sector_humans(
    humans: list[Any],
    stationary_humans: list[Any],
    sector_id: int,
) -> dict[int, HumanNPC]:
    """Возвращает всех живых NPC (человек + стационарные) в заданном секторе."""
    return {
        npc.id: npc
        for npc in humans + stationary_humans
        if npc.sector_id == sector_id
    }
