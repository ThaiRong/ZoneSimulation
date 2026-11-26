"""Боевые результаты: бессознательное состояние, смерть и урон. Основано на §11.10 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zonesim.world.entity import EntityStatus

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState
    from zonesim.world.entity import HumanNPC


def resolve_zero_health(state, npc: HumanNPC, start_health: int) -> str:
    """Здоровье 0: бессознательное состояние по шансу §11.10, иначе гибель."""
    from zonesim.combat.unconscious import calculate_unconscious_chance, resolve_unconscious_check

    start_share = start_health / npc.max_health if npc.max_health > 0 else 0.0
    chance = calculate_unconscious_chance(start_share)
    if resolve_unconscious_check(state.rng.random(), chance) == "unconscious":
        npc.status = EntityStatus.UNCONSCIOUS
        npc.unconscious_reason = "health_zero"
        npc.unconscious_start_hour = state.time.hour
        return "unconscious"
    npc.status = EntityStatus.DEAD
    return "dead"


def set_unconscious_or_dead(
    state,
    npc: HumanNPC,
    start_health: int,
    hour: int,
    cause: str,
) -> None:
    """Устанавливает статус NPC (бессознательный/мёртвый) и логирует событие.

    Вызывается когда npc.health <= 0. (§11.10)
    """
    outcome = resolve_zero_health(state, npc, start_health)
    state.news_manager.create_event(
        hour=hour, minute=0, sector_id=npc.sector_id,
        event_type="npc_death" if outcome == "dead" else "npc_unconscious",
        participants=[npc.id], result=outcome,
        importance=60 if outcome == "dead" else 40,
        summary=f"NPC {npc.id}: {outcome} ({cause})",
        details={"cause": cause},
    )
