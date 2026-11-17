"""Интеграционные проверки разрушения аномалий, захвата монстров и торговли."""

import pytest

from zonesim.ai import CAPTURE, DESTROY, IntentionContext, evaluate_actions
from zonesim.anomalies.artifact import Artifact
from zonesim.anomalies.core import Anomaly, AnomalyStatus, AnomalyType
from zonesim.economy.trade import CaptureManager
from zonesim.persistence.serialization import state_to_dict
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.entity import EntityStatus, Monster, MonsterSpecies
from zonesim.world.group import HumanGroup
from zonesim.world.item import ItemType, give_item


def _ctx(**overrides):
    base = {
        "hour": 10, "is_night": False, "bravery": 50, "faction": "Борзые",
        "health_share": 1.0, "stamina_share": 1.0,
        "at_home": False, "home_sector_id": None, "distance_to_border": 3,
    }
    base.update(overrides)
    return IntentionContext(**base)


def _solo_group(engine):
    """Одна одиночная человеческая группа, остальные мобильные убиты."""
    npc = engine.state.humans[0]
    for other in engine.state.humans:
        if other.id != npc.id:
            other.status = EntityStatus.DEAD
    engine._sync_human_groups()
    engine.state.human_groups = {}
    group = HumanGroup(
        id=engine.state.next_group_id,
        members=[npc.id],
        sector_id=npc.sector_id,
        leader_id=npc.id,
    )
    engine.state.next_group_id += 1
    engine.state.human_groups[group.id] = group
    npc.group_id = group.id
    npc.status = EntityStatus.ACTIVE
    return npc, group


def _clear_monsters(engine, keep=None):
    for monster in engine.state.monsters:
        if keep is None or monster.id != keep.id:
            monster.status = EntityStatus.DEAD
    engine._sync_monster_groups()


def _give_kit(engine, npc, item_ref):
    item = engine.catalog.create_item(engine.state.next_item_id, item_ref)
    engine.state.next_item_id += 1
    engine.state.items[item.id] = item
    give_item(item, npc.id, npc.inventory)
    return item


def _add_anomaly(engine, sector_id, anomaly_type=AnomalyType.VISIBLE, stability=60):
    anomaly = Anomaly(
        id=engine.state.next_anomaly_id,
        sector_id=sector_id,
        anomaly_type=anomaly_type,
        stability=stability,
    )
    engine.state.next_anomaly_id += 1
    engine.state.anomalies = {anomaly.id: anomaly}
    return anomaly


class TestIntentionsGating:
    def test_destroy_capture_gated_by_opportunity(self):
        u = evaluate_actions(_ctx(can_destroy=True, can_capture=True))
        assert u[DESTROY] > float("-inf")
        assert u[CAPTURE] > float("-inf")
        u = evaluate_actions(_ctx())
        assert u[DESTROY] == float("-inf")
        assert u[CAPTURE] == float("-inf")


