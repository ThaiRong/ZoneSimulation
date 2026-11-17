"""Проверки каталога предметов MVP: загрузка, валидация, интеграция в движок."""

import json

import pytest

from zonesim.combat.loot import EquipmentManager
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.catalog import CatalogError, ItemCatalog
from zonesim.world.item import ItemType


class TestCatalogLoading:
    def test_default_catalog_has_all_mvp_items(self):
        catalog = ItemCatalog.load()
        assert len(catalog) >= 24
        for item_id in (
            "weapon.pistol.p9", "weapon.carbine.k20", "weapon.auto.serp",
            "weapon.rifle.sokol", "weapon.lmg.grad", "weapon.melee.klyk",
            "ammo.pistol", "ammo.rifle", "ammo.heavy",
            "armor.uniform.jacket", "armor.vest.reinforced", "armor.body.b2",
            "armor.outer.scout", "armor.head.light",
            "gear.medkit.sanitar2", "gear.optics.zritel3", "gear.detector.radar1",
            "capture.kit.predator", "capture.kit.scavenger", "capture.kit.migrator",
            "anomaly.kit.subtle", "anomaly.kit.visible", "anomaly.kit.large",
            "shelter.kit.basic",
        ):
            assert item_id in catalog

    def test_create_item_copies_model_into_instance(self):
        catalog = ItemCatalog.load()
        item = catalog.create_item(7, "weapon.carbine.k20")
        assert item.id == 7
        assert item.type is ItemType.WEAPON
        assert item.name == "Карабин К-20"
        assert item.base_value == 250
        assert item.properties["base_damage"] == 20
        assert item.properties["ammo_type"] == "ammo.rifle"
        assert item.properties["durability_loss"] == 2

    def test_create_item_ammo_is_resource(self):
        catalog = ItemCatalog.load()
        item = catalog.create_item(8, "ammo.rifle", quantity=12)
        assert item.type is ItemType.AMMO
        assert item.quantity == 12
        assert item.base_value == 2

    def test_kits_carry_family_properties(self):
        catalog = ItemCatalog.load()
        capture = catalog.create_item(9, "capture.kit.migrator")
        assert capture.type is ItemType.CAPTURE_KIT
        assert capture.properties["target_species"] == "large_migrator"
        assert capture.properties["capture_bonus"] == 15
        kit = catalog.create_item(10, "anomaly.kit.visible")
        assert kit.type is ItemType.DESTROY_KIT
        assert kit.properties["target_anomaly_type"] == "visible"
        assert kit.properties["stability_damage"] == 52

    def test_unknown_id_raises(self):
        catalog = ItemCatalog.load()
        with pytest.raises(CatalogError):
            catalog.create_item(1, "weapon.unknown")


class TestCatalogValidation:
    def _write_catalog(self, tmp_path, items):
        path = tmp_path / "catalog.json"
        path.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
        return path

    @staticmethod
    def _base_entry(**overrides):
        entry = {
            "id": "ammo.x", "name": "Патрон Икс", "category": "ammo", "slot": "ammo",
            "quality": 1.0, "base_value": 5,
            "durability_max": 0, "durability_loss": 0,
            "import_required": False, "tags": ["test"],
        }
        entry.update(overrides)
        return entry

    def test_duplicate_id_rejected(self, tmp_path):
        entry = self._base_entry()
        path = self._write_catalog(tmp_path, [entry, dict(entry)])
        with pytest.raises(CatalogError, match="дубликат"):
            ItemCatalog.load(path)

    def test_missing_family_field_rejected(self, tmp_path):
        entry = self._base_entry(
            id="weapon.x", name="Винтовка Икс", category="weapon", slot="weapon",
            base_value=100, ammo_type="ammo.rifle",
        )
        path = self._write_catalog(tmp_path, [entry])
        with pytest.raises(CatalogError, match="семейства"):
            ItemCatalog.load(path)

    def test_missing_common_field_rejected(self, tmp_path):
        entry = self._base_entry()
        del entry["quality"]
        path = self._write_catalog(tmp_path, [entry])
        with pytest.raises(CatalogError, match="отсутствуют поля"):
            ItemCatalog.load(path)

    def test_unknown_category_rejected(self, tmp_path):
        entry = self._base_entry(category="mystery")
        path = self._write_catalog(tmp_path, [entry])
        with pytest.raises(CatalogError, match="категория"):
            ItemCatalog.load(path)

    def test_negative_price_rejected(self, tmp_path):
        entry = self._base_entry(base_value=-5)
        path = self._write_catalog(tmp_path, [entry])
        with pytest.raises(CatalogError, match="цена"):
            ItemCatalog.load(path)

    def test_invalid_json_rejected(self, tmp_path):
        path = tmp_path / "catalog.json"
        path.write_text("{ не json", encoding="utf-8")
        with pytest.raises(CatalogError, match="JSON"):
            ItemCatalog.load(path)

    def test_custom_catalog_path_used_by_engine(self, tmp_path):
        catalog = ItemCatalog.load()
        entries = list(catalog._entries.values())
        entries.append({
            "id": "ammo.x", "name": "Патрон Икс", "category": "ammo", "slot": "ammo",
            "quality": 1.0, "base_value": 9,
            "durability_max": 0, "durability_loss": 0,
            "import_required": False, "tags": ["custom"],
        })
        path = self._write_catalog(tmp_path, entries)
        engine = SimulationEngine(seed=42, config={"catalog_path": str(path)})
        item = engine.catalog.create_item(1, "ammo.x")
        assert item.name == "Патрон Икс"


class TestEngineIntegration:
    def test_starting_equipment_comes_from_catalog(self):
        engine = SimulationEngine(seed=42)
        for npc in engine.state.humans:
            weapon = engine.state.items[npc.equipped_weapon_id]
            armor = engine.state.items[npc.equipped_armor_id]
            if npc.faction == "Серая лига":
                assert weapon.properties["base_damage"] == 30
                assert armor.properties["armor_factor"] == 1.05
            else:
                assert weapon.properties["base_damage"] == 20
                assert armor.properties["armor_factor"] == 1.02
            assert npc.weapon_damage == weapon.properties["base_damage"]
            assert npc.armor_value == pytest.approx(
                armor.properties["armor_factor"]
                * EquipmentManager.get_armor_effectiveness(armor.condition)
            )
            ammo_items = [
                engine.state.items[item_id] for item_id in npc.inventory
                if engine.state.items[item_id].type is ItemType.AMMO
            ]
            assert len(ammo_items) == 1
            assert ammo_items[0].quantity == 12
            assert ammo_items[0].properties["category"] == "ammo"
            assert engine.catalog.get(weapon.properties["ammo_type"])["name"] == ammo_items[0].name
            medkits = [
                engine.state.items[item_id] for item_id in npc.inventory
                if engine.state.items[item_id].type is ItemType.MEDICINE
            ]
            assert len(medkits) == 1
            assert medkits[0].properties["charges"] == 2

    def test_catalog_survives_save_load(self, tmp_path):
        engine = SimulationEngine(seed=3, save_directory=tmp_path)
        for _ in range(6):
            engine.simulate_hour()
        engine.save("manual")
        restored = SimulationEngine.load("manual", tmp_path)
        assert restored.catalog is not None
        assert "weapon.carbine.k20" in restored.catalog
