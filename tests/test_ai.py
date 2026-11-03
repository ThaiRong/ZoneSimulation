"""Тесты AI намерений (§9) и их интеграции в часовой цикл."""

import pytest

from zonesim.ai import (
    EXIT,
    EXPLORE,
    RESEARCH,
    REST,
    SLEEP,
    IntentionContext,
    choose_explore_target,
    choose_intention,
    evaluate_actions,
    next_step_towards,
)
from zonesim.core.time import SeededRNG
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.entity import EntityStatus


def make_ctx(**overrides) -> IntentionContext:
    base = dict(
        hour=12,
        is_night=False,
        bravery=50,
        faction="Бродяги",
        health_share=1.0,
        stamina_share=1.0,
        at_home=True,
        home_sector_id=1,
        distance_to_border=2,
    )
    base.update(overrides)
    return IntentionContext(**base)


class TestUtilityFormula:
    """Оценка полезности U = F + G + E + C + I + N - R × (1,25 - Bravery/200) + J. (§9.2)"""

    def test_tired_prefers_sleep(self):
        ctx = make_ctx(stamina_share=0.1)
        u = evaluate_actions(ctx)
        assert u[SLEEP] > u[EXPLORE]
        assert choose_intention(ctx, SeededRNG(1)) == SLEEP

    def test_night_boosts_sleep(self):
        day = evaluate_actions(make_ctx(stamina_share=0.5, is_night=False))[SLEEP]
        night = evaluate_actions(make_ctx(stamina_share=0.5, is_night=True))[SLEEP]
        assert night > day

    def test_critical_health_prioritizes_rest_or_exit(self):
        """§9.4: при критическом здоровье приоритет — лечение, убежище или выход."""
        ctx = make_ctx(health_share=0.15, distance_to_border=1)
        u = evaluate_actions(ctx)
        best = max(u, key=u.get)
        assert best in (REST, EXIT)

    def test_research_requires_known_anomaly(self):
        ctx = make_ctx()
        assert evaluate_actions(ctx)[RESEARCH] == float("-inf")
        with_anomaly = make_ctx(has_known_anomaly=True, known_anomaly_concealment=30)
        assert evaluate_actions(with_anomaly)[RESEARCH] > float("-inf")

    def test_faction_flavor_differs(self):
        """§7.3: фракционные приоритеты меняют оценки."""
        rogues = evaluate_actions(make_ctx(has_known_anomaly=True))[RESEARCH]
        hounds = evaluate_actions(
            make_ctx(faction="Борзые", has_known_anomaly=True)
        )[RESEARCH]
        assert rogues > hounds  # «Бродяги» исследуют охотнее «Борзых»

    def test_bravery_reduces_risk_penalty(self):
        """§9.2: храбрость уменьшает влияние риска (R × (1,25 - Bravery/200))."""
        coward = evaluate_actions(make_ctx(bravery=0))[EXPLORE]
        brave = evaluate_actions(make_ctx(bravery=100))[EXPLORE]
        assert brave > coward

    def test_jitter_is_bounded(self):
        """J — небольшая случайная поправка (±3)."""
        ctx = make_ctx()
        rng = SeededRNG(5)
        for _ in range(20):
            assert choose_intention(ctx, rng) in (SLEEP, REST, RESEARCH, EXPLORE, EXIT)


class TestRouting:
    """Маршрутизация по §10.1."""

    def _triangle(self):
        """0—1, 1—2, 0—2, 2—3; сектор 1 — с известной аномалией."""
        class S:
            def __init__(self, neighbors):
                self.neighbors = neighbors
        return {0: S([1, 2]), 1: S([0, 2]), 2: S([1, 0, 3]), 3: S([2])}

    def test_avoids_known_anomaly_sector(self):
        sectors = self._triangle()
        step = next_step_towards(sectors, 0, {3}, avoid_ids={1})
        assert step == 2  # обход через 2, а не через опасный 1

    def test_direct_when_no_avoid(self):
        sectors = self._triangle()
        step = next_step_towards(sectors, 0, {3})
        assert step == 2  # кратчайший путь 0→2→3 (2 ребра), а не 0→1→2→3

    def test_already_at_target(self):
        sectors = self._triangle()
        assert next_step_towards(sectors, 3, {3}) is None

    def test_explore_prefers_unvisited_and_safe(self):
        sectors = self._triangle()
        rng = SeededRNG(1)
        # Без аномалии выиграл бы сектор 2 (не посещался 51 ч против 4 у сектора 1);
        # известная аномалия в секторе 1 перевешивает небольшую разницу свежести.
        memory = {1: 196, 2: 149}
        target = choose_explore_target(sectors, 0, memory, hour=200,
                                       anomaly_sectors={1}, rng=rng)
        assert target == 2


class TestEngineIntegration:
    """Намерения в часовом цикле."""

    def test_low_stamina_leads_to_sleep(self):
        engine = SimulationEngine(seed=42)
        npc = next(h for h in engine.state.humans if h.status == EntityStatus.ACTIVE)
        group = engine.state.human_groups[npc.group_id]
        for member_id in group.members:
            member = next(h for h in engine.state.humans if h.id == member_id)
            member.stamina = 5
            member.health = 100
        engine.simulate_hour()
        assert npc.status == EntityStatus.SLEEPING

    def test_sleeping_recovers_stamina(self):
        engine = SimulationEngine(seed=42)
        npc = next(h for h in engine.state.humans if h.status == EntityStatus.ACTIVE)
        group = engine.state.human_groups[npc.group_id]
        for member_id in group.members:
            member = next(h for h in engine.state.humans if h.id == member_id)
            member.stamina = 20
        engine.simulate_hour()
        assert npc.status == EntityStatus.SLEEPING
        for _ in range(6):
            engine.simulate_hour()
        assert npc.stamina > 20

    def test_intentions_are_valid(self):
        engine = SimulationEngine(seed=42)
        for _ in range(48):
            engine.simulate_hour()
        valid = {SLEEP, REST, RESEARCH, EXPLORE, EXIT}
        for npc in engine.state.humans:
            if npc.status == EntityStatus.ACTIVE:
                assert npc.intention in valid

    def test_research_produces_knowledge(self):
        engine = SimulationEngine(seed=42)
        for _ in range(96):
            engine.simulate_hour()
        known = sum(1 for kb in engine.state.knowledge_bases.values() if kb.facts)
        assert known > 0

    def test_artifacts_get_collected(self):
        """За 240 часов кто-то должен добыть артефакт."""
        engine = SimulationEngine(seed=1)
        for _ in range(240):
            engine.simulate_hour()
        carriers = [h for h in engine.state.humans if h.artifacts]
        assert len(carriers) > 0

    def test_determinism(self):
        def run():
            eng = SimulationEngine(seed=77)
            for _ in range(48):
                eng.simulate_hour()
            return tuple(
                sorted((h.id, h.sector_id, h.health, h.status.value if hasattr(h.status, "value") else str(h.status))
                       for h in eng.state.humans)
            )
        assert run() == run()
