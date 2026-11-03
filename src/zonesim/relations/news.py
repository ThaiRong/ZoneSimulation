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
    event_type: str
    participants: list[int]
    result: str
    importance: int = 10
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    notified_factions: list[str] = field(default_factory=list)

    @property
    def factions_notified(self) -> list[str]:
        return self.notified_factions

    @factions_notified.setter
    def factions_notified(self, value: list[str]) -> None:
        self.notified_factions = value

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
            "details": self.details,
            "notified_factions": self.notified_factions,
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
        self.hourly_summaries: list[dict] = []
        self._next_id: int = 0

    def add_event(self, event: WorldEvent) -> None:
        self.events.append(event)

    def create_event(
        self,
        hour: int,
        minute: int,
        sector_id: int,
        event_type: str,
        participants: list[int],
        result: str,
        importance: int,
        summary: str,
        details: dict | None = None,
        notified_factions: list[str] | None = None,
    ) -> WorldEvent:
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

    def get_hourly_summary(
        self,
        hour: int,
        sector_events: dict[int, list[WorldEvent]] | None = None,
    ) -> dict[str, Any]:
        if sector_events is not None:
            all_events = [
                (sector_id, event)
                for sector_id, events in sector_events.items()
                for event in events
            ]
            all_events.sort(key=lambda item: item[1].importance, reverse=True)
            top_events = all_events[:5]
            return {
                "hour": hour,
                "day": hour // 24,
                "total_events": len(all_events),
                "critical_events": [
                    {"sector_id": sector_id, "event": event}
                    for sector_id, event in top_events
                    if event.importance >= 60
                ],
                "sector_summaries": self._generate_sector_summaries(sector_events),
            }

        hour_events = [event for event in self.events if event.hour == hour]
        hour_events.sort(key=lambda event: event.importance, reverse=True)
        return {
            "hour": hour,
            "day": hour // 24,
            "total_events": len(hour_events),
            "top_events": [event.to_dict() for event in hour_events[:5]],
        }

    def _generate_sector_summaries(
        self,
        sector_events: dict[int, list[WorldEvent]],
    ) -> list[dict]:
        summaries = []
        for sector_id, events in sector_events.items():
            if not events:
                continue
            type_counts: dict[str, int] = {}
            for event in events:
                type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1
            summaries.append({
                "sector_id": sector_id,
                "event_count": len(events),
                "max_importance": max(event.importance for event in events),
                "summary": "; ".join(
                    f"{count}x {event_type}" for event_type, count in type_counts.items()
                ),
            })
        return summaries

    def get_sector_summary(self, sector_id: int, hour: int) -> list[dict[str, Any]]:
        return [
            event.to_dict()
            for event in self.events
            if event.sector_id == sector_id and event.hour == hour
        ]

    def get_last_n(self, n: int = 20) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.events[-n:]]

    def get_last_n_events(self, n: int = 20) -> list[WorldEvent]:
        return self.events[-n:]

    def filter_by_type(self, event_type: str) -> list[dict[str, Any]]:
        return [
            event.to_dict() for event in self.events if event.event_type == event_type
        ]

    def filter_by_importance(self, min_importance: int = 0) -> list[dict[str, Any]]:
        return [
            event.to_dict() for event in self.events if event.importance >= min_importance
        ]

    def get_events_by_sector(
        self, sector_id: int, hour: int | None = None,
    ) -> list[dict[str, Any]]:
        return [
            event.to_dict()
            for event in self.events
            if event.sector_id == sector_id and (hour is None or event.hour == hour)
        ]

    def get_events_by_type(self, event_type: str) -> list[WorldEvent]:
        return [event for event in self.events if event.event_type == event_type]

    def get_events_by_importance(self, min_importance: int = 0) -> list[WorldEvent]:
        return [event for event in self.events if event.importance >= min_importance]

    def get_total_count(self) -> int:
        return len(self.events)

    def get_total_events_count(self) -> int:
        return len(self.events)
