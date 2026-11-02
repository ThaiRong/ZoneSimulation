"""Сдача в плен и пленение. Основано на §11.9 ТЗ."""

from __future__ import annotations

from enum import Enum
from typing import Any


class SurrenderOutcome(str, Enum):
    KILL_ALL = "kill_all"
    CAPTURE_ALL = "capture_all"
    CAPTURE_PARTIAL = "capture_partial"
    RELEASE_ALL = "release_all"


class SurrenderManager:
    """Логика сдачи и пленения. (§11.9)"""

    @staticmethod
    def can_surrender(
        attacker_is_human: bool,
        defender_is_human: bool,
        bravery: float,
        health_share: float,
        power_ratio: float,
        relation: int = 0,
    ) -> bool:
        """
        Может ли группа сдаться? (§11.9)
        Только люди могут сдаваться людям. Монстры не принимают пленных.
        """
        if not attacker_is_human or not defender_is_human:
            return False

        # При подавляющем преимуществе и низком здоровье — шанс есть
        score = (
            0.5 * (1.0 - health_share) +
            0.3 * max(0, power_ratio - 1.0) +
            0.2 * (1.0 - bravery / 100.0)
        )

        # Отношения влияют: враги не примут сдавшихся
        if relation < -50:
            score -= 0.3  # сильная враждебность

        return score > 0.4

    @staticmethod
    def determine_outcome(
        surrendering_count: int,
        captor_count: int,
        relation: int,
        captor_faction: str,
        target_faction: str,
        bravery: float,
    ) -> dict[str, Any]:
        """
        Определяет исход: убить, пленить всех/частично, отпустить. (§11.9)
        """
        result: dict = {
            "outcome": SurrenderOutcome.KILL_ALL,
            "captured": [],
            "released": [],
            "killed": [],
        }

        if surrendering_count == 0:
            result["outcome"] = SurrenderOutcome.RELEASE_ALL
            return result

        # Шанс на плен зависит от отношений и выгоды
        capture_chance = 0.3
        if relation > 0:
            capture_chance += 0.2  # союзники — плен
        if relation > 49:  # союз
            capture_chance += 0.3
        elif relation > -20:  # нейтрал
            capture_chance += 0.1
        elif relation < -60:  # война
            capture_chance -= 0.3

        # Выгода от пленных (информация, рабсила)
        if captor_count < surrendering_count:
            capture_chance += 0.1

        import random
        if random.random() < capture_chance:
            # Пленят
            if surrendering_count <= captor_count or relation > 0:
                # Пленяют всех
                result["outcome"] = SurrenderOutcome.CAPTURE_ALL
                result["captured"] = list(range(surrendering_count))
            else:
                # Частичный плен
                result["outcome"] = SurrenderOutcome.CAPTURE_PARTIAL
                capture_count = min(captor_count, max(1, surrendering_count // 2))
                result["captured"] = list(range(capture_count))
                result["released"] = list(range(capture_count, surrendering_count))
        else:
            # Убивают или отпускают
            if bravery < 40:
                result["outcome"] = SurrenderOutcome.RELEASE_ALL
                result["released"] = list(range(surrendering_count))
            else:
                result["outcome"] = SurrenderOutcome.KILL_ALL
                result["killed"] = list(range(surrendering_count))

        return result

    @staticmethod
    def apply_outcome(
        prisoners: list[int],
        outcome: dict,
    ) -> dict:
        """Применяет исход к группам."""
        status_map: dict[int, str] = {}
        for pid in prisoners:
            if pid in outcome.get("captured", []):
                status_map[pid] = "prisoner"
            elif pid in outcome.get("killed", []):
                status_map[pid] = "killed"
            else:
                status_map[pid] = "released"
        return status_map
