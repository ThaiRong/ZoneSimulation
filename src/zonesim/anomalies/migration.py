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


def anomaly_move_candidates(state, anomaly) -> list[int]:
    """Допустимые цели перемещения: текущий или соседний сектор (§12.6)."""
    start_ids = {s.id for s in state.sectors.values() if s.is_faction_start}
    candidates = {anomaly.sector_id, *state.sectors[anomaly.sector_id].neighbors}
    return [sid for sid in candidates if sid not in start_ids]


def move_all_anomalies(state, hour: int) -> None:
    """Однократное перемещение всех активных аномалий в первый час выброса."""
    from zonesim.world.trails import roll_trail_blockage

    start_ids = {s.id for s in state.sectors.values() if s.is_faction_start}
    for anomaly in state.anomalies.values():
        migration = check_anomaly_migration(
            anomaly, hour, move_interval=0, move_chance=1.0,
            sector_ids=anomaly_move_candidates(state, anomaly),
            faction_start_ids=start_ids,
            rng_value=state.rng.random(),
        )
        if migration["moved"]:
            anomaly.sector_id = migration["to_sector"]
            anomaly.move_timer = 0
            roll_trail_blockage(state, anomaly)
            state.news_manager.create_event(
                hour=hour, minute=0, sector_id=migration["to_sector"],
                event_type="anomaly_move", participants=[], result="moved",
                importance=20,
                summary=f"Аномалия {anomaly.id} переместилась (выброс)",
                details=migration,
            )
