"""Проверки боевой петли §11 и её подключения к фазам 6–7."""

from zonesim.combat import CombatSystem
from zonesim.combat.base import Combatant
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.entity import EntityStatus


class TestCombatLoop:
    def test_combat_is_limited_to_ten_rounds(self):
        attacker = Combatant(
            1, "A", True, attack=1, defense=100, health=1000, max_health=1000,
            bravery=100, ammo=20, weapon_damage=1,
        )
        defender = Combatant(
            2, "D", True, attack=1, defense=100, health=1000, max_health=1000,
            bravery=100, ammo=20, weapon_damage=1,
        )
        result = CombatSystem([attacker], [defender], max_rounds=999).fight(lambda: 0.5)

        assert result.rounds_fought == 10
        assert result.outcome == "draw"

    def test_human_can_retreat_before_first_round_with_bonus(self):
        attacker = Combatant(1, "A", True, health=10, bravery=0, ammo=5)
        defender = Combatant(2, "D", True, attack=100, ammo=5)
        sector = type("Sector", (), {"neighbors": [1]})()

        result = CombatSystem(
            [attacker], [defender], sectors={0: sector}, battle_sector_id=0,
        ).fight(lambda: 0.5)

        assert result.outcome == "attacker_retreated"
        assert result.rounds_fought == 0
        assert result.attacker_retreat_sector == 1
        assert attacker.health == 10
        assert attacker.ammo == 5
        assert result.equipment_wear == []
        retreat = next(entry for entry in result.battle_log if entry["type"] == "retreat")
        assert retreat["round"] == 0
        assert retreat["pre_combat"] is True
        assert retreat["chance"] == 65

    def test_monster_cannot_retreat_before_first_round(self):
        attacker = Combatant(
            1, "M", False, attack=1, health=10, bravery=0, species="TerritorialPredator",
        )
        defender = Combatant(
            2, "D", True, attack=1, defense=100, health=1000, max_health=1000,
            bravery=100, ammo=20, weapon_damage=1,
        )
        sector = type("Sector", (), {"neighbors": [1]})()

        result = CombatSystem(
            [attacker], [defender], sectors={0: sector}, battle_sector_id=0,
        ).fight(lambda: 0.0)

        assert result.rounds_fought >= 1
        assert not any(
            entry.get("type") == "retreat" and entry["round"] == 0
            for entry in result.battle_log
        )

    def test_defender_win_is_reported(self):
        attacker = Combatant(1, "A", True, attack=1, health=1, max_health=100, bravery=100)
        defender = Combatant(
            2, "D", True, attack=100, health=100, weapon_damage=100, ammo=10,
        )
        result = CombatSystem([attacker], [defender]).fight(lambda: 0.1)

        assert result.outcome == "defender_wins"
        assert result.attacker_dead == [1]
        assert result.defender_survivors == [2]

    def test_retreat_requires_available_sector(self):
        attacker = Combatant(1, "A", True, health=10, bravery=0)
        defender = Combatant(2, "D", True, attack=100, ammo=10)
        result = CombatSystem([attacker], [defender]).fight(lambda: 0.4)

        assert result.attacker_retreat_sector is None
        assert result.outcome != "attacker_retreated"


class TestEngineCombat:
    def _isolate_encounter(self, engine, at_base=False):
        group = next(g for g in engine.state.human_groups.values() if g.member_count == 1)
        humans = {npc.id: npc for npc in engine.state.humans}
        npc = humans[group.members[0]]
        home = engine._home_sector_id(npc.faction)
        sector_id = home if at_base else next(
            sid for sid, sector in engine.state.sectors.items()
            if not sector.is_faction_start and sector.neighbors
        )
        for other in engine.state.humans:
            if other.id != npc.id:
                other.status = EntityStatus.DEAD
        engine._sync_human_groups()
        group = engine.state.human_groups[group.id]
        group.sector_id = sector_id
        npc.sector_id = sector_id
        npc.status = EntityStatus.ACTIVE
        npc.health = 20 if at_base else 1
        npc.stamina = 100
        npc.ammo = 10

        monster = engine.state.monsters[0]
        for other in engine.state.monsters:
            if other.id != monster.id:
                other.status = EntityStatus.DEAD
        monster.species = "LargeMigrator"
        monster.sector_id = sector_id
        monster.status = EntityStatus.ACTIVE
        monster.health = 100
        monster.attack = 70
        engine.state.anomalies = {}
        engine._sync_monster_groups()
        engine._moved_human_ids = set()
        engine.state.rng.random = lambda: 0.0
        return npc, monster

    def test_monster_encounter_executes_in_phase_seven(self):
        engine = SimulationEngine(seed=42)
        npc, monster = self._isolate_encounter(engine)
        engine.state.sectors[npc.sector_id].neighbors = []

        engine._phase6_detections(engine.state.time.hour)
        assert len(engine._pending_battles) == 1
        engine._phase7_actions(engine.state.time.hour, is_night=False)

        battles = [e for e in engine.state.news_manager.events if e.event_type == "combat"]
        assert len(battles) == 1
        assert battles[0].details["rounds"] <= 10
        assert npc.id in engine._combat_human_ids
        assert monster.id in engine._combat_monster_ids
        assert npc.health <= 1
        assert engine.state.corpses

    def test_base_guards_join_without_trader(self):
        engine = SimulationEngine(seed=42)
        npc, _monster = self._isolate_encounter(engine, at_base=True)

        engine._phase6_detections(engine.state.time.hour)

        assert len(engine._pending_battles) == 1
        defenders = engine._pending_battles[0]["defenders"]
        guards = [entity for entity in defenders if getattr(entity, "stationary_role", None) == "guard"]
        traders = [entity for entity in defenders if getattr(entity, "stationary_role", None) == "trader"]
        assert len(guards) == 2
        assert not traders
        assert all(guard.sector_id == npc.sector_id for guard in guards)
