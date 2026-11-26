"""Интеграционные проверки видового поведения монстров (§13 ТЗ)."""

import pytest

from zonesim.anomalies.core import Anomaly, AnomalyType
from zonesim.combat.loot import Corpse
from zonesim.monsters.behavior import select_weakest_target, species_value
from zonesim.monsters.hunt import should_pursue
from zonesim.persistence.serialization import state_to_dict
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.groups import sync_monster_groups
from zonesim.world.entity import EntityStatus, Monster, MonsterSpecies
from zonesim.world.group import HumanGroup, MonsterGroup
from zonesim.world.item import ItemType
from zonesim.world.item import create_item
from zonesim.world.sector import get_shortest_path

SPECIES_PARAMS_KEY = {
    "territorial_predator": MonsterSpecies.TERRITORIAL_PREDATOR,
    "scavenger_pack": MonsterSpecies.SCAVENGER_PACK,
    "large_migrator": MonsterSpecies.LARGE_MIGRATOR,
}


def _sector_with_neighbors(engine, exclude=None):
    exclude = set(exclude or ())
    return next(
        sid for sid, sector in engine.state.sectors.items()
        if sid not in exclude and sector.neighbors and not sector.is_faction_start
    )


def _clear_monsters(engine, keep=None):
    """Убивает всех монстров, кроме keep, и пересобирает группы."""
    for monster in engine.state.monsters:
        if keep is None or monster.id != keep.id:
            monster.status = EntityStatus.DEAD
    sync_monster_groups(engine.state)


def _fresh_monsters(engine, *monsters):
    """Убивает стартовых монстров и регистрирует новых с пересборкой групп."""
    _clear_monsters(engine)
    engine.state.monsters.extend(monsters)
    for monster in monsters:
        monster.status = EntityStatus.ACTIVE
        engine.state.next_monster_id = max(engine.state.next_monster_id, monster.id + 1)
    sync_monster_groups(engine.state)


def _make_human_group(engine, *npcs, group_id=None):
    group_id = engine.state.next_group_id if group_id is None else group_id
    if group_id == engine.state.next_group_id:
        engine.state.next_group_id += 1
    group = HumanGroup(
        id=group_id,
        members=[npc.id for npc in npcs],
        sector_id=npcs[0].sector_id,
        leader_id=npcs[0].id,
    )
    engine.state.human_groups[group_id] = group
    for npc in npcs:
        npc.group_id = group_id
    return group


def _split_group(engine, group, *monsters):
    """Отделяет монстров в собственную новую группу."""
    split = MonsterGroup(
        id=engine.state.next_monster_group_id,
        members=[monster.id for monster in monsters],
        sector_id=monsters[0].sector_id,
        species=species_value(monsters[0]),
        home_sector_id=monsters[0].home_sector_id,
    )
    engine.state.next_monster_group_id += 1
    engine.state.monster_groups[split.id] = split
    group.members = [mid for mid in group.members if mid not in split.members]
    for monster in monsters:
        monster.group_id = split.id
    return split


def _add_corpse(engine, sector_id, with_items=False):
    corpse = Corpse(
        id=engine.state.next_corpse_id,
        original_entity_id=engine.state.next_human_id + 100000,
        original_entity_type="human",
        sector_id=sector_id,
        created_hour=engine.state.time.hour,
        money=50,
        monster_parts=[{"type": "коготь", "value": 30}],
    )
    engine.state.next_corpse_id += 1
    if with_items:
        for _ in range(2):
            item = create_item(engine.state, ItemType.ARTIFACT, "Артефакт", 100.0, owner_id=None)
            corpse.items.append(item.id)
    engine.state.corpses.append(corpse)
    return corpse


class TestGroupSync:
    def test_initial_groups_are_single_species_sized_and_co_located(self):
        engine = SimulationEngine(seed=42)
        assignment = {}
        for monster in engine.state.monsters:
            if monster.status == EntityStatus.DEAD:
                assert monster.group_id is None
                continue
            group = engine.state.monster_groups.get(monster.group_id)
            assert group is not None, f"монстр {monster.id} без группы"
            assert monster.id in group.members
            assert group.species == species_value(monster)
            assert group.sector_id == monster.sector_id
            assignment.setdefault(monster.id, set()).add(group.id)

        for monster_id, group_ids in assignment.items():
            assert len(group_ids) == 1, f"монстр {monster_id} в нескольких группах"

        for group in engine.state.monster_groups.values():
            limit = Monster.SPECIES_PARAMS[
                SPECIES_PARAMS_KEY[group.species]
            ]["normal_group_size"][1]
            assert 1 <= group.member_count <= limit


