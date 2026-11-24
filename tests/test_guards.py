"""Охрана баз: лучшее снаряжение бесплатно, ротация при тяжёлых ранениях."""

import pytest

from zonesim.simulation.engine import SimulationEngine
from zonesim.simulation.phases import run_phase7_actions
from zonesim.world.entity import EntityStatus
from zonesim.world.item import ItemType
from zonesim.combat.power import squad_power


def _guards(engine):
    return [n for n in engine.state.stationary_humans if n.stationary_role == "guard"]


class TestGuardEquipment:
    def test_guards_have_best_weapon_and_armor(self):
        engine = SimulationEngine(seed=42)
        best_damage = max(
            e["base_damage"] for e in engine.catalog.entries()
            if e["category"] == "weapon"
        )
        best_armor = max(
            e["armor_factor"] for e in engine.catalog.entries()
            if e["category"] == "body_armor"
        )
        guards = _guards(engine)
        assert guards
        for guard in guards:
            weapon = engine.state.items[guard.equipped_weapon_id]
            armor = engine.state.items[guard.equipped_armor_id]
            assert weapon.properties["base_damage"] == best_damage
            assert armor.properties["armor_factor"] == pytest.approx(best_armor)

    def test_guards_get_ammo_and_medkits_for_free(self):
        engine = SimulationEngine(seed=42)
        for guard in _guards(engine):
            ammo = sum(
                engine.state.items[i].quantity for i in guard.inventory
                if i in engine.state.items
                and engine.state.items[i].type is ItemType.AMMO
            )
            medkits = sum(
                engine.state.items[i].properties.get("charges", 0)
                for i in guard.inventory
                if i in engine.state.items
                and engine.state.items[i].type is ItemType.MEDICINE
            )
            assert ammo >= 60
            assert medkits >= 6  # три аптечки по два заряда
            assert guard.money == 100  # снаряжение бесплатно

    def test_traders_keep_standard_equipment(self):
        engine = SimulationEngine(seed=42)
        trader = next(
            n for n in engine.state.stationary_humans
            if n.stationary_role == "trader"
        )
        weapon = engine.state.items[trader.equipped_weapon_id]
        assert weapon.properties["base_damage"] != 30  # не «Сокол» охраны


class TestGuardRotation:
    def test_wounded_guard_replaced_by_reserve(self):
        engine = SimulationEngine(seed=42)
        guard = _guards(engine)[0]
        guard.health = int(guard.max_health * 0.3)
        sector_before = guard.sector_id

        engine._process_guard_rotation(hour=24)

        assert guard.on_treatment
        assert guard.status == EntityStatus.SLEEPING
        reserves = [
            n for n in engine.state.stationary_humans
            if getattr(n, "reserve_for", None) == guard.id
        ]
        assert len(reserves) == 1
        reserve = reserves[0]
        assert reserve.status == EntityStatus.ACTIVE
        assert reserve.sector_id == sector_before
        # резервист тоже получает полное снаряжение охраны
        weapon = engine.state.items[reserve.equipped_weapon_id]
        assert weapon.properties["base_damage"] == 30

    def test_healthy_guard_not_replaced(self):
        engine = SimulationEngine(seed=42)
        engine._process_guard_rotation(hour=24)
        assert not any(getattr(n, "on_treatment", False) for n in _guards(engine))
        assert not any(
            getattr(n, "reserve_for", None) is not None
            for n in engine.state.stationary_humans
        )

    def test_guard_returns_and_reserve_leaves_after_recovery(self):
        engine = SimulationEngine(seed=42)
        guard = _guards(engine)[0]
        guard.health = int(guard.max_health * 0.3)
        engine._process_guard_rotation(hour=24)
        reserve = next(
            n for n in engine.state.stationary_humans
            if getattr(n, "reserve_for", None) == guard.id
        )
        # лазарет лечит 50% в сутки: два дня до полного восстановления
        engine._process_guard_rotation(hour=48)
        assert guard.on_treatment  # ещё лечится
        engine._process_guard_rotation(hour=72)
        assert not guard.on_treatment
        assert guard.status == EntityStatus.ACTIVE
        assert reserve.status == EntityStatus.EXILED  # резервист убыл

    def test_no_second_reserve_for_same_guard(self):
        engine = SimulationEngine(seed=42)
        guard = _guards(engine)[0]
        guard.health = int(guard.max_health * 0.3)
        engine._process_guard_rotation(hour=24)
        engine._process_guard_rotation(hour=48)  # пока лечится
        reserves = [
            n for n in engine.state.stationary_humans
            if getattr(n, "reserve_for", None) == guard.id
        ]
        assert len(reserves) == 1


