"""Выслеживание целей. Основано на §10.2 ТЗ.

Если группа занята выслеживанием и обнаруживает след, выполняется проверка
внимательности. Результаты: полный/частичный/провал.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType


class StalkResult(str, Enum):
    """Результат выслеживания (§10.2)."""
    FULL = "full"           # точное направление: конкретный сектор
    PARTIAL = "partial"     # примерное направление: суженный набор
    FAIL = "fail"           # след потерян


# Модификаторы выслеживания (§10.2)
STALK_BASE_DIFFICULTY = 50        # базовая сложность
STALK_FRESHNESS_DECREASE = 10     # снижение за каждый час свежести
STALK_SIZE_PENALTY_SINGLE = 0     # одиночная цель
STALK_SIZE_PENALTY_GROUP_4 = 10   # штраф за группу из 4 человек
STALK_SPEED_BONUS_PREDATOR = 10   # территориальный хищник быстро двигается
STALK_SPEED_PENALTY_MIGRANT = -5  # мигрант медленно
STALK_NIGHT_PENALTY = 15          # ночью сложнее выслеживать
STALK_TERRAIN_BONUS = 10          # местность помогает скрытию
STALK_PARTIAL_THRESHOLD = 0.45    # порог для частичного успеха (P >= 0.45)
STALK_FAIL_THRESHOLD = 0.30       # порог для провала (P < 0.30)


@dataclass
class StalkCheck:
    """Результат проверки выслеживания."""
    result: StalkResult
    target_sector: int | None       # для FULL — конкретный сектор цели
    direction_sectors: list[int] | None  # для PARTIAL — суженный набор
    confidence: float               # уверенность 0–1


def calculate_stalk_check(
    pursuer_attentiveness: int,
    trail_freshness_hours: int,
    terrain_concealment: int,
    target_size: int = 1,  # 1 = одиночка, 2-4 = группа
    target_speed: float = 1.0,  # 1.0 = нормальная, 2.0 = территориальный хищник
    is_night: bool = False,
    has_detector: bool = False,
    rng_value: float | None = None,
) -> StalkCheck:
    """
    Вычисляет результат выслеживания (§10.2).
    
    Args:
        pursuer_attentiveness: внимательность преследователя
        trail_freshness_hours: сколько часов прошло с последнего перемещения цели
        terrain_concealment: модификатор местности (0-100)
        target_size: размер цели (1-4)
        target_speed: скорость цели (1.0 норм, 2.0 быстро)
        is_night: ночное время
        has_detector: есть ли детектор у преследователя
        rng_value: бросок 0-1 (если None — случайный)
    
    Returns:
        StalkCheck с результатом, направлением и уверенностью
    """
    if rng_value is None:
        from zonesim.core.time import SeededRNG
        rng_value = SeededRNG._default_rng().random()

    # Расчёт вероятности успеха (§10.2)
    p = STALK_BASE_DIFFICULTY
    
    # Свежесть следа: каждый час снижает шансы
    p -= STALK_FRESHNESS_DECREASE * min(trail_freshness_hours, 6)
    
    # Размер цели: группа заметнее
    if target_size >= 2:
        p += min((target_size - 1) * 5, STALK_SIZE_PENALTY_GROUP_4)
    
    # Скорость: быстрые цели оставляют менее чёткие следы
    if target_speed >= 2.0:
        p -= STALK_SPEED_BONUS_PREDATOR  # штраф к следжению за быстрыми
    elif target_speed < 1.0:
        p += STALK_SPEED_PENALTY_MIGRANT  # мигрант медленный, след длиннее
    
    # Ночной штраф: сложнее заметить след
    if is_night:
        p -= STALK_NIGHT_PENALTY
    
    # Местность: высокая скрытность местности помогает цели
    p += terrain_concealment // 5
    
    # Детектор: бонус для преследователя
    if has_detector:
        p += 10
    
    # Клamp 5-95
    p = max(5, min(95, p))
    
    # Определяем результат по броску
    roll = rng_value * 100
    if roll < p * 0.6:  # полный успех: нужно значительно превысить порог
        # Определяем направление: следующий сектор цели
        # Для FULL — точный сектор
        target_sector = None  # заполняется вызывающим кодом
        return StalkCheck(
            result=StalkResult.FULL,
            target_sector=target_sector,
            direction_sectors=None,
            confidence=min(0.95, p / 100.0),
        )
    elif roll < p * 1.2:  # частичный успех: примерно направление
        direction_sectors = []  # заполняется вызывающим кодом
        return StalkCheck(
            result=StalkResult.PARTIAL,
            target_sector=None,
            direction_sectors=direction_sectors,
            confidence=min(0.7, p / 120.0),
        )
    else:  # провал
        return StalkCheck(
            result=StalkResult.FAIL,
            target_sector=None,
            direction_sectors=None,
            confidence=0.0,
        )


def create_stalk_knowledge(
    result: StalkResult,
    target_sector: int | None,
    direction_sectors: list[int] | None,
    knower_npc_id: int,
    target_group_id: int,
    hour: int,
    knowledge_base: KnowledgeBase,
) -> None:
    """
    Создаёт KnowledgeFact для преследователя на основе результата выслеживания.
    
    Args:
        result: результат выслеживания
        target_sector: конкретный сектор цели (для FULL)
        direction_sectors: набор возможных секторов (для PARTIAL)
        knower_npc_id: ID NPC, который выслеживал
        target_group_id: ID группы/цели
        hour: час события
        knowledge_base: KnowledgeBase преследователя
    """
    if result == StalkResult.FULL and target_sector is not None:
        # Точное направление: конкретный сектор (§10.2 "полный успех")
        knowledge_base.add_manual(
            npc_id=knower_npc_id,
            fact_type="MONSTERS_STALK",  # тип знания о выслеживании
            subject_id=target_group_id,
            payload={
                "type": "stalking",
                "result": "full_success",
                "target_sector_id": target_sector,
                "confidence": 0.9,
                "freshness_hours": 0,
            },
            hour=hour,
        )
    elif result == StalkResult.PARTIAL and direction_sectors is not None:
        # Примерное направление: суженный набор секторов (§10.2 "частичный успех")
        knowledge_base.add_manual(
            npc_id=knower_npc_id,
            fact_type="MONSTERS_STALK",
            subject_id=target_group_id,
            payload={
                "type": "stalking",
                "result": "partial_success",
                "possible_sectors": direction_sectors,
                "confidence": 0.6,
                "freshness_hours": 1,
            },
            hour=hour,
        )
    # При FAIL знание не создаётся — след потерян


def calculate_stalking_check(
    pursuer_attentiveness: int,
    trail_freshness_hours: int,
    terrain_concealment: int,
    target_size: int,
    target_speed: float,
    is_night: bool,
    has_detector: bool,
    rng_value: float,
) -> str:
    """
    Старая функция совместимости — вызывает calculate_stalk_check.
    Возвращает строку результата для совместимости с существующим кодом.
    """
    result = calculate_stalk_check(
        pursuer_attentiveness=pursuer_attentiveness,
        trail_freshness_hours=trail_freshness_hours,
        terrain_concealment=terrain_concealment,
        target_size=target_size,
        target_speed=target_speed,
        is_night=is_night,
        has_detector=has_detector,
        rng_value=rng_value,
    )
    return result.result.value