class TestTargeting:
    def test_weakest_target_is_preferred(self):
        wounded = Monster(id=1, health=30, max_health=100)
        healthy = Monster(id=2, health=95, max_health=100)
        assert select_weakest_target([healthy, wounded]).id == 1
        assert select_weakest_target([]) is None

    def test_engine_targets_wounded_human_group(self):
        engine = SimulationEngine(seed=42)
        sector_id = _sector_with_neighbors(engine)
        npc_wounded, npc_healthy = engine.state.humans[0], engine.state.humans[1]
        for npc in (npc_wounded, npc_healthy):
            npc.sector_id = sector_id
            npc.status = EntityStatus.ACTIVE
            npc.stamina = 100
        npc_wounded.health = 25
        npc_wounded.max_health = 100
        npc_healthy.health = 100
        npc_healthy.max_health = 100
        # убираем чужие группы, чтобы остались только две одиночные
        _clear_monsters(engine)
        engine.state.human_groups = {}
        wounded_group = _make_human_group(engine, npc_wounded)
        _make_human_group(engine, npc_healthy)

        monster = Monster(
            id=engine.state.next_monster_id,
            species=MonsterSpecies.LARGE_MIGRATOR,
            sector_id=sector_id,
            health=100,
            max_health=100,
            stamina=100,
            max_stamina=100,
        )
        engine.state.monsters.append(monster)
        _clear_monsters(engine, keep=monster)
        engine.state.anomalies = {}
        engine._moved_monster_ids = set()
        engine.state.rng.random = lambda: 0.0

        engine._schedule_encounters(is_night=False, hour=engine.state.time.hour)

        assert len(engine._pending_battles) == 1
        defenders = engine._pending_battles[0]["defenders"]
        assert npc_wounded.id in [entity.id for entity in defenders]
        assert npc_healthy.id not in [entity.id for entity in defenders]
        assert engine._pending_battles[0]["defender_group_id"] == wounded_group.id


class TestSpeciesAttackRules:
    def test_solitary_territorial_predator_avoids_healthy_human(self):
        engine = SimulationEngine(seed=42)
        npc = engine.state.humans[0]
        npc.health = npc.max_health
        monster = Monster(
            id=engine.state.next_monster_id,
            species=MonsterSpecies.TERRITORIAL_PREDATOR,
            sector_id=npc.sector_id,
            health=100,
            max_health=100,
        )
        engine.state.monsters.append(monster)
        assert not engine._monsters_attack([monster], [npc], is_night=False)

    def test_territorial_pack_can_attack_healthy_human(self):
        engine = SimulationEngine(seed=42)
        npc = engine.state.humans[0]
        npc.health = npc.max_health
        first = Monster(
            id=engine.state.next_monster_id,
            species=MonsterSpecies.TERRITORIAL_PREDATOR,
            health=100,
            max_health=100,
        )
        second = Monster(
            id=engine.state.next_monster_id + 1,
            species=MonsterSpecies.TERRITORIAL_PREDATOR,
            health=100,
            max_health=100,
        )
        engine.state.monsters.extend([first, second])
        engine.state.rng.random = lambda: 0.0
        assert engine._monsters_attack([first, second], [npc], is_night=False)


