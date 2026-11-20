"""Фаза 2: Окружающая среда и торговля.

Этап 3, Промпт 3.4: делегирование engine._phase2_environment.
Логика НЕ переписана.
"""

from __future__ import annotations

from zonesim.simulation.context import SimulationContext


def run_phase2_environment(ctx: SimulationContext) -> None:
    """Фаза 2: delegate to engine._phase2_environment."""
    ctx.engine_ref._phase2_environment(ctx.hour)
