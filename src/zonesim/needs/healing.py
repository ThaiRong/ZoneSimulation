"""Лечение в час отдыха. Основано на §14.3 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zonesim.world.item import ItemType
from zonesim.combat.medkit import use_medkit_charge
from zonesim.world.item import sync_npc_from_items


def rest_heal(state, group, members: list[HumanNPC]) -> None:
    """Лечение в час отдыха: заряд на каждого раненого члена группы. (§14.3)"""
    medkits = [
        state.items[item_id]
        for npc in members for item_id in npc.inventory
        if item_id in state.items
        and state.items[item_id].type is ItemType.MEDICINE
        and state.items[item_id].properties.get("charges", 0) > 0
    ]
    if not medkits:
        return
    wounded = sorted(
        (npc for npc in members if npc.health_share < 0.95),
        key=lambda npc: npc.health_share,
    )
    for patient in wounded:
        kit = next(
            (
                entry for entry in medkits
                if entry.properties.get("charges", 0) > 0
            ),
            None,
        )
        if kit is None:
            break
        heal = kit.properties.get("heal_amount", 30)
        patient.health = min(patient.max_health, patient.health + heal)
        use_medkit_charge(state, kit, members)
        sync_npc_from_items(state, patient)
