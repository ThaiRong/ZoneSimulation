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
    items: list[dict] = field(default_factory=list)
    monster_parts: list[dict] = field(default_factory=list)
    status: str = "available"  # available, looted, consumed
    consumed_by: int | None = None
    consumed_hour: int | None = None

    @property
    def is_human(self) -> bool:
        return self.original_entity_type == "human"

    def get_total_loot_value(self) -> int:
        return sum(item.get("value", 0) for item in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "original_entity_id": self.original_entity_id,
            "original_entity_type": self.original_entity_type,
            "sector_id": self.sector_id,
            "created_hour": self.created_hour,
            "items": self.items,
            "monster_parts": self.monster_parts,
            "status": self.status,
        }


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
