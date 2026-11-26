"""Уничтожение аномалий группами. Основано на §15 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zonesim.world.item import ItemType
from zonesim.anomalies.core import AnomalyStatus

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState
    from zonesim.world.group import HumanGroup


def group_can_destroy(state, group: HumanGroup, members) -> bool:
    """Проверяет возможность уничтожения аномалии группой. (§15)"""
    from zonesim.world.groups import group_kit

    anomaly = next(
        (
            a for a in state.anomalies.values()
            if a.sector_id == group.sector_id and a.status == AnomalyStatus.ACTIVE
        ),
        None,
    )
    if anomaly is None:
        return False
    _, kit = group_kit(
        state,
        members, ItemType.DESTROY_KIT,
        lambda item: item.properties.get("target_anomaly_type") == anomaly.anomaly_type.value,
    )
    return kit is not None
