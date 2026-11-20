"""Фаза 2: Окружающая среда и торговля.

Этап 3, Промпт 3.4: тело перенесено из engine.py.
Работает с SimulationContext, вспомогательные — через ctx.engine_ref.
"""

from __future__ import annotations

from zonesim.simulation.context import SimulationContext


def run_phase2_environment(ctx: SimulationContext) -> None:
    """Фаза 2: Окружающая среда и торговля. (§8)"""
    engine = ctx.engine_ref
    state = ctx.state

    # Формирование артефактов (§12.5, Фаза 2)
    engine._process_artifact_formations(ctx.hour)

    # Добыча артефактов: убираем авто-подбор (§12.4) — артефакты
    # извлекаются только через исследование (§12.3) или разрушение (§12.5).

    # Обработка контрактов
    expired = state.contracts.expire_inactive_contracts(ctx.hour)
    for cid in expired:
        pass  # просрочка контрактов
