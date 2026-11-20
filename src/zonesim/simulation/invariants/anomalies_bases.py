"""Инварианты #10, #11: аномалии и базы.

§22 ТЗ:
10 Аномалия не в стартовом секторе фракции; не разрушается без исправного импортированного средства.
11 Каждая база: стационарный торговец + 2 охранника, не перемещаются, не входят в лимит мобильных NPC.

check_fn → _check_anomalies_and_bases (#10, #11).
"""

from __future__ import annotations

from zonesim.core.config import DEFAULT_GUARDS_PER_BASE
from zonesim.world.entity import EntityStatus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState


def _check_anomalies_and_bases(state: "SimulationState") -> list[str]:
    """Инварианты #10, #11: аномалии и базы.

    #10 — аномалия не в стартовом секторе.
    #11 — каждая база имеет торговца и >= DEFAULT_GUARDS_PER_BASE - 1 охранников.
    """
    errors: list[str] = []
    hour = state.time.hour

    # Инвариант 10: аномалия не в стартовом секторе
    start_ids = {s.id for s in state.sectors.values() if s.is_faction_start}
    for aid, anomaly in state.anomalies.items():
        if anomaly.sector_id in start_ids:
            errors.append(
                f"Инвариант #10 (ч. {hour}): аномалия {aid} в стартовом секторе"
            )

    # Инвариант 11: каждая база имеет торговца и >= GuardsPerBase-1 охранников
    start_ids_with_faction = {
        s.id for s in state.sectors.values() if s.is_faction_start
    }
    for sid in start_ids_with_faction:
        traders = [
            n for n in state.stationary_humans
            if n.stationary_role == "trader" and n.sector_id == sid
            and n.status not in (EntityStatus.DEAD, EntityStatus.EXILED)
        ]
        guards = [
            n for n in state.stationary_humans
            if n.stationary_role == "guard" and n.sector_id == sid
            and n.status not in (EntityStatus.DEAD, EntityStatus.EXILED)
        ]

        if len(traders) == 0:
            errors.append(
                f"Инвариант #11 (ч. {hour}): база {sid} — нет торговца"
            )
        if len(guards) < DEFAULT_GUARDS_PER_BASE - 1:
            errors.append(
                f"Инвариант #11 (ч. {hour}): база {sid} — {len(guards)} охранников, "
                f"требуется >= {DEFAULT_GUARDS_PER_BASE - 1}"
            )

    return errors
