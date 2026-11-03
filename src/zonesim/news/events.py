"""Совместимый импорт единой системы событий и новостей."""

from zonesim.relations.news import EventImportance, NewsManager, WorldEvent

Importance = EventImportance

__all__ = ["EventImportance", "Importance", "NewsManager", "WorldEvent"]
