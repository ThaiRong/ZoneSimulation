"""Система новостей и сводок. Основано на §18 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Importance(str, Enum):
    LOW = "низкая"
    MEDIUM = "средняя"
    HIGH = "высокая"
    CRITICAL = "критическая"


@dataclass
class WorldEvent:
    """Событие мира. (§7.15)"""
    id: int
    hour: int
    minute: int
    sector_id: int
    event_type: str  # "combat", "trade", "hunt", "discovery" и т.д.
    participants: list[int]  # IDs участников
    result: str  # "success", "failure", "retreated"
    importance: int = 10  # 1-100
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    factions_notified: list[str] = field(default_factory=list)

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
        }


class NewsManager:
    """Управление новостями и сводками. (§18)"""

    def __init__(self):
        self.events: list[WorldEvent] = []
        self.hourly_summaries: list[dict] = []
        self._next_event_id: int = 0

    def add_event(self, event: WorldEvent) -> None:
        """Добавляет событие в журнал."""
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
    ) -> WorldEvent:
        """Создаёт событие."""
        event = WorldEvent(
            id=self._next_event_id,
            hour=hour,
            minute=minute,
            sector_id=sector_id,
            event_type=event_type,
            participants=participants,
            result=result,
            importance=importance,
            summary=summary,
            details=details or {},
        )
        self._next_event_id += 1
        self.add_event(event)
        return event

    def get_hourly_summary(self, hour: int, sector_events: dict[int, list[WorldEvent]]) -> dict:
        """
        Формирует сводку часа. (§18.2)
        sector_events: {sector_id: [events]}
        """
        all_events = []
        for sector_id, evts in sector_events.items():
            for evt in evts:
                all_events.append((sector_id, evt))

        # Сортируем по важности
        all_events.sort(key=lambda x: x[1].importance, reverse=True)

        # Берём топ-5 событий для общей сводки
        top_events = all_events[:5]

        return {
            "hour": hour,
            "day": hour // 24,
            "total_events": len(all_events),
            "critical_events": [
                {"sector_id": sid, "event": evt}
                for sid, evt in top_events
                if evt.importance >= 60
            ],
            "sector_summaries": self._generate_sector_summaries(sector_events),
        }

    def _generate_sector_summaries(
        self,
        sector_events: dict[int, list[WorldEvent]],
    ) -> list[dict]:
        """Формирует краткие сводки по секторам. (§18.2)"""
        summaries = []
        for sector_id, evts in sector_events.items():
            if not evts:
                continue
            # Объединяем однотипные события
            type_counts: dict[str, int] = {}
            for evt in evts:
                type_counts[evt.event_type] = type_counts.get(evt.event_type, 0) + 1

            summary_text = "; ".join(f"{count}x {etype}" for etype, count in type_counts.items())
            summaries.append({
                "sector_id": sector_id,
                "event_count": len(evts),
                "max_importance": max(e.importance for e in evts),
                "summary": summary_text,
            })

        return summaries

    def get_events_by_sector(self, sector_id: int, hour: int | None = None) -> list[WorldEvent]:
        """Получает события по сектору."""
        result = [e for e in self.events if e.sector_id == sector_id]
        if hour is not None:
            result = [e for e in result if e.hour == hour]
        return result

    def get_events_by_type(self, event_type: str) -> list[WorldEvent]:
        """Получает события по типу."""
        return [e for e in self.events if e.event_type == event_type]

    def get_last_n_events(self, n: int = 20) -> list[WorldEvent]:
        """Получает последние N событий."""
        return self.events[-n:]

    def get_total_events_count(self) -> int:
        return len(self.events)

    def get_events_by_importance(self, min_importance: int = 0) -> list[WorldEvent]:
        """Фильтрация по важности."""
        return [e for e in self.events if e.importance >= min_importance]
