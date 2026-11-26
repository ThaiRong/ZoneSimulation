"""Периодический выброс. Основано на §12.7 ТЗ."""

from __future__ import annotations

# Стартовые балансовые настройки (настраиваемые заглушки §12.7)
EMISSION_PERIOD_MIN = 48       # раз в 48–96 часов
EMISSION_PERIOD_MAX = 96
EMISSION_DURATION_MIN = 2      # длительность 2–4 часа
EMISSION_DURATION_MAX = 4
EMISSION_WARNING_MIN = 4       # предупреждение за 4–6 часов
EMISSION_WARNING_MAX = 6
EMISSION_ARTIFACT_ACCELERATION = 8    # интервал формирования короче в 5–10 раз
EMISSION_EXPOSURE_DAMAGE = 0.55       # 50+% макс. здоровья за первый час
EMISSION_EXPOSURE_KILL_HOUR = 2       # второй час открытого пребывания — гибель
EMISSION_TRAIL_BLOCK_CHANCE = 0.25    # вероятность перекрытия тропы аномалией
EMISSION_MONSTER_SHELTER_CHANCE = 0.10  # 1–20% раз в сутки на свободное укрытие
EMISSION_MONSTER_STAY_MIN = 12
EMISSION_MONSTER_STAY_MAX = 24
SHELTER_COUNT = 8


def schedule_next_emission(rng) -> int:
    """Час следующего выброса."""
    return rng.randint(EMISSION_PERIOD_MIN, EMISSION_PERIOD_MAX)


def roll_warning_lead(rng) -> int:
    return rng.randint(EMISSION_WARNING_MIN, EMISSION_WARNING_MAX)


def roll_duration(rng) -> int:
    return rng.randint(EMISSION_DURATION_MIN, EMISSION_DURATION_MAX)


def is_emission_active(start_hour: int, end_hour: int, hour: int) -> bool:
    return start_hour >= 0 and start_hour <= hour < end_hour


def is_emission_known(warning_hour: int, hour: int) -> bool:
    """Сведения о выбросе уже разосланы (предупреждение не устаревает)."""
    return warning_hour >= 0 and hour >= warning_hour


def emission_safe_sectors(state) -> set[int]:
    """Постоянные секторы, защищающие от выброса (§12.7, #20).

    Включает:
    - Сектора StormShelter (стационарные убежища)
    - Стартовые сектора фракций (базы)
    - Сектора активных стационарных торговцев
    Временные убежища (temp_shelters) НЕ защищают (§12.7).
    """
    from zonesim.world.entity import EntityStatus
    return {
        s.sector_id for s in state.shelters.values()
    } | {
        s.id for s in state.sectors.values() if s.is_faction_start
    } | {
        npc.sector_id for npc in state.stationary_humans
        if npc.stationary_role == "trader" and npc.status == EntityStatus.ACTIVE
    }


def is_group_emission_sheltered(state, group) -> bool:
    """Проверяет, укрота ли группа от выброса (§12.7, #20).

    Использует group.sector_id (синхронизирован с членами группы)
    и единое множество безопасных секторов.
    """
    safe = emission_safe_sectors(state)
    return group.sector_id in safe
