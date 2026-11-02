"""Тесты Фазы 7: отношения, развитие, новости (§14-15, §18 ТЗ)."""

import pytest
from zonesim.relations.personal import PersonalRelations, RelationState
from zonesim.relations.factions import FactionRelations
from zonesim.relations.development import (
    DevelopmentManager, StatType, PracticeProgress,
    ExileManager, FactionChangeManager, get_practice_rewards,
)
from zonesim.relations.news import NewsManager, WorldEvent
from zonesim.world.entity import HumanNPC, EntityStatus


# ==================== Personal Relations Tests ====================

class TestPersonalRelations:
    """Тесты личных отношений NPC (§15.1)."""

    def test_initial_neutral(self):
        pr = PersonalRelations()
        assert pr.get(1, 2) == 0
        assert pr.get_state(1, 2) == RelationState.NEUTRAL

    def test_change_relation(self):
        pr = PersonalRelations()
        pr.change(1, 2, 30)
        assert pr.get(1, 2) == 30
        assert pr.get_state(1, 2) == RelationState.ALLY

    def test_negative_relation(self):
        pr = PersonalRelations()
        pr.change(1, 2, -30)
        assert pr.get(1, 2) == -30
        assert pr.get_state(1, 2) == RelationState.ENEMY

    def test_clamped_at_100(self):
        pr = PersonalRelations()
        pr.change(1, 2, 150)
        assert pr.get(1, 2) == 100

    def test_clamped_at_negative_100(self):
        pr = PersonalRelations()
        pr.change(1, 2, -150)
        assert pr.get(1, 2) == -100

    def test_symmetric(self):
        pr = PersonalRelations()
        pr.change(1, 2, 25)
        assert pr.get(1, 2) == 25
        assert pr.get(2, 1) == 25

    def test_is_ally(self):
        pr = PersonalRelations()
        pr.change(1, 2, 50)
        assert pr.is_ally(1, 2) is True
        assert pr.is_enemy(1, 2) is False

    def test_is_enemy(self):
        pr = PersonalRelations()
        pr.change(1, 2, -50)
        assert pr.is_enemy(1, 2) is True
        assert pr.is_ally(1, 2) is False


# ==================== Faction Relations Tests ====================

class TestFactionRelations:
    """Тесты фракционных отношений (§15.2)."""

    def test_initial_relations(self):
        fr = FactionRelations()
        # Бродяги vs Борзые = -25
        assert fr.get("Бродяги", "Борзые") == -25
        # Бродяги vs Серая лига = +10
        assert fr.get("Бродяги", "Серая лига") == 10

    def test_symmetric(self):
        fr = FactionRelations()
        assert fr.get("Бродяги", "Борзые") == fr.get("Борзые", "Бродяги")

    def test_change_relation(self):
        fr = FactionRelations()
        fr.change("Бродяги", "Борзые", +40)
        # -25 + 40 = +15 → нейтралитет
        assert fr.get("Бродяги", "Борзые") == 15

    def test_clamped_at_100(self):
        fr = FactionRelations()
        fr.change("Бродяги", "Борзые", 200)
        assert fr.get("Бродяги", "Борзые") == 100

    def test_clamped_at_negative_100(self):
        fr = FactionRelations()
        fr.change("Бродяги", "Борзые", -200)
        assert fr.get("Бродяги", "Борзые") == -100

    def test_to_dict(self):
        fr = FactionRelations()
        d = fr.to_dict()
        assert "Бродяги→Борзые" in d
        assert d["Бродяги→Борзые"] == -25


# ==================== Development Tests ====================

