"""Охрана баз: лучшее снаряжение бесплатно, ротация при тяжёлых ранениях."""

import pytest

from zonesim.simulation.engine import SimulationEngine
from zonesim.world.entity import EntityStatus
from zonesim.world.item import ItemType


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
