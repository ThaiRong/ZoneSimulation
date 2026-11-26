"""Журналирование изменений отношений. Основано на §17 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState


def log_relation_change(state, hour: int, faction_a: str, faction_b: str,
                        delta: int, event_id: int | None) -> None:
    """Записывает изменение отношений в журнал (§17 инвариант)."""
    state.relation_change_journal.append({
        "hour": hour,
        "faction_a": faction_a,
        "faction_b": faction_b,
        "delta": delta,
        "event_id": event_id,
    })


def check_and_journal_relations(state, hour: int) -> None:
    """
    Сравнивает текущие отношения со снимком и логирует изменения.
    Должен вызываться ПОСЛЕ фаз, которые могут менять отношения.
    """
    fr = state.faction_relations
    snap = state.prev_relation_snapshot
    for (a, b), current_val in fr._relations.items():
        prev_val = snap.get((a, b), current_val)
        if current_val != prev_val:
            delta = current_val - prev_val
            # event_id = None означает изменение БЕЗ события — нарушение
            log_relation_change(state, hour, a, b, delta, event_id=None)