class TestPracticeProgress:
    """Тесты прогресса практики (§14.5)."""

    def test_add_points(self):
        prog = PracticeProgress(StatType.ATTACK)
        prog.add_points(3.0)
        assert prog.practice_points == 3.0

    def test_grow_with_enough_points(self):
        prog = PracticeProgress(StatType.ATTACK, practice_points=5.0, last_growth_hour=0)
        new_val, grown = prog.try_grow(50, 100, current_hour=30, points_needed=5.0)
        assert new_val == 51
        assert grown is True

    def test_no_grow_not_enough_points(self):
        prog = PracticeProgress(StatType.ATTACK, practice_points=2.0, last_growth_hour=0)
        new_val, grown = prog.try_grow(50, 100, current_hour=30, points_needed=5.0)
        assert new_val == 50
        assert grown is False

    def test_no_grow_cooldown(self):
        prog = PracticeProgress(StatType.ATTACK, practice_points=5.0, last_growth_hour=10)
        new_val, grown = prog.try_grow(50, 100, current_hour=20, points_needed=5.0)
        # 20 - 10 = 10 < 24, cooldown
        assert new_val == 50
        assert grown is False

    def test_no_grow_at_max(self):
        prog = PracticeProgress(StatType.ATTACK, practice_points=5.0, last_growth_hour=0)
        new_val, grown = prog.try_grow(100, 100, current_hour=30, points_needed=5.0)
        assert new_val == 100
        assert grown is False


class TestDevelopmentManager:
    """Тесты менеджера развития."""

    def test_get_practice(self):
        dm = DevelopmentManager()
        prog = dm.get_progress(1, StatType.ATTACK)
        assert prog.stat_type == StatType.ATTACK

    def test_add_practice(self):
        dm = DevelopmentManager()
        dm.add_practice(1, StatType.ATTACK, 3.0, current_hour=10)
        prog = dm.get_progress(1, StatType.ATTACK)
        assert prog.practice_points == 3.0

    def test_grow_all_stats(self):
        dm = DevelopmentManager()
        npc = HumanNPC(id=1, faction="Бродяги", attack=50, defense=50,
                       stamina=50, attentiveness=50, bravery=50)
        dm.add_practice(1, StatType.ATTACK, 5.0, current_hour=0)

        results = dm.grow_all_stats(npc, current_hour=30)
        assert results[StatType.ATTACK.value] == (51, True)

    def test_reset_progress(self):
        dm = DevelopmentManager()
        dm.add_practice(1, StatType.ATTACK, 5.0, current_hour=0)
        dm.reset_progress(1)
        prog = dm.get_progress(1, StatType.ATTACK)
        assert prog.practice_points == 0.0


class TestExileManager:
    """Тесты выхода из Зоны (§14.6)."""

    def test_can_attempt_heavy_injury(self):
        em = ExileManager()
        npc = HumanNPC(id=1, faction="Бродяги", health=20)
        npc.status = EntityStatus.ACTIVE
        allowed, reason = em.can_attempt_exile(npc)
        assert allowed is True
        assert reason == "heavy_injury"

    def test_cannot_attempt_full_health(self):
        em = ExileManager()
        npc = HumanNPC(id=1, faction="Бродяги", health=100)
        npc.status = EntityStatus.ACTIVE
        allowed, reason = em.can_attempt_exile(npc)
        assert allowed is False

    def test_exile_success(self):
        em = ExileManager()
        npc = HumanNPC(id=1, faction="Бродяги", health=25)  # тяжелое состояние
        npc.status = EntityStatus.ACTIVE
        border = {5}
        npc.sector_id = 5

        import random
        rng = random.Random(1)  # seed для успеха (0.33 < 0.4)
        success, result = em.process_exile_attempt(npc, 5, border, rng)
        assert success is True
        assert result == "exiled"

    def test_exile_not_at_border(self):
        em = ExileManager()
        npc = HumanNPC(id=1, faction="Бродяги", health=20)
        npc.status = EntityStatus.ACTIVE
        border = {5}
        npc.sector_id = 10

        import random
        rng = random.Random(42)
        success, result = em.process_exile_attempt(npc, 10, border, rng)
        assert success is False
        assert result == "not_at_border"