class TestMovement:
    def _path_of_two_edges(self, engine):
        sectors = engine.state.sectors
        for start in sectors:
            for finish in sectors:
                if start == finish:
                    continue
                path = get_shortest_path(sectors, start, finish)
                if path and len(path) == 3:
                    return path
        pytest.skip("в мире нет пути длиной 2 ребра")

    def test_territorial_predator_moves_two_edges_others_one(self):
        engine = SimulationEngine(seed=42)
        start, middle, finish = self._path_of_two_edges(engine)
        territorial = Monster(
            id=900001,
            species=MonsterSpecies.TERRITORIAL_PREDATOR,
            sector_id=start,
            health=100,
            max_health=100,
            home_sector_id=finish,
        )
        scavenger = Monster(
            id=900002,
            species=MonsterSpecies.SCAVENGER_PACK,
            sector_id=start,
            health=100,
            max_health=100,
            home_sector_id=finish,
        )
        _fresh_monsters(engine, territorial, scavenger)
        territorial_group = engine.state.monster_groups[territorial.group_id]
        scavenger_group = engine.state.monster_groups[scavenger.group_id]
        territorial_group.intention = "return_home"
        scavenger_group.intention = "return_home"

        engine._move_monster_groups(hour=engine.state.time.hour)

        assert territorial_group.sector_id == finish
        assert territorial.sector_id == finish
        assert scavenger_group.sector_id == middle
        assert scavenger.sector_id == middle

    def test_group_with_inactive_member_does_not_move(self):
        engine = SimulationEngine(seed=42)
        start, _, finish = self._path_of_two_edges(engine)
        first = Monster(
            id=900001,
            species=MonsterSpecies.TERRITORIAL_PREDATOR,
            sector_id=start,
            health=100,
            max_health=100,
            home_sector_id=finish,
        )
        second = Monster(
            id=900002,
            species=MonsterSpecies.TERRITORIAL_PREDATOR,
            sector_id=start,
            health=100,
            max_health=100,
            home_sector_id=finish,
        )
        _fresh_monsters(engine, first, second)
        second.status = EntityStatus.SLEEPING
        group = engine.state.monster_groups[first.group_id]
        group.intention = "return_home"

        engine._move_monster_groups(hour=engine.state.time.hour)

        assert group.sector_id == start
        assert first.sector_id == start


class TestPursuitMemory:
    def test_large_migrator_pursuit_window_is_24_hours(self):
        migrator = Monster(id=1, species=MonsterSpecies.LARGE_MIGRATOR)
        scavenger = Monster(id=2, species=MonsterSpecies.SCAVENGER_PACK)
        assert should_pursue(migrator, True, 5)
        assert should_pursue(migrator, True, 23)
        assert not should_pursue(migrator, True, 24)
        assert not should_pursue(migrator, False, 5)
        assert not should_pursue(scavenger, True, 1)

    def test_stalk_intention_and_memory_expiry(self):
        engine = SimulationEngine(seed=42)
        hour = engine.state.time.hour
        sector_id = _sector_with_neighbors(engine)
        neighbor = engine.state.sectors[sector_id].neighbors[0]
        npc = engine.state.humans[0]
        npc.sector_id = neighbor
        npc.health = 40
        npc.max_health = 100
        npc.status = EntityStatus.ACTIVE

        monster = Monster(
            id=900001,
            species=MonsterSpecies.SCAVENGER_PACK,
            sector_id=sector_id,
            health=100,
            max_health=100,
            target_id=npc.id,
            target_memory_hour=hour - 5,
        )
        engine.state.monsters.append(monster)
        _clear_monsters(engine, keep=monster)
        group = engine.state.monster_groups[monster.group_id]

        engine._phase4_monster_intentions(hour)
        assert group.intention == "stalk"
        assert group.target_id == npc.id
        assert group.target_sector_id == neighbor

        engine._move_monster_groups(hour=engine.state.time.hour)
        assert group.sector_id == neighbor

        monster.target_memory_hour = hour - 13
        engine._phase4_monster_intentions(hour)
        assert group.intention != "stalk"
        assert group.target_id is None


class TestBattleMemory:
    def test_large_migrator_remembers_attacker_after_battle(self, monkeypatch):
        engine = SimulationEngine(seed=42)
        sector_id = _sector_with_neighbors(engine)
        npc = engine.state.humans[0]
        npc.sector_id = sector_id
        npc.status = EntityStatus.ACTIVE
        npc.health = npc.max_health = 1000
        npc.stamina = npc.max_stamina = 100
        npc.attack = 100
        npc.defense = 100
        npc.bravery = 100

        monster = Monster(
            id=900001,
            species=MonsterSpecies.LARGE_MIGRATOR,
            sector_id=sector_id,
            health=100,
            max_health=100,
            stamina=100,
            max_stamina=100,
            attack=1,
            defense=1,
        )
        engine.state.monsters.append(monster)
        _clear_monsters(engine, keep=monster)
        group = engine.state.monster_groups[monster.group_id]
        engine.state.rng.random = lambda: 0.1
        monkeypatch.setattr("zonesim.combat.should_attempt_retreat", lambda *a, **k: False)

        engine._schedule_monster_attack(group, [monster], [npc], None, sector_id, False)
        engine._execute_battles(engine.state.time.hour)

        assert monster.target_id == npc.id
        assert monster.target_memory_hour == engine.state.time.hour


