"""Фаза 7: Основные действия.

Этап 3, Промпт 3.7: тело перенесено из engine.py в standalone функцию.
Работает с SimulationContext; вспомогательные методы — через ctx.engine_ref.
"""

from __future__ import annotations

from zonesim.ai import (
    ARTIFACT_SEARCH,
    CAPTURE,
    CREATE_SHELTER,
    DESTROY,
    EXIT,
    HELP,
    RESEARCH,
    REST,
    SLEEP,
)
from zonesim.needs.sleep import (
    STAMINA_COST_AWAKE,
    update_stamina,
)
from zonesim.simulation.context import SimulationContext
from zonesim.world.entity import EntityStatus


def run_phase7_actions(ctx: SimulationContext) -> None:
    """Фаза 7: сначала бои, затем остальные основные действия (§8)."""
    engine = ctx.engine_ref
    state = ctx.state
    hour = ctx.hour
    is_night = ctx.is_night

    engine._execute_battles(hour)
    fed_monster_groups = engine._process_monster_feeding(hour)
    acted_groups = set()
    for group in state.human_groups.values():
        if engine._process_corpse_action(group, hour) is not None:
            acted_groups.add(group.id)
    for group in state.human_groups.values():
        if group.id in acted_groups or group.intention not in (DESTROY, CAPTURE):
            continue
        if group.intention == DESTROY:
            done = engine._process_destroy_anomaly(group, hour, is_night)
        else:
            done = engine._process_capture_monster(group, hour)
        if done:
            acted_groups.add(group.id)

    resting_groups = [
        group for group in state.human_groups.values()
        if group.intention == REST
    ]
    engine._process_rest_exchanges(hour, resting_groups)
    engine._process_rest_trade(hour, resting_groups)

    # Создание убежищ (§7.10)
    for group in state.human_groups.values():
        if group.intention != CREATE_SHELTER:
            continue
        if engine._process_create_shelter(group, hour):
            acted_groups.add(group.id)
            group.intention = REST  # после создания — отдых в убежище
    for group in state.human_groups.values():
        if group.id in acted_groups or group.intention != HELP:
            continue
        distress = engine._active_distress_for(group, hour)
        members = engine._active_members(group)
        if distress is None or not members:
            continue
        if group.sector_id == distress["sector_id"]:
            engine._aid_distress_group(group, members, distress, hour)
            acted_groups.add(group.id)
    # _apply_emission_exposure вызывается в фазе 1 — ДО движения групп
    for npc in state.humans:
        if npc.id in engine._combat_human_ids or npc.group_id in acted_groups:
            continue
        if npc.status == EntityStatus.SLEEPING:
            # Инвариант #13: будим SLEEPING если comfort=True но нет защиты
            group = state.human_groups.get(npc.group_id)
            if group and group.comfort:
                if not engine._has_strict_comfort(
                    group,
                    {m.id: m for m in state.humans},
                    {n.id: n for n in state.stationary_humans},
                    state.shelters,
                    state.temp_shelters,
                    state.sectors,
                    npc.sector_id,
                    npc.faction,
                ):
                    # Разбуживаем ВСЕХ SLEEPING NPC группы
                    group.comfort = False
                    for mid in group.members:
                        for m in state.humans:
                            if m.id == mid and m.status == EntityStatus.SLEEPING:
                                m.status = EntityStatus.ACTIVE
                                m.intention = REST
            if not getattr(npc, "on_treatment", False):
                engine._sleep_tick(npc)
            continue
        if npc.status == EntityStatus.UNCONSCIOUS:
            engine._unconscious_tick(npc, hour)
            continue
        if npc.status != EntityStatus.ACTIVE:
            continue

        # Базовый расход выносливости за час бодрствования (§14.1)
        update_stamina(npc, STAMINA_COST_AWAKE, "awake", state.time)
        if npc.status != EntityStatus.ACTIVE:
            continue  # истощение → потеря сознания

        if npc.intention == SLEEP:
            # Инвариант #13: SLEEP только при реальных условиях комфорта
            # (проверка в Phase 7, т.к. shelter мог expire между Phase 4 и Phase 7)
            group = state.human_groups.get(npc.group_id)
            if group and group.comfort:
                if not engine._has_strict_comfort(
                    group,
                    {m.id: m for m in state.humans},
                    {n.id: n for n in state.stationary_humans},
                    state.shelters,
                    state.temp_shelters,
                    state.sectors,
                    npc.sector_id,
                    npc.faction,
                ):
                    # Нет комфорта — отменяем сон
                    npc.intention = REST
                    group.comfort = False

            if npc.intention == SLEEP:
                npc.status = EntityStatus.SLEEPING
                npc.intention = SLEEP  # инвариант #5: спящие имеют SLEEP
        elif npc.intention == REST:
            engine._rest_tick(npc)
        elif npc.intention in (RESEARCH, ARTIFACT_SEARCH):
            engine._research_tick(npc, hour)
        elif npc.intention == EXIT:
            engine._exit_tick(npc, hour)

    engine._process_monster_rest(fed_monster_groups, is_night)
