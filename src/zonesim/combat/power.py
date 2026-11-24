"""Боевая сила отрядов и групп монстров. Основано на §11.2 ТЗ."""

from __future__ import annotations

from typing import Any

from zonesim.monsters.behavior import species_value
from zonesim.world.entity import Monster

# Монстровые видовые силы (§11.2)
_SPECIES_POWER_VALUE = {
    "territorial_predator": 0.33,
    "scavenger_pack": 0.70,
    "large_migrator": 4.00,
}


def squad_power(members: list, items: dict[int, Any]) -> float:
    """Конечная боевая сила отряда: характеристики, снаряжение,
    состояние (§11.2)."""
    total = 0.0
    for member in members:
        if isinstance(member, Monster):
            sp = _SPECIES_POWER_VALUE.get(species_value(member), 0.33)
            bp = sp * (0.5 + member.attack / 100.0)
        else:
            weapon = items.get(member.equipped_weapon_id)
            damage = (
                weapon.properties.get("base_damage", member.weapon_damage)
                if weapon else member.weapon_damage
            )
            weapon_factor = max(damage / 20.0, 0.25)
            condition_factor = max(0.25, (weapon.condition if weapon else 50) / 100.0)
            bp = 1.0 * (0.5 + member.attack / 100.0) * weapon_factor * condition_factor
        h = 0.35 + 0.65 * member.health_share
        s = 0.5 + 0.5 * member.stamina_share
        total += bp * h * s
    return total


def monster_group_power(members: list[Monster]) -> float:
    """Сила группы монстров с бонусом за численность (§11.2)."""
    total = 0.0
    for monster in members:
        health = 0.35 + 0.65 * monster.health_share
        stamina = 0.5 + 0.5 * monster.stamina_share
        total += monster.species_params.get("species_power", 0.33) * (
            0.5 + monster.attack / 100
        ) * health * stamina
    return total * min(1.15, 1 + 0.03 * (len(members) - 1))
