"""Механики ТЗ 0.4: выброс, укрытия, тропы, находки, сигналы бедствия."""

import pytest

from zonesim.ai import HELP, SHELTER
from zonesim.anomalies.core import Anomaly, AnomalyStatus, AnomalyType
from zonesim.anomalies.emission import is_emission_active
from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.entity import EntityStatus
from zonesim.world.sector import get_distance

from tests.test_actions_integration import _solo_group


def _trail_chain(engine, length=2):
    """Цепочка из length+1 сектора, все рёбра — тропы."""
    trails = engine._trail_set
    for a, sector in engine.state.sectors.items():
        for b in sector.neighbors:
            if (a, b) not in trails:
                continue
            chain = [a, b]
            while len(chain) <= length:
                last = engine.state.sectors[chain[-1]]
                nxt = next(
                    (n for n in last.neighbors
                     if n not in chain and (min(chain[-1], n), max(chain[-1], n)) in trails),
                    None,
                )
                if nxt is None:
                    break
                chain.append(nxt)
            if len(chain) == length + 1:
                return chain
    pytest.skip("нет цепочки троп нужной длины")


class TestTrails:
    def test_worldgen_marks_about_forty_percent_edges(self):
        engine = SimulationEngine(seed=42)
        total = sum(len(s.neighbors) for s in engine.state.sectors.values()) // 2
        assert len(engine.state.trails) > 0
        assert 0.2 <= len(engine.state.trails) / max(total, 1) <= 0.6

    def test_humans_walk_two_trail_edges_per_hour(self):
        engine = SimulationEngine(seed=42)
        a, b, c = _trail_chain(engine, 2)
        path = engine._walk(a, {c}, set(), points=1.0)
        assert path == [b, c]

    def test_normal_edges_cost_full_point(self):
        engine = SimulationEngine(seed=42)
        plain = [
            edge for edge in (
                (s.id, n) for s in engine.state.sectors.values() for n in s.neighbors
            )
            if edge not in engine._trail_set and (edge[1], edge[0]) not in engine._trail_set
        ]
        a, b = plain[0]
        path = engine._walk(a, {b}, set(), points=1.0)
        assert path == [b]
        path = engine._walk(a, {b}, set(), points=0.5)
        assert path == []

    def test_territorial_predator_walks_four_trail_edges(self):
        engine = SimulationEngine(seed=42)
        # линейный мир 0-1-2-3-4, все рёбра — тропы
        from zonesim.world.sector import Sector
        engine.state.sectors = {
            i: Sector(id=i, name=f"S{i}", neighbors=[i - 1, i + 1]) for i in range(1, 4)
        }
        engine.state.sectors[0] = Sector(id=0, name="S0", neighbors=[1])
        engine.state.sectors[4] = Sector(id=4, name="S4", neighbors=[3])
        engine.state.trails = [[0, 1], [1, 2], [2, 3], [3, 4]]
        path = engine._walk(0, {4}, set(), points=2.0)
        assert path == [1, 2, 3, 4]

    def test_blocked_trail_requires_passage_knowledge(self):
        """Без знания прохода переход по блокированной тропе бьёт по группе."""
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        chain = _trail_chain(engine, 1)
        a, b = chain
        group.sector_id = a
        npc.sector_id = a
        npc.health = 1000
        engine.state.anomalies = {}
        anomaly = Anomaly(
            id=engine.state.next_anomaly_id, sector_id=a,
            anomaly_type=AnomalyType.VISIBLE, concealment=10,
            damage_min=10, damage_max=20, blocks_trail=sorted((a, b)),
        )
        engine.state.next_anomaly_id += 1
        engine.state.anomalies[anomaly.id] = anomaly
        hour = engine.state.time.hour
        engine.state.rng.random = lambda: 0.9  # avoid_chance < 90 -> hit
        engine._apply_human_move(group, [npc], [b], {npc.id: npc}, hour)
        assert npc.health < 1000

    def test_passage_knowledge_allows_crossing(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        chain = _trail_chain(engine, 1)
        a, b = chain
        group.sector_id = a
        npc.sector_id = a
        npc.health = 1000
        engine.state.anomalies = {}
        anomaly = Anomaly(
            id=engine.state.next_anomaly_id, sector_id=a,
            anomaly_type=AnomalyType.VISIBLE, concealment=10,
            damage_min=10, damage_max=20, blocks_trail=sorted((a, b)),
        )
        engine.state.next_anomaly_id += 1
        engine.state.anomalies[anomaly.id] = anomaly
        kb = engine.state.knowledge_bases.setdefault(npc.id, KnowledgeBase())
        kb.add_manual(
            npc.id, KnowledgeType.SAFE_PATH, anomaly.id,
            {"edge": sorted((a, b))}, hour=0,
        )
        hour = engine.state.time.hour
        engine.state.rng.random = lambda: 0.9
        engine._apply_human_move(group, [npc], [b], {npc.id: npc}, hour)
        assert npc.health == 1000


class TestShelters:
    def test_eight_shelters_within_two_edges_of_every_sector(self):
        engine = SimulationEngine(seed=42)
        assert len(engine.state.shelters) == 8
        sectors = {s.sector_id for s in engine.state.shelters.values()}
        assert len(sectors) == 8  # не более одного в секторе
        ref = sectors | {s.id for s in engine.state.sectors.values() if s.is_faction_start}
        for sid in engine.state.sectors:
            assert any(
                (dist := get_distance(engine.state.sectors, sid, r)) is not None and dist <= 2
                for r in ref
            ), f"сектор {sid} дальше двух рёбер от укрытия"

    def test_monsters_occupy_shelter_and_leave(self):
        engine = SimulationEngine(seed=42)
        engine.state.rng.random = lambda: 0.0
        engine._process_shelter_occupation(24)
        occupied = [s for s in engine.state.shelters.values() if s.is_occupied]
        assert occupied
        shelter = occupied[0]
        group = engine.state.monster_groups[shelter.occupied_by]
        assert group.sector_id == shelter.sector_id
        engine._process_shelter_occupation(shelter.occupied_until)
        assert not shelter.is_occupied


class TestEmission:
    def _activate(self, engine, duration=2):
        hour = engine.state.time.hour
        engine.state.emission_start_hour = hour
        engine.state.emission_end_hour = hour + duration
        return hour

    def test_schedule_warning_and_intention(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        hour = engine.state.time.hour
        engine.state.next_emission_hour = hour + 1
        engine.state.emission_warning_hour = hour
        engine._phase4_intentions(hour)
        assert group.intention == SHELTER

    def test_unsheltered_group_takes_damage_and_dies_next_hour(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        sector_id = next(
            sid for sid, s in engine.state.sectors.items()
            if s.neighbors and not s.is_faction_start
            and all(t.sector_id != sid for t in engine.state.stationary_humans)
            and sid not in {sh.sector_id for sh in engine.state.shelters.values()}
        )
        group.sector_id = sector_id
        npc.sector_id = sector_id
        npc.health = npc.max_health = 100
        hour = self._activate(engine)
        stamina_before = npc.stamina
        engine._apply_emission_exposure(hour)
        assert npc.health <= 50  # 50+% урона
        assert npc.stamina < stamina_before  # лёгкая травма
        npc.health = 100
        engine._apply_emission_exposure(hour + 1)
        assert npc.status == EntityStatus.DEAD

    def test_sheltered_group_unharmed(self):
        engine = SimulationEngine(seed=42)
        npc, group = _solo_group(engine)
        trader = next(
            t for t in engine.state.stationary_humans if t.stationary_role == "trader"
        )
        group.sector_id = trader.sector_id
        npc.sector_id = trader.sector_id
        npc.health = 100
        hour = self._activate(engine)
        engine._apply_emission_exposure(hour)
        assert npc.health == 100

    def test_emission_moves_anomalies_once(self):
        engine = SimulationEngine(seed=42)
        before = {a.id: a.sector_id for a in engine.state.anomalies.values()
                  if a.status == AnomalyStatus.ACTIVE}
        hour = engine.state.time.hour
        engine._move_all_anomalies(hour)
        after = {a.id: a.sector_id for a in engine.state.anomalies.values()
                 if a.status == AnomalyStatus.ACTIVE}
        moved = sum(1 for aid in before if after.get(aid) != before[aid])
        assert moved > 0
        # цели — текущий или соседний сектор
        for aid, old in before.items():
            new = after[aid]
            assert new == old or new in engine.state.sectors[old].neighbors

    def test_emission_lifecycle_via_schedule(self):
        engine = SimulationEngine(seed=42)
        hour = engine.state.time.hour
        engine.state.next_emission_hour = hour
        engine._process_emission_schedule(hour)
        assert is_emission_active(
            engine.state.emission_start_hour, engine.state.emission_end_hour, hour,
        )
        assert engine.state.next_emission_hour == -1
        engine._process_emission_schedule(engine.state.emission_end_hour)
        assert engine.state.emission_start_hour == -1
        assert engine.state.next_emission_hour > engine.state.emission_end_hour


class TestFindings:
    def test_corpse_expires_after_24_hours(self):
        engine = SimulationEngine(seed=42)
        corpse = engine._create_corpse(engine.state.humans[0], hour=0)
        corpse.status = "available"
        item = engine._create_item(
            __import__("zonesim.world.item", fromlist=["ItemType"]).ItemType.ARTIFACT,
            "Артефакт", 100.0,
        )
        corpse.items.append(item.id)
        engine._expire_findings(24)
        assert corpse not in engine.state.corpses
        assert item.id not in engine.state.items

    def test_fresh_corpse_survives(self):
        engine = SimulationEngine(seed=42)
        corpse = engine._create_corpse(engine.state.humans[0], hour=20)
        corpse.status = "available"
        engine._expire_findings(24)
        assert corpse in engine.state.corpses


class TestDistressSignals:
    def test_wounded_group_signals_and_helper_comes(self):
        engine = SimulationEngine(seed=42)
        victim, victim_group = _solo_group(engine)
        # вторая здоровая группа рядом
        helper = engine.state.humans[1]
        helper.status = EntityStatus.ACTIVE
        from zonesim.world.group import HumanGroup
        helper_group = HumanGroup(
            id=engine.state.next_group_id, members=[helper.id],
            sector_id=victim_group.sector_id, leader_id=helper.id,
        )
        engine.state.next_group_id += 1
        engine.state.human_groups[helper_group.id] = helper_group
        helper.group_id = helper_group.id
        helper.sector_id = victim_group.sector_id
        if helper.faction == victim.faction:
            helper.faction = "Серая лига" if victim.faction != "Серая лига" else "Борзые"
        engine.state.faction_relations.set(helper.faction, victim.faction, 50)
        victim.health = 20  # среднее здоровье 0.2 < 0.3

        engine.state.rng.random = lambda: 0.0
        engine._process_distress_signals(engine.state.time.hour)

        kb = engine.state.knowledge_bases.get(helper.id)
        facts = [f for f in kb.get_facts(KnowledgeType.EVENT)
                 if f.payload.get("type") == "distress"]
        assert facts and facts[0].payload["group_id"] == victim_group.id

        engine._phase4_intentions(engine.state.time.hour)
        assert helper_group.intention == HELP
        victim_health_before = victim.health
        engine._aid_distress_group(
            helper_group, [helper], facts[0].payload, engine.state.time.hour,
        )
        assert victim.health > victim_health_before
