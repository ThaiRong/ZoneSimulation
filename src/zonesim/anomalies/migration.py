"""Перемещение аномалий. Основано на §12.6 ТЗ."""

from __future__ import annotations

from zonesim.anomalies.core import Anomaly, AnomalyStatus, AnomalyType


def check_anomaly_migration(
    anomaly: Anomaly,
    current_hour: int,
    move_interval: int = 48,
    move_chance: float = 0.25,
    sector_ids: list[int] = None,
    faction_start_ids: set[int] = None,
    rng_value: float = 0.5,
) -> dict:
    """
    Проверяет необходимость перемещения аномалии. (§12.6)
    Каждые 48 часов, шанс 25%.
    Не перемещается в стартовые сектора фракций.
    """
    if anomaly.status != AnomalyStatus.ACTIVE:
        return {"moved": False, "reason": "inactive"}

    # Сбрасываем таймер
    anomaly.move_timer += 1
    if anomaly.move_timer < move_interval:
        return {"moved": False, "timer": anomaly.move_timer}

    anomaly.move_timer = 0

    # Проверка шанса
    if rng_value * 100 >= move_chance * 100:
        return {"moved": False, "rng_failed": True}

    # Перемещение
    if not sector_ids or not faction_start_ids:
        return {"moved": False, "reason": "no_valid_sectors"}

    # Выбираем допустимый сектор (не стартовый) — детерминированно по rng_value
    valid_targets = [s for s in sector_ids if s not in faction_start_ids]
    if not valid_targets:
        return {"moved": False, "reason": "no_valid_targets"}

    new_sector = valid_targets[int(rng_value * len(valid_targets)) % len(valid_targets)]
    old_sector = anomaly.sector_id

    anomaly.sector_id = new_sector

    return {
        "moved": True,
        "from_sector": old_sector,
        "to_sector": new_sector,
        "timer": 0,
    }


def calculate_anomaly_move_timer(
    anomaly: Anomaly,
) -> int:
    """Возвращает оставшееся время до следующей проверки перемещения."""
    if anomaly.status != AnomalyStatus.ACTIVE:
        return 0
    return 48 - (anomaly.move_timer % 48)
