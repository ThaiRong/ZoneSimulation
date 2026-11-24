"""Фаза 10: Автосохранение и отчёт.

Этап 3, Промпт 3.8: тело перенесено из engine.py в standalone функцию.
Работает с SimulationContext; вспомогательные методы — через ctx.engine_ref.
"""

from __future__ import annotations

from zonesim.simulation.context import SimulationContext


def run_phase10_report(ctx: SimulationContext) -> None:
    """Фаза 10: автосохранение после завершённого часа."""
    engine = ctx.engine_ref
    state = ctx.state
    hour = ctx.hour

    if engine.save_manager is None:
        return
    settings = state.config.get("persistence", {})
    if not settings.get("autosave_enabled", True):
        return
    interval = settings.get("autosave_interval", 6)
    slot_count = settings.get("autosave_slots", 3)
    if interval <= 0 or slot_count <= 0 or state.time.hour % interval != 0:
        return
    slot_index = (state.time.hour // interval - 1) % slot_count
    engine.save(f"autosave_{slot_index}")
