"""Разрушение аномалий. Основано на §12.4 ТЗ."""

from __future__ import annotations

from zonesim.anomalies.core import Anomaly, AnomalyStatus

# Износ комплекта за одну часовую попытку разрушения
KIT_WEAR_PER_ATTEMPT = 25


def calculate_destroy_damage(
    base_damage: float,
    kit_condition: int = 100,
    quality: float = 1.0,
    group_attentiveness: int = 50,
    num_participants: int = 1,
) -> int:
    """
    Урон по устойчивости аномалии за час работы комплекта. (§12.4)

    Зависит от базового урона модели комплекта (каталог), её качества,
    состояния, подготовки и внимательности участников.
    """
    condition_mult = max(0.0, kit_condition / 100.0)
    attentiveness_mult = 0.5 + max(0, group_attentiveness) / 100.0
    participant_mult = 1.0 + 0.1 * max(0, num_participants - 1)
    damage = int(base_damage * quality * condition_mult * attentiveness_mult * participant_mult)
    return max(1, damage)


def attempt_destroy_anomaly(
    anomaly: Anomaly,
    base_damage: float,
    kit_condition: int = 100,
    quality: float = 1.0,
    group_attentiveness: int = 50,
    participants_count: int = 1,
) -> dict:
    """
    Часовая попытка разрушения аномалии. (§12.4)

    Возвращает нанесённый урон и флаг разрушения. Воздействие аномалии
    на группу проверяется вызывающим кодом отдельно для каждой попытки.
    """
    if anomaly.status != AnomalyStatus.ACTIVE:
        return {"success": False, "reason": "already_destroyed"}

    damage_dealt = calculate_destroy_damage(
        base_damage, kit_condition, quality, group_attentiveness, participants_count,
    )

    old_stability = anomaly.stability
    anomaly.stability -= damage_dealt
    destroyed = anomaly.stability <= 0
    if destroyed:
        anomaly.stability = 0
        anomaly.status = AnomalyStatus.DESTROYED

    return {
        "success": True,
        "damage_dealt": damage_dealt,
        "old_stability": old_stability,
        "new_stability": anomaly.stability,
        "destroyed": destroyed,
        "kit_new_condition": max(0, kit_condition - KIT_WEAR_PER_ATTEMPT),
    }


def get_anomaly_parts_after_destruction(anomaly: Anomaly) -> dict:
    """
    Части, остающиеся после разрушения. (§12.4)
    """
    parts = {
        "anomaly_parts": anomaly.id,
        "part_type": anomaly.anomaly_type.value + "_parts",
        "quantity": 2,
        "condition": 100,
    }
    return parts
