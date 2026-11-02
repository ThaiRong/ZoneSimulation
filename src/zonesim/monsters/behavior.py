"""Модели и поведение монстров. Основано на §7.6 и §13 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MonsterSpecies(str, Enum):
    TERRITORIAL_PREDATOR = "territorial_predator"  # территориальный хищник
    SCAVENGER_PACK = "scavenger_pack"  # стайный падальщик
    LARGE_MIGRATOR = "large_migrator"  # крупный всеядный мигрант


class MonsterStatus(str, Enum):
    ACTIVE = "active"
    SLEEPING = "sleeping"
    UNCONSCIOUS = "unconscious"
    DEAD = "dead"


@dataclass
class Monster:
    """Монстр. (§7.6, §13)"""
    id: int
    species: MonsterSpecies
    sector_id: int
    group_id: int | None = None
    health: int = 100
    max_health: int = 100
    stamina: float = 100
    max_stamina: float = 100
    attack: int = 50
    defense: int = 50
    attentiveness: int = 50
    bravery: int = 50
    home_sector_id: int | None = None
    target_memory_hour: int = 0
    target_id: int | None = None
    status: MonsterStatus = MonsterStatus.ACTIVE

    # Видыые параметры
    SPECIES_PARAMS = {
        MonsterSpecies.TERRITORIAL_PREDATOR: {
            "species_power": 0.33,
            "max_group_size": 12,
            "normal_group_size": (3, 8),
            "speed_edges_per_hour": 2,
            "base_attack": 50,
            "base_defense": 50,
            "base_attentiveness": 40,
        },
        MonsterSpecies.SCAVENGER_PACK: {
            "species_power": 0.70,
            "max_group_size": 4,
            "normal_group_size": (1, 4),
            "speed_edges_per_hour": 1,
            "base_attack": 40,
            "base_defense": 60,
            "base_attentiveness": 60,
        },
        MonsterSpecies.LARGE_MIGRATOR: {
            "species_power": 4.00,
            "max_group_size": 2,
            "normal_group_size": (1, 2),
            "speed_edges_per_hour": 1,
            "base_attack": 70,
            "base_defense": 70,
            "base_attentiveness": 20,
        },
    }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "species": self.species.value,
            "sector_id": self.sector_id,
            "group_id": self.group_id,
            "health": self.health,
            "max_health": self.max_health,
            "stamina": self.stamina,
            "status": self.status.value,
        }

    @classmethod
    def create_from_species(cls, id: int, species: MonsterSpecies, sector_id: int,
                            rng) -> Monster:
        """Создаёт монстра по виду."""
        params = cls.SPECIES_PARAMS[species]
        return cls(
            id=id,
            species=species,
            sector_id=sector_id,
            health=100,
            max_health=100,
            stamina=100,
            max_stamina=100,
            attack=params["base_attack"],
            defense=params["base_defense"],
            attentiveness=params["base_attentiveness"],
            home_sector_id=sector_id,
        )

    @property
    def species_params(self) -> dict:
        return self.SPECIES_PARAMS.get(self.species, {})

    @property
    def health_share(self) -> float:
        return self.health / self.max_health if self.max_health > 0 else 0

    @property
    def stamina_share(self) -> float:
        return self.stamina / self.max_stamina if self.max_stamina > 0 else 0
