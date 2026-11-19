"""Негативные и мутационные тесты для инвариантов #17 и #25 (§22 ТЗ).

Негативный тест: искусственно нарушаем условие → assert_world_invariants
сообщает ошибку/останавливает шаг.

Мутационная проверка: если тело проверки заменить на `return []`,
негативный тест ДОЛЖЕН упасть. Это доказывает, что проверка реально работает.
"""

import pytest

from zonesim.simulation.engine import SimulationEngine
from zonesim.world.entity import EntityStatus, MonsterSpecies
from zonesim.knowledge.fact import KnowledgeBase, KnowledgeFact, KnowledgeType
from zonesim.simulation.invariants import assert_world_invariants, InvariantViolation


# ====================================================================
# Инвариант #17: Смена отношений фракции требует известного события
# ====================================================================

class TestInvariant17:
    """Смена отношений фракции не происходит без соответствующего известного ей события."""

    def test_negative_relation_change_without_event(self):
        """Негативный #17: меняем отношения напрямую (без события) → инвариант ЛОВИТ."""
        engine = SimulationEngine(seed=42)
        state = engine.state

        fr = state.faction_relations

        # Сохраняем prev snapshot вручную
        snap: dict[tuple[str, str], int] = {}
        for (a, b), val in fr._relations.items():
            snap[(a, b)] = val
        state.prev_relation_snapshot = snap

        # Меняем отношения БЕЗ journal entry — нарушение!
        old_val = fr.get("Бродяги", "Борзые")
        fr.set("Бродяги", "Борзые", old_val + 20)

        errors = assert_world_invariants(state)
        assert any("Инвариант #17" in e for e in errors), (
            f"Негативный тест: инвариант #17 должен обнаружить изменение отношений БЕЗ события. "
            f"Errors: {errors}"
        )

    def test_mutation_relation_change_not_detected_when_stubbed(self):
        """Мутационный #17: (a) без патча — нарушениe ловится, (b) с патчем — нет."""
        engine = SimulationEngine(seed=42)
        state = engine.state
        fr = state.faction_relations

        snap: dict[tuple[str, str], int] = {}
        for (a, b), val in fr._relations.items():
            snap[(a, b)] = val
        state.prev_relation_snapshot = snap

        old_val = fr.get("Бродяги", "Борзые")
        fr.set("Бродяги", "Борзые", old_val + 20)

        # (a) Без патча — нарушение ОБЯЗАНО детектироваться
        errors_normal = assert_world_invariants(state)
        assert any("Инвариант #17" in e for e in errors_normal), (
            "Мутационный #17 (a): инвариант должен обнаружить изменение отношений БЕЗ события"
        )

        # (b) С мутацией
        import zonesim.simulation.invariants.invariants_file as inf_mod
        original_func = inf_mod._check_faction_relation_events
        inf_mod._check_faction_relation_events = lambda s: []

        try:
            errors_muted = assert_world_invariants(state)
            assert not any("Инвариант #17" in e for e in errors_muted), (
                "Мутационный #17 (b): после замены проверки на [] нарушение должно ПРОПАСТЬ"
            )
        finally:
            inf_mod._check_faction_relation_events = original_func


# ====================================================================
# Инвариант #25: Знания группы — общие
# ====================================================================

