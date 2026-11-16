"""Тесты Фазы 2: группы, сон, выносливость, движение, миграция."""

import random
import pytest
from zonesim.core.time import GameTime, PhaseOfDay, SeededRNG
from zonesim.world.entity import HumanNPC, Monster, EntityStatus
from zonesim.world.group import HumanGroup, MonsterGroup
from zonesim.needs.sleep import (
    update_stamina,
    human_sleep_recover,
    monster_sleep_recover,
    calculate_stamina_cost,
)
from zonesim.actions.movement import (
    calculate_move_target,
    move_entity,
    get_move_distance,
)
from zonesim.generation.migration import MigrationState, process_migration


class TestHumanGroup:
    """Тесты групп людей (§7.5)."""

    def test_add_members(self):
        group = HumanGroup(id=1)
        group.add_member(1)
        group.add_member(2)
        group.add_member(3)
        group.add_member(4)
        assert group.member_count == 4

        # Пятый не добавится
        group.add_member(5)
        assert group.member_count == 4

    def test_remove_member(self):
        group = HumanGroup(id=1, members=[1, 2, 3])
        group.remove_member(2)
        assert group.member_count == 2
        assert 2 not in group.members

    def test_select_leader(self):
        npcs = {
            1: type('obj', (object,), {"bravery": 30, "attentiveness": 40})(),
            2: type('obj', (object,), {"bravery": 80, "attentiveness": 70})(),
            3: type('obj', (object,), {"bravery": 50, "attentiveness": 50})(),
        }
        group = HumanGroup(id=1, members=[1, 2, 3])
        group.select_leader(npcs)
        # Лидер — тот у кого bravery + attentiveness максимальны
        assert group.leader_id == 2

    def test_prisoners_not_in_limit(self):
        group = HumanGroup(id=1, members=[1, 2, 3, 4])
        group.prisoners.append(10)
        group.prisoners.append(20)
        # Пленные не входят в лимит 4 активных
        assert group.member_count == 4
        assert len(group.prisoners) == 2


class TestStamina:
    """Тесты выносливости (§14.1)."""

    def test_awake_cost(self):
        npc = HumanNPC(id=1, faction="Бродяги")
        update_stamina(npc, calculate_stamina_cost("rest", False), "rest", GameTime(7))
        assert npc.stamina == 100  # сон не тратит

        npc.stamina = 100
        update_stamina(npc, calculate_stamina_cost("movement", False), "movement", GameTime(7))
        assert npc.stamina == 97  # 100 - 3

    def test_exhaustion_unconscious(self):
        npc = HumanNPC(id=1, faction="Бродяги", stamina=5)
        time = GameTime(7)
        result = update_stamina(npc, 10, "movement", time)
        assert result is True  # произошло истощение
        assert npc.status == EntityStatus.UNCONSCIOUS
        assert npc.stamina == 0

    def test_stamina_does_not_go_below_zero(self):
        npc = HumanNPC(id=1, faction="Бродяги", stamina=3)
        update_stamina(npc, 10, "combat", GameTime(7))
        assert npc.stamina == 0


class TestSleepRecovery:
    """Тесты восстановления сна (§14.1)."""

    def test_full_comfort_sleep(self):
        """4 часа комфортного сна = 100% stamina."""
        npc = HumanNPC(id=1, faction="Бродяги", stamina=0, max_stamina=100)
        npc.status = EntityStatus.SLEEPING

        # Имитация группы с охранником
        guard_npc = HumanNPC(id=2, faction="Бродяги", status=EntityStatus.ACTIVE, sector_id=0)
        npcs = {1: npc, 2: guard_npc}

        # Охранник должен быть в members группы
        group = HumanGroup(id=1, members=[1, 2], sector_id=0)

        # Комфортный сон: есть бодрствующий член группы (охранник)
        assert group.is_comfort_sleep_possible(
            npcs, {}, {}, 0, "Бродяги"
        ) is True

        time = GameTime(22)
        recovered = human_sleep_recover(group, npcs, time, None)
        # За 1 час комфортного сна: 100 / 4 = 25
        assert abs(recovered - 25.0) < 0.1
        assert npc.stamina == 25

    def test_non_comfort_sleep(self):
        """6 часов некомфортного сна = 100% stamina."""
        npc = HumanNPC(id=1, faction="Бродяги", stamina=0, max_stamina=100)
        npc.status = EntityStatus.SLEEPING

        npcs = {1: npc}
        group = HumanGroup(id=1, members=[1], sector_id=0)

        # Нет охранника — некомфортный сон
        assert group.is_comfort_sleep_possible(
            npcs, {}, {}, 0, "Бродяги"
        ) is False

        time = GameTime(22)
        recovered = human_sleep_recover(group, npcs, time, None)
        # За 1 час некомфортного сна: 100 / 6 ≈ 16.67
        assert abs(recovered - 16.67) < 0.1
        assert abs(npc.stamina - 16.67) < 0.1

    def test_partial_sleep(self):
        """Более короткий сон даёт пропорциональное восстановление."""
        npc = HumanNPC(id=1, faction="Бродяги", stamina=50, max_stamina=100)
        npc.status = EntityStatus.SLEEPING

        guard_npc = HumanNPC(id=2, faction="Бродяги", status=EntityStatus.ACTIVE, sector_id=0)
        npcs = {1: npc, 2: guard_npc}
        group = HumanGroup(id=1, members=[1, 2], sector_id=0)

        time = GameTime(22)
        human_sleep_recover(group, npcs, time, None)
        # 50 + 25 = 75
        assert npc.stamina == 75

    def test_monster_sleep(self):
        """Монстры отдыхают за 2 часа, всегда комфортно."""
        monster = Monster(id=100, species="TerritorialPredator", stamina=0, max_stamina=100)
        monster.status = EntityStatus.SLEEPING

        monsters = {100: monster}
        group = MonsterGroup(id=1, members=[100], species="TerritorialPredator")

        time = GameTime(6)
        recovered = monster_sleep_recover(group, monsters, time)
        # За 1 час: 100 / 2 = 50
        assert abs(recovered - 50.0) < 0.1
        assert monster.stamina == 50

    def test_awake_members_do_not_recover(self):
        """Бодрствующие члены группы не восстанавливают stamina от сна."""
        awake_npc = HumanNPC(id=1, faction="Бродяги", stamina=50, max_stamina=100)
        awake_npc.status = EntityStatus.ACTIVE
        sleeping_npc = HumanNPC(id=2, faction="Бродяги", stamina=0, max_stamina=100)
        sleeping_npc.status = EntityStatus.SLEEPING

        npcs = {1: awake_npc, 2: sleeping_npc}
        group = HumanGroup(id=1, members=[1, 2], sector_id=0)

        time = GameTime(22)
        human_sleep_recover(group, npcs, time, None)

        assert awake_npc.stamina == 50  # не изменилась
        assert sleeping_npc.stamina == 25  # восстановилась