class TestDestroyPrerequisites:
    def test_can_destroy_requires_matching_kit_and_anomaly(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        sector_id = group.sector_id
        anomaly = _add_anomaly(engine, sector_id, AnomalyType.VISIBLE)
        assert not engine._group_can_destroy(group, [npc])
        kit = _give_kit(engine, npc, "anomaly.kit.subtle")
        assert not engine._group_can_destroy(group, [npc])  # несовпадение типа
        kit.properties["target_anomaly_type"] = "visible"
        assert engine._group_can_destroy(group, [npc])
        kit.condition = 0
        assert not engine._group_can_destroy(group, [npc])
        kit.condition = 100
        anomaly.status = AnomalyStatus.DESTROYED
        assert not engine._group_can_destroy(group, [npc])


class TestDestroyAction:
    def test_destroy_damages_anomaly_and_wears_kit(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        anomaly = _add_anomaly(engine, group.sector_id, stability=60)
        kit = _give_kit(engine, npc, "anomaly.kit.visible")
        engine.state.rng.random = lambda: 0.9
        hour = engine.state.time.hour

        done = engine._process_destroy_anomaly(group, hour, is_night=False)

        assert done
        assert 0 < anomaly.stability < 60
        assert kit.condition == 75
        events = [e for e in engine.state.news_manager.events if e.event_type == "anomaly_destroyed"]
        assert len(events) == 1
        assert events[0].result == "damaged"

    def test_destroy_completes_and_yields_parts_and_artifact(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        anomaly = _add_anomaly(engine, group.sector_id, stability=5)
        _give_kit(engine, npc, "anomaly.kit.visible")
        engine.state.artifacts.artifacts.append(
            Artifact(id=0, anomaly_id=anomaly.id, rarity="rare", value=500.0)
        )
        engine.state.rng.random = lambda: 0.9
        npc.health = 1000

        done = engine._process_destroy_anomaly(group, engine.state.time.hour, is_night=False)

        assert done
        assert anomaly.status == AnomalyStatus.DESTROYED
        parts = [
            engine.state.items[item_id] for item_id in npc.inventory
            if engine.state.items[item_id].type is ItemType.ANOMALY_PART
        ]
        assert len(parts) == 2
        assert all(p.properties["source_anomaly_id"] == anomaly.id for p in parts)
        artifacts = [
            engine.state.items[item_id] for item_id in npc.inventory
            if engine.state.items[item_id].type is ItemType.ARTIFACT
        ]
        assert len(artifacts) == 1
        assert npc.artifacts == [0]
        events = [e for e in engine.state.news_manager.events if e.event_type == "anomaly_destroyed"]
        assert events[0].result == "destroyed"
        assert events[0].importance == 50


class TestCapturePrerequisites:
    def _setup(self, engine, monster_health=25):
        npc, group = _solo_group(engine)
        monster = Monster(
            id=900001,
            species=MonsterSpecies.LARGE_MIGRATOR,
            sector_id=group.sector_id,
            health=monster_health,
            max_health=100,
        )
        engine.state.monsters.append(monster)
        _clear_monsters(engine, keep=monster)
        return npc, group, monster

    def test_can_capture_requires_wounded_target_and_kit(self):
        engine = SimulationEngine(seed=42)
        npc, group, monster = self._setup(engine, monster_health=80)
        assert not engine._group_can_capture(group, [npc])  # цель не ранена
        monster.health = 25
        assert not engine._group_can_capture(group, [npc])  # нет комплекта
        kit = _give_kit(engine, npc, "capture.kit.scavenger")
        assert not engine._group_can_capture(group, [npc])  # несовпадение вида
        kit.properties["target_species"] = "large_migrator"
        assert engine._group_can_capture(group, [npc])
        # активное сопротивление другого монстра рядом
        other = Monster(
            id=900002,
            species=MonsterSpecies.SCAVENGER_PACK,
            sector_id=group.sector_id,
            health=100,
            max_health=100,
        )
        engine.state.monsters.append(other)
        engine._sync_monster_groups()
        assert not engine._group_can_capture(group, [npc])

    def test_capture_success_removes_monster_from_population(self):
        engine = SimulationEngine(seed=42)
        npc, group, monster = self._setup(engine)
        _give_kit(engine, npc, "capture.kit.migrator")
        engine.state.rng.random = lambda: 0.0

        done = engine._process_capture_monster(group, engine.state.time.hour)

        assert done
        assert monster.status == EntityStatus.EXILED
        assert monster.group_id is None
        live = [
            engine.state.items[item_id] for item_id in npc.inventory
            if engine.state.items[item_id].type is ItemType.LIVE_MONSTER
        ]
        assert len(live) == 1
        assert live[0].properties["species"] == "large_migrator"
        assert live[0].properties["source_monster_id"] == monster.id
        engine._sync_monster_groups()
        assert all(monster.id not in g.members for g in engine.state.monster_groups.values())
        events = [e for e in engine.state.news_manager.events if e.event_type == "monster_captured"]
        assert events[0].result == "captured"

    def test_capture_failure_damages_kit_and_counterattacks(self, monkeypatch):
        engine = SimulationEngine(seed=42)
        npc, group, monster = self._setup(engine)
        kit = _give_kit(engine, npc, "capture.kit.migrator")
        npc.health = 1000
        monkeypatch.setattr(CaptureManager, "resolve_capture", staticmethod(lambda *a: False))
        engine.state.rng.random = lambda: 0.0  # ветка контратаки

        done = engine._process_capture_monster(group, engine.state.time.hour)

        assert done
        assert 70 <= kit.condition <= 90  # износ 10–30 за попытку
        expected = max(5, round(monster.attack * 0.5))
        assert npc.health == 1000 - expected
        assert monster.status == EntityStatus.ACTIVE  # не пойман
        events = [e for e in engine.state.news_manager.events if e.event_type == "monster_captured"]
        assert events[0].result == "failed"
        assert events[0].details["outcome"] == "counterattack"


class TestTrading:
    def test_trader_stock_initialized_from_catalog(self):
        engine = SimulationEngine(seed=42)
        traders = [
            npc for npc in engine.state.stationary_humans
            if npc.stationary_role == "trader"
        ]
        assert traders
        for trader in traders:
            stock = engine.state.trader_stock[trader.id]
            assert stock["capture.kit.predator"] == 2
            assert stock["anomaly.kit.visible"] == 2
            assert stock["gear.medkit.sanitar2"] == 4
            assert stock["weapon.carbine.k20"] == 2
            assert stock["gear.detector.radar1"] == 2
            # отечественные позиции не импортируются
            assert "armor.uniform.jacket" not in stock
            assert "ammo.rifle" in stock

    def test_group_buys_missing_medkit_from_trader(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        trader = next(
            npc for npc in engine.state.stationary_humans
            if npc.stationary_role == "trader"
        )
        group.sector_id = trader.sector_id
        npc.sector_id = trader.sector_id
        # убираем стартовую аптечку
        for item_id in list(npc.inventory):
            item = engine.state.items[item_id]
            if item.type is ItemType.MEDICINE:
                npc.inventory.remove(item_id)
                engine.state.items.pop(item_id)
        npc.money = 500.0
        stock_before = engine.state.trader_stock[trader.id]["gear.medkit.sanitar2"]
        price_before = engine.trade_price("gear.medkit.sanitar2")  # цена ДО покупки

        engine._process_rest_trade(engine.state.time.hour, [group])

        # Проверяем что куплен только медикит (не detector!)
        medkits = [
            engine.state.items[item_id] for item_id in npc.inventory
            if engine.state.items[item_id].type is ItemType.MEDICINE
        ]
        detectors = [
            engine.state.items[item_id] for item_id in npc.inventory
            if engine.state.items[item_id].type is ItemType.DETECTOR
        ]
        assert len(medkits) == 1, f"Expected 1 medkit, got {len(medkits)}"
        assert len(detectors) == 0, f"Expected 0 detectors, got {len(detectors)}"
        assert npc.money == pytest.approx(500.0 - price_before)
        assert trader.money == pytest.approx(100.0 + price_before)
        assert engine.state.trader_stock[trader.id]["gear.medkit.sanitar2"] == stock_before - 1

    def test_group_sells_loot_to_trader(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        trader = next(
            npc for npc in engine.state.stationary_humans
            if npc.stationary_role == "trader"
        )
        group.sector_id = trader.sector_id
        npc.sector_id = trader.sector_id
        artifact = engine._create_item(ItemType.ARTIFACT, "Артефакт", 500.0, npc.id)
        npc.money = 0.0

        engine._process_rest_trade(engine.state.time.hour, [group])

        assert npc.money == pytest.approx(300.0)  # 500 × 0.6
        assert artifact.id not in engine.state.items
        assert artifact.id not in npc.inventory

    def test_save_load_preserves_trader_stock_and_continuation(self, tmp_path):
        original = SimulationEngine(seed=7, save_directory=tmp_path)
        for _ in range(6):
            original.simulate_hour()
        original.save("manual")
        restored = SimulationEngine.load("manual", tmp_path)
        assert restored.state.trader_stock == original.state.trader_stock
        assert state_to_dict(restored.state) == state_to_dict(original.state)
        for _ in range(4):
            original.simulate_hour()
            restored.simulate_hour()
            assert state_to_dict(restored.state) == state_to_dict(original.state)
