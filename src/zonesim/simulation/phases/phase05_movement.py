"""Фаза 5: Перемещение.

Этап 3, Промпт 3.6: тело перенесено из engine.py в standalone функцию.
Работает с SimulationContext, вспомогательные методы вызываются через ctx.engine_ref.
"""

from __future__ import annotations

from zonesim.ai import (
    ARTIFACT_SEARCH,
    EXIT,
    EXPLORE,
    HELP,
    RESEARCH,
    REST,
    SHELTER,
    choose_explore_target,
    edge_cost,
    edge_key,
)
from zonesim.needs.sleep import STAMINA_COST_MOVEMENT, update_stamina
from zonesim.simulation.context import SimulationContext
from zonesim.world.entity import EntityStatus
from zonesim.world.faction import home_sector_id
from zonesim.world.shelter import shelter_targets
from zonesim.world.trails import trail_set


def run_phase5_movement(ctx: SimulationContext) -> None:
    """Фаза 5: Перемещение групп людей и монстров."""
    engine = ctx.engine_ref
    state = ctx.state
    hour = ctx.hour
    is_night = ctx.is_night

    engine._moved_human_ids: set[int] = set()

    # Запрет движения во время выброса (§12.7, #20)
    if engine._emission_active(hour):
        return

    border_ids = {s.id for s in state.sectors.values() if s.is_border}

    npcs = {npc.id: npc for npc in state.humans}
    for group in state.human_groups.values():
        leader = npcs.get(group.leader_id) if group.leader_id is not None else None
        if leader is None:
            continue
        members = [npcs[mid] for mid in group.members if mid in npcs]
        if not members or any(npc.status != EntityStatus.ACTIVE for npc in members):
            continue  # группа не оставляет спящих и бессознательных членей
        if engine._emission_active(hour):
            # Во время выброса разрешено ТОЛЬКО движение к Shelter
            if group.intention == SHELTER:
                # Продолжаем обработку SHELTER ниже
                pass
            else:
                continue  # остальные движения запрещены

        avoid = engine._known_anomaly_sectors(leader)
        trails = trail_set(state)
        if group.intention == EXPLORE:
            memory = state.visit_memory.setdefault(leader.id, {})
            destination = choose_explore_target(
                state.sectors, group.sector_id, memory, hour,
                avoid, state.rng,
            )
            if destination is not None:
                cost = edge_cost(trails, group.sector_id, destination)
                if cost <= 1.0 + 1e-9:
                    engine._apply_human_move(group, members, [destination], npcs, hour)
            continue

        # Для RESEARCH — не избегать секторов с аномалиями (цель — к ним!)
        research_target = group.target_sector_id if group.intention == RESEARCH else None
        group_avoid = set() if group.intention == RESEARCH else avoid

        target_ids: set[int] | None = None
        if group.intention == EXIT:
            target_ids = border_ids
        elif group.intention == REST:
            home = home_sector_id(state.sectors, leader.faction, engine._home_cache)
            if home is not None and group.sector_id != home:
                target_ids = {home}
        elif group.intention == HELP:
            distress = engine._active_distress_for(group, hour)
            if distress is not None and group.sector_id != distress["sector_id"]:
                target_ids = {distress["sector_id"]}
        elif group.intention == SHELTER:
            target_ids = shelter_targets(engine.state, group, hour)
        elif group.intention == RESEARCH and group.target_sector_id is not None:
            target_ids = {group.target_sector_id}
        elif group.intention == ARTIFACT_SEARCH and group.target_sector_id is not None:
            target_ids = {group.target_sector_id}
        if not target_ids:
            continue
        path = engine._walk(group.sector_id, target_ids, group_avoid, points=1.0)
        if path:
            engine._apply_human_move(group, members, path, npcs, hour)

    engine._move_monster_groups(hour)
