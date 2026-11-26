"""Фаза 9: Последствия.

Этап 3, Промпт 3.8: тело перенесено из engine.py в standalone функцию.
Работает с SimulationContext; вспомогательные методы — через ctx.engine_ref.
"""

from __future__ import annotations

from zonesim.simulation.context import SimulationContext
from zonesim.world.groups import sync_human_groups


def run_phase9_consequences(ctx: SimulationContext) -> None:
    """Фаза 9: последствия и актуализация состава групп. (§8)

    — Синхронизация групп
    — Экспорт артефактов и ресурсов (§16.4)
    """
    engine = ctx.engine_ref
    state = ctx.state
    hour = ctx.hour

    sync_human_groups(state)

    # Экспорт артефактов и ресурсов (ежедневно)
    if state.time.hour % 24 == 7:
        engine._process_daily_export(hour)
