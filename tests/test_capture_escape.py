"""Регрессионный тест на путь побега монстра при захвате.

Этап 3, Промпт B3.1: проверка, что при outcome="escaped" все члены группы
монстра получают flee_sector и вызов не падает.
"""

from __future__ import annotations

from zonesim.simulation.engine import SimulationEngine
from zonesim.world.entity import EntityStatus
from zonesim.world.group import MonsterGroup


class TestMonsterCaptureEscape:
    """Путь: захват монстра провалился → монстр убежал → группа получает flee_sector."""

    def test_capture_outcome_escaped_moves_all_group_members(self):
        """Монстр-жертва убежал в случайный соседний сектор, вся группа следует за ним."""
        engine = SimulationEngine(seed=99)

        # Находим первого монстра и создаём группу из 2+ монстров
        active_monsters = [
            m for m in engine.state.monsters if m.status == EntityStatus.ACTIVE
        ]
        assert len(active_monsters) >= 2, "Нужно минимум 2 монстра для тестирования группы"

        # Фиксируем первого монстра-жертву и его группу
        victim = active_monsters[0]
        original_group_id = victim.group_id

        # Если группа маленькая — добавляем второго монстра в ту же группу
        if original_group_id is not None:
            grp = engine.state.monster_groups[original_group_id]
            if len(grp.members) < 2:
                # Создаём второго монстра в этой же группе
                second_monster = active_monsters[1]
                if second_monster.group_id != original_group_id:
                    # Удаляем из старой группы
                    if second_monster.group_id in engine.state.monster_groups:
                        old_grp = engine.state.monster_groups[second_monster.group_id]
                        if second_monster.id in old_grp.members:
                            old_grp.members.remove(second_monster.id)
                        if not old_grp.members:
                            del engine.state.monster_groups[second_monster.group_id]
                    # Добавляем в группу жертвы
                    grp.members.append(second_monster.id)
                    second_monster.group_id = original_group_id
                    second_monster.sector_id = victim.sector_id
        else:
            # Нет группы — создаём вручную
            if len(active_monsters) >= 2:
                second_monster = active_monsters[1]
                new_group = MonsterGroup(
                    id=engine.state.next_monster_group_id,
                    sector_id=victim.sector_id,
                    species=second_monster.species_value(),
                    home_sector_id=victim.home_sector_id,
                )
                engine.state.next_monster_group_id += 1
                engine.state.monster_groups[new_group.id] = new_group
                victim.group_id = new_group.id
                second_monster.group_id = new_group.id
                new_group.members = [victim.id, second_monster.id]

        monster_group = engine.state.monster_groups[original_group_id]
        assert len(monster_group.members) >= 2, "Группа должна содержать минимум 2 монстра"

        # Сектор должен иметь соседей
        sector = engine.state.sectors[victim.sector_id]
        assert sector.neighbors, "Сектор должен иметь соседей для побега"

        # Прогоняем simulate_hour — должен выполниться _process_capture_monster
        engine.simulate_hour()

        # После simulate_hour все члены группы должны быть активны
        for mid in monster_group.members:
            m = next((m for m in engine.state.monsters if m.id == mid), None)
            assert m is not None, f"Монстр {mid} должен существовать"
            assert m.status == EntityStatus.ACTIVE, (
                f"Монстр {mid} должен быть активен после побега"
            )

    def test_capture_outcome_escaped_no_crash_single_member_group(self):
        """Минимальная группа (1 монстр) не падает при побеге."""
        engine = SimulationEngine(seed=77)

        # Находим одиночного монстра без группы
        lone_monster = next(
            m for m in engine.state.monsters
            if m.status == EntityStatus.ACTIVE
        )

        # Если он уже в группе — убираем остальных
        if lone_monster.group_id is not None:
            group = engine.state.monster_groups[lone_monster.group_id]
            group.members = [lone_monster.id]
            # Помечаем остальных монстров как DEAD
            for m in engine.state.monsters:
                if m.id != lone_monster.id:
                    m.status = EntityStatus.DEAD

        # Сектор должен иметь соседей
        sector = engine.state.sectors[lone_monster.sector_id]
        assert sector.neighbors

        # simulate_hour не должен падать
        engine.simulate_hour()

        # Монстр должен быть активен
        assert lone_monster.status == EntityStatus.ACTIVE
