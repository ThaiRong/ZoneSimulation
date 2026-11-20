"""Фаза 1: Запланированные события (миграции, эмиссии, охрана, торговцы).

Этап 3, Промпт 3.4: тело перенесено из engine.py.
Все access к state через ctx.state, вызовы вспомогательных — через ctx.engine_ref.
"""

from __future__ import annotations

from zonesim.generation.migration import process_migration
from zonesim.simulation.context import SimulationContext
from zonesim.world.entity import EntityStatus, HumanNPC, Monster
from zonesim.world.group import HumanGroup


def run_phase1_scheduled(ctx: SimulationContext) -> None:
    """Фаза 1: Запланированные события."""
    engine = ctx.engine_ref
    state = ctx.state
    hour = ctx.hour

    # === Миграция людей и монстров ===
    border_ids = {s.id for s in state.sectors.values() if s.is_border}
    start_ids = {s.id for s in state.sectors.values() if s.is_faction_start}

    new_entities = process_migration(
        state.sectors,
        state.humans,
        state.monsters,
        state.time,
        state.migration_state,
        state.rng,
    )

    for entity in new_entities:
        if isinstance(entity, Monster):
            entity.id = state.next_monster_id
            state.next_monster_id += 1
            state.monsters.append(entity)
        elif isinstance(entity, HumanNPC):
            entity.id = state.next_human_id
            state.next_human_id += 1
            group = HumanGroup(
                id=state.next_group_id,
                members=[entity.id],
                sector_id=entity.sector_id,
                leader_id=entity.id,
            )
            state.next_group_id += 1
            entity.group_id = group.id
            state.human_groups[group.id] = group
            state.humans.append(entity)
            engine._give_starting_equipment(entity)

    # === Монстры: пополнение численности ===
    active_monsters = sum(
        1 for m in state.monsters if m.status == EntityStatus.ACTIVE
    )
    new_monsters = state.monster_migration.check_and_spawn(
        active_monster_count=active_monsters,
        border_sectors=list(border_ids),
        faction_start_ids=start_ids,
        hour=hour,
        rng=state.rng,
    )
    for m in new_monsters:
        m.id = state.next_monster_id
        state.next_monster_id += 1
    state.monsters.extend(new_monsters)
    if new_entities or new_monsters:
        engine._sync_monster_groups()

    # === Эмиссия ===
    engine._process_emission_schedule(hour)
    if engine._emission_active(hour):
        engine._apply_emission_exposure(hour)

    # === Укрытия ===
    engine._process_shelter_occupation(hour)
    engine._free_emptied_shelters(hour)

    # === Охрана ===
    engine._process_guard_rotation(hour)

    # === Ситуативный торговец ===
    engine._process_conditional_trader_schedule(hour)
    engine._expire_conditional_trader_if_expired(hour)
