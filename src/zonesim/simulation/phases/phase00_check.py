"""Фаза 0: Проверка состояния мира и состава групп.

Этап 3, Промпт 3.4: извлечена из engine.py как обёртка поверх
methods engine. Логика НЕ переписана — только делегирование.
"""

from __future__ import annotations

from zonesim.simulation.context import SimulationContext


def run_phase0_check(ctx: SimulationContext) -> None:
    """Фаза 0: delegate to engine._phase0_check + helpers."""
    ctx.engine_ref._phase0_check(ctx.hour)
