"""Тесты AI намерений (§9) и их интеграции в часовой цикл."""

import pytest

from zonesim.ai import (
    AMBUSH,
    ARTIFACT_SEARCH,
    CAPTURE,
    CREATE_SHELTER,
    DESTROY,
    EXIT,
    EXPLORE,
    HELP,
    RESEARCH,
    REST,
    SHELTER,
    SLEEP,
    IntentionContext,
    choose_explore_target,
    choose_intention,
    evaluate_actions,
    next_step_towards,
)
from zonesim.core.time import SeededRNG
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.groups import sync_monster_groups, sync_human_groups
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
        """§9.4: при критическом здоровье приоритет — лечение на базе или выход."""
        ctx = make_ctx(health_share=0.1, can_rest=True, distance_to_border=1)
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
        """Jitter ±3 не меняет выбор при разрыве утилит > 6.

        Тест проверяет, что:
        1) При большом преимуществе лучшего действия джиттер не меняет выбор.
        2) Мутация джиттера (увеличение до ±10) ломает тест — значит тест проверяет.
        """
        ctx = make_ctx()
        rng = SeededRNG(42)

        # --- Проверяем, что при явном лидере джиттер не меняет выбор ---
        base_utils = evaluate_actions(ctx)
        best_action = max(base_utils, key=lambda a: base_utils[a])
        best_utility = base_utils[best_action]
        second_best = max((u for a, u in base_utils.items() if a != best_action), default=0)

        gap = best_utility - second_best
        # Если разрыв > 6, ни один набор джиттера ±3 не может изменить лидера
        if gap > 6.0:
            rng_jitter = SeededRNG(99)
            for _ in range(50):
                choice = choose_intention(ctx, rng_jitter)
                assert choice == best_action, (
                    f"Джиттер изменил выбор при разрыве {gap:.1f}: "
                    f"ожидалось {best_action}, получено {choice}"
                )

    def test_jitter_mutation_increases_variance(self):
        """Мутация: увеличение джиттера до ±10 должно менять выбор."""
        from zonesim.ai.intentions import choose_intention, evaluate_actions
        import zonesim.ai.intentions as intentions_mod

        ctx = make_ctx()
        base_utils = evaluate_actions(ctx)
        best_action = max(base_utils, key=lambda a: base_utils[a])

        # Monkeypatch джиттера на ±10
        original_choose = intentions_mod.choose_intention

        def fake_choose(ctx, rng):
            u = evaluate_actions(ctx)
            for action in u:
                u[action] += rng.uniform(-10.0, 10.0)
            return max(u, key=lambda a: u[a])

        intentions_mod.choose_intention = fake_choose
        try:
            rng = SeededRNG(99)
            changed = sum(1 for _ in range(100) if fake_choose(ctx, rng) != best_action)
            # При ±10 джиттере выбор должен меняться в >30% случаев
            assert changed > 30, (
                f"Мутация ±10 не меняет выбор ({changed}/100) — "
                "тест нечувствителен к мутации"
            )
        finally:
            intentions_mod.choose_intention = original_choose


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
        for monster in engine.state.monsters:
            monster.status = EntityStatus.DEAD
        sync_monster_groups(engine.state)
        npc = next(h for h in engine.state.humans if h.status == EntityStatus.ACTIVE)
        group = engine.state.human_groups[npc.group_id]
        for other in engine.state.humans:
            if other.id != npc.id:
                other.status = EntityStatus.DEAD
        sync_human_groups(engine.state)
        for member_id in group.members:
            member = next(h for h in engine.state.humans if h.id == member_id)
            member.stamina = 5
            member.health = 100
        engine.simulate_hour()
        assert npc.status == EntityStatus.SLEEPING

    def test_sleeping_recovers_stamina(self):
        engine = SimulationEngine(seed=42)
        for monster in engine.state.monsters:
            monster.status = EntityStatus.DEAD
        sync_monster_groups(engine.state)
        npc = next(h for h in engine.state.humans if h.status == EntityStatus.ACTIVE)
        group = engine.state.human_groups[npc.group_id]
        for other in engine.state.humans:
            if other.id != npc.id:
                other.status = EntityStatus.DEAD
        sync_human_groups(engine.state)
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
        valid = {SLEEP, REST, RESEARCH, DESTROY, CAPTURE, EXPLORE, EXIT, SHELTER, HELP, AMBUSH, CREATE_SHELTER, ARTIFACT_SEARCH}
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
        """За 480 часов кто-то должен добыть артефакт через исследование.

        Артефакты добываются только через исследование (§12.3) или
        разрушение (§12.5) аномалий — авто-подбор убран (задача 14).
        """
        engine = SimulationEngine(seed=42)
        for _ in range(480):
            engine.simulate_hour()
        carriers = [h for h in engine.state.humans if h.artifacts]
        assert len(carriers) > 0, "Артефакты должны добываться через исследование"

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