class TestFactionChangeManager:
    """Тесты смены фракций (§14.7)."""

    def test_can_change_min_time(self):
        fcm = FactionChangeManager()
        npc = HumanNPC(id=1, faction="Бродяги")
        npc.last_faction_change = 0

        allowed, reason = fcm.can_change_faction(npc, "Борзые", 50, {})
        assert allowed is False
        assert reason == "cooldown"

    def test_can_change_allowed(self):
        fcm = FactionChangeManager()
        npc = HumanNPC(id=1, faction="Бродяги")
        npc.last_faction_change = 0
        npc.can_join = True

        allowed, reason = fcm.can_change_faction(npc, "Борзые", 100, {})
        assert allowed is True
        assert reason == "allowed"

    def test_cannot_change_hostile_faction(self):
        fcm = FactionChangeManager()
        npc = HumanNPC(id=1, faction="Бродяги")
        npc.last_faction_change = 0
        npc.can_join = True

        allowed, reason = fcm.can_change_faction(npc, "Борзые", 100,
                                                  {"Борзые": -60})
        assert allowed is False
        assert reason == "hostile_faction"

    def test_process_faction_change(self):
        fcm = FactionChangeManager()
        npc = HumanNPC(id=1, faction="Бродяги")

        result = fcm.process_faction_change(npc, "Борзые", current_hour=100)
        assert result is True
        assert npc.faction == "Борзые"
        assert npc.last_faction_change == 100


# ==================== Practice Rewards Tests ====================

class TestPracticeRewards:
    """Тесты наград за практику."""

    def test_combat_win_rewards(self):
        rewards = get_practice_rewards("combat_win", is_successful=True)
        assert StatType.ATTACK in rewards
        assert rewards[StatType.ATTACK] == 1.0

    def test_no_reward_if_failed(self):
        rewards = get_practice_rewards("combat_win", is_successful=False)
        assert len(rewards) == 0

    def test_unknown_action(self):
        rewards = get_practice_rewards("unknown_action")
        assert len(rewards) == 0


# ==================== News Manager Tests ====================

class TestNewsManager:
    """Тесты менеджера новостей (§18)."""

    def test_create_event(self):
        nm = NewsManager()
        event = nm.create_event(
            hour=10, minute=30, sector_id=5,
            event_type="combat", participants=[1, 2],
            result="success", importance=50,
            summary="Бой в секторе 5",
        )
        assert event.id == 0
        assert event.hour == 10

    def test_get_hourly_summary(self):
        nm = NewsManager()
        nm.create_event(10, 0, 1, "combat", [1], "success", 50, "Бой")
        nm.create_event(10, 30, 2, "trade", [3], "success", 10, "Торговля")

        summary = nm.get_hourly_summary(10)
        assert summary["total_events"] == 2
        assert len(summary["top_events"]) == 2

    def test_filter_by_type(self):
        nm = NewsManager()
        nm.create_event(10, 0, 1, "combat", [1], "success", 50, "Бой")
        nm.create_event(10, 30, 2, "trade", [3], "success", 10, "Торговля")

        combat_events = nm.filter_by_type("combat")
        assert len(combat_events) == 1

    def test_filter_by_importance(self):
        nm = NewsManager()
        nm.create_event(10, 0, 1, "low", [1], "success", 5, "Низкая")
        nm.create_event(10, 30, 2, "high", [3], "success", 75, "Высокая")

        high_events = nm.filter_by_importance(50)
        assert len(high_events) == 1
        assert high_events[0]["importance"] == 75

    def test_get_last_n(self):
        nm = NewsManager()
        for i in range(10):
            nm.create_event(i, 0, 0, "test", [], "success", 10, f"Event {i}")

        last_5 = nm.get_last_n(5)
        assert len(last_5) == 5

    def test_total_count(self):
        nm = NewsManager()
        nm.create_event(0, 0, 0, "test", [], "success", 10, "Test")
        assert nm.get_total_count() == 1

    def test_sector_events(self):
        nm = NewsManager()
        nm.create_event(10, 0, 5, "combat", [1], "success", 50, "Бой в 5")
        nm.create_event(10, 30, 3, "trade", [3], "success", 10, "Торговля в 3")

        sector_5 = nm.get_events_by_sector(5)
        assert len(sector_5) == 1
        assert sector_5[0]["sector_id"] == 5
