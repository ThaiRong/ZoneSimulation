"""Система сна, выносливости и истощения. Основано на §14.1-14.2 ТЗ."""

from __future__ import annotations

from zonesim.core.time import PhaseOfDay
from zonesim.world.entity import EntityStatus
from zonesim.world.group import HumanGroup, MonsterGroup
from zonesim.ai import SLEEP


# Стоимость выносливости за час
STAMINA_COST_AWAKE = 2.0  # базовый расход за бодрствование
STAMINA_COST_MOVEMENT = 3.0  # за перемещение
STAMINA_COST_COMBAT = 5.0  # за бой
STAMINA_COST_RESEARCH = 4.0  # за исследование

# Время полного восстановления
HUMAN_COMFORT_HOURS = 4  # 4 часа комфортного сна
HUMAN_NONCOMFORT_HOURS = 6  # 6 часов некомфортного сна
MONSTER_COMFORT_HOURS = 2  # 2 часа для монстров

# Минимальное время бессознательности от истощения
UNCONSCIOUS_MIN_HOURS = 1
UNCONSCIOUS_MIN_STAMINA_PCT = 0.10  # 10% от макс. выносливости


def calculate_stamina_cost(action: str, is_night: bool = False) -> float:
    """Вычисляет стоимость действия в очках выносливости."""
    base_costs = {
        "rest": 0.0,
        "guard": 1.0,
        "movement": STAMINA_COST_MOVEMENT,
        "combat": STAMINA_COST_COMBAT,
        "research": STAMINA_COST_RESEARCH,
        "stash": STAMINA_COST_RESEARCH,
        "shelter": STAMINA_COST_RESEARCH,
        "trade": 1.5,
        "ambush": 2.0,
        "hunt": STAMINA_COST_COMBAT,
        "attempt_exit": STAMINA_COST_MOVEMENT * 1.5,
    }
    cost = base_costs.get(action, STAMINA_COST_AWAKE)
    # Ночью чуть дороже из-за повышенного напряжения
    if is_night:
        cost *= 1.1
    return cost


def update_stamina(entity, cost: float, action: str, time) -> bool:
    """
    Обновляет выносливость сущности.
    Возвращает True если произошло истощение.
    """
    if cost <= 0:
        return False

    current = getattr(entity, "stamina", 0)
    max_st = getattr(entity, "max_stamina", 100)

    entity.stamina = max(0, current - cost)

    # Проверка истощения
    if entity.stamina <= 0 and current > 0:
        entity.status = EntityStatus.UNCONSCIOUS
        entity.unconscious_start_hour = time.hour
        entity.unconscious_reason = "exhaustion"
        return True

    return False


def human_sleep_recover(
    group: HumanGroup,
    npcs: dict[int, object],
    time,
    rng,
    stationary: dict[int, object] | None = None,
    shelters: dict[int, object] | None = None,
    temp_shelters: dict[int, object] | None = None,
    sectors: dict[int, object] | None = None,
    faction: str | None = None,
) -> float:
    """
    Восстанавливает выносливость спящим NPC группы.
    Возвращает сколько выносливости восстановлено.
    """
    if not group or not group.members:
        return 0.0

    is_comfort = group.is_comfort_sleep_possible(
        npcs,
        stationary or {},
        shelters or {},
        temp_shelters or {},
        sectors or {},
        group.sector_id,
        faction,
    )
    recovery_rate = 1.0 / HUMAN_COMFORT_HOURS if is_comfort else 1.0 / HUMAN_NONCOMFORT_HOURS

    total_recovered = 0.0
    for member_id in group.members:
        npc = npcs.get(member_id)
        if not npc:
            continue

        # Спящие восстанавливают, бодрствующие — нет (они охраняют)
        if npc.status == EntityStatus.SLEEPING:
            max_st = getattr(npc, "max_stamina", 100)
            recovery = max_st * recovery_rate
            npc.stamina = min(max_st, npc.stamina + recovery)
            total_recovered += recovery

            # Проверка пробуждения
            if npc.stamina >= getattr(npc, "max_stamina", 100):
                npc.status = EntityStatus.ACTIVE
                npc.awake_since_hour = time.hour  # сон необходим раз в 24 часа (§14.1)

        elif npc.status == EntityStatus.UNCONSCIOUS:
            # Бессознательные тоже медленно приходят в себя
            max_st = getattr(npc, "max_stamina", 100)
            recovery = max_st * recovery_rate * 0.5
            npc.stamina = min(max_st, npc.stamina + recovery)
            total_recovered += recovery

            if npc.stamina >= max_st * UNCONSCIOUS_MIN_STAMINA_PCT:
                # Проверяем: прошло ли минимум 1 час
                start_h = getattr(npc, "unconscious_start_hour", 0)
                if time.hour - start_h >= UNCONSCIOUS_MIN_HOURS:
                    npc.status = EntityStatus.SLEEPING
                    npc.intention = SLEEP  # инвариант #5
                    npc.unconscious_start_hour = time.hour

    return total_recovered


def monster_sleep_recover(group: MonsterGroup, monsters: dict[int, object], time) -> float:
    """
    Восстанавливает выносливость спящих монстров.
    Монстрам достаточно 2 часов, всегда комфортно.
    """
    if not group or not group.members:
        return 0.0

    recovery_rate = 1.0 / MONSTER_COMFORT_HOURS
    total_recovered = 0.0

    for member_id in group.members:
        monster = monsters.get(member_id)
        if not monster:
            continue

        if monster.status == EntityStatus.SLEEPING:
            max_st = getattr(monster, "max_stamina", 100)
            recovery = max_st * recovery_rate
            monster.stamina = min(max_st, monster.stamina + recovery)
            total_recovered += recovery

            if monster.stamina >= getattr(monster, "max_stamina", 100):
                monster.status = EntityStatus.ACTIVE

        elif monster.status == EntityStatus.UNCONSCIOUS:
            max_st = getattr(monster, "max_stamina", 100)
            recovery = max_st * recovery_rate * 0.5
            monster.stamina = min(max_st, monster.stamina + recovery)
            total_recovered += recovery

            start_h = getattr(monster, "unconscious_start_hour", 0)
            if time.hour - start_h >= UNCONSCIOUS_MIN_HOURS:
                if monster.stamina >= max_st * UNCONSCIOUS_MIN_STAMINA_PCT:
                    monster.status = EntityStatus.SLEEPING

    return total_recovered


def is_comfortable_sleep_needed(time_obj, current_phase) -> bool:
    """Определяет, нужно ли существам искать комфортный сон."""
    # Монстры пытаются спать утром и вечером (§13.6)
    if current_phase in (PhaseOfDay.MORNING, PhaseOfDay.EVENING):
        return True
    # Ночью все хотят спать
    if current_phase == PhaseOfDay.NIGHT:
        return True
    return False


def calculate_guard_shift(group: HumanGroup, npcs: dict[int, object], hour: int) -> None:
    """Организует смены караула: минимум один бодрствует."""
    awake_members = [
        mid for mid in group.members
        if mid in npcs and npcs[mid].status != EntityStatus.SLEEPING
    ]

    if not awake_members:
        return

    # Если все спят — будим одного
    if len(awake_members) == 0:
        group.guard_schedule.append({
            "npc_id": group.members[0],
            "start_hour": hour,
        })
