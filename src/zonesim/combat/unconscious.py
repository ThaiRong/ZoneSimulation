"""Потеря сознания и лечение. Основано на §11.10 и §14.3 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field


def calculate_unconscious_chance(start_health_share: float) -> float:
    """
    Шанс перехода в бессознательное вместо гибели. (§11.10)
    P_unconscious = clamp(20 + 60 × StartHealthShare, 10, 85)
    Здоровый человек имеет больше шансов выжить, чем уже раненый.
    """
    p = 20 + 60 * start_health_share
    return max(10.0, min(p, 85.0))


def resolve_unconscious_check(rng_value: float, chance: float) -> str:
    """
    Определяет результат проверки: 'unconscious' или 'dead'.
    """
    if rng_value * 100 < chance:
        return "unconscious"
    return "dead"


def provide_medical_help(
    unconscious_ids: list[int],
    available_medicines: int,
    unconscious_state: dict[int, int],
    max_healths: dict[int, int],
    rng_value: float,
) -> dict:
    """
    Побоевая медицинская помощь. (§11.10)
    Помогает бессознательным бойцам, если есть медикаменты.
    Переводит в тяжёлое состояние с health > 0.
    """
    result: dict = {
        "helped": [],
        "unhelped": [],
        "medicines_used": 0,
    }

    for uid in unconscious_ids:
        if available_medicines <= 0:
            result["unhelped"].append(uid)
            continue

        # Перевод в тяжёлое состояние: health = max_health * 0.15
        max_h = max_healths.get(uid, 100)
        new_health = int(max_h * (0.15 + 0.10 * rng_value))
        new_health = max(1, min(new_health, int(max_h * 0.29)))  # тяжёлое состояние 1-29%

        unconscious_state[uid] = new_health
        result["helped"].append({
            "id": uid,
            "new_health": new_health,
            "max_health": max_h,
        })
        result["medicines_used"] += 1
        available_medicines -= 1

    if not result["helped"]:
        result["unhelped"] = unconscious_ids

    return result


@dataclass
class WoundInfo:
    """Информация о ранении."""
    health_pct: float
    injury_applied: bool = False
    injury_penalty: dict = field(default_factory=dict)


def check_injury(
    received_damage: float,
    final_health_pct: float,
    rng_value: float,
) -> WoundInfo:
    """
    Проверка на травму. (§14.4)
    Базовый шанс 8%, если урон >= 25 или финальное здоровье < 20%.
    """
    injury = WoundInfo(health_pct=final_health_pct)

    base_chance = 0.0
    if received_damage >= 25.0:
        base_chance += 0.08
    if final_health_pct < 0.20:
        base_chance += 0.05  # дополнительный шанс при низком здоровье

    if base_chance > 0 and rng_value < base_chance:
        injury.injury_applied = True
        # Умеренный штраф к одной или нескольким характеристикам
        penalties: dict[str, int] = {}
        if rng_value < 0.3:
            penalties["stamina"] = -5
        elif rng_value < 0.6:
            penalties["attentiveness"] = -3
        else:
            penalties["health"] = -10
        injury.injury_penalty = penalties

    return injury


def update_stamina_after_combat(
    original_stamina: float,
    stamina_cost: float,
    has_shelter: bool = False,
) -> float:
    """Восстановление выносливости после боя."""
    # Немедленное частичное восстановление
    recovered = original_stamina - stamina_cost
    if has_shelter:
        recovered = min(original_stamina, recovered + original_stamina * 0.1)
    return max(0, recovered)
