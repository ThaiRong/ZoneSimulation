"""Фракционные отношения. Основано на §15.2 ТЗ."""

from __future__ import annotations

from typing import Any


class FactionRelations:
    """Отношения между фракциями. (§15.2)"""

    FACTIONS = ["Бродяги", "Борзые", "Серая лига"]

    INITIAL = {
        ("Бродяги", "Борзые"): -25,
        ("Бродяги", "Серая лига"): +10,
        ("Борзые", "Серая лига"): -10,
    }

    def __init__(self):
        self._relations: dict[tuple[str, str], int] = {}
        for (a, b), val in self.INITIAL.items():
            self._relations[(a, b)] = val
            self._relations[(b, a)] = val

    def get(self, faction_a: str, faction_b: str) -> int:
        return self._relations.get((faction_a, faction_b), 0)

    def set(self, faction_a: str, faction_b: str, value: int) -> None:
        self._relations[(faction_a, faction_b)] = value
        self._relations[(faction_b, faction_a)] = value

    def change(self, faction_a: str, faction_b: str, delta: int) -> None:
        current = self.get(faction_a, faction_b)
        new_val = max(-100, min(100, current + delta))
        self.set(faction_a, faction_b, new_val)

    def to_dict(self) -> dict[str, Any]:
        return {
            f"{a}→{b}": val
            for (a, b), val in self._relations.items()
        }