class TestGuardReplenishment:
    def test_dead_guards_replaced_by_recruits(self):
        engine = SimulationEngine(seed=42)
        # убиваем всех охранников одной базы
        base_sector = next(
            s.id for s in engine.state.sectors.values() if s.is_faction_start
        )
        for guard in _guards(engine):
            if guard.sector_id == base_sector:
                guard.status = EntityStatus.DEAD
        alive_before = sum(
            1 for n in _guards(engine)
            if n.sector_id == base_sector and n.status == EntityStatus.ACTIVE
            and getattr(n, "reserve_for", None) is None
        )

        engine._process_guard_rotation(hour=24)

        assert alive_before < 2
        recruits = [
            n for n in engine.state.stationary_humans
            if n.stationary_role == "guard" and n.sector_id == base_sector
            and n.status == EntityStatus.ACTIVE and n.name == "Охранник-новобранец"
        ]
        assert len(recruits) == engine.GUARDS_PER_BASE - alive_before

    def test_treatment_guard_does_not_auto_wake(self):
        engine = SimulationEngine(seed=42)
        guard = _guards(engine)[0]
        guard.health = int(guard.max_health * 0.3)
        guard.stamina = guard.max_stamina
        engine._process_guard_rotation(hour=24)
        assert guard.status == EntityStatus.SLEEPING
        # час отдыха/сна не будит лечащегося охранника
        engine.context.hour = engine.state.time.hour
        engine.context.day = engine.state.time.day
        engine.context.is_night = False
        run_phase7_actions(engine.context)
        assert guard.status == EntityStatus.SLEEPING
        assert guard.on_treatment

    def test_base_defense_gets_fortification_bonus(self, monkeypatch):
        """Бой в секторе базы создаётся с бонусом укрепления 0.7."""
        import zonesim.simulation.engine as engine_module

        captured = {}
        class StubCombat:
            def __init__(self, attackers, defenders, **kwargs):
                self.attackers = attackers
                self.defenders = defenders
                captured.update(kwargs)
            def fight(self, rng):
                class Result:
                    outcome = "draw"
                    rounds_fought = 0
                    battle_log = []
                    attacker_dead = []
                    defender_dead = []
                    attacker_prisoners = []
                    defender_prisoners = []
                    attacker_retreat_sector = None
                    defender_retreat_sector = None
                    attacker_retreated = False
                    defender_retreated = False
                return Result()

        monkeypatch.setattr(engine_module, "CombatSystem", StubCombat)
        engine = SimulationEngine(seed=42)
        base_sector = next(s for s in engine.state.sectors.values() if s.is_faction_start)
        guard = next(
            n for n in engine.state.stationary_humans
            if n.stationary_role == "guard" and n.sector_id == base_sector.id
        )
        monster = next(m for m in engine.state.monsters if m.status.value == "Активен")
        monster_group = engine.state.monster_groups[monster.group_id]
        engine._schedule_monster_attack(
            monster_group, [monster], [guard], None, base_sector.id, False,
        )
        engine._execute_battles(engine.state.time.hour)
        assert captured["defender_has_shelter"] is True
        assert captured["defender_bonus"] == pytest.approx(0.7)

    def test_field_battle_has_no_shelter_bonus(self, monkeypatch):
        import zonesim.simulation.engine as engine_module

        captured = {}
        class StubCombat:
            def __init__(self, attackers, defenders, **kwargs):
                self.attackers = attackers
                self.defenders = defenders
                captured.update(kwargs)
            def fight(self, rng):
                class Result:
                    outcome = "draw"
                    rounds_fought = 0
                    battle_log = []
                    attacker_dead = []
                    defender_dead = []
                    attacker_prisoners = []
                    defender_prisoners = []
                    attacker_retreat_sector = None
                    defender_retreat_sector = None
                    attacker_retreated = False
                    defender_retreated = False
                return Result()

        monkeypatch.setattr(engine_module, "CombatSystem", StubCombat)
        engine = SimulationEngine(seed=42)
        open_sector = next(
            s for s in engine.state.sectors.values()
            if not s.is_faction_start
            and s.id not in {sh.sector_id for sh in engine.state.shelters.values()}
        )
        npc = engine.state.humans[0]
        monster = next(m for m in engine.state.monsters if m.status.value == "Активен")
        monster_group = engine.state.monster_groups[monster.group_id]
        engine._schedule_monster_attack(
            monster_group, [monster], [npc], None, open_sector.id, False,
        )
        engine._execute_battles(engine.state.time.hour)
        assert captured["defender_has_shelter"] is False


class TestMonsterAttackDecision:
    def _migrator(self, engine):
        from zonesim.world.entity import Monster, MonsterSpecies
        monster = Monster(
            id=900001, species=MonsterSpecies.LARGE_MIGRATOR,
            sector_id=1, health=100, max_health=100, attack=70,
        )
        engine.state.monsters.append(monster)
        for other in engine.state.monsters:
            if other.id != monster.id:
                other.status = EntityStatus.DEAD
        engine._sync_monster_groups()
        return monster

    def test_monster_avoids_fortified_garrison(self):
        """Полный гарнизон базы с укреплением — конечная сила выше предела."""
        engine = SimulationEngine(seed=42)
        monster = self._migrator(engine)
        base = next(s for s in engine.state.sectors.values() if s.is_faction_start)
        monster.sector_id = base.id
        garrison = [
            n for n in engine.state.stationary_humans
            if n.stationary_role == "guard" and n.sector_id == base.id
        ]
        assert len(garrison) == 4
        engine.state.rng.random = lambda: 0.0
        assert not engine._monsters_attack([monster], garrison, is_night=False)

    def test_monster_attacks_weakened_garrison(self):
        """Ослабленный гарнизон остаётся целью."""
        engine = SimulationEngine(seed=42)
        monster = self._migrator(engine)
        base = next(s for s in engine.state.sectors.values() if s.is_faction_start)
        monster.sector_id = base.id
        garrison = [
            n for n in engine.state.stationary_humans
            if n.stationary_role == "guard" and n.sector_id == base.id
        ]
        for guard in garrison[1:]:
            guard.status = EntityStatus.DEAD
        garrison[0].health = int(garrison[0].max_health * 0.4)
        engine.state.rng.random = lambda: 0.0
        assert engine._monsters_attack([monster], [garrison[0]], is_night=False)

    def test_squad_power_counts_equipment(self):
        """Конечная сила людей растёт от лучшего оружия."""
        engine = SimulationEngine(seed=42)
        npc = engine.state.humans[0]
        strong = squad_power([npc], engine.state.items)
        weapon = engine.state.items[npc.equipped_weapon_id]
        weapon.properties["base_damage"] = 5  # разоружить
        weak = squad_power([npc], engine.state.items)
        assert strong > weak * 2
