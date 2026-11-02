"""Личные отношения NPC. Основано на §15.1 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RelationState(str, Enum):
    ALLY = "ally"
    NEUTRAL = "neutral"
    ENEMY = "enemy"


class PersonalRelations:
    """Управление личными отношениями NPC. (§15.1)"""

    def __init__(self):
        # (id_a, id_b) -> int (-100 до 100)
        self._relations: dict[tuple[int, int], int] = {}

    def get(self, id_a: int, id_b: int) -> int:
        key = (min(id_a, id_b), max(id_a, id_b))
        return self._relations.get(key, 0)

    def set(self, id_a: int, id_b: int, value: int) -> None:
        value = max(-100, min(100, value))
        key = (min(id_a, id_b), max(id_a, id_b))
        self._relations[key] = value

    def change(self, id_a: int, id_b: int, delta: int) -> None:
        current = self.get(id_a, id_b)
        new_val = current + delta
        self.set(id_a, id_b, new_val)

    def get_state(self, id_a: int, id_b: int) -> RelationState:
        val = self.get(id_a, id_b)
        if val > 0:
            return RelationState.ALLY
        if val < -20:
            return RelationState.ENEMY
        return RelationState.NEUTRAL

    def is_ally(self, id_a: int, id_b: int) -> bool:
        return self.get_state(id_a, id_b) == RelationState.ALLY

    def is_enemy(self, id_a: int, id_b: int) -> bool:
        return self.get_state(id_a, id_b) == RelationState.ENEMY

    def to_dict(self) -> dict[str, Any]:
        return {
            f"{a}-{b}": val for (a, b), val in self._relations.items()
        }
