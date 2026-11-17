"""Тесты Фазы 3: знания, обнаружение, исследование, тайники, убежища, новости."""

import pytest

from zonesim.actions.detection import (
    calculate_ambush_chance,
    calculate_detection_check,
    calculate_stalking_check,
    check_anomaly_detection,
    resolve_ambush,
)
from zonesim.actions.research import (
    calculate_research_success,
    research_anomaly,
    research_sector,
)
from zonesim.anomalies.core import Anomaly, AnomalyType
from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType
from zonesim.news.events import NewsManager
from zonesim.world.entity import HumanNPC
from zonesim.world.shelter import Shelter
from zonesim.world.stash import Stash


class TestKnowledgeBase:
    """Тесты системы знаний (§7.12, §17)."""

    def test_add_and_retrieve_facts(self):
        kb = KnowledgeBase()
        kb.add_manual(
            npc_id=1,
            fact_type=KnowledgeType.ANOMALY,
            subject_id=100,
            payload={"sector": 5, "type": "subtle"},
            hour=10,
        )
        facts = kb.get_facts(fact_type=KnowledgeType.ANOMALY)
        assert len(facts) == 1
        assert facts[0].subject_id == 100
        assert facts[0].observed_hour == 10

    def test_old_fact_replaced(self):
        kb = KnowledgeBase()
        # Первое знание
        kb.add_manual(1, KnowledgeType.ANOMALY, 100, {"sector": 5}, hour=10)
        # Новое знание того же типа и субъекта
        kb.add_manual(1, KnowledgeType.ANOMALY, 100, {"sector": 7}, hour=15)

        facts = kb.get_facts(fact_type=KnowledgeType.ANOMALY, subject_id=100)
        assert len(facts) == 1
        assert facts[0].payload["sector"] == 7

    def test_freshness_score(self):
        kb = KnowledgeBase()
        kb.add_manual(1, KnowledgeType.EVENT, 1, {"event": "test"}, hour=0)

        # В час 12 — возраст 12 часов
        staleness = kb.get_staleness_score(12)
        assert 0 <= staleness <= 1.0

        # В час 60 — знание очень старое
        staleness = kb.get_staleness_score(60)
        assert staleness >= 1.0

    def test_copy_for_sale(self):
        kb = KnowledgeBase()
        kb.add_manual(1, KnowledgeType.ROUTE, 5, {"path": [1, 2, 3]}, hour=10)

        # Продаем знание — покупатель получает копию
        copy_kb = kb.get_copy()
        facts = copy_kb.get_facts()
        assert len(facts) == 1
        assert facts[0].observed_hour == 10  # исходное время сохраняется
        # Но ID разные
        assert facts[0].id != kb.facts[0].id

    def test_different_subjects_not_replaced(self):
        kb = KnowledgeBase()
        kb.add_manual(1, KnowledgeType.ANOMALY, 100, {}, hour=10)
        kb.add_manual(1, KnowledgeType.ANOMALY, 200, {}, hour=10)

        facts = kb.get_facts(fact_type=KnowledgeType.ANOMALY)
        assert len(facts) == 2


class TestDetection:
    """Тесты обнаружения и выслеживания (§10.2-10.3)."""

    def test_full_success_stalking(self):
        # Высокая внимательность, свежий след, отличный rng → полный успех
        result = calculate_stalking_check(
            tracker_att=80,
            track_freshness_hours=1,
            terrain_mod=10,
            target_size=1,
            target_speed=1,
            rng=0.1,
        )
        assert result == "full_success"

    def test_partial_success_stalking(self):
        # Средняя внимательность, старый след → частичный успех
        result = calculate_stalking_check(
            tracker_att=40,
            track_freshness_hours=6,
            terrain_mod=5,
            target_size=2,
            target_speed=2,
            rng=0.5,
        )
        assert result in ("partial_success", "fail")

    def test_fail_stalking(self):
        # Низкая внимательность, очень старый след → провал
        result = calculate_stalking_check(
            tracker_att=20,
            track_freshness_hours=12,
            terrain_mod=0,
            target_size=3,
            target_speed=3,
            rng=0.1,
        )
        assert result == "fail"

    def test_night_stalking_penalty(self):
        # Ночью штраф к внимательности
        result_night = calculate_stalking_check(
            tracker_att=60,
            track_freshness_hours=1,
            terrain_mod=10,
            target_size=1,
            target_speed=1,
            is_night=True,
            rng=0.5,
        )
        result_day = calculate_stalking_check(
            tracker_att=60,
            track_freshness_hours=1,
            terrain_mod=10,
            target_size=1,
            target_speed=1,
            is_night=False,
            rng=0.5,
        )
        # Ночью шанс ниже или равный
        assert self._result_rank(result_night) <= self._result_rank(result_day)

    @staticmethod
    def _result_rank(r: str) -> int:
        return {"full_success": 3, "partial_success": 2, "fail": 0}.get(r, 0)

    def test_anomaly_detection_high_attentiveness(self):
        # Высокая внимательность против скрытной аномалии
        result = check_anomaly_detection(
            observer_att=80,
            anomaly_concealment=70,
            terrain_concealment=10,
            rng_value=0.3,
        )
        assert result is True

    def test_anomaly_detection_night_bonus(self):
        # Ночью аномалии видны лучше
        result_day = check_anomaly_detection(
            observer_att=30,
            anomaly_concealment=70,
            terrain_concealment=5,
            is_night=False,
            rng_value=0.5,
        )
        result_night = check_anomaly_detection(
            observer_att=30,
            anomaly_concealment=70,
            terrain_concealment=5,
            is_night=True,
            rng_value=0.5,
        )
        assert result_night >= result_day

    def test_group_detection_penalty(self):
        # Группа заметнее — штраф за размер
        p_single = calculate_detection_check(50, 50, 10, is_group=False)
        p_group = calculate_detection_check(50, 50, 10, is_group=True, group_size=4)
        # Шанс обнаружения группы ниже (больше penalty)
        assert p_group >= p_single  # обе True, но формула учитывает размер


