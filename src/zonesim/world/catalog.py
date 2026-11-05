"""Каталог предметов MVP: загрузка, проверка и создание экземпляров.

Соответствует «Каталог предметов MVP»: предметы — данные конфигурации (JSON),
а не код. Числовые параметры моделей живут в файле каталога.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from zonesim.world.item import Item, ItemType

CATEGORY_TO_ITEM_TYPE = {
    "weapon": ItemType.WEAPON,
    "ammo": ItemType.AMMO,
    "body_armor": ItemType.ARMOR,
    "head_armor": ItemType.ARMOR,
    "outer_layer": ItemType.ARMOR,
    "medical": ItemType.MEDICINE,
    "optics": ItemType.OPTICS,
    "capture_kit": ItemType.CAPTURE_KIT,
    "anomaly_destruction_kit": ItemType.DESTROY_KIT,
}

COMMON_REQUIRED = (
    "id", "name", "category", "slot", "quality", "base_value",
    "durability_max", "durability_loss", "import_required", "tags",
)

FAMILY_REQUIRED = {
    "weapon": ("base_damage", "weapon_factor", "ammo_per_round"),
    "body_armor": ("armor_factor", "damage_reduction"),
    "head_armor": ("armor_factor", "damage_reduction"),
    "outer_layer": ("armor_factor", "damage_reduction"),
    "medical": ("charges", "heal_amount"),
    "optics": ("attentiveness_bonus",),
    "capture_kit": ("target_species", "capture_bonus", "danger_rank", "uses"),
    "anomaly_destruction_kit": (
        "target_anomaly_type", "stability_damage", "danger_rank", "uses",
    ),
}

QUALITY_MULTIPLIERS = (0.90, 1.00, 1.15, 1.30)


class CatalogError(Exception):
    """Ошибка загрузки или проверки каталога предметов."""


def _validate_entry(entry: dict[str, Any]) -> None:
    missing = [field for field in COMMON_REQUIRED if field not in entry]
    if missing:
        raise CatalogError(f"предмет {entry.get('id', '?')}: отсутствуют поля {missing}")
    if not isinstance(entry["id"], str) or not entry["id"]:
        raise CatalogError("id предмета должен быть непустой строкой")
    if entry["category"] not in CATEGORY_TO_ITEM_TYPE:
        raise CatalogError(f"предмет {entry['id']}: неизвестная категория {entry['category']}")
    if not isinstance(entry["base_value"], (int, float)) or entry["base_value"] < 0:
        raise CatalogError(f"предмет {entry['id']}: базовая цена должна быть неотрицательным числом")
    quality = entry.get("quality", 1.0)
    if quality not in QUALITY_MULTIPLIERS:
        raise CatalogError(
            f"предмет {entry['id']}: качество {quality} вне допустимых {QUALITY_MULTIPLIERS}"
        )
    family_missing = [
        field for field in FAMILY_REQUIRED.get(entry["category"], ())
        if field not in entry
    ]
    if family_missing:
        raise CatalogError(
            f"предмет {entry['id']}: отсутствуют поля семейства {family_missing}"
        )
    if entry["category"] == "weapon":
        ammo_type = entry.get("ammo_type")
        if ammo_type is not None and not str(ammo_type).startswith("ammo."):
            raise CatalogError(f"предмет {entry['id']}: неверный тип патронов {ammo_type}")


class ItemCatalog:
    """Загруженный каталог: поиск моделей и создание экземпляров предметов."""

    def __init__(self, entries: dict[str, dict[str, Any]]):
        self._entries = entries

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ItemCatalog":
        """Загружает каталог из файла; без пути — встроенный каталог пакета."""
        if path is None:
            text = (
                resources.files("zonesim.data")
                .joinpath("items.json")
                .read_text(encoding="utf-8")
            )
        else:
            text = Path(path).read_text(encoding="utf-8")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CatalogError(f"неверный JSON каталога: {exc}") from exc
        items = raw["items"] if isinstance(raw, dict) else raw
        if not isinstance(items, list) or not items:
            raise CatalogError("каталог должен содержать непустой список items")

        entries: dict[str, dict[str, Any]] = {}
        for entry in items:
            if not isinstance(entry, dict):
                raise CatalogError("запись каталога должна быть объектом")
            _validate_entry(entry)
            if entry["id"] in entries:
                raise CatalogError(f"дубликат id предмета {entry['id']}")
            entries[entry["id"]] = entry
        return cls(entries)

    def __contains__(self, item_id: str) -> bool:
        return item_id in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> list[dict[str, Any]]:
        """Все записи каталога (для инициализации запасов торговцев)."""
        return list(self._entries.values())

    def get(self, item_id: str) -> dict[str, Any]:
        if item_id not in self._entries:
            raise CatalogError(f"предмет {item_id} отсутствует в каталоге")
        return self._entries[item_id]

    def create_item(
        self,
        numeric_id: int,
        item_id: str,
        condition: int = 100,
        quantity: int = 1,
    ) -> Item:
        """Создаёт экземпляр предмета по модели каталога.

        Свойства модели копируются в properties экземпляра, чтобы механики
        читали параметры из предмета, а не ходили в каталог.
        """
        entry = self.get(item_id)
        properties = {
            key: value
            for key, value in entry.items()
            if key not in ("id", "name", "base_value")
        }
        return Item(
            id=numeric_id,
            type=CATEGORY_TO_ITEM_TYPE[entry["category"]],
            name=entry["name"],
            condition=condition if entry["durability_max"] else 100,
            base_value=entry["base_value"],
            quantity=quantity,
            properties=properties,
        )


__all__ = ["CatalogError", "ItemCatalog"]
