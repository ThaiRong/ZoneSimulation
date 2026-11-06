"""Временные убежища (Shelter) и стационарные укрытия (StormShelter).

Основано на §7.10 и §7.16 ТЗ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Shelter:
    """Временное убежище в секторе. (§7.10)"""
    id: int
    sector_id: int
    owner_group_id: int
    owner_npc_ids: list[int] = field(default_factory=list)
    created_hour: int = 0
    duration_hours: int = 12  # стандартная длительность
    quality: int = 50  # качество от 1-100
    materials: int = 0  # расходные материалы использованы
    destroyed: bool = False

    @property
    def is_active(self) -> bool:
        return not self.destroyed

    @property
    def remaining_hours(self) -> int:
        # caller должен передать current_hour
        return self.duration_hours

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

    def expire(self, current_hour: int) -> bool:
        """Проверяет, истёк ли срок. Возвращает True если уничтожено."""
        if not self.is_active:
            return True
        # caller должен передать current_hour
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sector_id": self.sector_id,
            "owner_group_id": self.owner_group_id,
            "owner_npc_ids": self.owner_npc_ids,
            "created_hour": self.created_hour,
            "duration_hours": self.duration_hours,
            "quality": self.quality,
            "destroyed": self.destroyed,
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
