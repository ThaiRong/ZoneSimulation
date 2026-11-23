"""Баланс: детектор аномалий, обнаружение монстрами, помощь и лечение группы."""

import pytest

from zonesim.ai import REST, IntentionContext, evaluate_actions
from zonesim.anomalies.core import Anomaly, AnomalyStatus, AnomalyType
from zonesim.combat import CombatSystem
from zonesim.combat.base import Combatant
from zonesim.simulation.engine import SimulationEngine
from zonesim.simulation.phases import run_phase6_detections
from zonesim.world.entity import EntityStatus, Monster, MonsterSpecies
from zonesim.world.item import ItemType, give_item

from tests.test_actions_integration import _solo_group
from tests.test_rest_trade import _trader_sector


def _give_item(engine, npc, item_ref):
    item = engine.catalog.create_item(engine.state.next_item_id, item_ref)
    engine.state.next_item_id += 1
    engine.state.items[item.id] = item
    give_item(item, npc.id, npc.inventory)
    return item


def _ctx(**overrides):
    base = dict(
        hour=12, is_night=False, bravery=50, faction="Бродяги",
        health_share=1.0, stamina_share=1.0,
        at_home=True, home_sector_id=1, distance_to_border=2,
    )
    base.update(overrides)
    return IntentionContext(**base)


