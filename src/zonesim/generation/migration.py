"""Миграция: прибытие и уход людей/монстров через границы. Основано на §14.6 и §13.6 ТЗ."""

from __future__ import annotations

import random
from zonesim.world.entity import EntityStatus, HumanNPC, Monster

# Лимиты миграции монстров (§13.6)
MONSTER_SOFT_MIN = 18
MONSTER_SOFT_MAX = 45
MONSTER_MAX_GROUPS_PER_DAY = 3

# Лимит прибытия людей (§14.6)
HUMAN_MAX_PER_DAY = 1
HUMAN_ARRIVAL_CHANCE_LOW_POP = 0.3  # при критически малом населении
HUMAN_ARRIVAL_CHANCE_NORMAL = 0.02  # обычный фоновый приток


class MigrationState:
    """Состояние миграции."""

    def __init__(self):
        self.last_human_arrival_day = -1
        self.last_monster_arrival_day = -1
        self.monster_groups_today = 0
        self.human_groups_today = 0


def process_migration(
    sectors: dict[int, object],
    humans: list[HumanNPC],
    monsters: list[Monster],
    time,
    migration_state: MigrationState,
    rng: random.Random,
    config: dict | None = None,
) -> list[HumanNPC]:
    """
    Обрабатывает миграцию за один час.
    Возвращает список новых NPC.
    """
    config = config or {}
    new_humans: list[HumanNPC] = []
    new_monsters: list[Monster] = []

    # Обработка прибытия людей (§14.6)
    _process_human_migration(sectors, humans, time, migration_state, rng, config, new_humans)

    # Обработка прибытия монстров (§13.6)
    _process_monster_migration(sectors, monsters, time, migration_state, rng, config, new_monsters)

    # Обработка выхода людей (§14.6)
    _process_human_departure(humans, time, rng)

    return new_humans + new_monsters


def _process_human_migration(
    sectors: dict[int, object],
    humans: list[HumanNPC],
    time,
    migration_state: MigrationState,
    rng: random.Random,
    config: dict,
    result: list[HumanNPC],
) -> None:
    """Прибытие мобильных NPC через внешние границы (§14.6)."""
    current_day = time.hour // 24

    # Проверяем лимиты
    if current_day != migration_state.last_human_arrival_day:
        migration_state.human_groups_today = 0
        migration_state.last_human_arrival_day = current_day

    if migration_state.human_groups_today >= HUMAN_MAX_PER_DAY:
        return

    # Вероятность зависит от численности: при критически малой — выше
    current_human_count = sum(
        1 for h in humans
        if h.status in (EntityStatus.ACTIVE, EntityStatus.SLEEPING)
    )
    arrival_chance = HUMAN_ARRIVAL_CHANCE_LOW_POP if current_human_count < 10 else HUMAN_ARRIVAL_CHANCE_NORMAL
    if rng.random() > arrival_chance:
        return

    # Выбираем случайный граничный сектор
    border_ids = [sid for sid, s in sectors.items() if s.is_border]
    if not border_ids:
        return

    sector_id = rng.choice(border_ids)
    faction = rng.choice(["Бродяги", "Борзые", "Серая лига"])

    new_npc = HumanNPC(
        id=int(rng.random() * 100000),
        faction=faction,
        sector_id=sector_id,
        name=rng.choice(["Новичок", "Странник", "Искатель", "Одиночка"]),
    )
    result.append(new_npc)
    migration_state.human_groups_today += 1


def _process_monster_migration(
    sectors: dict[int, object],
    monsters: list[Monster],
    time,
    migration_state: MigrationState,
    rng: random.Random,
    config: dict,
    result: list[Monster],
) -> None:
    """Пополнение численности монстров через границы (§13.6)."""
    current_day = time.hour // 24

    if current_day != migration_state.last_monster_arrival_day:
        migration_state.monster_groups_today = 0
        migration_state.last_monster_arrival_day = current_day

    # Проверка мягкого минимума
    total_monsters = len([m for m in monsters + result if m.status == EntityStatus.ACTIVE])
    if total_monsters >= MONSTER_SOFT_MIN:
        return

    if migration_state.monster_groups_today >= MONSTER_MAX_GROUPS_PER_DAY:
        return

    # Выбор граничного сектора (не стартового)
    start_ids = {sid for sid, s in sectors.items() if s.is_faction_start}
    border_ids = [sid for sid, s in sectors.items() if s.is_border and sid not in start_ids]
    if not border_ids:
        return

    sector_id = rng.choice(border_ids)
    species = rng.choice(["TerritorialPredator", "ScavengerPack", "LargeMigrator"])

    new_monster = Monster(
        id=int(rng.random() * 100000),
        species=species,
        sector_id=sector_id,
        home_sector_id=sector_id,
    )
    result.append(new_monster)
    migration_state.monster_groups_today += 1


def _process_human_departure(
    humans: list[HumanNPC],
    time,
    rng: random.Random,
) -> None:
    """Обработка выхода людей из Зоны (§14.6)."""
    for npc in humans:
        if npc.status == EntityStatus.ACTIVE and npc.health < 20:
            # Тяжелораненые могут попытаться выйти
            if rng.random() < 0.05:  # 5% шанс попытаться выйти
                # В полной версии здесь была бы проверка пути к границе
                npc.status = EntityStatus.EXILED