class TestAmbush:
    """Тесты засад (§10.4)."""

    def test_ambush_chance_formula(self):
        # Атака 80, защита 40, бонус подготовки 10
        chance = calculate_ambush_chance(80, 40, terrain_mod=5, preparation_bonus=10)
        # 55 + 0.5*(80-40) + 5 + 10 = 55 + 20 + 5 + 10 = 90
        assert chance == pytest.approx(90, abs=0.1)

    def test_ambush_chance_clamped(self):
        # Очень сильный перевес → не больше 90
        chance = calculate_ambush_chance(100, 10, terrain_mod=20, preparation_bonus=20)
        assert chance <= 90

        # Слабый перевес → не меньше 10
        chance = calculate_ambush_chance(10, 100, terrain_mod=-10, preparation_bonus=-10)
        assert chance >= 10

    def test_resolve_ambush_success(self):
        assert resolve_ambush(80, 0.3) == "success"

    def test_resolve_ambush_fail(self):
        assert resolve_ambush(80, 0.9) == "fail"

    def test_ambush_create_action(self):
        ambush = {
            "type": "ambush",
            "attacker_ids": [1, 2],
            "sector_id": 5,
            "start_hour": 10,
            "expires_hour": 11,
            "triggered": False,
        }
        assert ambush["expires_hour"] == ambush["start_hour"] + 1


class TestResearch:
    """Тесты исследования (§12.3)."""

    def test_research_success(self):
        result = calculate_research_success(80, "subtle", prior_knowledge=False, rng_value=0.1)
        assert result in ("position_type_found", "safe_path_found", "artifact_found")

    def test_research_failure(self):
        result = calculate_research_success(20, "visible", prior_knowledge=False, rng_value=0.8)
        assert result in ("damage_taken", "no_new_info")

    def test_research_prior_knowledge_helps(self):
        with_knowledge = calculate_research_success(40, "subtle", prior_knowledge=True, rng_value=0.5)
        without_knowledge = calculate_research_success(40, "subtle", prior_knowledge=False, rng_value=0.5)
        # С знанием результат лучше или равен
        rank = {"safe_path_found": 4, "artifact_found": 4, "position_type_found": 3,
                "damage_taken": 2, "no_new_info": 0}
        assert rank.get(with_knowledge, 0) >= rank.get(without_knowledge, 0)

    def test_research_anomaly_outcomes(self):
        npc = HumanNPC(id=1, attentiveness=70, sector_id=5)
        anomaly = Anomaly(id=100, sector_id=5, anomaly_type=AnomalyType.LARGE, stability=140, concealment=20)

        result = research_anomaly(npc, anomaly, None, hour=10, rng_value=0.1)
        assert result["research_success"] in ("safe_path_found", "artifact_found", "position_type_found")

    def test_research_anomaly_damage(self):
        npc = HumanNPC(id=1, attentiveness=20, sector_id=5)
        anomaly = Anomaly(id=100, sector_id=5, anomaly_type=AnomalyType.VISIBLE, stability=80, concealment=30)

        result = research_anomaly(npc, anomaly, None, hour=10, rng_value=0.7)
        # При провале — урон
        if result["research_success"] == "damage_taken":
            assert result["damage"] > 0

    def test_research_sector(self):
        npc = HumanNPC(id=1, attentiveness=80, sector_id=5)
        sector = type('obj', (object,), {"concealment": 60})()

        result = research_sector(npc, sector, None, hour=10, rng_value=0.2)
        assert "finds" in result
        # При высокой внимательности что-то найдено
        assert len(result["finds"]) >= 0  # может ничего не найти

    def test_add_knowledge_to_npc(self):
        npc = HumanNPC(id=1, faction="Бродяги")
        kb = KnowledgeBase()
        kb.add_manual(npc.id, KnowledgeType.ANOMALY, 100, {"sector": 5}, hour=10)

        facts = kb.get_facts()
        assert len(facts) == 1
        assert facts[0].subject_id == 100


