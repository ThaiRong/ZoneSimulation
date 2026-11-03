"""Исследование секторов и аномалий. Основано на §12.3 ТЗ."""

from __future__ import annotations

from zonesim.anomalies.core import Anomaly
from zonesim.world.entity import HumanNPC, EntityStatus
from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType


def calculate_research_success(
    researcher_att: int,
    anomaly_type: str,
    prior_knowledge: bool = False,
    anomaly: Anomaly | None = None,
    rng_value: float = 0.5,
) -> str:
    """
    Исследование аномалии. (§12.3)
    Результат зависит от внимательности, предыдущих знаний и типа.
    Возвращает: 'position_type_found', 'artifact_found', 'safe_path_found', 'damage_taken', 'no_new_info'
    """
    base_difficulty = {"subtle": 60, "visible": 40, "large": 25}
    difficulty = base_difficulty.get(anomaly_type, 50)

    if prior_knowledge:
        difficulty -= 15

    # Шанс успеха зависит от внимательности
    p_success = researcher_att - difficulty
    p_success = max(5, min(p_success, 90))

    # Используем rng_value вместо случайного числа
    roll = rng_value * 100

    if roll < p_success * 0.3:
        # Критический успех — находим что-то особенное
        if anomaly and anomaly.anomaly_type == "large" and rng_value < 0.3:
            return "safe_path_found"
        if rng_value < 0.2:
            return "artifact_found"
        return "position_type_found"
    elif roll < p_success:
        return "position_type_found"
    elif roll < p_success + 10:
        # Частичный успех — урон, но узнали что-то
        return "damage_taken"
    else:
        return "no_new_info"


def research_anomaly(
    npc: HumanNPC,
    anomaly: Anomaly,
    knowledge_base: KnowledgeBase | None,
    hour: int,
    rng_value: float = 0.5,
    prior_anomaly_knowledge: bool = False,
    prior_path_knowledge: bool = False,
) -> dict:
    """
    Выполняет исследование аномалии.
    Возвращает результаты исследования.
    """
    result = calculate_research_success(
        researcher_att=npc.attentiveness,
        anomaly_type=anomaly.anomaly_type,
        prior_knowledge=prior_anomaly_knowledge,
        anomaly=anomaly,
        rng_value=rng_value,
    )

    outcomes: dict = {
        "research_success": result,
        "researcher_id": npc.id,
        "sector_id": npc.sector_id,
        "anomaly_id": anomaly.id,
        "hour": hour,
    }

    if result == "position_type_found":
        outcomes["knowledge"] = {
            "fact_type": KnowledgeType.ANOMALY,
            "subject_id": anomaly.id,
            "payload": {
                "sector_id": npc.sector_id,
                "anomaly_type": anomaly.anomaly_type,
                "stability": anomaly.stability,
            },
            "hour": hour,
        }

    elif result == "safe_path_found":
        outcomes["knowledge"] = {
            "fact_type": KnowledgeType.SAFE_PATH,
            "subject_id": anomaly.id,
            "payload": {
                "sector_id": npc.sector_id,
                "anomaly_id": anomaly.id,
                "active": True,
            },
            "hour": hour,
        }
        anomaly.safe_path = True

    elif result == "artifact_found":
        outcomes["knowledge"] = {
            "fact_type": KnowledgeType.ANOMALY,
            "subject_id": anomaly.id,
            "payload": {
                "has_artifact": True,
                "sector_id": npc.sector_id,
            },
            "hour": hour,
        }

    elif result == "damage_taken":
        # Исследователь получает урон от аномалии
        if anomaly.anomaly_type == "subtle":
            damage_range = (5, 12)
        elif anomaly.anomaly_type == "visible":
            damage_range = (20, 40)
        else:  # large
            damage_range = (10, 25)
        damage = int((damage_range[0] + damage_range[1]) / 2 * rng_value)
        outcomes["damage"] = damage

    return outcomes


def research_sector(
    npc: HumanNPC,
    sector: dict,
    knowledge_base: KnowledgeBase | None,
    hour: int,
    rng_value: float = 0.5,
) -> dict:
    """
    Исследование сектора (не аномалии).
    Может найти: тайник, монстров, артефакты на земле, следы.
    """
    outcomes: dict = {
        "research_type": "sector",
        "sector_id": npc.sector_id,
        "npc_id": npc.id,
        "hour": hour,
        "finds": [],
    }

    # Шанс найти что-то зависит от внимательности и качества укрытия сектора
    concealment_mod = getattr(sector, "concealment", 50)
    p_find = npc.attentiveness - (100 - concealment_mod)

    if rng_value * 100 < p_find:
        outcomes["finds"].append({
            "type": "trails",
            "description": "обнаружены следы",
        })
    if rng_value * 100 < p_find * 0.5:
        outcomes["finds"].append({
            "type": "remnants",
            "description": "остатки прошлых событий",
        })

    return outcomes


def add_knowledge_to_npc(
    npc: HumanNPC,
    knowledge_type: KnowledgeType,
    subject_id: int,
    payload: dict,
    hour: int,
    source: str = "research",
) -> KnowledgeBase:
    """
    Добавляет знание NPC.
    Возвращает KnowledgeBase с новым фактом.
    """
    kb = KnowledgeBase()
    kb.add_manual(
        npc_id=npc.id,
        fact_type=knowledge_type,
        subject_id=subject_id,
        payload=payload,
        hour=hour,
        source=source,
    )
    return kb


def get_research_cost(action: str = "research") -> float:
    """Стоимость исследования в очках выносливости."""
    if action == "research_anomaly":
        return 4.0
    return 4.0  # обычное исследование
