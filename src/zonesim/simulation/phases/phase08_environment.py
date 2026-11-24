"""Фаза 8: Воздействие окружающей среды.

Этап 3, Промпт 3.8: тело перенесено из engine.py в standalone функцию.
Работает с SimulationContext; вспомогательные методы — через ctx.engine_ref.
"""

from __future__ import annotations

from zonesim.anomalies.core import AnomalyStatus
from zonesim.anomalies.migration import check_anomaly_migration
from zonesim.simulation.context import SimulationContext


def run_phase8_environment(ctx: SimulationContext) -> None:
    """Фаза 8: Воздействие окружающей среды."""
    engine = ctx.engine_ref
    state = ctx.state
    hour = ctx.hour

    # Перемещение аномалий каждые 48 часов
    if hour % 48 == 0:
        start_ids = {s.id for s in state.sectors.values() if s.is_faction_start}
        for anomaly in state.anomalies.values():
            if anomaly.status == AnomalyStatus.ACTIVE:
                rng_val = state.rng.random()
                migration = check_anomaly_migration(
                    anomaly, hour,
                    sector_ids=engine._anomaly_move_candidates(anomaly),
                    faction_start_ids=start_ids,
                    rng_value=rng_val,
                )
                if migration["moved"]:
                    engine._roll_trail_blockage(anomaly)
                    state.news_manager.create_event(
                        hour=hour,
                        minute=0,
                        sector_id=migration["to_sector"],
                        event_type="anomaly_move",
                        participants=[],
                        result="moved",
                        importance=20,
                        summary=f"Аномалия {anomaly.id} переместилась",
                        details=migration,
                    )

    # Формирование артефактов вынесено в _phase2_environment (§12.7, Фаза 2)
