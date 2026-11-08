"""Базовые классы сущностей. Основано на §7.4-7.7 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar


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
    intention: str = ""  # выбранное намерение (фаза 4, §9)
    artifacts: list[int] = field(default_factory=list)  # id переносимых артефактов
    inventory: list[int] = field(default_factory=list)
    money: int = 0
    debt: int = 0
    equipped_weapon_id: int | None = None
    equipped_armor_id: int | None = None
    is_stationary: bool = False
    stationary_role: str | None = None  # trader / guard
    awake_since_hour: int = 0  # час последнего пробуждения (сон необходим раз в 24 ч)
    base_heal_until: int = -100  # лечение на базе оплачено до этого часа (§14.3)

    @property
    def health_share(self) -> float:
        return self.health / self.max_health if self.max_health > 0 else 0

    @property
    def stamina_share(self) -> float:
        return self.stamina / self.max_stamina if self.max_stamina > 0 else 0


class MonsterSpecies(str, Enum):
    TERRITORIAL_PREDATOR = "territorial_predator"
    SCAVENGER_PACK = "scavenger_pack"
    LARGE_MIGRATOR = "large_migrator"


@dataclass(init=False)
class Monster(BaseEntity):
    species: str | MonsterSpecies = "TerritorialPredator"
    group_id: int | None = None
    home_sector_id: int | None = None
    target_memory_hour: int = 0
    target_id: int | None = None

    SPECIES_PARAMS: ClassVar[dict] = {
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

    def __init__(
        self,
        id: int = 0,
        species: str | MonsterSpecies = "TerritorialPredator",
        sector_id: int = 0,
        group_id: int | None = None,
        health: int = 100,
        max_health: int = 100,
        stamina: int = 100,
        max_stamina: int = 100,
        attack: int = 50,
        defense: int = 50,
        attentiveness: int = 50,
        bravery: int = 50,
        home_sector_id: int | None = None,
        target_memory_hour: int = 0,
        target_id: int | None = None,
        status: EntityStatus = EntityStatus.ACTIVE,
        type: EntityType = EntityType.MONSTER,
    ):
        self.id = id
        self.species = species
        self.sector_id = sector_id
        self.group_id = group_id
        self.health = health
        self.max_health = max_health
        self.stamina = stamina
        self.max_stamina = max_stamina
        self.attack = attack
        self.defense = defense
        self.attentiveness = attentiveness
        self.bravery = bravery
        self.home_sector_id = home_sector_id
        self.target_memory_hour = target_memory_hour
        self.target_id = target_id
        self.status = status
        self.type = type

    def to_dict(self) -> dict:
        species = self.species.value if hasattr(self.species, "value") else self.species
        status = self.status.value if hasattr(self.status, "value") else str(self.status)
        status = {
            EntityStatus.ACTIVE.value: "active",
            EntityStatus.SLEEPING.value: "sleeping",
            EntityStatus.UNCONSCIOUS.value: "unconscious",
            EntityStatus.DEAD.value: "dead",
        }.get(status, status)
        return {
            "id": self.id,
            "species": species,
            "sector_id": self.sector_id,
            "group_id": self.group_id,
            "health": self.health,
            "max_health": self.max_health,
            "stamina": self.stamina,
            "status": status,
        }

    @classmethod
    def create_from_species(
        cls, id: int, species: MonsterSpecies, sector_id: int, rng,
    ) -> Monster:
        params = cls.SPECIES_PARAMS[species]
        return cls(
            id=id,
            species=species,
            sector_id=sector_id,
            attack=params["base_attack"],
            defense=params["base_defense"],
            attentiveness=params["base_attentiveness"],
            home_sector_id=sector_id,
        )

    @property
    def species_params(self) -> dict:
        species = self.species
        if isinstance(species, str) and not isinstance(species, MonsterSpecies):
            species = {
                "TerritorialPredator": MonsterSpecies.TERRITORIAL_PREDATOR,
                "ScavengerPack": MonsterSpecies.SCAVENGER_PACK,
                "LargeMigrator": MonsterSpecies.LARGE_MIGRATOR,
            }.get(species, species)
        return self.SPECIES_PARAMS.get(species, {})

    @property
    def health_share(self) -> float:
        return self.health / self.max_health if self.max_health > 0 else 0

    @property
    def stamina_share(self) -> float:
        return self.stamina / self.max_stamina if self.max_stamina > 0 else 0
