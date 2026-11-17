"""Отдых как час торговли и обмена; необходимость сна раз в 24 часа."""

import pytest

from tests.test_actions_integration import _solo_group
from zonesim.ai import REST, SLEEP, IntentionContext, evaluate_actions
from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.entity import EntityStatus
from zonesim.world.group import HumanGroup
from zonesim.world.item import ItemType


def _ctx(**overrides):
    base = {
        "hour": 12, "is_night": False, "bravery": 50, "faction": "Бродяги",
        "health_share": 1.0, "stamina_share": 1.0,
        "at_home": True, "home_sector_id": 1, "distance_to_border": 2,
    }
    base.update(overrides)
    return IntentionContext(**base)


def _trader_sector(engine):
    trader = next(
        npc for npc in engine.state.stationary_humans
        if npc.stationary_role == "trader"
    )
    return trader


def _second_group(engine, sector_id):
    npc = engine.state.humans[1]
    npc.status = EntityStatus.ACTIVE
    # убираем из прежней группы, если была
    old = engine.state.human_groups.get(npc.group_id)
    if old and npc.id in old.members:
        old.members.remove(npc.id)
    if npc.faction == engine.state.humans[0].faction:
        npc.faction = "Борзые" if npc.faction != "Борзые" else "Бродяги"
    group = HumanGroup(
        id=engine.state.next_group_id,
        members=[npc.id],
        sector_id=sector_id,
        leader_id=npc.id,
    )
    engine.state.next_group_id += 1
    engine.state.human_groups[group.id] = group
    npc.group_id = group.id
    npc.sector_id = sector_id
    return npc, group


