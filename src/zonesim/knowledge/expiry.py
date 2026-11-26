"""Срок годности находок. Основано на §10.3 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState


def expire_findings(state, hour: int) -> None:
    """Удаляет находки старше 24 часов. (§10.3)"""
    remaining = []
    for corpse in state.corpses:
        if corpse.status == "available" and hour - corpse.created_hour >= 24:
            for item_id in list(corpse.items):
                state.items.pop(item_id, None)
            state.news_manager.create_event(
                hour=hour, minute=0, sector_id=corpse.sector_id,
                event_type="finding_expired", participants=[], result="expired",
                importance=5,
                summary=f"Находка в секторе {corpse.sector_id} исчезла",
                details={"corpse_id": corpse.id},
            )
            continue
        remaining.append(corpse)
    state.corpses = remaining
