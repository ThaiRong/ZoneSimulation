"""Формирование артефактов. Основано на §12.5 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zonesim.anomalies.core import Anomaly, AnomalyStatus, AnomalyType
from zonesim.core.time import SeededRNG


@dataclass
class Artifact:
    """Артефакт. (§12.5)"""
    id: int
    anomaly_id: int
    rarity: str = "common"  # common, uncommon, rare
    condition: int = 100
    value: float = 200.0
    discovered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "anomaly_id": self.anomaly_id,
            "rarity": self.rarity,
            "condition": self.condition,
            "value": self.value,
            "discovered": self.discovered,
        }


class ArtifactManager:
    """Управление формированием артефактов (§12.5)."""

    def __init__(self):
        self.artifacts: list[Artifact] = []
        self._next_id: int = 0

    def check_artifact_formation(
        self,
        anomaly: Anomaly,
        hour: int,
        rng_value: float = 0.5,
        rng: SeededRNG | None = None,
    ) -> dict:
        """
        Проверяет, сформировался ли артефакт.
        Интервал 48-120 часов (§12.5). По завершении таймера — шанс 60%,
        после чего начинается новый цикл независимо от результата.
        """
        if anomaly.status != AnomalyStatus.ACTIVE:
            return {"formed": False, "reason": "anomaly_inactive"}

        # Уменьшаем таймер
        anomaly.artifact_timer -= 1

        if anomaly.artifact_timer > 0:
            return {"formed": False, "timer_remaining": anomaly.artifact_timer}

        roll = rng.random() if rng is not None else rng_value
        if roll < 0.6:
            artifact = self._create_artifact(anomaly, roll)
            anomaly.artifact_timer = self._roll_new_timer(rng, rng_value)
            return {
                "formed": True,
                "artifact_id": artifact.id,
                "rarity": artifact.rarity,
                "value": artifact.value,
            }

        anomaly.artifact_timer = self._roll_new_timer(rng, rng_value)
        return {"formed": False, "new_timer": anomaly.artifact_timer}

    @staticmethod
    def _roll_new_timer(rng, rng_value: float) -> int:
        if rng is not None:
            return rng.randint(48, 120)
        return 48 + int(rng_value * 72)  # 48..119, детерминированный запасной вариант

    def _create_artifact(self, anomaly: Anomaly, rarity_roll: float) -> Artifact:
        """Создаёт артефакт."""
        if rarity_roll < 0.7:
            rarity = "common"
            value = 150.0 + rarity_roll * 100
        elif rarity_roll < 0.9:
            rarity = "uncommon"
            value = 250.0 + rarity_roll * 150
        else:
            rarity = "rare"
            value = 400.0 + rarity_roll * 200

        artifact = Artifact(
            id=self._next_id,
            anomaly_id=anomaly.id,
            rarity=rarity,
            value=value,
        )
        self._next_id += 1
        self.artifacts.append(artifact)
        return artifact

    def retrieve_artifact(
        self,
        artifact_id: int,
        anomaly: Anomaly,
    ) -> dict:
        """
        Извлекает артефакт из аномалии. (§12.4)
        """
        artifact = next((a for a in self.artifacts if a.id == artifact_id), None)
        if not artifact:
            return {"success": False, "reason": "not_found"}

        if anomaly.id != artifact.anomaly_id:
            return {"success": False, "reason": "wrong_anomaly"}

        artifact.discovered = True
        return {
            "success": True,
            "artifact": artifact.to_dict(),
            "removed_from_anomaly": True,
        }

    def get_active_artifacts(self) -> list[dict]:
        return [a.to_dict() for a in self.artifacts if a.discovered]