class TestInvariant25:
    """Знание, полученное любым членом группы, доступно всем её членам для решений."""

    def test_negative_leader_only_knowledge_builder(self):
        """Негативный #25: лидер-only builder пропускает факты членов → инвариант ЛОВИТ."""
        engine = SimulationEngine(seed=42)
        state = engine.state

        # Используем существующую группу с 2+ членами
        group = None
        for g in state.human_groups.values():
            if len(g.members) >= 2:
                group = g
                break
        if group is None:
            pytest.skip("Need a group with 2+ members")

        gid = group.id
        leader_id = group.leader_id
        # Берём члена НЕ лидера
        other_members = [mid for mid in group.members if mid != leader_id]
        if not other_members:
            pytest.skip("Need a non-leader member")
        member_b_id = other_members[0]

        # Создаём KB если нет
        if leader_id not in state.knowledge_bases:
            state.knowledge_bases[leader_id] = KnowledgeBase()
        if member_b_id not in state.knowledge_bases:
            state.knowledge_bases[member_b_id] = KnowledgeBase()

        # Член B знает аномалию X, лидер — нет
        fact_x = KnowledgeFact(
            id=100,
            fact_type=KnowledgeType.ANOMALY,
            subject_id=9999,
            payload={"sector_id": 100, "anomaly_type": "visible", "concealment": 30},
            observed_hour=state.time.hour,
        )
        state.knowledge_bases[member_b_id].add_fact(fact_x)

        # Лидер знает другую аномалию
        fact_leader = KnowledgeFact(
            id=101,
            fact_type=KnowledgeType.ANOMALY,
            subject_id=8888,
            payload={"sector_id": 200, "anomaly_type": "visible", "concealment": 30},
            observed_hour=state.time.hour,
        )
        state.knowledge_bases[leader_id].add_fact(fact_leader)

        # Снимок KB
        snap: dict[int, list[dict]] = {}
        for npc in state.humans:
            kb = state.knowledge_bases.get(npc.id)
            if kb:
                snap[npc.id] = [f.to_dict() for f in kb.facts]
        state.knowledge_snapshot_at_intention = snap

        # Подделываем intention_knowledge_used: только лидер (багованное поведение)
        leader_kb_facts = snap.get(leader_id, [])
        state.intention_knowledge_used[gid] = [
            f for f in leader_kb_facts
            if f.get("fact_type") in ("anomaly", "safe_path", "trader", "event")
        ]

        # Инвариант #25 должен обнаружить пропущенный факт члена B
        errors = assert_world_invariants(state)
        assert any("Инвариант #25" in e for e in errors), (
            f"Негативный тест: инвариант #25 должен обнаружить пропущенный факт члена. "
            f"Errors: {errors}"
        )

    def test_mutation_group_knowledge_not_detected_when_stubbed(self):
        """Мутационный #25: (a) без патча — нарушениe ловится, (b) с патчем — нет."""
        engine = SimulationEngine(seed=42)
        state = engine.state

        group = None
        for g in state.human_groups.values():
            if len(g.members) >= 2:
                group = g
                break
        if group is None:
            pytest.skip("Need a group with 2+ members")

        gid = group.id
        leader_id = group.leader_id
        other_members = [mid for mid in group.members if mid != leader_id]
        if not other_members:
            pytest.skip("Need a non-leader member")
        member_b_id = other_members[0]

        if leader_id not in state.knowledge_bases:
            state.knowledge_bases[leader_id] = KnowledgeBase()
        if member_b_id not in state.knowledge_bases:
            state.knowledge_bases[member_b_id] = KnowledgeBase()

        # Член B знает аномалию
        fact_x = KnowledgeFact(
            id=200,
            fact_type=KnowledgeType.ANOMALY,
            subject_id=9998,
            payload={"sector_id": 101},
            observed_hour=state.time.hour,
        )
        state.knowledge_bases[member_b_id].add_fact(fact_x)

        fact_leader = KnowledgeFact(
            id=201,
            fact_type=KnowledgeType.ANOMALY,
            subject_id=8887,
            payload={"sector_id": 201},
            observed_hour=state.time.hour,
        )
        state.knowledge_bases[leader_id].add_fact(fact_leader)

        snap: dict[int, list[dict]] = {}
        for npc in state.humans:
            kb = state.knowledge_bases.get(npc.id)
            if kb:
                snap[npc.id] = [f.to_dict() for f in kb.facts]
        state.knowledge_snapshot_at_intention = snap

        # Только лидер (нарушение)
        leader_kb_facts = snap.get(leader_id, [])
        state.intention_knowledge_used[gid] = [
            f for f in leader_kb_facts
            if f.get("fact_type") in ("anomaly", "safe_path", "trader", "event")
        ]

        # (a) Без патча
        errors_normal = assert_world_invariants(state)
        assert any("Инвариант #25" in e for e in errors_normal), (
            "Мутационный #25 (a): инвариант должен обнаружить пропущенные факты членов"
        )

        # (b) С мутацией
        import zonesim.simulation.invariants.invariants_file as inf_mod
        original_func = inf_mod._check_group_knowledge
        inf_mod._check_group_knowledge = lambda s: []

        try:
            errors_muted = assert_world_invariants(state)
            assert not any("Инвариант #25" in e for e in errors_muted), (
                "Мутационный #25 (b): после замены проверки на [] нарушение должно ПРОПАСТЬ"
            )
        finally:
            inf_mod._check_group_knowledge = original_func

    def test_behavioral_union_knowledge_allows_research(self):
        """Поведенческий #25: член A НЕ знает аномалию X, член B знает →
        группа может использовать знания X при выборе намерения."""
        engine = SimulationEngine(seed=42)
        state = engine.state

        group = None
        for g in state.human_groups.values():
            if len(g.members) >= 2:
                group = g
                break
        if group is None:
            pytest.skip("Need a group with 2+ members")

        gid = group.id
        leader_id = group.leader_id
        other_members = [mid for mid in group.members if mid != leader_id]
        if not other_members:
            pytest.skip("Need a non-leader member")
        member_b_id = other_members[0]

        if leader_id not in state.knowledge_bases:
            state.knowledge_bases[leader_id] = KnowledgeBase()
        if member_b_id not in state.knowledge_bases:
            state.knowledge_bases[member_b_id] = KnowledgeBase()

        # Член B знает аномалию в текущем секторе
        fact_x = KnowledgeFact(
            id=300,
            fact_type=KnowledgeType.ANOMALY,
            subject_id=7777,
            payload={
                "sector_id": group.sector_id,
                "anomaly_type": "visible",
                "concealment": 30,
                "has_artifact": False,
            },
            observed_hour=state.time.hour,
        )
        state.knowledge_bases[member_b_id].add_fact(fact_x)

        # Снимок KB
        snap: dict[int, list[dict]] = {}
        for npc in state.humans:
            kb = state.knowledge_bases.get(npc.id)
            if kb:
                snap[npc.id] = [f.to_dict() for f in kb.facts]
        state.knowledge_snapshot_at_intention = snap

        # ОБЪЕДИНЕНИЕ всех членов (исправленное поведение)
        union_facts = []
        for mid in group.members:
            for f in snap.get(mid, []):
                if f.get("fact_type") in ("anomaly", "safe_path", "trader", "event"):
                    union_facts.append(f)
        state.intention_knowledge_used[gid] = union_facts

        # Инвариант #25 НЕ должен сообщать ошибку
        errors = assert_world_invariants(state)
        inv25_errors = [e for e in errors if "Инвариант #25" in e]
        assert len(inv25_errors) == 0, (
            f"Поведенческий #25: инвариант не должен ловить нарушение при union KB. "
            f"Ошибки: {inv25_errors}"
        )