class TestFeeding:
    def test_feeding_consumes_corpse_and_removes_items(self):
        engine = SimulationEngine(seed=42)
        sector_id = _sector_with_neighbors(engine)
        monster = Monster(
            id=900001,
            species=MonsterSpecies.SCAVENGER_PACK,
            sector_id=sector_id,
            health=100,
            max_health=100,
            stamina=10,
            max_stamina=100,
        )
        engine.state.monsters.append(monster)
        _clear_monsters(engine, keep=monster)
        group = engine.state.monster_groups[monster.group_id]
        corpse = _add_corpse(engine, sector_id, with_items=True)
        item_ids = list(corpse.items)
        hour = engine.state.time.hour
        engine.state.rng.random = lambda: 0.9  # подавить человеческие стычки

        engine._phase4_monster_intentions(hour)
        assert group.intention == "feed"
        engine._schedule_encounters(is_night=False, hour=engine.state.time.hour)
        assert engine._pending_battles == []
        assert engine._feeding_claims == {group.id: corpse.id}

        fed = engine._process_monster_feeding(hour)

        assert fed == {group.id}
        corpse = next(c for c in engine.state.corpses if c.id == corpse.id)
        assert corpse.status == "consumed"
        assert corpse.consumed_by == monster.id
        assert corpse.consumed_hour == hour
        assert corpse.money == 0
        assert corpse.monster_parts == []
        assert corpse.items == []
        for item_id in item_ids:
            assert item_id not in engine.state.items
        assert monster.stamina == 40

    def test_feeding_group_does_not_fight(self):
        engine = SimulationEngine(seed=42)
        sector_id = _sector_with_neighbors(engine)
        monster = Monster(
            id=900001,
            species=MonsterSpecies.SCAVENGER_PACK,
            sector_id=sector_id,
            health=100,
            max_health=100,
        )
        engine.state.monsters.append(monster)
        _clear_monsters(engine, keep=monster)
        group = engine.state.monster_groups[monster.group_id]
        _add_corpse(engine, sector_id)
        npc = engine.state.humans[0]
        npc.sector_id = sector_id
        npc.status = EntityStatus.ACTIVE
        npc.health = 10
        engine.state.human_groups = {}
        _make_human_group(engine, npc)
        engine.state.rng.random = lambda: 0.9

        engine._phase4_monster_intentions(engine.state.time.hour)
        engine._schedule_encounters(is_night=False, hour=engine.state.time.hour)

        assert engine._pending_battles == []
        assert group.intention == "feed"

    def test_strong_group_claims_corpse_weak_group_backs_off(self):
        engine = SimulationEngine(seed=42)
        sector_id = _sector_with_neighbors(engine)
        strong = Monster(
            id=900001,
            species=MonsterSpecies.LARGE_MIGRATOR,
            sector_id=sector_id,
            health=100,
            max_health=100,
            attack=70,
        )
        weak = Monster(
            id=900002,
            species=MonsterSpecies.TERRITORIAL_PREDATOR,
            sector_id=sector_id,
            health=100,
            max_health=100,
            attack=50,
        )
        _fresh_monsters(engine, strong, weak)
        strong_group = engine.state.monster_groups[strong.group_id]
        weak_group = engine.state.monster_groups[weak.group_id]
        strong_group.intention = "feed"
        weak_group.intention = "feed"
        corpse = _add_corpse(engine, sector_id)
        engine.state.rng.random = lambda: 0.9

        engine._schedule_encounters(is_night=False, hour=engine.state.time.hour)

        assert engine._feeding_claims == {strong_group.id: corpse.id}
        assert weak_group.intention == "roam"
        assert not engine._pending_battles

    def test_close_power_corpse_dispute_starts_battle(self):
        engine = SimulationEngine(seed=42)
        sector_id = _sector_with_neighbors(engine)
        first = Monster(
            id=900001,
            species=MonsterSpecies.LARGE_MIGRATOR,
            sector_id=sector_id,
            health=100,
            max_health=100,
            attack=70,
        )
        second = Monster(
            id=900002,
            species=MonsterSpecies.LARGE_MIGRATOR,
            sector_id=sector_id,
            health=100,
            max_health=100,
            attack=71,
        )
        _fresh_monsters(engine, first, second)
        # синхронизация сложила обоих мигрантов в одну группу — разводим вручную
        merged = engine.state.monster_groups[first.group_id]
        second_group = _split_group(engine, merged, second)
        first_group = engine.state.monster_groups[first.group_id]
        first_group.intention = "feed"
        second_group.intention = "feed"
        corpse = _add_corpse(engine, sector_id)
        engine.state.rng.random = lambda: 0.9

        engine._schedule_encounters(is_night=False, hour=engine.state.time.hour)

        assert engine._feeding_claims == {}
        assert len(engine._pending_battles) == 1
        battle = engine._pending_battles[0]
        assert battle["feed_corpse_id"] == corpse.id
        assert battle["attacker_is_monster"] and battle["defender_is_monster"]
        fed = engine._process_monster_feeding(engine.state.time.hour)
        assert fed == set()
        corpse = next(c for c in engine.state.corpses if c.id == corpse.id)
        assert corpse.status == "available"


