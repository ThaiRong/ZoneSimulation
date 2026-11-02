"""Разрушение аномалий. Основано на §12.4 ТЗ."""

from __future__ import annotations

from zonesim.anomalies.core import Anomaly, AnomalyStatus


# Стоимость импортированных комплектов разрушения
DESTROY_KIT_DAMAGES = {
    "destroy_kit_subtle": 15,
    "destroy_kit_visible": 25,
    "destroy_kit_large": 35,
    "destroy_kit_universal": 20,
}


def calculate_destroy_damage(
    kit_type: str,
    kit_condition: int = 100,
    group_attentiveness: int = 50,
    num_participants: int = 1,
) -> int:
    """
    Вычисляет урон по устойчивости аномалии за один час работы комплекта.
    (§12.4)
    """
    base_damage = DESTROY_KIT_DAMAGES.get(kit_type, 10)

    # Состояние комплекта
    condition_mult = kit_condition / 100.0

    # Внимательность
    attentiveness_bonus = group_attentiveness / 100.0

    # Количество участников
    participant_bonus = 1.0 + 0.1 * (num_participants - 1)

    damage = int(base_damage * condition_mult * attentiveness_bonus * participant_bonus)
    return max(1, damage)


def attempt_destroy_anomaly(
    anomaly: Anomaly,
    kit_type: str,
    kit_condition: int,
    group_attentiveness: int,
    participants_count: int,
    rng_value: float = 0.5,
) -> dict:
    """
    Попытка разрушения аномалии за один час. (§12.4)
    Возвращает результат: damage dealt, stability remaining, destroyed, anomaly_hit.
    """
    if anomaly.status != AnomalyStatus.ACTIVE:
        return {"success": False, "reason": "already_destroyed"}

    # Проверка наличия комплекта
    if DESTROY_KIT_DAMAGES.get(kit_type, 0) == 0:
        return {"success": False, "reason": "invalid_kit"}

    # Расход комплекта
    damage_dealt = calculate_destroy_damage(
        kit_type, kit_condition, group_attentiveness, participants_count,
    )

    old_stability = anomaly.stability
    anomaly.stability -= damage_dealt

    # Проверка попадания аномалии
    anomaly_hit = rng_value < 0.3  # 30% шанс воздействия на группу

    # Проверка разрушения
    destroyed = anomaly.stability <= 0
    if destroyed:
        anomaly.status = AnomalyStatus.DESTROYED

    return {
        "success": True,
        "damage_dealt": damage_dealt,
        "old_stability": old_stability,
        "new_stability": max(0, anomaly.stability),
        "destroyed": destroyed,
        "anomaly_hit": anomaly_hit,
        "kit_degraded": True,
        "kit_new_condition": max(0, kit_condition - 10),
    }


def get_anomaly_parts_after_destruction(anomaly: Anomaly) -> dict:
    """
    Возвращает части, оставшиеся после разрушения. (§12.4)
    """
    parts = {
        "anomaly_parts": anomaly.id,
        "part_type": anomaly.anomaly_type.value + "_parts",
        "quantity": 2,
        "condition": 100,
    }
    return parts