class TestAnomalyDetector:
    def test_detector_in_catalog_and_stock(self):
        engine = SimulationEngine(seed=42)
        trader = _trader_sector(engine)
        assert engine.state.trader_stock[trader.id]["gear.detector.radar1"] == 2

    def test_detector_raises_avoid_chance(self):
        """С детектором группы NPC избегает контакта, без него — получает урон."""
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        sector_id = next(
            sid for sid, s in engine.state.sectors.items()
            if s.neighbors and not s.is_faction_start
            and all(t.sector_id != sid for t in engine.state.stationary_humans)
        )
        group.sector_id = sector_id
        npc.sector_id = sector_id
        engine.state.anomalies = {}
        anomaly = Anomaly(
            id=engine.state.next_anomaly_id, sector_id=sector_id,
            anomaly_type=AnomalyType.VISIBLE, concealment=50,
            damage_min=10, damage_max=20,
        )
        engine.state.next_anomaly_id += 1
        engine.state.anomalies[anomaly.id] = anomaly
        engine._moved_human_ids = {npc.id}
        npc.health = 1000
        npc.attentiveness = 50
        hour = engine.state.time.hour
        # без детектора: avoid = 50 + 0.7×(50−50) = 50; бросок 50 → попадание
        engine.state.rng.random = lambda: 0.5
        run_phase6_detections(engine.context)
        assert npc.health < 1000

    def test_detector_group_member_avoids(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        sector_id = next(
            sid for sid, s in engine.state.sectors.items()
            if s.neighbors and not s.is_faction_start
            and all(t.sector_id != sid for t in engine.state.stationary_humans)
        )
        group.sector_id = sector_id
        npc.sector_id = sector_id
        _give_item(engine, npc, "gear.detector.radar1")
        engine.state.anomalies = {}
        anomaly = Anomaly(
            id=engine.state.next_anomaly_id, sector_id=sector_id,
            anomaly_type=AnomalyType.VISIBLE, concealment=50,
            damage_min=10, damage_max=20,
        )
        engine.state.next_anomaly_id += 1
        engine.state.anomalies[anomaly.id] = anomaly
        engine._moved_human_ids = {npc.id}
        npc.health = 1000
        npc.attentiveness = 50
        hour = engine.state.time.hour
        # с детектором: avoid = 50 + 25 = 75; бросок 50 → избежал
        engine.state.rng.random = lambda: 0.5
        run_phase6_detections(engine.context)
        assert npc.health == 1000


class TestMonsterAnomalySense:
    def _setup(self, engine, species):
        monster = Monster(
            id=900001, species=species, sector_id=5,
            health=100, max_health=100, attentiveness=50,
        )
        engine.state.monsters.append(monster)
        for other in engine.state.monsters:
            if other.id != monster.id:
                other.status = EntityStatus.DEAD
        engine._sync_monster_groups()
        engine.state.anomalies = {}
        anomaly = Anomaly(
            id=engine.state.next_anomaly_id, sector_id=5,
            anomaly_type=AnomalyType.VISIBLE, concealment=50,
            damage_min=10, damage_max=20,
        )
        engine.state.next_anomaly_id += 1
        engine.state.anomalies[anomaly.id] = anomaly
        engine._moved_monster_ids = {monster.id}
        engine.state.rng.random = lambda: 0.5
        return monster

    def test_native_species_sense_anomalies(self):
        """Территориальный хищник (+25) избегает; бросок 50 < 75."""
        engine = SimulationEngine(seed=42)
        monster = self._setup(engine, MonsterSpecies.TERRITORIAL_PREDATOR)
        engine._check_monster_anomaly_contacts(engine.state.time.hour, is_night=False)
        assert monster.health == 100

    def test_large_migrator_has_no_bonus(self):
        engine = SimulationEngine(seed=42)
        monster = self._setup(engine, MonsterSpecies.LARGE_MIGRATOR)
        engine._check_monster_anomaly_contacts(engine.state.time.hour, is_night=False)
        assert monster.health < 100


class TestRestHealing:
    def test_each_wounded_member_heals_per_rest_hour(self):
        engine = SimulationEngine(seed=42)
        npc_a, group = _solo_group(engine)
        npc_b = engine.state.humans[1]
        npc_b.status = EntityStatus.ACTIVE
        group.members.append(npc_b.id)
        group.sector_id = npc_a.sector_id
        npc_b.sector_id = npc_a.sector_id
        npc_b.group_id = group.id
        npc_b.inventory = list(npc_a.inventory)
        npc_a.inventory = []
        npc_a.health = 40
        npc_b.health = 50
        hour = engine.state.time.hour

        engine._process_rest_trade(hour, [group])

        assert npc_a.health == 70  # 40 + 30
        assert npc_b.health == 80  # 50 + 30, второй заряд той же аптечки

    def test_rest_intention_pulls_below_sixty_health(self):
        u = evaluate_actions(_ctx(can_rest=True, health_share=0.5, stamina_share=1.0))
        assert u[REST] > float("-inf")
        healthy = evaluate_actions(_ctx(can_rest=True, health_share=0.9, stamina_share=1.0))
        assert u[REST] > healthy[REST]


class TestGroupAid:
    def test_group_medkit_revives_unconscious(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        medic = engine.state.humans[1]
        medic.status = EntityStatus.ACTIVE
        group.members.append(medic.id)
        medic.group_id = group.id
        medic.sector_id = npc.sector_id
        medic.inventory = list(npc.inventory)  # аптечка у медика
        npc.inventory = []
        npc.health = 0
        npc.status = EntityStatus.UNCONSCIOUS
        npc.unconscious_reason = "health_zero"
        npc.unconscious_start_hour = engine.state.time.hour - 2

        engine._unconscious_tick(npc, engine.state.time.hour)

        assert npc.status == EntityStatus.ACTIVE
        assert 0 < npc.health <= 60
        medkits = [
            engine.state.items[i] for i in medic.inventory
            if i in engine.state.items and engine.state.items[i].type is ItemType.MEDICINE
        ]
        assert not medkits or all(m.quantity == 1 for m in medkits)  # заряд израсходован

    def test_unconscious_without_help_dies(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        npc.inventory = []  # нет медикаментов ни у кого в одиночной группе
        npc.health = 0
        npc.status = EntityStatus.UNCONSCIOUS
        npc.unconscious_reason = "health_zero"
        npc.unconscious_start_hour = engine.state.time.hour - 2

        engine._unconscious_tick(npc, engine.state.time.hour)

        assert npc.status == EntityStatus.DEAD


class TestExecutionIntent:
    def _battle(self, attacker, defender, relation):
        sector = type("Sector", (), {"neighbors": []})()  # отступление невозможно
        system = CombatSystem(
            [attacker], [defender], sectors={0: sector}, battle_sector_id=0,
            relation=relation,
        )
        return system.fight(lambda: 0.1)

    def test_monster_winners_execute(self):
        human = Combatant(1, "H", True, attack=1, health=30, max_health=100, bravery=100, ammo=5)
        monster = Combatant(2, "M", False, attack=100, health=500, max_health=500, weapon_damage=40)
        result = self._battle(human, monster, relation=0)
        assert result.attacker_dead == [1]  # добит несмотря на медикаменты

    def test_human_winners_spare_with_medicines(self):
        weak = Combatant(1, "W", True, attack=1, health=10, max_health=100, bravery=100,
                         ammo=0, medicines=1)
        strong = Combatant(2, "S", True, attack=100, health=1000, max_health=1000,
                           bravery=100, ammo=10, weapon_damage=50)
        result = self._battle(weak, strong, relation=0)
        assert result.attacker_dead == []
        assert result.defender_dead == []
