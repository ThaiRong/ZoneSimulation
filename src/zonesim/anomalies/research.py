"""Исследование аномалий и безопасная тропа. Основано на §12.3 ТЗ."""

from __future__ import annotations

from zonesim.anomalies.core import Anomaly, AnomalyStatus, AnomalyType
from zonesim.world.entity import HumanNPC


def calculate_research_success(
    researcher_attentiveness: int,
    anomaly_type: AnomalyType,
    prior_knowledge: bool = False,
    rng_value: float = 0.5,
) -> str:
    """
    Результат исследования аномалии.
    Возвращает: 'position_type_found', 'artifact_found', 'safe_path_found',
               'damage_taken', 'no_new_info'
    """
    base_difficulty = {
        AnomalyType.SUBTLE: 60,
        AnomalyType.VISIBLE: 40,
        AnomalyType.LARGE: 25,
    }
    difficulty = base_difficulty.get(anomaly_type, 50)

    if prior_knowledge:
        difficulty -= 15

    # Шанс успеха зависит от внимательности
    p_success = researcher_attentiveness - difficulty
    p_success = max(5, min(p_success, 90))

    roll = rng_value * 100

    if roll < p_success * 0.3:
        # Критический успех
        if anomaly_type == AnomalyType.LARGE and rng_value < 0.3:
            return "safe_path_found"
        return "artifact_found"
    elif roll < p_success:
        return "position_type_found"
    elif roll < p_success + 10:
        return "damage_taken"
    else:
        return "no_new_info"


def research_anomaly(
    npc: HumanNPC,
    anomaly: Anomaly,
    hour: int,
    rng_value: float = 0.5,
    prior_anomaly_knowledge: bool = False,
) -> dict:
    """
    Выполняет исследование аномалии одним NPC.
    """
    result = calculate_research_success(
        researcher_attentiveness=npc.attentiveness,
        anomaly_type=anomaly.anomaly_type,
        prior_knowledge=prior_anomaly_knowledge,
        rng_value=rng_value,
    )

    outcomes: dict = {
        "result": result,
        "npc_id": npc.id,
        "sector_id": npc.sector_id,
        "anomaly_id": anomaly.id,
        "hour": hour,
    }

    if result == "position_type_found":
        outcomes["knowledge"] = {
            "type": "anomaly_location",
            "anomaly_id": anomaly.id,
            "sector_id": npc.sector_id,
            "anomaly_type": anomaly.anomaly_type.value,
            "stability": anomaly.stability,
        }

    elif result == "safe_path_found":
        outcomes["knowledge"] = {
            "type": "safe_path",
            "anomaly_id": anomaly.id,
            "sector_id": npc.sector_id,
        }
        anomaly.safe_path = True

    elif result == "artifact_found":
        outcomes["knowledge"] = {
            "type": "artifact_present",
            "anomaly_id": anomaly.id,
            "sector_id": npc.sector_id,
        }

    elif result == "damage_taken":
        damage = int((anomaly.damage_min + anomaly.damage_max) * rng_value)
        outcomes["damage"] = damage
        outcomes["damage_taken"] = True

    return outcomes


def research_sector_for_anomalies(
    npc: HumanNPC,
    anomalies_in_sector: list,
    hour: int,
    rng_value: float = 0.5,
    prior_sector_researched: bool = False,
) -> list[dict]:
    """
    Исследует сектор на наличие аномалий.
    Возвращает список найденных аномалий.
    """
    findings = []

    for anomaly in anomalies_in_sector:
        # Шанс обнаружения зависит от внимательности и concealment
        detect_chance = 50 + npc.attentiveness - anomaly.concealment
        detect_chance = max(5, min(detect_chance, 90))

        if prior_sector_researched:
            detect_chance += 10

        if rng_value * 100 < detect_chance:
            findings.append({
                "anomaly_id": anomaly.id,
                "anomaly_type": anomaly.anomaly_type.value,
                "concealment": anomaly.concealment,
                "discovered": True,
                "hour": hour,
            })

    return findings
