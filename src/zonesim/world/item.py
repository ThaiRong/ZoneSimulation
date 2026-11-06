"""Уникальные предметы и инвентарь NPC (§7.8, §22 ТЗ)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ItemType(str, Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    AMMO = "ammo"
    MEDICINE = "medicine"
    OPTICS = "optics"
    DETECTOR = "detector"
    CAPTURE_KIT = "capture_kit"
    DESTROY_KIT = "destroy_kit"
    MONSTER_PART = "monster_part"
    LIVE_MONSTER = "live_monster"
    ARTIFACT = "artifact"
    ANOMALY_PART = "anomaly_part"
    SUPPLIES = "supplies"


@dataclass
class Item:
    id: int
    type: ItemType
    name: str
    condition: int = 100
    base_value: float = 0.0
    owner_id: int | None = None
    location: str = "inventory"
    quantity: int = 1
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.condition = max(0, min(100, self.condition))
        self.quantity = max(0, self.quantity)

    @property
    def is_broken(self) -> bool:
        return self.condition == 0

    @property
    def current_value(self) -> float:
        return self.base_value * (0.25 + 0.75 * self.condition / 100)


def give_item(item: Item, owner_id: int, inventory: list[int]) -> None:
    if item.id in inventory:
        raise ValueError(f"Предмет {item.id} уже находится у владельца {owner_id}")
    item.owner_id = owner_id
    item.location = "inventory"
    inventory.append(item.id)


def place_item_on_corpse(item: Item, corpse_id: int, inventory: list[int]) -> None:
    if item.id not in inventory:
        raise ValueError(f"Предмет {item.id} отсутствует в инвентаре владельца")
    inventory.remove(item.id)
    item.owner_id = None
    item.location = f"corpse:{corpse_id}"


def take_item_from_corpse(item: Item, corpse, owner_id: int, inventory: list[int]) -> None:
    if item.id not in corpse.items or item.location != f"corpse:{corpse.id}":
        raise ValueError(f"Предмет {item.id} не находится на трупе {corpse.id}")
    corpse.items.remove(item.id)
    give_item(item, owner_id, inventory)
