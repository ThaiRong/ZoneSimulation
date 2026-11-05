"""Износ снаряжения, повреждение ценностей, трупы. Основано на §11.8 и §7.11 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from zonesim.world.entity import EntityStatus


class LootType(str, Enum):
    GEAR = "gear"
    PARTS = "parts"
    ARTEFACT = "artefact"
    ANOMALY_PARTS = "anomaly_parts"
    MONEY = "money"
    CORRUPTED = "corrupted"


@dataclass
class EquipmentDamage:
    """Результат износа снаряжения."""
    item_id: int
    item_name: str
    old_condition: int
    new_condition: int
    destroyed: bool = False
    original_damage: int = 0


@dataclass
class Corpse:
    """Труп. (§7.11)"""
    id: int
    original_entity_id: int
    original_entity_type: str  # "human" или вид монстра
    sector_id: int
    created_hour: int = 0
    items: list[int] = field(default_factory=list)
    monster_parts: list[dict] = field(default_factory=list)
    money: int = 0
    body_condition: int = 100
    status: str = "available"  # available, looted, consumed
    consumed_by: int | None = None
    consumed_hour: int | None = None

    @property
    def is_human(self) -> bool:
        return self.original_entity_type == "human"

    def get_total_loot_value(self, items: dict[int, Any] | None = None) -> float:
        if items is None:
            return sum(item.get("value", 0) for item in self.items if isinstance(item, dict))
        return sum(items[item_id].current_value for item_id in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "original_entity_id": self.original_entity_id,
            "original_entity_type": self.original_entity_type,
            "sector_id": self.sector_id,
            "created_hour": self.created_hour,
            "items": self.items,
            "monster_parts": self.monster_parts,
            "money": self.money,
            "body_condition": self.body_condition,
            "status": self.status,
        }


class LootManager:
    """Обыск трупов и извлечение частей монстров (§7.11, §16.8-16.9)."""

    PARTS_BY_SPECIES = {
        "TerritorialPredator": (1, "monster_parts_standard", 25.0),
        "ScavengerPack": (2, "monster_parts_standard", 25.0),
        "LargeMigrator": (3, "monster_parts_rare", 100.0),
        "territorial_predator": (1, "monster_parts_standard", 25.0),
        "scavenger_pack": (2, "monster_parts_standard", 25.0),
        "large_migrator": (3, "monster_parts_rare", 100.0),
    }

    @staticmethod
    def available_monster_parts(monster) -> list[dict]:
        species = monster.species.value if hasattr(monster.species, "value") else monster.species
        count, part_type, value = LootManager.PARTS_BY_SPECIES.get(
            species, (1, "monster_parts_standard", 25.0)
        )
        return [{"type": part_type, "base_value": value} for _ in range(count)]

    @staticmethod
    def loot_corpse(corpse: Corpse, leader, members: list, items: dict) -> dict:
        from zonesim.world.item import ItemType, take_item_from_corpse

        if corpse.status != "available":
            return {"success": False, "reason": "corpse_unavailable"}
        recipients = members or [leader]
        assignments = []
        for item_id in list(corpse.items):
            item = items[item_id]
            recipient = leader
            if item.type in (ItemType.WEAPON, ItemType.ARMOR):
                equipped_field = (
                    "equipped_weapon_id" if item.type is ItemType.WEAPON else "equipped_armor_id"
                )
                candidate = min(
                    recipients,
                    key=lambda npc: LootManager._equipment_score(npc, equipped_field, items),
                )
                if LootManager._equipment_score(candidate, equipped_field, items) < LootManager._item_score(item):
                    recipient = candidate
                    setattr(recipient, equipped_field, item.id)
            elif item.type in (ItemType.AMMO, ItemType.MEDICINE):
                recipient = min(
                    recipients,
                    key=lambda npc: LootManager._consumable_count(npc, item.type, items),
                )
            take_item_from_corpse(item, corpse, recipient.id, recipient.inventory)
            assignments.append({"item_id": item.id, "recipient_id": recipient.id})

        corpse.money = max(0, corpse.money)
        leader.money += corpse.money
        money = corpse.money
        corpse.money = 0
        if not corpse.monster_parts:
            corpse.status = "looted"
        return {
            "success": True,
            "corpse_id": corpse.id,
            "money": money,
            "assignments": assignments,
        }

    @staticmethod
    def harvest_monster_parts(corpse: Corpse, leader, items: dict, next_item_id: int) -> dict:
        from zonesim.world.item import Item, ItemType, give_item

        if corpse.status != "available" or corpse.is_human or not corpse.monster_parts:
            return {"success": False, "reason": "parts_unavailable"}
        created = []
        for template in corpse.monster_parts:
            item = Item(
                id=next_item_id,
                type=ItemType.MONSTER_PART,
                name="Часть монстра",
                condition=corpse.body_condition,
                base_value=template["base_value"],
                properties={"part_type": template["type"], "source_id": corpse.original_entity_id},
            )
            next_item_id += 1
            items[item.id] = item
            give_item(item, leader.id, leader.inventory)
            created.append(item.id)
        corpse.monster_parts.clear()
        if not corpse.items and corpse.money == 0:
            corpse.status = "looted"
        return {
            "success": True,
            "corpse_id": corpse.id,
            "item_ids": created,
            "next_item_id": next_item_id,
        }

    @staticmethod
    def _equipment_score(npc, equipped_field: str, items: dict) -> float:
        item_id = getattr(npc, equipped_field, None)
        item = items.get(item_id)
        return LootManager._item_score(item) if item is not None else -1.0

    @staticmethod
    def _item_score(item) -> float:
        power = item.properties.get(
            "base_damage",
            item.properties.get(
                "damage", item.properties.get("armor_factor", item.properties.get("armor", 1.0)) * 20
            ),
        )
        return power * max(0.25, item.condition / 100)

    @staticmethod
    def _consumable_count(npc, item_type, items: dict) -> int:
        return sum(
            items[item_id].quantity
            for item_id in npc.inventory
            if items[item_id].type is item_type
        )


class EquipmentManager:
    """Управление износом снаряжения. (§11.8)"""

    GEAR_DAMAGE_RANGE = (2, 8)  # стартовое значение износа оружия после боя

    @staticmethod
    def apply_weapon_wear(
        weapon_condition: int,
        participated: bool,
        rng_value: float,
    ) -> EquipmentDamage:
        """
        Износ оружия активного участника боя. (§11.8)
        -2..8 единиц состояния.
        """
        if not participated:
            return EquipmentDamage(
                item_id=0, item_name="weapon",
                old_condition=weapon_condition, new_condition=weapon_condition,
            )

        old = weapon_condition
        damage = int(EquipmentManager.GEAR_DAMAGE_RANGE[0] +
                     (EquipmentManager.GEAR_DAMAGE_RANGE[1] - EquipmentManager.GEAR_DAMAGE_RANGE[0]) * rng_value)
        new = max(0, old - damage)
        destroyed = new <= 0

        return EquipmentDamage(
            item_id=0, item_name="weapon",
            old_condition=old, new_condition=new,
            destroyed=destroyed,
            original_damage=damage,
        )

    @staticmethod
    def apply_armor_damage(
        armor_condition: int,
        damage_received: float,
        rng_value: float,
    ) -> EquipmentDamage:
        """Износ защитного снаряжения при получении урона. (§11.8)"""
        old = armor_condition
        damage = max(1, int(damage_received * 0.1))  # 10% от урона
        new = max(0, old - damage)
        destroyed = new <= 0

        return EquipmentDamage(
            item_id=0, item_name="armor",
            old_condition=old, new_condition=new,
            destroyed=destroyed,
            original_damage=damage,
        )

    @staticmethod
    def check_value_damage(
        condition: int,
        received_damage: float,
        rng_value: float,
    ) -> tuple[bool, int]:
        """
        Шанс повредить переносимую ценность при сильном попадании. (§11.8)
        Возвращает (повреждено, новый_condition).
        """
        # При уроне > 15 — шанс повредить ценности
        if received_damage > 15 and rng_value < 0.15:
            value_damage = max(1, int(condition * 0.2))
            new_condition = max(0, condition - value_damage)
            return True, new_condition
        return False, condition

    @staticmethod
    def get_weapon_effectiveness(condition: int) -> float:
        """Эффективность оружия по состоянию. (§11.8)"""
        if condition <= 0:
            return 0.25  # сломанное — минимальный бонус
        return max(0.25, condition / 100.0)

    @staticmethod
    def get_armor_effectiveness(condition: int) -> float:
        """Эффективность брони по состоянию."""
        if condition <= 0:
            return 0.5
        return condition / 100.0

    @staticmethod
    def apply_corruption_on_consumption(
        items: list[dict],
    ) -> list[dict]:
        """
        При поедании трупа оставшееся снаряжение считается испорченным. (§11.8)
        """
        for item in items:
            item["condition"] = 0
            item["value"] = item.get("value", 0) * 0.1  # остаточная стоимость 10%
        return items
