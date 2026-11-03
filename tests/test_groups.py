"""Тесты мобильных групп и стационарного персонала баз (§6.2–6.3, §7.5)."""

from collections import Counter

from zonesim.ai import EXPLORE
from zonesim.generation.worldgen import generate_world
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.entity import EntityStatus


class TestWorldPopulation:
    def test_default_faction_distribution(self):
        world = generate_world(seed=42)

        assert len(world["humans"]) == 40
        assert Counter(npc.faction for npc in world["humans"]) == {
            "Бродяги": 16,
            "Борзые": 18,
            "Серая лига": 6,
        }
        assert len(world["stationary_humans"]) == 9
        assert {npc.id for npc in world["humans"]}.isdisjoint(
            npc.id for npc in world["stationary_humans"]
        )

    def test_every_base_has_trader_and_two_guards(self):
        world = generate_world(seed=42)
        start_ids = {
            sector.id for sector in world["sectors"].values() if sector.is_faction_start
        }

        for sector_id in start_ids:
            staff = [
                npc for npc in world["stationary_humans"]
                if npc.sector_id == sector_id
            ]
            assert Counter(npc.stationary_role for npc in staff) == {
                "trader": 1,
                "guard": 2,
            }
            assert all(npc.is_stationary for npc in staff)
            assert all(npc.group_id is None for npc in staff)
            assert all(
                npc.faction == world["sectors"][sector_id].controller_faction
                for npc in staff
            )

    def test_starting_stats_have_spread(self):
        world = generate_world(seed=42)
        for npc in world["humans"]:
            for stat in (npc.attack, npc.defense, npc.attentiveness, npc.bravery):
                assert 45 <= stat <= 60
        assert len({npc.attack for npc in world["humans"]}) > 1


class TestHumanGroups:
    def test_all_mobile_humans_belong_to_one_valid_group(self):
        world = generate_world(seed=42)
        humans = {npc.id: npc for npc in world["humans"]}
        memberships = []

        for group in world["human_groups"].values():
            assert 1 <= group.member_count <= 4
            assert group.leader_id in group.members
            assert len(group.members) == len(set(group.members))
            factions = {humans[mid].faction for mid in group.members}
            assert len(factions) == 1
            assert {humans[mid].sector_id for mid in group.members} == {group.sector_id}
            for member_id in group.members:
                assert humans[member_id].group_id == group.id
                memberships.append(member_id)

        assert sorted(memberships) == sorted(humans)

    def test_group_chooses_one_common_intention(self):
        engine = SimulationEngine(seed=42)
        group = next(g for g in engine.state.human_groups.values() if g.member_count > 1)

        engine._phase4_intentions(engine.state.time.hour)

        assert group.intention
        for member_id in group.members:
            npc = next(h for h in engine.state.humans if h.id == member_id)
            if npc.status == EntityStatus.ACTIVE:
                assert npc.intention == group.intention

    def test_group_moves_together(self):
        engine = SimulationEngine(seed=42)
        group = next(g for g in engine.state.human_groups.values() if g.member_count > 1)
        members = [h for h in engine.state.humans if h.group_id == group.id]
        for npc in members:
            npc.status = EntityStatus.ACTIVE
        group.intention = EXPLORE
        old_sector = group.sector_id

        engine._phase5_movement(engine.state.time.hour, is_night=False)

        assert group.sector_id != old_sector
        assert {npc.sector_id for npc in members} == {group.sector_id}
        assert {npc.id for npc in members} <= engine._moved_human_ids

    def test_group_does_not_leave_sleeping_member(self):
        engine = SimulationEngine(seed=42)
        group = next(g for g in engine.state.human_groups.values() if g.member_count > 1)
        members = [h for h in engine.state.humans if h.group_id == group.id]
        for npc in members:
            npc.status = EntityStatus.ACTIVE
        members[0].status = EntityStatus.SLEEPING
        group.intention = EXPLORE
        old_sector = group.sector_id

        engine._phase5_movement(engine.state.time.hour, is_night=False)

        assert group.sector_id == old_sector
        assert {npc.sector_id for npc in members} == {old_sector}

    def test_dead_member_is_removed_from_group(self):
        engine = SimulationEngine(seed=42)
        group = next(g for g in engine.state.human_groups.values() if g.member_count > 1)
        member_id = group.members[0]
        npc = next(h for h in engine.state.humans if h.id == member_id)
        npc.status = EntityStatus.DEAD

        engine._phase9_consequences(engine.state.time.hour)

        assert member_id not in group.members
        assert npc.group_id is None

    def test_groups_stay_co_located_during_simulation(self):
        engine = SimulationEngine(seed=42)
        for _ in range(96):
            engine.simulate_hour()

        humans = {npc.id: npc for npc in engine.state.humans}
        for group in engine.state.human_groups.values():
            assert group.members
            assert {humans[mid].sector_id for mid in group.members} == {group.sector_id}


class TestStationaryStaff:
    def test_staff_never_moves_or_joins_mobile_simulation(self):
        engine = SimulationEngine(seed=42)
        initial_positions = {npc.id: npc.sector_id for npc in engine.state.stationary_humans}

        for _ in range(48):
            engine.simulate_hour()

        assert len(engine.state.stationary_humans) == 9
        for npc in engine.state.stationary_humans:
            assert npc.sector_id == initial_positions[npc.id]
            assert npc.group_id is None
            assert npc.intention == ""
