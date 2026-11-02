"""Тайники (Stash). Основано на §7.9 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Stash:
    """Тайник в секторе. (§7.9)"""
    id: int
    sector_id: int
    owner_id: int  # ID NPC-владельца
    items: list[dict] = field(default_factory=list)  # предметы и деньги
    money: int = 0
    concealment: int = 50  # уровень скрытности
    known_by: list[int] = field(default_factory=list)  # IDs NPC, знающих о тайнике
    created_hour: int = 0
    discovered: bool = False
    discovered_by: int | None = None
    discovered_hour: int | None = None
    _snapshot: dict | None = None  # снимок на момент первого получения

    def _capture_snapshot(self) -> None:
        """Ленивый снимок содержимого при первом запросе."""
        if self._snapshot is None:
            self._snapshot = {
                "sector_id": self.sector_id,
                "owner_id": self.owner_id,
                "items": [i.copy() for i in self.items],
                "money": self.money,
            }

    @property
    def total_value(self) -> int:
        return self.money + sum(item.get("value", 0) for item in self.items)

    def add_item(self, item: dict) -> None:
        self.items.append(item)

    def remove_item(self, item_index: int) -> dict | None:
        if 0 <= item_index < len(self.items):
            return self.items.pop(item_index)
        return None

    def get_knowledge_payload(self) -> dict[str, Any]:
        """Мгновенный снимок текущего состояния (для создания нового знания)."""
        return {
            "sector_id": self.sector_id,
            "owner_id": self.owner_id,
            "items": [i.copy() for i in self.items],
            "money": self.money,
        }

    def get_snapshot(self) -> dict[str, Any]:
        """Неизменный снимок. Первый вызов фиксирует текущее состояние, последующие возвращают старое. (§7.9)"""
        self._capture_snapshot()
        return self._snapshot.copy() if self._snapshot else {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sector_id": self.sector_id,
            "owner_id": self.owner_id,
            "items": self.items,
            "money": self.money,
            "concealment": self.concealment,
            "known_by": self.known_by.copy(),
            "created_hour": self.created_hour,
            "discovered": self.discovered,
            "discovered_by": self.discovered_by,
        }
