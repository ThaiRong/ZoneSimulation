"""Лечение на базе группировки и низкий приоритет выхода из Зоны."""

import pytest

from zonesim.ai import EXIT, REST, SLEEP, IntentionContext, evaluate_actions
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.entity import EntityStatus
from zonesim.world.faction import home_sector_id

from tests.test_actions_integration import _solo_group


def _ctx(**overrides):
    base = dict(
        hour=12, is_night=False, bravery=50, faction="Бродяги",
        health_share=1.0, stamina_share=1.0,
        at_home=True, home_sector_id=1, distance_to_border=2,
    )
    base.update(overrides)
    return IntentionContext(**base)


class TestBaseHealing:
    def _at_home(self, engine, npc, group):
        home = home_sector_id(engine.state.sectors, npc.faction, engine._home_cache)
        group.sector_id = home
        npc.sector_id = home
        return home

    def test_two_rest_hours_heal_to_full_for_half_medkit_price(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        self._at_home(engine, npc, group)
        npc.health = 20
        npc.money = 500.0
        cost = round(engine.trade_price("gear.medkit.sanitar2") / 2, 1)
        hour = engine.state.time.hour

        engine._rest_tick(npc)          # первый час: оплата курса + 50%
        assert npc.health == pytest.approx(70)
        assert npc.money == pytest.approx(500.0 - cost)

        engine.state.time.hour = hour + 1
        engine._rest_tick(npc)          # второй час: остаток до полного
        assert npc.health == npc.max_health
        assert npc.money == pytest.approx(500.0 - cost)  # без повторной оплаты

    def test_new_course_charges_again(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        self._at_home(engine, npc, group)
        npc.health = 10
        npc.money = 1000.0
        cost = round(engine.trade_price("gear.medkit.sanitar2") / 2, 1)
        hour = engine.state.time.hour

        engine._rest_tick(npc)
        npc.health = 30  # снова ранен после курса
        engine.state.time.hour = hour + 5  # курс уже истёк
        engine._rest_tick(npc)
        assert npc.money == pytest.approx(1000.0 - 2 * cost)

    def test_no_money_no_healing(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        self._at_home(engine, npc, group)
        npc.health = 20
        npc.money = 0.0
        engine._rest_tick(npc)
        assert npc.health == 20

    def test_healing_only_at_own_base(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        foreign = next(
            sid for sid, s in engine.state.sectors.items()
            if s.is_faction_start and s.controller_faction != npc.faction
        )
        group.sector_id = foreign
        npc.sector_id = foreign
        npc.health = 20
        npc.money = 500.0
        engine._rest_tick(npc)
        assert npc.health == 20

    def test_full_health_pays_nothing(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        self._at_home(engine, npc, group)
        npc.money = 100.0
        engine._rest_tick(npc)
        assert npc.money == 100.0


class TestExitLowestPriority:
    def test_exit_loses_to_idle_intentions(self):
        """Критическое здоровье, нет комфорта, день: EXIT не побеждает."""
        u = evaluate_actions(_ctx(health_share=0.1, can_rest=False))
        assert u[EXIT] < u[SLEEP]
        assert u[EXIT] < max(u.values())

    def test_rest_beats_exit_at_critical_health(self):
        u = evaluate_actions(_ctx(health_share=0.1, can_rest=True))
        assert u[REST] > u[EXIT]

    def test_exit_still_available(self):
        """EXIT остаётся в списке намерений (конечная опция)."""
        u = evaluate_actions(_ctx(health_share=0.05))
        assert u[EXIT] > float("-inf")
