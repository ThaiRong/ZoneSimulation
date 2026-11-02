"""Отступление. Основано на §11.6-11.7 ТЗ."""

from __future__ import annotations

from zonesim.world.sector import get_shortest_path


def calculate_retreat_score(
    health_share: float,
    enemy_power_ratio: float,
    bravery: float,
    loss_share: float,
) -> float:
    """
    Склонность к отступлению. (§11.6)
    RetreatScore = 0.45 × (1 - HealthShare) + 0.35 × max(0, EnemyPowerRatio - 1)
                   + 0.25 × (1 - Bravery/100) + 0.20 × LossShare
    При > 0.55 — группа пытается отступить.
    """
    score = (
        0.45 * (1.0 - health_share) +
        0.35 * max(0.0, enemy_power_ratio - 1.0) +
        0.25 * (1.0 - bravery / 100.0) +
        0.20 * loss_share
    )
    return score


def calculate_retreat_chance(
    speed_ratio: float,
    escape_att: int,
    pursuer_att: int,
    terrain_bonus: int = 0,
    shelter_bonus: float = 0.0,
    pursuit_bonus: int = 0,
) -> float:
    """
    Шанс успешного отступления. (§11.7)
    P_retreat = clamp(45 + 20 × (SpeedRatio - 1) + 0.15 × (EscapeAtt - PursuerAtt)
                      + Terrain + Shelter - Pursuit, 5, 95)
    """
    p = (
        45 +
        20.0 * (speed_ratio - 1.0) +
        0.15 * (escape_att - pursuer_att) +
        terrain_bonus +
        shelter_bonus * 100 +
        pursuit_bonus * -1
    )
    return max(5.0, min(p, 95.0))


def resolve_retreat(
    retreat_score: float,
    retreat_chance: float,
    rng_value: float,
    current_sector_id: int,
    sectors: dict[int, object],
    has_shelter: bool = False,
    ambush: bool = False,
) -> dict:
    """
    Разрешение отступления. (§11.6-11.7)
    Возвращает: outcome, new_sector_id, penalties
    """
    result: dict = {
        "attempted": True,
        "success": False,
        "new_sector_id": current_sector_id,
        "attack_penalty": 1.0,
        "defense_penalty": 1.0,
        "retreated": False,
    }

    # Если атаковали в засаду — отступление невозможно в этом раунде
    if ambush:
        result["reason"] = "ambush_prevents_retreat"
        return result

    # Проверка score
    if retreat_score <= 0.55:
        result["reason"] = "not_enecessary"
        return result

    # Проверка шанса
    p_retreat = calculate_retreat_chance(
        speed_ratio=1.0,
        escape_att=50,
        pursuer_att=50,
        terrain_bonus=10 if has_shelter else 0,
        shelter_bonus=0.1 if has_shelter else 0,
    )
    p_retreat = max(5.0, min(p_retreat, 95.0))

    roll = rng_value * 100
    if roll < p_retreat:
        result["success"] = True
        # Перемещение в соседний сектор
        sector = sectors.get(current_sector_id)
        if sector and sector.neighbors:
            import random
            new_id = random.choice(sector.neighbors)
            result["new_sector_id"] = new_id
            result["retreated"] = True
            result["reason"] = "success"
        else:
            result["reason"] = "no_valid_sector"
    else:
        result["reason"] = "failed"
        # Штрафы атаки ×0.9, защиты ×0.8 (§11.7)
        result["attack_penalty"] = 0.9
        result["defense_penalty"] = 0.8

    return result


def calculate_enemy_power_ratio(
    enemy_power: float,
    own_power: float,
) -> float:
    """Соотношение сил врага к своим."""
    if own_power <= 0:
        return 2.0  # максимальное соотношение при нулевых своих силах
    return enemy_power / own_power


def should_attempt_retreat(
    retreat_score: float,
    is_overwhelming: bool = False,
) -> bool:
    """
    Решение об отступлении. (§11.6)
    При подавляющем преимуществе противника — независимо от храбрости.
    """
    if is_overwhelming:
        return retreat_score > 0.3  # более низкий порог
    return retreat_score > 0.55
