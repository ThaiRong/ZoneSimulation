"""Временные убежища (Shelter) и стационарные укрытия (StormShelter).

Основано на §7.10 и §7.16 ТЗ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Shelter:
    """Временное убежище в секторе. (§7.10)

    Может использоваться группами одной фракции.
    Передается между группами.
    Разрушается через 4 часа без использования.
    Максимум 10 человек.
    Монстры не занимают.
    """
    id: int
    sector_id: int
    owner_group_id: int
    owner_faction: str = ""
    created_hour: int = 0
    last_used_hour: int = 0  # последний кто использовал
    quality: int = 50  # качество от 1-100
    destroyed: bool = False

    # Участники: group_id -> list[npc_id]
    participants: dict[int, list[int]] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return not self.destroyed

    @property
    def participant_count(self) -> int:
        return sum(len(npcs) for npcs in self.participants.values())

    @property
    def remaining_hours(self) -> int:
        """Оставшиеся часы жизни (6 часов по умолчанию, +4 за каждое использование)."""
        return 6 + (self.last_used_hour - self.created_hour)

    def can_accept_group(self, group_id: int, faction: str) -> bool:
        """Можно ли принять группу?"""
        if not self.is_active:
            return False
        if self.participant_count >= 10:
            return False
        # Та же фракция или нейтральная
        if self.owner_faction and faction and faction != self.owner_faction:
            return False
        # Проверка что группа ещё не участвует
        return group_id not in self.participants

    def add_group(self, group_id: int, npc_ids: list[int]) -> bool:
        """Добавить группу в убежище."""
        if not self.can_accept_group(group_id, ""):
            return False
        self.participants[group_id] = npc_ids
        self.last_used_hour = self.last_used_hour  # caller должен передать current_hour
        return True

    def remove_group(self, group_id: int) -> bool:
        """Убрать группу из убежища."""
        if group_id in self.participants:
            del self.participants[group_id]
            return True
        return False

    def expire(self, current_hour: int) -> bool:
        """Проверяет, истёк ли срок. Возвращает True если уничтожено."""
        if not self.is_active:
            return True
        # 4 часа без использования
        if current_hour - self.last_used_hour >= 4 and self.participant_count == 0:
            self.destroyed = True
            return True
        # Максимум 6 часов жизни
        if current_hour - self.created_hour >= 6:
            self.destroyed = True
            return True
        return False

    @property
    def concealment_bonus(self) -> int:
        """Бонус к скрытности. (§7.10)"""
        return int(self.quality * 0.3)

    @property
    def defense_bonus(self) -> int:
        """Ограниченный защитный бонус при нападении. (§7.10)"""
        return int(self.quality * 0.15)

    @property
    def recovery_bonus(self) -> float:
        """Улучшение отдыха и лечения. (§7.10)"""
        return 1.0 + (self.quality / 100.0) * 0.5  # +до 50% к восстановлению

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sector_id": self.sector_id,
            "owner_group_id": self.owner_group_id,
            "owner_faction": self.owner_faction,
            "created_hour": self.created_hour,
            "last_used_hour": self.last_used_hour,
            "quality": self.quality,
            "destroyed": self.destroyed,
            "participants": dict(self.participants),
        }


@dataclass
class StormShelter:
    """Стационарное укрытие от выброса — неподвижный объект ландшафта. (§7.16)"""
    id: int
    sector_id: int
    capacity: int = 4        # сколько человек одновременно могут укрыться
    condition: int = 100     # в MVP только для отображения
    occupied_by: int | None = None   # id группы монстров (§13.7)
    occupied_until: int = 0          # час окончания занятия

    @property
    def is_occupied(self) -> bool:
        return self.occupied_by is not None
