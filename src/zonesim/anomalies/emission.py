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


def emission_active(state, hour: int) -> bool:
    return is_emission_active(
        state.emission_start_hour, state.emission_end_hour, hour,
    )


def emission_known(state, hour: int) -> bool:
    return is_emission_known(state.emission_warning_hour, hour)


def process_emission_schedule(state, hour: int) -> None:
    if state.next_emission_hour < 0 and state.emission_start_hour < 0:
        state.next_emission_hour = hour + schedule_next_emission(state.rng)
        state.emission_warning_hour = -1
    if state.emission_start_hour >= 0 and hour >= state.emission_end_hour:
        # завершение выброса
        state.emission_start_hour = -1
        state.emission_end_hour = -1
        state.emission_warning_hour = -1
        state.emission_exposed.clear()
        state.next_emission_hour = hour + schedule_next_emission(state.rng)
        state.news_manager.create_event(
            hour=hour, minute=0, sector_id=0,
            event_type="emission", participants=[], result="ended",
            importance=60, summary="Выброс завершился",
            details={"next_emission_hour": state.next_emission_hour},
        )
    elif emission_active(state, hour):
        pass  # выброс продолжается
    elif state.next_emission_hour >= 0 and hour >= state.next_emission_hour:
        state.emission_start_hour = hour
        state.emission_end_hour = hour + roll_duration(state.rng)
        state.next_emission_hour = -1  # перепланируется при завершении
        from zonesim.anomalies.migration import move_all_anomalies as _move_all_anomalies
        _move_all_anomalies(state, hour)
        state.news_manager.create_event(
            hour=hour, minute=0, sector_id=0,
            event_type="emission", participants=[], result="started",
            importance=70,
            summary=f"Начался выброс (до часа {state.emission_end_hour})",
            details={"end_hour": state.emission_end_hour},
        )
    elif state.emission_warning_hour < 0 and hour >= state.next_emission_hour - 6:
        lead = roll_warning_lead(state.rng)
        state.emission_warning_hour = state.next_emission_hour - lead
        if hour >= state.emission_warning_hour:
            broadcast_emission_warning(state, hour)


def broadcast_emission_warning(state, hour: int) -> None:
    from zonesim.knowledge import KnowledgeBase, KnowledgeType
    for npc in state.humans:
        if npc.status in (EntityStatus.DEAD, EntityStatus.EXILED):
            continue
        kb = state.knowledge_bases.setdefault(npc.id, KnowledgeBase())
        kb.add_manual(
            npc.id, KnowledgeType.EVENT, subject_id=state.next_emission_hour,
            payload={
                "type": "emission",
                "start": state.next_emission_hour,
                "end": state.emission_end_hour
                if emission_active(state, hour) else -1,
            },
            hour=hour,
        )
    state.news_manager.create_event(
        hour=hour, minute=0, sector_id=0,
        event_type="emission", participants=[], result="warning",
        importance=65,
        summary=f"Предупреждение: выброс ожидается к часу {state.next_emission_hour}",
        details={"start": state.next_emission_hour},
    )


def mark_group_emission_exposed(state, group, hour: int) -> None:
    """Записывает группу в emission_exposed и применяет урон (§12.7).

    Вызывается когда группа НЕ shelter во время выброса.
    Первый час: урон + лёгкая травма; второй час: гибель.
    """
    from zonesim.world.groups import active_members
    from zonesim.combat.medkit import emergency_medkit
    from zonesim.combat.results import set_unconscious_or_dead
    from zonesim.world.entity import EntityStatus

    first_hour = state.emission_exposed.get(group.id)
    if first_hour is None:
        state.emission_exposed[group.id] = hour
        members = active_members(state, group)
        if not members:
            return
        for npc in members:
            if npc.health_share < 0.5:
                emergency_medkit(state, npc, members)
            start = npc.health
            npc.health = max(0, npc.health - int(npc.max_health * EMISSION_EXPOSURE_DAMAGE))
            npc.stamina = max(1, npc.stamina - 5)  # гарантированная лёгкая травма
            npc.attentiveness = max(1, npc.attentiveness - 3)
            if npc.health <= 0:
                set_unconscious_or_dead(state, npc, start, hour, cause="emission")
        state.news_manager.create_event(
            hour=hour, minute=30, sector_id=group.sector_id,
            event_type="emission", participants=[m.id for m in members],
            result="exposed", importance=50,
            summary=f"Группа {group.id} оказалась под выбросом без укрытия",
            details={"group_id": group.id},
        )
    elif hour - first_hour >= EMISSION_EXPOSURE_KILL_HOUR - 1:
        members = active_members(state, group)
        for npc in members:
            npc.health = 0
            npc.status = EntityStatus.DEAD
        state.emission_exposed.pop(group.id, None)
        state.news_manager.create_event(
            hour=hour, minute=30, sector_id=group.sector_id,
            event_type="emission", participants=[m.id for m in members],
            result="wiped", importance=60,
            summary=f"Группа {group.id} погибла под выбросом",
            details={"group_id": group.id},
        )


def apply_emission_exposure(state, hour: int) -> None:
    """Урон группам, не успевшим укрыться. (§12.7)

    Группы НЕ перемещаются во время выброса (запрет в Phase 5).
    Группы в permanent shelter — защищены.
    Группы вне shelter — получают урон.
    """
    from zonesim.world.groups import active_members

    for group in state.human_groups.values():
        members = active_members(state, group)
        if not members:
            state.emission_exposed.pop(group.id, None)
            continue
        # Используем единый helper — group.sector_id (синхронизирован с членами)
        if is_group_emission_sheltered(state, group):
            state.emission_exposed.pop(group.id, None)
            continue
        mark_group_emission_exposed(state, group, hour)
