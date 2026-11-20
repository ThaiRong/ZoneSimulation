"""Фаза 1: Запланированные события.

Этап 3, Промпт 3.4: делегирование engine._phase1_scheduled.
Логика НЕ переписана.
"""

from __future__ import annotations

from zonesim.simulation.context import SimulationContext


def run_phase1_scheduled(ctx: SimulationContext) -> None:
    """Фаза 1: delegate to engine._phase1_scheduled."""
    ctx.engine_ref._phase1_scheduled(ctx.hour, ctx.day)