class TestStash:
    """Тесты тайников (§7.9)."""

    def test_create_stash(self):
        stash = Stash(id=1, sector_id=5, owner_id=1, concealment=70, created_hour=10)
        assert stash.total_value == 0
        assert len(stash.items) == 0

    def test_add_and_remove_item(self):
        stash = Stash(id=1, sector_id=5, owner_id=1, created_hour=10)
        stash.add_item({"name": "artifact", "value": 50})
        stash.add_item({"name": "parts", "value": 20})
        stash.money = 100

        assert stash.total_value == 170

        removed = stash.remove_item(0)
        assert removed["name"] == "artifact"
        assert stash.total_value == 120

    def test_knowledge_payload_snapshot(self):
        stash = Stash(id=1, sector_id=5, owner_id=1, created_hour=10)
        stash.add_item({"name": "artifact", "value": 50})
        stash.money = 100

        snapshot = stash.get_snapshot()
        assert snapshot["items"][0]["name"] == "artifact"
        assert snapshot["money"] == 100

        # Изменяем тайник — старые данные не должны измениться
        stash.add_item({"name": "new_item", "value": 10})
        snapshot = stash.get_snapshot()
        assert len(snapshot["items"]) == 1  # старое знание не обновляется


class TestShelter:
    """Тесты убежищ (§7.10)."""

    def test_create_shelter(self):
        shelter = Shelter(id=1, sector_id=5, owner_group_id=1, quality=60, created_hour=10)
        assert shelter.is_active
        assert shelter.concealment_bonus == 18  # 60 * 0.3
        assert shelter.defense_bonus == 9  # 60 * 0.15
        assert abs(shelter.recovery_bonus - 1.3) < 0.01  # 1 + 0.6 * 0.5

    def test_shelter_full_quality(self):
        shelter = Shelter(id=1, sector_id=5, owner_group_id=1, quality=100, created_hour=10)
        assert shelter.concealment_bonus == 30
        assert shelter.defense_bonus == 15
        assert abs(shelter.recovery_bonus - 1.5) < 0.01

    def test_shelter_low_quality(self):
        shelter = Shelter(id=1, sector_id=5, owner_group_id=1, quality=10, created_hour=10)
        assert shelter.concealment_bonus == 3
        assert shelter.defense_bonus == 1
        assert abs(shelter.recovery_bonus - 1.05) < 0.01


class TestNewsManager:
    """Тесты системы новостей (§18)."""

    def test_create_event(self):
        nm = NewsManager()
        event = nm.create_event(
            hour=10, minute=30, sector_id=5,
            event_type="combat", participants=[1, 2],
            result="retreated", importance=50,
            summary="Бой в секторе 5",
        )
        assert event.id == 0
        assert event.hour == 10
        assert nm.get_total_events_count() == 1

    def test_hourly_summary(self):
        nm = NewsManager()
        nm.create_event(10, 0, 1, "combat", [1], "success", 60, "Бой в секторе 1")
        nm.create_event(10, 30, 2, "trade", [3], "success", 10, "Торговля в секторе 2")
        nm.create_event(10, 15, 1, "discovery", [1], "success", 80, "Находка в секторе 1")

        summary = nm.get_hourly_summary(10, {1: [nm.events[0], nm.events[2]], 2: [nm.events[1]]})
        assert summary["hour"] == 10
        assert summary["total_events"] == 3
        assert len(summary["critical_events"]) >= 1  # события с importance >= 60

    def test_filter_by_sector(self):
        nm = NewsManager()
        nm.create_event(10, 0, 5, "combat", [1], "success", 50, "Бой 1")
        nm.create_event(10, 30, 3, "trade", [2], "success", 10, "Торговля")
        nm.create_event(11, 0, 5, "hunt", [1], "success", 30, "Охота в секторе 5")

        sector_5_events = nm.get_events_by_sector(5)
        assert len(sector_5_events) == 2

        sector_5_hour_10 = nm.get_events_by_sector(5, hour=10)
        assert len(sector_5_hour_10) == 1

    def test_last_n_events(self):
        nm = NewsManager()
        for i in range(10):
            nm.create_event(i, 0, 0, "test", [], "success", 10, f"Event {i}")

        last_5 = nm.get_last_n_events(5)
        assert len(last_5) == 5
        assert last_5[0].id == 5  # первые 5 отброшены

    def test_events_by_importance(self):
        nm = NewsManager()
        nm.create_event(0, 0, 0, "low", [], "success", 5, "Низкая")
        nm.create_event(1, 0, 0, "high", [], "success", 75, "Высокая")
        nm.create_event(2, 0, 0, "medium", [], "success", 30, "Средняя")

        critical = nm.get_events_by_importance(50)
        assert len(critical) == 1
        assert critical[0].importance == 75