class TestRestMechanics:
    def test_rest_requires_comfort_and_low_stamina(self):
        u = evaluate_actions(_ctx(can_rest=False, stamina_share=0.5))
        assert u[REST] == float("-inf")
        u = evaluate_actions(_ctx(can_rest=True, stamina_share=0.5))
        assert u[REST] > float("-inf")
        # при полной выносливости отдых не нужен
        u = evaluate_actions(_ctx(can_rest=True, stamina_share=1.0))
        assert u[REST] < evaluate_actions(_ctx(can_rest=True, stamina_share=0.5))[REST]

    def test_sleep_wins_over_rest_when_due(self):
        """Сон в приоритете: после 24 часов бодрствования он побеждает отдых."""
        u = evaluate_actions(_ctx(can_rest=True, stamina_share=0.5, hours_awake=25))
        assert u[SLEEP] > u[REST]

    def test_rest_tick_recovers_half_comfort_rate(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        trader = _trader_sector(engine)
        group.sector_id = trader.sector_id
        npc.sector_id = trader.sector_id
        npc.stamina = 50
        engine._rest_tick(npc)
        assert npc.stamina == pytest.approx(62.5)  # 50 + 100×0.5/4

    def test_rest_tick_without_comfort_does_nothing(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        sector_id = next(
            sid for sid, s in engine.state.sectors.items()
            if s.neighbors and not s.is_faction_start
            and all(t.sector_id != sid for t in engine.state.stationary_humans)
        )
        group.sector_id = sector_id
        npc.sector_id = sector_id
        npc.stamina = 50
        engine._rest_tick(npc)
        assert npc.stamina == 50

    def test_wake_sets_awake_since(self):
        engine = SimulationEngine(seed=42)
        npc = engine.state.humans[0]
        npc.status = EntityStatus.SLEEPING
        npc.stamina = 99
        engine._sleep_tick(npc)
        assert npc.status == EntityStatus.ACTIVE
        assert npc.awake_since_hour == engine.state.time.hour


class TestRestTrade:
    def test_sell_happens_before_purchase(self):
        """Продажа добычи финансирует закупку в тот же час отдыха."""
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        trader = _trader_sector(engine)
        group.sector_id = trader.sector_id
        npc.sector_id = trader.sector_id
        artifact = engine._create_item(ItemType.ARTIFACT, "Артефакт", 500.0, npc.id)
        npc.money = 0.0
        # убираем аптечку, чтобы сработала закупка
        for item_id in list(npc.inventory):
            item = engine.state.items[item_id]
            if item.type is ItemType.MEDICINE:
                npc.inventory.remove(item_id)
                engine.state.items.pop(item_id)

        price_before = engine.trade_price("gear.medkit.sanitar2")  # цена ДО покупки
        engine._process_rest_trade(engine.state.time.hour, [group])

        assert artifact.id not in engine.state.items  # продано
        medkits = [
            engine.state.items[i] for i in npc.inventory
            if engine.state.items[i].type is ItemType.MEDICINE
        ]
        assert len(medkits) == 1  # куплено на вырученное
        assert npc.money == pytest.approx(300.0 - price_before)

    def test_no_trade_without_rest_hour(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        trader = _trader_sector(engine)
        group.sector_id = trader.sector_id
        npc.sector_id = trader.sector_id
        npc.money = 0.0

        engine._process_rest_trade(engine.state.time.hour, [])

        assert npc.money == 0.0


class TestRestExchange:
    def _two_groups(self, engine, relation):
        npc_a, group_a = _solo_group(engine)
        npc_b, group_b = _second_group(engine, group_a.sector_id)
        engine.state.faction_relations.set(
            npc_a.faction, npc_b.faction, relation,
        )
        return npc_a, group_a, npc_b, group_b

    def test_knowledge_shared_between_resting_groups(self):
        engine = SimulationEngine(seed=42)
        npc_a, group_a, npc_b, group_b = self._two_groups(engine, relation=50)
        kb_a = engine.state.knowledge_bases.setdefault(npc_a.id, KnowledgeBase())
        kb_a.add_manual(npc_a.id, KnowledgeType.ANOMALY, 777, {"sector_id": 5}, 1)
        engine.state.knowledge_bases.setdefault(npc_b.id, KnowledgeBase())

        engine._process_rest_exchanges(engine.state.time.hour, [group_a, group_b])

        kb_b = engine.state.knowledge_bases[npc_b.id]
        facts = kb_b.get_facts(KnowledgeType.ANOMALY, subject_id=777)
        assert len(facts) == 1
        assert facts[0].payload["sector_id"] == 5
        assert facts[0].source == "conversation"

    def test_no_exchange_with_poor_relations(self):
        engine = SimulationEngine(seed=42)
        npc_a, group_a, npc_b, group_b = self._two_groups(engine, relation=-30)
        kb_a = engine.state.knowledge_bases.setdefault(npc_a.id, KnowledgeBase())
        kb_a.add_manual(npc_a.id, KnowledgeType.ANOMALY, 777, {"sector_id": 5}, 1)
        engine.state.knowledge_bases.setdefault(npc_b.id, KnowledgeBase())

        engine._process_rest_exchanges(engine.state.time.hour, [group_a, group_b])

        kb_b = engine.state.knowledge_bases[npc_b.id]
        assert kb_b.get_facts(KnowledgeType.ANOMALY, subject_id=777) == []

    def test_barter_valuables_between_resting_groups(self):
        engine = SimulationEngine(seed=42)
        npc_a, group_a, npc_b, group_b = self._two_groups(engine, relation=60)
        artifact = engine._create_item(ItemType.ARTIFACT, "Артефакт", 500.0, npc_a.id)
        npc_a.money = 0
        npc_b.money = 1000

        engine._process_rest_exchanges(engine.state.time.hour, [group_a, group_b])

        assert artifact.id in npc_b.inventory
        assert npc_b.money == pytest.approx(600.0)  # 500 × 0.8
        assert npc_a.money == pytest.approx(400.0)
        events = [e for e in engine.state.news_manager.events if e.event_type == "rest_trade"]
        assert len(events) == 1

    def test_no_barter_below_trade_threshold(self):
        engine = SimulationEngine(seed=42)
        npc_a, group_a, npc_b, group_b = self._two_groups(engine, relation=30)
        artifact = engine._create_item(ItemType.ARTIFACT, "Артефакт", 500.0, npc_a.id)
        npc_b.money = 1000

        engine._process_rest_exchanges(engine.state.time.hour, [group_a, group_b])

        assert artifact.id in npc_a.inventory
        assert npc_b.money == 1000