class TestMovement:
    """Тесты перемещения (§10.1)."""

    def test_calculate_move_target(self):
        class FakeSector:
            def __init__(self, neighbors):
                self.neighbors = neighbors

        sectors = {
            0: FakeSector([1, 2]),
            1: FakeSector([0]),
            2: FakeSector([0]),
        }

        rng = random.Random(42)
        target = calculate_move_target(0, sectors, rng=rng)
        assert target in [1, 2]

    def test_no_movement_no_neighbors(self):
        class FakeSector:
            neighbors = []

        sectors = {0: FakeSector()}
        target = calculate_move_target(0, sectors)
        assert target is None

    def test_move_entity(self):
        class FakeSector:
            def __init__(self, neighbors):
                self.neighbors = neighbors

        sectors = {
            0: FakeSector([1]),
            1: FakeSector([0, 2]),
            2: FakeSector([1]),
        }

        entity = type('obj', (object,), {"sector_id": 0})
        move_entity(entity, sectors, 2, max_edges=2)
        assert entity.sector_id == 2

    def test_move_limited_by_path(self):
        class FakeSector:
            def __init__(self, neighbors):
                self.neighbors = neighbors

        sectors = {
            0: FakeSector([1]),
            1: FakeSector([0, 2]),
            2: FakeSector([1]),
        }

        entity = type('obj', (object,), {"sector_id": 0})
        move_entity(entity, sectors, 2, max_edges=5)
        # Максимум 2 шага (0→1→2)
        assert entity.sector_id == 2

    def test_monster_speed(self):
        assert get_move_distance("TerritorialPredator") == 2
        assert get_move_distance("ScavengerPack") == 1
        assert get_move_distance("Human") == 1


class TestMigration:
    """Тесты миграции (§13.6, §14.6)."""

    def test_human_migration_limit(self):
        class FakeSector:
            is_border = True
            is_faction_start = False
            neighbors = []

        sectors = {0: FakeSector(), 1: FakeSector()}
        humans: list = []
        # Добавляем монстров, чтобы монстр-миграция не срабатывала
        monsters = [Monster(id=1, species="TerritorialPredator", sector_id=0)]
        time = GameTime(24)
        ms = MigrationState()
        rng = random.Random(42)

        new = process_migration(sectors, humans, monsters, time, ms, rng)
        # При нормальном населении людей и лимите миграции — не должно прийти
        assert len(new) <= 1  # максимум 1 человек в час

    def test_monster_migration_soft_min(self):
        class FakeSector:
            is_border = True
            is_faction_start = False
            neighbors = []

        sectors = {0: FakeSector(), 1: FakeSector()}
        monsters: list = []
        humans: list = []
        time = GameTime(24)
        ms = MigrationState()
        rng = random.Random(42)

        new = process_migration(sectors, humans, monsters, time, ms, rng)
        # При 0 монстров должно прийти
        assert len(new) >= 1

    def test_stamina_costs(self):
        assert calculate_stamina_cost("rest") == 0.0
        assert calculate_stamina_cost("guard") == 1.0
        assert calculate_stamina_cost("movement") == 3.0
        assert calculate_stamina_cost("combat") == 5.0
        assert calculate_stamina_cost("research") == 4.0
        # Ночью дороже
        assert calculate_stamina_cost("movement", is_night=True) == pytest.approx(3.3, abs=0.01)