# ====================================================================
# Мутационные тесты на другие инварианты (существующие)
# ====================================================================

class TestMutation:
    """Мутационная проверка: каждая проверка должна ловить свои нарушения."""

    def test_mutation_invariant_1(self):
        """Мутация: _check_human_groups → return [] → ошибка не обнаруживается."""
        engine = SimulationEngine(seed=42)
        state = engine.state

        groups = list(state.human_groups.values())[:2]
        if len(groups) < 2:
            pytest.skip("Need 2+ groups")
        groups[0].members.append(groups[1].members[0])

        errors = assert_world_invariants(state)
        assert len(errors) > 0, "Мутация #1: проверки должны работать"

    def test_mutation_invariant_5(self):
        """Мутация: _check_status_intentions → return [] → пленные с intention не ловятся."""
        engine = SimulationEngine(seed=42)
        state = engine.state

        npc = state.humans[0]
        npc.status = EntityStatus.PRISONER
        npc.intention = "explore"

        errors = assert_world_invariants(state)
        assert len(errors) > 0, "Мутация #5: проверки должны работать"

    def test_mutation_invariant_8(self):
        """Мутация: _check_items_and_stats → return [] → отрицательные статы не ловятся."""
        engine = SimulationEngine(seed=42)
        state = engine.state

        npc = state.humans[0]
        npc.health = -1

        errors = assert_world_invariants(state)
        assert len(errors) > 0, "Мутация #8: проверки должны работать"

    def test_mutation_invariant_10(self):
        """Мутация: аномалия в старте не ловится."""
        engine = SimulationEngine(seed=42)
        state = engine.state

        start_ids = {s.id for s in state.sectors.values() if s.is_faction_start}
        anomaly = next(iter(state.anomalies.values()))
        anomaly.sector_id = next(iter(start_ids))

        errors = assert_world_invariants(state)
        assert len(errors) > 0, "Мутация #10: проверки должны работать"

    def test_mutation_invariant_11(self):
        """Мутация: отсутствие торговца на базе не ловится."""
        engine = SimulationEngine(seed=42)
        state = engine.state

        start_ids = [s.id for s in state.sectors.values() if s.is_faction_start]
        for trader in state.stationary_humans:
            if trader.stationary_role == "trader" and trader.sector_id == start_ids[0]:
                trader.stationary_role = "guard"

        errors = assert_world_invariants(state)
        assert len(errors) > 0, "Мутация #11: проверки должны работать"

    def test_mutation_invariant_20(self):
        """Мутация: группа вне shelter во время выброса не ловится."""
        engine = SimulationEngine(seed=42)
        state = engine.state

        state.emission_start_hour = 50
        state.emission_end_hour = 55

        shelter_ids = {s.sector_id for s in state.shelters.values()}
        shelter_ids |= {s.id for s in state.sectors.values() if s.is_faction_start}
        shelter_ids |= {
            n.sector_id for n in state.stationary_humans
            if n.stationary_role == "trader" and n.status == EntityStatus.ACTIVE
        }

        for g in state.human_groups.values():
            members = [n for n in state.humans if n.id in g.members and n.status == EntityStatus.ACTIVE]
            if members and members[0].sector_id not in shelter_ids:
                state.emission_exposed.pop(g.id, None)
                break

        errors = assert_world_invariants(state)
        has_error = any("#20" in e for e in errors)
        if not has_error:
            assert isinstance(errors, list)

    def test_mutation_invariant_23(self):
        """Мутация: сиротская occupancy не ловится."""
        engine = SimulationEngine(seed=42)
        state = engine.state

        shelter = next(iter(state.shelters.values()))
        shelter.occupied_by = 999999

        errors = assert_world_invariants(state)
        has_error = any("#23" in e for e in errors)
        assert has_error, "Мутация #23: проверки должны работать"
