"""Конфигурация мира и баланса. Основана на §21.1 и §20.1 ТЗ."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ====================================================================
# Расхождение ТЗ / код по охране баз (§21)
# ====================================================================
# ТЗ (раздел про базы) указывает 2 охранника на базу.
# В коде (worldgen.py, engine.py) заложено 4 охранника + торговец.
# ЗДЕСЬ — единственный источник истины: GUARDS_PER_BASE = 4.
# При изменении ТЗ — исправить здесь, не хардкодить в инвариантах.
# ====================================================================
DEFAULT_GUARDS_PER_BASE = 4


class WorldConfig(BaseModel):
    """Параметры генерации мира."""
    sectors_count: int = Field(default=20, ge=15, le=25)
    mobile_humans_count: int = Field(default=40, ge=30, le=50)
    monsters_count: int = Field(default=28, le=40)
    anomalies_count: int = Field(default=30, ge=20, le=40)
    faction_start_distance: int = Field(default=1, ge=1)  # расстояние от старта до границы
    faction_inter_distance: int = Field(default=4, ge=4)  # минимальное расстояние между стартами


class HumanStatsConfig(BaseModel):
    """Стартовые характеристики мобильного человека."""
    attack: int = Field(default=50, ge=1, le=100)
    defense: int = Field(default=50, ge=1, le=100)
    stamina: int = Field(default=100, ge=1, le=100)
    attentiveness: int = Field(default=50, ge=1, le=100)
    bravery: int = Field(default=50, ge=1, le=100)
    health: int = Field(default=100, ge=1, le=100)


class FactionConfig(BaseModel):
    """Настройки фракций."""
    name: str
    share: float = Field(default=0.5, ge=0.0, le=1.0)  # доля от мобильных людей
    relation_bonus: dict[str, float] = Field(default_factory=dict)


class GameConfig(BaseModel):
    """Главный конфигурационный объект."""
    world: WorldConfig = Field(default_factory=WorldConfig)
    human_stats: HumanStatsConfig = Field(default_factory=HumanStatsConfig)
    factions: list[FactionConfig] = Field(default_factory=lambda: [
        FactionConfig(name="Бродяги", share=0.4),
        FactionConfig(name="Борзые", share=0.45),
        FactionConfig(name="Серая лига", share=0.15),
    ])
