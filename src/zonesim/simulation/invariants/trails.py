"""Инвариант #24: одна аномалия = одна тропа.

§22 ТЗ:
24 Перекрытая тропа связана ровно с одной блокирующей аномалией; после перемещения
   аномалии знание прохода устаревшее, блокировка старой тропы снимается.

check_fn → _check_trail_blockages (#24).
coverage: full.
"""

from __future__ import annotations

from zonesim.anomalies.core import AnomalyStatus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _check_trail_blockages(state: "SimulationState") -> list[str]:
    """Инвариант #24: тропа не перекрыта более чем одной активной аномалией."""
    errors: list[str] = []
    hour = state.time.hour

    for aid, anomaly in state.anomalies.items():
        if anomaly.status != AnomalyStatus.ACTIVE:
            continue
        if not getattr(anomaly, 'on_trail', False):
            continue
        trail_id = getattr(anomaly, 'trail_id', None)
        if trail_id is None:
            continue
        same_trail = sum(
            1 for other_id, other in state.anomalies.items()
            if other_id != aid
            and other.status == AnomalyStatus.ACTIVE
            and getattr(other, 'trail_id', None) == trail_id
        )
        if same_trail > 0:
            errors.append(
                f"Инвариант #24 (ч. {hour}): аномалия {aid} на тропе {trail_id} "
                f"перекрывается {same_trail + 1} активными аномалиями"
            )

    return errors
