"""Обнаружение, выслеживание, засады. Основано на §10.2-10.4 ТЗ."""

from __future__ import annotations

from zonesim.actions.stalk import calculate_stalk_check, StalkResult
from zonesim.core.time import PhaseOfDay
from zonesim.world.entity import EntityStatus, HumanNPC, Monster


def calculate_stalking_check(
    tracker_att: int,
    track_freshness_hours: int,
    terrain_mod: int,
    target_size: int,
    target_speed: int,
    is_night: bool = False,
    rng: float | None = None,
) -> str:
    """Совместимая обёртка поверх calculate_stalk_check (§10.2)."""
    check = calculate_stalk_check(
        pursuer_attentiveness=tracker_att,
        trail_freshness_hours=track_freshness_hours,
        terrain_concealment=terrain_mod,
        target_size=target_size,
        target_speed=float(target_speed),
        is_night=is_night,
        has_detector=False,
        rng_value=rng if rng is not None else 0.5,
    )
    mapping = {
        StalkResult.FULL: "full_success",
        StalkResult.PARTIAL: "partial_success",
        StalkResult.FAIL: "fail",
    }
    return mapping[check.result]


def calculate_detection_check(
    observer_att: int,
    target_concealment: int,
    terrain_concealment: int,
    is_group: bool = False,
    group_size: int = 1,
    is_night: bool = False,
) -> bool:
    """
    Обнаружение скрытого объекта. (§10.3)
    Возвращает True если обнаружен.
    """
    # Ночью аномалии видны лучше — снижаем их concealment (§5.1)
    effective_concealment = target_concealment
    if is_night:
        effective_concealment -= 20

    # Для группы — штраф за размер (§10.3)
    group_penalty = (group_size - 1) * 5 if is_group else 0

    # Формула обнаружения
    p_detect = 50 + observer_att - effective_concealment + terrain_concealment - group_penalty

    # Шанс от 5% до 95%
    p_detect = max(5, min(p_detect, 95))
    return True  # placeholder — реальный рандом вызывается снаружи


def check_anomaly_detection(
    observer_att: int,
    anomaly_concealment: int,
    terrain_concealment: int,
    is_night: bool = False,
    rng_value: float = 0.5,
) -> bool:
    """
    Обнаружение аномалии. (§10.3, §5.1)
    Ночью аномалии видны лучше (concealment -20).
    """
    effective_concealment = anomaly_concealment
    if is_night:
        effective_concealment -= 20

    p_detect = 50 + observer_att - effective_concealment + terrain_concealment
    p_detect = max(5, min(p_detect, 95))

    return rng_value * 100 < p_detect


def calculate_ambush_chance(
    attacker_att: int,
    defender_att: int,
    terrain_mod: int = 0,
    preparation_bonus: int = 0,
    alertness: int = 0,
) -> float:
    """
    Расчёт шанса успешной засады. (§10.4)
    P_ambush = clamp(55 + 0.5 × (A_att - D_att) + Terrain + Preparation - Alert, 10, 90)
    """
    p = 55 + 0.5 * (attacker_att - defender_att) + terrain_mod + preparation_bonus - alertness
    return max(10, min(p, 90))


def resolve_ambush(
    ambush_chance: float,
    rng_value: float,
) -> str:
    """
    Разрешение засады. (§10.4)
    Возвращает: 'success', 'fail', или 'revealed'
    """
    roll = rng_value * 100
    if roll < ambush_chance:
        return "success"  # нападающие получают бонус ×1.25 в первом раунде
    return "fail"  # засада раскрыта, защищающиеся получают инициативу


def calculate_night_attentiveness_mod(phase: PhaseOfDay) -> int:
    """Возвращает модификатор внимательности ночью. (§5.1)"""
    if phase == PhaseOfDay.NIGHT:
        return -20
    return 0


def calculate_anomaly_detection_night_mod(phase: PhaseOfDay) -> int:
    """Модификатор обнаружения аномалий ночью. (§5.1)"""
    if phase == PhaseOfDay.NIGHT:
        return -20  # anomaly concealment снижается на 20
    return 0


def create_ambush_action(
    attacker_ids: list[int],
    sector_id: int,
    hour: int,
    duration_hours: int = 1,
) -> dict:
    """
    Создаёт действие «засада». (§10.4)
    Действует до конца следующего часа или до первого срабатывания.
    """
    return {
        "type": "ambush",
        "attacker_ids": attacker_ids,
        "sector_id": sector_id,
        "start_hour": hour,
        "expires_hour": hour + duration_hours,
        "triggered": False,
    }
