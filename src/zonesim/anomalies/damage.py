"""Воздействие аномалий и избегание урона. Основано на §12.2 ТЗ."""

from __future__ import annotations

from zonesim.anomalies.core import Anomaly, AnomalyStatus


def calculate_avoid_chance(
    attentiveness: int,
    anomaly_concealment: int,
    known_bonus: int = 0,
    path_bonus: int = 0,
    is_group: bool = False,
    group_size: int = 1,
    is_night: bool = False,
) -> float:
    """
    P_avoid = clamp(50 + 0.7 × (Att - Concealment) + KnownBonus + PathBonus, 5, 98)
    (§12.2)
    Для группы: лучшая внимательность с штрафом за размер.
    Ночью concealment снижается на 20 (§5.1).
    """
    effective_concealment = anomaly_concealment
    if is_night:
        effective_concealment -= 20  # ночью аномалии видны лучше

    if is_group and group_size > 1:
        # Штраф за размер группы
        group_penalty = (group_size - 1) * 2
        effective_att = attentiveness - group_penalty
    else:
        effective_att = attentiveness

    p = 50 + 0.7 * (effective_att - effective_concealment) + known_bonus + path_bonus
    return max(5.0, min(p, 98.0))


def apply_anomaly_damage(
    entity_health: int,
    entity_max_health: int,
    anomaly: Anomaly,
    rng_value: float,
) -> dict:
    """
    Применяет урон аномалии.
    Возвращает информацию о полученном уроне.
    """
    if anomaly.status != AnomalyStatus.ACTIVE:
        return {"damage": 0, "survived": True, "status": "no_damage"}

    # Урон в диапазоне аномалии
    base_damage = int((anomaly.damage_min + anomaly.damage_max) / 2 +
                      (rng_value - 0.5) * (anomaly.damage_max - anomaly.damage_min))
    base_damage = max(1, min(base_damage, anomaly.damage_max))

    new_health = entity_health - base_damage
    new_health = max(0, new_health)

    return {
        "damage": base_damage,
        "original_health": entity_health,
        "new_health": new_health,
        "survived": new_health > 0,
        "status": "hit" if new_health > 0 else ("dead" if not hasattr(entity_health, '__class__') else "critical"),
    }


def check_anomaly_contact(
    entity_sector: int,
    anomaly: Anomaly,
    rng_func,
    attentiveness: int = 50,
    known_bonus: int = 0,
    has_safe_path: bool = False,
    is_night: bool = False,
) -> dict:
    """
    Проверяет контакт с аномалией при перемещении.
    Возвращает результат: avoided или hit.
    """
    avoid_chance = calculate_avoid_chance(
        attentiveness=attentiveness,
        anomaly_concealment=anomaly.concealment,
        known_bonus=known_bonus,
        path_bonus=70 if has_safe_path else 0,
        is_night=is_night,
    )

    roll = rng_func() * 100
    if roll < avoid_chance:
        return {"result": "avoided", "avoid_chance": avoid_chance}

    damage = int((anomaly.damage_min + anomaly.damage_max) * rng_func())
    damage = max(1, min(damage, anomaly.damage_max))

    return {
        "result": "hit",
        "avoid_chance": avoid_chance,
        "damage": damage,
    }


def apply_anomaly_effect_on_movement(
    entity_attentiveness: int,
    entity_sector: int,
    anomaly: Anomaly,
    rng_func,
    known_sector: bool = False,
    has_safe_path: bool = False,
    is_group: bool = False,
    group_size: int = 1,
) -> dict:
    """
    Применяет эффект аномалии при перемещении через неё.
    """

    avoid_chance = calculate_avoid_chance(
        attentiveness=entity_attentiveness,
        anomaly_concealment=anomaly.concealment,
        known_bonus=20 if known_sector else 0,
        path_bonus=70 if has_safe_path else 0,
        is_group=is_group,
        group_size=group_size,
    )

    roll = rng_func() * 100
    if roll < avoid_chance:
        return {"result": "avoided", "damage": 0}

    # Промах — урон
    damage = int((anomaly.damage_min + anomaly.damage_max) / 2 +
                 (rng_func() - 0.5) * (anomaly.damage_max - anomaly.damage_min))
    damage = max(1, min(damage, anomaly.damage_max))

    return {"result": "hit", "damage": damage}
