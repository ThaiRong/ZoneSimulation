"""Фаза 0: Проверка состояния мира и состава групп.

Этап 3, Промпт 3.4: тело перенесено из engine.py в standalone функцию.
Работает с SimulationContext, вспомогательные методы вызываются через ctx.engine_ref.
Тело: набор вызовов вспомогательных методов (логика НЕ переписана).
"""

from __future__ import annotations

from zonesim.simulation.context import SimulationContext


def run_phase0_check(ctx: SimulationContext) -> None:
    """Фаза 0: Проверка состояния мира и состава групп."""
    engine = ctx.engine_ref

    engine._sync_human_groups()
    engine._sync_monster_groups()
    engine._expire_findings(ctx.hour)
    engine._update_shelter_participants(ctx.hour)
    # Освобождаем укрытия, если монстры ушли (§13.7)
    engine._free_emptied_shelters(ctx.hour)
