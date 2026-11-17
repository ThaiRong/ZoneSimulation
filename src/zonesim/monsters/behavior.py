"""Единая модель и видовые решения монстров (§13 ТЗ)."""

from enum import Enum

from zonesim.world.entity import Monster, MonsterSpecies


class MonsterStatus(str, Enum):
    ACTIVE = "active"
    SLEEPING = "sleeping"
    UNCONSCIOUS = "unconscious"
    DEAD = "dead"


def species_value(monster_or_species) -> str:
    species = getattr(monster_or_species, "species", monster_or_species)
    value = species.value if hasattr(species, "value") else species
    return {
        "TerritorialPredator": "territorial_predator",
        "ScavengerPack": "scavenger_pack",
        "LargeMigrator": "large_migrator",
    }.get(value, value)


def select_weakest_target(targets: list):
    if not targets:
        return None
    return min(targets, key=lambda target: (target.health_share, target.id))


def choose_group_intention(
    members: list[Monster],
    has_accessible_corpse: bool,
    target=None,
    target_in_sector: bool = False,
) -> str:
    if not members:
        return "roam"
    if has_accessible_corpse:
        return "feed"
    weakest = min(members, key=lambda monster: monster.health_share)
    if weakest.health_share <= 0.2:
        return "rest"
    if target is not None:
        return "hunt" if target_in_sector else "stalk"
    return "roam"


__all__ = [
    "Monster",
    "MonsterSpecies",
    "MonsterStatus",
    "choose_group_intention",
    "select_weakest_target",
    "species_value",
]
