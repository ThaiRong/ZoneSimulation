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
    SHELTER_KIT = "shelter_kit"  # нерасходный набор для убежища (§7.10)


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


def consume_item(state, item: Item, members: list[HumanNPC]) -> None:
    """Удаляет израсходованный предмет из инвентаря и реестра."""
    owner = next((npc for npc in members if item.id in npc.inventory), None)
    if owner is not None:
        owner.inventory.remove(item.id)
        if owner.equipped_weapon_id == item.id:
            owner.equipped_weapon_id = None
        if owner.equipped_armor_id == item.id:
            owner.equipped_armor_id = None
    state.items.pop(item.id, None)


def create_item(state, item_type: ItemType, name: str, base_value: float,
                owner_id: int | None = None, quantity: int = 1,
                properties: dict | None = None) -> Item:
    """Создаёт уникальный предмет и добавляет в реестр."""
    item = Item(
        id=state.next_item_id,
        type=item_type,
        name=name,
        base_value=base_value,
        quantity=quantity,
        properties=properties or {},
    )
    state.next_item_id += 1
    state.items[item.id] = item
    if owner_id is not None:
        owner = next(
            npc for npc in state.humans + state.stationary_humans
            if npc.id == owner_id
        )
        give_item(item, owner_id, owner.inventory)
    return item


def sync_npc_from_items(state, npc: HumanNPC) -> None:
    """Синхронизирует характеристики NPC с экипированными предметами."""
    from zonesim.combat.loot import EquipmentManager

    weapon = state.items.get(npc.equipped_weapon_id)
    armor = state.items.get(npc.equipped_armor_id)
    npc.weapon_condition = weapon.condition if weapon else 0
    npc.weapon_damage = (
        weapon.properties.get("base_damage", weapon.properties.get("damage", 20))
        if weapon else 5
    )
    npc.armor_condition = armor.condition if armor else 0
    npc.armor_value = (
        armor.properties.get("armor_factor", armor.properties.get("armor", 1.0))
        * EquipmentManager.get_armor_effectiveness(armor.condition)
        if armor else 1.0
    )
    npc.ammo = sum(
        item.quantity for item_id in npc.inventory
        if (item := state.items[item_id]).type is ItemType.AMMO
    )
    npc.medicines = sum(
        item.quantity for item_id in npc.inventory
        if (item := state.items[item_id]).type is ItemType.MEDICINE
    )


def spawn_catalog_item(state, catalog, item_ref: str, owner_id: int,
                       quantity: int = 1) -> Item:
    """Создаёт предмет из каталога и добавляет владельцу. (§7.8)"""
    item = catalog.create_item(state.next_item_id, item_ref, quantity=quantity)
    state.next_item_id += 1
    state.items[item.id] = item
    owner = next(
        npc for npc in state.humans + state.stationary_humans
        if npc.id == owner_id
    )
    give_item(item, owner_id, owner.inventory)
    return item


def give_starting_equipment(state, npc: HumanNPC, catalog) -> None:
    """Выдаёт стартовое снаряжение NPC. (§7.8)"""
    if npc.inventory:
        return
    npc.money = 100
    if npc.faction == "Серая лига":
        weapon_ref, armor_ref = "weapon.rifle.sokol", "armor.outer.scout"
    else:
        weapon_ref, armor_ref = "weapon.carbine.k20", "armor.uniform.jacket"
    weapon = spawn_catalog_item(state, catalog, weapon_ref, npc.id)
    armor = spawn_catalog_item(state, catalog, armor_ref, npc.id)
    npc.equipped_weapon_id = weapon.id
    npc.equipped_armor_id = armor.id
    ammo_ref = weapon.properties.get("ammo_type")
    if ammo_ref:
        spawn_catalog_item(state, catalog, ammo_ref, npc.id, quantity=12)
    spawn_catalog_item(state, catalog, "gear.medkit.sanitar2", npc.id)
    spawn_catalog_item(state, catalog, "shelter.kit.basic", npc.id)
    sync_npc_from_items(state, npc)
