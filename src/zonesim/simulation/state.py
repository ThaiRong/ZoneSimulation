"""Состояние симуляции — SimulationState dataclass.

Перенесено из simulation/engine.py для декомпозиции (Этап 3, Промпт 3.1).
БЕЗ изменений в полях или порядке — чистый перенос.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from zonesim.anomalies.artifact import ArtifactManager
from zonesim.anomalies.core import Anomaly as AnomalyEntity
from zonesim.combat.loot import Corpse
from zonesim.core.config import GameConfig
from zonesim.core.time import GameTime, SeededRNG
from zonesim.economy.contracts import ContractManager
from zonesim.economy.trade import ImportExportManager
from zonesim.generation.migration import MigrationState
from zonesim.knowledge.fact import KnowledgeBase
from zonesim.monsters.feed import FeedManager
from zonesim.monsters.migration import MonsterMigrationManager
from zonesim.relations.development import (
    DevelopmentManager,
    ExileManager,
    FactionChangeManager,
)
from zonesim.relations.factions import FactionRelations
from zonesim.relations.news import NewsManager
from zonesim.relations.personal import PersonalRelations
from zonesim.world.entity import EntityStatus, EntityType, HumanNPC, Monster
from zonesim.world.group import HumanGroup, MonsterGroup
from zonesim.world.item import Item
from zonesim.world.sector import Sector
from zonesim.world.shelter import Shelter, StormShelter
from zonesim.world.stash import Stash


@dataclass
class SimulationState:
    """Состояние симуляции."""
    time: GameTime = field(default_factory=GameTime)
    rng: SeededRNG = field(default_factory=lambda: SeededRNG(42))
    sectors: dict[int, Sector] = field(default_factory=dict)
    humans: list[HumanNPC] = field(default_factory=list)  # только мобильные NPC
    stationary_humans: list[HumanNPC] = field(default_factory=list)
    human_groups: dict[int, HumanGroup] = field(default_factory=dict)
    monsters: list[Monster] = field(default_factory=list)
    monster_groups: dict[int, MonsterGroup] = field(default_factory=dict)
    anomalies: dict[int, AnomalyEntity] = field(default_factory=dict)
    artifacts: ArtifactManager = field(default_factory=ArtifactManager)
    corpses: list[Corpse] = field(default_factory=list)
    items: dict[int, Item] = field(default_factory=dict)

    contracts: ContractManager = field(default_factory=ContractManager)
    import_export: ImportExportManager = field(default_factory=ImportExportManager)

    personal_relations: PersonalRelations = field(default_factory=PersonalRelations)
    faction_relations: FactionRelations = field(default_factory=FactionRelations)
    development: DevelopmentManager = field(default_factory=DevelopmentManager)
    exile_manager: ExileManager = field(default_factory=ExileManager)
    faction_change_manager: FactionChangeManager = field(default_factory=FactionChangeManager)
    news_manager: NewsManager = field(default_factory=NewsManager)

    knowledge_bases: dict[int, KnowledgeBase] = field(default_factory=dict)

    stashs: list[Stash] = field(default_factory=list)
    shelter_count: int = 0
    next_shelter_id: int = 100  # ID для временных убежищ
    trader_stock: dict[int, dict[str, int]] = field(default_factory=dict)  # npc торговца -> item_ref -> количество
    trails: list[list[int]] = field(default_factory=list)  # рёбра-тропы [a, b] (§10.4)
    shelters: dict[int, "StormShelter"] = field(default_factory=dict)  # стационарные укрытия (§7.16)
    temp_shelters: dict[int, Shelter] = field(default_factory=dict)  # временные убежища
    next_emission_hour: int = -1      # час начала следующего выброса (§12.7)
    emission_start_hour: int = -1
    emission_end_hour: int = -1
    emission_warning_hour: int = -1   # когда всем стало известно
    emission_exposed: dict[int, int] = field(default_factory=dict)  # group_id -> первый час под выбросом

    migration_state: MigrationState = field(default_factory=MigrationState)
    monster_migration: MonsterMigrationManager = field(default_factory=MonsterMigrationManager)

    next_human_id: int = 0
    next_monster_id: int = 0
    next_group_id: int = 0
    next_monster_group_id: int = 0
    next_anomaly_id: int = 0
    next_stash_id: int = 0
    next_corpse_id: int = 0
    next_item_id: int = 0

    visit_memory: dict[int, dict[int, int]] = field(default_factory=dict)  # npc_id -> sector -> hour

    config: dict = field(default_factory=dict)

    # Журнал изменений отношений фракций (§17 инвариант)
    # Снимок отношений перед каждым шагом: faction_a,faction_b -> value
    prev_relation_snapshot: dict[tuple[str, str], int] = field(default_factory=dict)
    # Журнал: каждый entry — изменение отношений с привязкой к событию
    relation_change_journal: list[dict] = field(default_factory=list)

    # Знания, использованные при выборе намерений групп (§25 инвариант)
    # group_id -> список фактов, используемых для решения
    intention_knowledge_used: dict[int, list[dict]] = field(default_factory=dict)
    # Снимок KB на момент выбора намерений (для корректной проверки #25)
    knowledge_snapshot_at_intention: dict[int, list[dict]] = field(default_factory=dict)

    # Ситуативный торговец «Серой лиги» (§16.6)
    next_conditional_spawn_hour: int = -1  # когда запланирован следующий
    conditional_trader_id: int | None = None  # ID NPC-торговца
    conditional_trader_sector: int = -1       # сектор появления
    conditional_trader_start_hour: int = -1   # час появления
    conditional_trader_end_hour: int = -1     # час ухода (старт + 12ч)
    conditional_trader_knowledge_hour: int = -1  # когда лига узнала расписание

    # Штурм убежищ монстрами в выброс (§12.7, условия A-D)
    # shelter_id -> {"attacking_group_ids": list[int], "sector_id": int}
    ongoing_shelter_assaults: dict[int, dict] = field(default_factory=dict)
