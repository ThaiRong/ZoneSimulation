"""Совместимый импорт единой модели монстров и их статусов."""

from enum import Enum

from zonesim.world.entity import Monster, MonsterSpecies


class MonsterStatus(str, Enum):
    ACTIVE = "active"
    SLEEPING = "sleeping"
    UNCONSCIOUS = "unconscious"
    DEAD = "dead"


__all__ = ["Monster", "MonsterSpecies", "MonsterStatus"]