class TestMonsterVersusMonster:
    def test_different_species_groups_battle(self):
        engine = SimulationEngine(seed=42)
        sector_id = _sector_with_neighbors(engine)
        predator = Monster(
            id=900001,
            species=MonsterSpecies.TERRITORIAL_PREDATOR,
            sector_id=sector_id,
            health=100,
            max_health=100,
        )
        scavenger = Monster(
            id=900002,
            species=MonsterSpecies.SCAVENGER_PACK,
            sector_id=sector_id,
            health=50,
            max_health=100,
        )
        _fresh_monsters(engine, predator, scavenger)
        engine._phase4_monster_intentions(engine.state.time.hour)
        engine.state.rng.random = lambda: 0.0

        engine._schedule_encounters(is_night=False, hour=engine.state.time.hour)

        monster_battles = [
            battle for battle in engine._pending_battles
            if battle["attacker_is_monster"] and battle["defender_is_monster"]
        ]
        assert len(monster_battles) == 1


class TestAnomalyContact:
    def test_monster_can_die_to_anomaly_and_leave_corpse(self):
        engine = SimulationEngine(seed=42)
        sector_id = _sector_with_neighbors(engine)
        monster = Monster(
            id=900001,
            species=MonsterSpecies.LARGE_MIGRATOR,
            sector_id=sector_id,
            health=3,
            max_health=100,
        )
        engine.state.monsters.append(monster)
        _clear_monsters(engine, keep=monster)
        engine.state.anomalies = {}
        anomaly = Anomaly(
            id=engine.state.next_anomaly_id,
            sector_id=sector_id,
            anomaly_type=AnomalyType.VISIBLE,
            concealment=10,
            damage_min=5,
            damage_max=10,
        )
        engine.state.next_anomaly_id += 1
        engine.state.anomalies[anomaly.id] = anomaly
        engine._moved_monster_ids = {monster.id}
        engine.state.rng.random = lambda: 0.9
        hour = engine.state.time.hour

        engine._check_monster_anomaly_contacts(hour, is_night=False)

        assert monster.status == EntityStatus.DEAD
        corpse = next(
            c for c in engine.state.corpses
            if c.original_entity_id == monster.id
        )
        assert corpse.sector_id == sector_id
        assert corpse.status == "available"


class TestPersistence:
    def test_save_load_preserves_monster_groups_and_continuation(self, tmp_path):
        original = SimulationEngine(seed=11, save_directory=tmp_path)
        for _ in range(12):
            original.simulate_hour()
        assert original.state.monster_groups
        original.save("manual")
        restored = SimulationEngine.load("manual", tmp_path)

        assert restored.state.next_monster_group_id == original.state.next_monster_group_id
        for group_id, group in original.state.monster_groups.items():
            loaded = restored.state.monster_groups[group_id]
            assert loaded.members == group.members
            assert loaded.intention == group.intention
            assert loaded.target_id == group.target_id
            assert loaded.sector_id == group.sector_id
        assert state_to_dict(restored.state) == state_to_dict(original.state)

        for _ in range(12):
            original.simulate_hour()
            restored.simulate_hour()
            assert state_to_dict(restored.state) == state_to_dict(original.state)
