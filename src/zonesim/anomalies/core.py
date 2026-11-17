"""Базовые модели аномалий. Основано на §7.8 и §12.1 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AnomalyType(str, Enum):
    SUBTLE = "subtle"       # малозаметная
    VISIBLE = "visible"     # заметная
    LARGE = "large"         # большая


class AnomalyStatus(str, Enum):
    ACTIVE = "active"
    DESTROYED = "destroyed"


@dataclass
class Anomaly:
    """Аномалия. (§7.8, §12.1)"""
    id: int
    sector_id: int
    anomaly_type: AnomalyType
    stability: int = 40
    concealment: int = 70
    damage_min: int = 5
    damage_max: int = 12
    artifact_timer: int = 0
    artifact_interval_min: int = 48
    artifact_interval_max: int = 120
    move_timer: int = 0
    safe_path: bool = False
    status: AnomalyStatus = AnomalyStatus.ACTIVE
    blocks_trail: list[int] | None = None  # перекрытое ребро-тропа (§10.5)

    # Стартовые параметры по типу (§12.1)
    TYPE_PARAMS = {
        AnomalyType.SUBTLE: {"concealment": 70, "damage_min": 5, "damage_max": 12, "stability": 40, "path_chance": 0,
                             "artifact_interval_min": 48, "artifact_interval_max": 120},
        AnomalyType.VISIBLE: {"concealment": 30, "damage_min": 20, "damage_max": 40, "stability": 80, "path_chance": 0,
                              "artifact_interval_min": 48, "artifact_interval_max": 120},
        AnomalyType.LARGE: {"concealment": 20, "damage_min": 10, "damage_max": 25, "stability": 140, "path_chance": 0.60,
                            "artifact_interval_min": 48, "artifact_interval_max": 120},
    }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sector_id": self.sector_id,
            "type": self.anomaly_type.value,
            "stability": self.stability,
            "concealment": self.concealment,
            "damage_range": (self.damage_min, self.damage_max),
            "safe_path": self.safe_path,
            "status": self.status.value,
            "artifact_timer": self.artifact_timer,
        }

    @classmethod
    def create_from_type(cls, id: int, sector_id: int, atype: AnomalyType,
                         rng) -> Anomaly:
        """Создаёт аномалию по типу со стартовыми параметрами из §12.1."""
        params = cls.TYPE_PARAMS[atype]
        return cls(
            id=id,
            sector_id=sector_id,
            anomaly_type=atype,
            concealment=params["concealment"],
            damage_min=params["damage_min"],
            damage_max=params["damage_max"],
            stability=params["stability"],
            artifact_timer=rng.randint(params["artifact_interval_min"], params["artifact_interval_max"]),
            move_timer=0,
            safe_path=rng.random() < params["path_chance"],
        )
