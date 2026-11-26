"""Фаза 0: Проверка состояния мира и состава групп.

Этап 3, Промпт 3.4: тело перенесено из engine.py в standalone функцию.
Работает с SimulationContext, вспомогательные методы вызываются через ctx.engine_ref.
Тело: набор вызовов вспомогательных методов (логика НЕ переписана).
"""

from __future__ import annotations

from zonesim.simulation.context import SimulationContext
from zonesim.world.groups import sync_human_groups, sync_monster_groups
from zonesim.knowledge.expiry import expire_findings
from zonesim.world.shelter import update_shelter_participants, free_emptied_shelters


def run_phase0_check(ctx: SimulationContext) -> None:
    """Фаза 0: Проверка состояния мира и состава групп."""
    engine = ctx.engine_ref
    state = ctx.state
    hour = state.time.hour

    sync_human_groups(state)
    sync_monster_groups(state)
    expire_findings(state, hour)
    update_shelter_participants(state, hour)
    # Освобождаем укрытия, если монстры ушли (§13.7)
    free_emptied_shelters(state, hour)
