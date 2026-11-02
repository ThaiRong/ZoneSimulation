"""Базовые классы сущностей. Основано на §7.4-7.7 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EntityStatus(str, Enum):
    ACTIVE = "Активен"
    SLEEPING = "Спит"
    UNCONSCIOUS = "Без сознания"
    PRISONER = "В плену"
    DEAD = "Погиб"
    EXILED = "Покинул Зону"


class EntityType(str, Enum):
    HUMAN = "human"
    MONSTER = "monster"
    ANOMALY = "anomaly"
    TRADER = "trader"


@dataclass
class StatsMixin:
    """Миксин для характеристик 1-100."""
    attack: int = 50
    defense: int = 50
    stamina: int = 100
    max_stamina: int = 100
    attentiveness: int = 50
    bravery: int = 50
    health: int = 100
    max_health: int = 100


@dataclass
class BaseEntity(StatsMixin):
    id: int = 0
    type: EntityType = EntityType.HUMAN
    sector_id: int = 0
    status: EntityStatus = field(default=EntityStatus.ACTIVE)

    def is_alive(self) -> bool:
        return self.status != EntityStatus.DEAD and self.status != EntityStatus.EXILED


@dataclass
class HumanNPC(BaseEntity):
    faction: str = "Бродяги"
    group_id: int | None = None
    name: str = "Unknown"

    @property
    def health_share(self) -> float:
        return self.health / self.max_health if self.max_health > 0 else 0

    @property
    def stamina_share(self) -> float:
        return self.stamina / self.max_stamina if self.max_stamina > 0 else 0


@dataclass
class Monster(BaseEntity):
    species: str = "TerritorialPredator"
    group_id: int | None = None
    home_sector_id: int | None = None


@dataclass
class Anomaly:
    id: int
    sector_id: int
    anomaly_type: str = "subtle"  # subtle, visible, large
    stability: int = 40
    concealment: int = 70
    damage_min: int = 5
    damage_max: int = 12
    artifact_timer: int = 0
    move_timer: int = 0
    safe_path: bool = False
    status: str = "active"  # active, destroyed
