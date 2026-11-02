"""Система новостей и сводок. Основано на §18 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventImportance(str, Enum):
    LOW = "низкая"
    MEDIUM = "средняя"
    HIGH = "высокая"
    CRITICAL = "критическая"


@dataclass
class WorldEvent:
    """Событие мира. (§7.15, §18)"""
    id: int
    hour: int
    minute: int
    sector_id: int
    event_type: str  # combat, trade, hunt, discovery, etc.
    participants: list[int]
    result: str
    importance: int = 10  # 1-100
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    notified_factions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hour": self.hour,
            "minute": self.minute,
            "sector_id": self.sector_id,
            "event_type": self.event_type,
            "participants": self.participants,
            "result": self.result,
            "importance": self.importance,
            "summary": self.summary,
        }


class NewsManager:
    """Управление новостями и сводками. (§18)"""

    IMPORTANCE_THRESHOLDS = {
        "movement": (1, 5),
        "trade": (5, 15),
        "resource_find": (10, 20),
        "stash_create": (15, 25),
        "anomaly_discovery": (25, 45),
        "ambush": (35, 60),
        "combat_no_death": (30, 55),
        "npc_death": (60, 85),
        "anomaly_destroy": (65, 85),
        "conditional_trader_appear": (50, 70),
        "faction_change": (75, 90),
        "war_start": (90, 100),
    }

    def __init__(self):
        self.events: list[WorldEvent] = []
        self._next_id: int = 0

    def create_event(self, hour: int, minute: int, sector_id: int,
                     event_type: str, participants: list[int],
                     result: str, importance: int, summary: str,
                     details: dict | None = None,
                     notified_factions: list[str] | None = None) -> WorldEvent:
        """Создаёт событие."""
        event = WorldEvent(
            id=self._next_id,
            hour=hour,
            minute=minute,
            sector_id=sector_id,
            event_type=event_type,
            participants=participants,
            result=result,
            importance=importance,
            summary=summary,
            details=details or {},
            notified_factions=notified_factions or [],
        )
        self._next_id += 1
        self.events.append(event)
        return event

    def get_hourly_summary(self, hour: int) -> dict[str, Any]:
        """Краткая сводка часа. (§18.2)"""
        hour_events = [e for e in self.events if e.hour == hour]
        hour_events.sort(key=lambda e: e.importance, reverse=True)

        return {
            "hour": hour,
            "day": hour // 24,
            "total_events": len(hour_events),
            "top_events": [e.to_dict() for e in hour_events[:5]],
        }

    def get_sector_summary(self, sector_id: int, hour: int) -> list[dict[str, Any]]:
        """Сводка по сектору за час. (§18.2)"""
        events = [e for e in self.events
                  if e.sector_id == sector_id and e.hour == hour]
        return [e.to_dict() for e in events]

    def get_last_n(self, n: int = 20) -> list[dict[str, Any]]:
        """Последние N событий."""
        return [e.to_dict() for e in self.events[-n:]]

    def filter_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Фильтр по типу события."""
        return [e.to_dict() for e in self.events if e.event_type == event_type]

    def filter_by_importance(self, min_importance: int = 0) -> list[dict[str, Any]]:
        """Фильтр по важности."""
        return [e.to_dict() for e in self.events if e.importance >= min_importance]

    def get_events_by_sector(self, sector_id: int) -> list[dict[str, Any]]:
        """Все события по сектору."""
        return [e.to_dict() for e in self.events if e.sector_id == sector_id]

    def get_total_count(self) -> int:
        return len(self.events)
