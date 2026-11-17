"""Пополнение численности монстров. Основано на §13.6 ТЗ."""

from __future__ import annotations

from zonesim.monsters.behavior import Monster, MonsterSpecies

# Лимиты миграции (§13.6)
MONSTER_SOFT_MIN = 18
MONSTER_SOFT_MAX = 45
MONSTER_MAX_GROUPS_PER_DAY = 3


class MonsterMigrationManager:
    """Пополнение численности монстров через границы. (§13.6)"""

    def __init__(self):
        self.last_day = -1
        self.groups_today = 0

    def check_and_spawn(
        self,
        active_monster_count: int,
        border_sectors: list[int],
        faction_start_ids: set[int],
        hour: int,
        rng,
    ) -> list[Monster]:
        """
        Проверяет, нужно ли добавить новых монстров.
        Возвращает список новых монстров.
        """
        new_monsters: list[Monster] = []

        current_day = hour // 24
        if current_day != self.last_day:
            self.groups_today = 0
            self.last_day = current_day

        # Проверка мягкого минимума
        if active_monster_count >= MONSTER_SOFT_MIN:
            return new_monsters

        # Лимит групп в день
        if self.groups_today >= MONSTER_MAX_GROUPS_PER_DAY:
            return new_monsters

        # Выбор граничного сектора (не стартового)
        valid_sectors = [s for s in border_sectors if s not in faction_start_ids]
        if not valid_sectors:
            return new_monsters

        species = rng.choice(list(MonsterSpecies))
        sector = rng.choice(valid_sectors)

        new_monster = Monster.create_from_species(
            id=rng.randint(10000, 99999),
            species=species,
            sector_id=sector,
            rng=rng,
        )
        new_monsters.append(new_monster)
        self.groups_today += 1

        return new_monsters

    def get_population_status(self, active_monster_count: int) -> dict:
        """Текущий статус популяции."""
        if active_monster_count < MONSTER_SOFT_MIN:
            status = "below_minimum"
        elif active_monster_count > MONSTER_SOFT_MAX:
            status = "above_maximum"
        else:
            status = "normal"

        return {
            "count": active_monster_count,
            "soft_min": MONSTER_SOFT_MIN,
            "soft_max": MONSTER_SOFT_MAX,
            "status": status,
            "migration_enabled": active_monster_count < MONSTER_SOFT_MIN,
        }
