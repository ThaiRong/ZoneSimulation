"""Преобразование полного состояния симуляции в JSON-совместимые данные."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from zonesim.anomalies.artifact import Artifact, ArtifactManager
from zonesim.anomalies.core import Anomaly, AnomalyStatus, AnomalyType
from zonesim.combat.loot import Corpse
from zonesim.core.time import GameTime, SeededRNG
from zonesim.economy.contracts import Contract, ContractManager, ContractStatus, ContractType
from zonesim.economy.trade import ExportRecord, ImportExportManager, ImportRecord
from zonesim.generation.migration import MigrationState
from zonesim.knowledge.fact import KnowledgeBase, KnowledgeFact, KnowledgeType
from zonesim.monsters.migration import MonsterMigrationManager
from zonesim.relations.development import (
    DevelopmentManager,
    ExileManager,
    FactionChangeManager,
    PracticeProgress,
    StatType,
)
from zonesim.relations.factions import FactionRelations
from zonesim.relations.news import NewsManager, WorldEvent
from zonesim.relations.personal import PersonalRelations
from zonesim.world.entity import EntityStatus, EntityType, HumanNPC, Monster, MonsterSpecies
from zonesim.world.group import HumanGroup, MonsterGroup
from zonesim.world.item import Item, ItemType
from zonesim.world.sector import Sector
from zonesim.world.stash import Stash

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _encode(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return _encode(vars(value))
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, tuple):
        return {"__kind__": "tuple", "items": [_encode(item) for item in value]}
    if isinstance(value, set):
        return {"__kind__": "set", "items": [_encode(item) for item in sorted(value)]}
    if isinstance(value, dict):
        return {
            "__kind__": "dict",
            "items": [[_encode(key), _encode(item)] for key, item in value.items()],
        }
    raise TypeError(f"Неподдерживаемый тип сохранения: {type(value).__name__}")


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value.get("__kind__")
    if kind == "tuple":
        return tuple(_decode(item) for item in value["items"])
    if kind == "set":
        return set(_decode(item) for item in value["items"])
    if kind == "dict":
        return {_decode(key): _decode(item) for key, item in value["items"]}
    return {key: _decode(item) for key, item in value.items()}


def _object_data(obj: Any) -> Any:
    return _encode(vars(obj))


def _restore(cls, data: dict, enum_fields: dict[str, type[Enum]] | None = None):
    obj = cls.__new__(cls)
    obj.__dict__.update(_decode(data))
    for field_name, enum_type in (enum_fields or {}).items():
        value = getattr(obj, field_name, None)
        if value is not None:
            setattr(obj, field_name, enum_type(value))
    return obj


def state_to_dict(state: SimulationState) -> dict[str, Any]:
    return {
        "time": {"hour": state.time.hour},
        "rng": {
            "seed": state.rng.seed,
            "state": _encode(state.rng.get_state()),
        },
        "sectors": _encode({key: vars(value) for key, value in state.sectors.items()}),
        "humans": _encode([vars(value) for value in state.humans]),
        "stationary_humans": _encode([vars(value) for value in state.stationary_humans]),
        "human_groups": _encode({key: vars(value) for key, value in state.human_groups.items()}),
        "monsters": _encode([vars(value) for value in state.monsters]),
        "monster_groups": _encode({key: vars(value) for key, value in state.monster_groups.items()}),
        "anomalies": _encode({key: vars(value) for key, value in state.anomalies.items()}),
        "artifacts": _object_data(state.artifacts),
        "corpses": _encode([vars(value) for value in state.corpses]),
        "items": _encode({key: vars(value) for key, value in state.items.items()}),
        "contracts": _object_data(state.contracts),
        "import_export": _object_data(state.import_export),
        "personal_relations": _object_data(state.personal_relations),
        "faction_relations": _object_data(state.faction_relations),
        "development": _object_data(state.development),
        "exile_manager": _object_data(state.exile_manager),
        "faction_change_manager": _object_data(state.faction_change_manager),
        "news_manager": _object_data(state.news_manager),
        "knowledge_bases": _encode({key: vars(value) for key, value in state.knowledge_bases.items()}),
        "stashs": _encode([vars(value) for value in state.stashs]),
        "shelter_count": state.shelter_count,
        "migration_state": _object_data(state.migration_state),
        "monster_migration": _object_data(state.monster_migration),
        "next_human_id": state.next_human_id,
        "next_monster_id": state.next_monster_id,
        "next_group_id": state.next_group_id,
        "next_monster_group_id": state.next_monster_group_id,
        "next_anomaly_id": state.next_anomaly_id,
        "next_stash_id": state.next_stash_id,
        "next_corpse_id": state.next_corpse_id,
        "next_item_id": state.next_item_id,
        "visit_memory": _encode(state.visit_memory),
        "config": _encode(state.config),
    }


def _restore_monster(data: dict) -> Monster:
    monster = _restore(Monster, data, {"status": EntityStatus, "type": EntityType})
    try:
        monster.species = MonsterSpecies(monster.species)
    except ValueError:
        pass
    return monster


def state_from_dict(data: dict[str, Any]) -> SimulationState:
    from zonesim.simulation.engine import SimulationState

    rng = SeededRNG(data["rng"]["seed"])
    rng.set_state(_decode(data["rng"]["state"]))

    humans = [
        _restore(HumanNPC, value, {"status": EntityStatus, "type": EntityType})
        for value in _decode(data["humans"])
    ]
    stationary_humans = [
        _restore(HumanNPC, value, {"status": EntityStatus, "type": EntityType})
        for value in _decode(data["stationary_humans"])
    ]
    anomalies = {
        key: _restore(
            Anomaly,
            value,
            {"anomaly_type": AnomalyType, "status": AnomalyStatus},
        )
        for key, value in _decode(data["anomalies"]).items()
    }

    artifacts = _restore(ArtifactManager, data["artifacts"])
    artifacts.artifacts = [_restore(Artifact, value) for value in artifacts.artifacts]

    contracts = _restore(ContractManager, data["contracts"])
    contracts.contracts = {
        key: _restore(
            Contract,
            value,
            {"contract_type": ContractType, "status": ContractStatus},
        )
        for key, value in contracts.contracts.items()
    }

    import_export = _restore(ImportExportManager, data["import_export"])
    import_export.export_records = [
        _restore(ExportRecord, value) for value in import_export.export_records
    ]
    import_export.import_records = [
        _restore(ImportRecord, value) for value in import_export.import_records
    ]

    development = DevelopmentManager()
    for npc_id, stats in _decode(data["development"])["progress"].items():
        development.progress[npc_id] = {
            StatType(stat_type): _restore(
                PracticeProgress,
                progress,
                {"stat_type": StatType},
            )
            for stat_type, progress in stats.items()
        }

    news_manager = _restore(NewsManager, data["news_manager"])
    news_manager.events = [_restore(WorldEvent, value) for value in news_manager.events]

    knowledge_bases = {}
    for npc_id, value in _decode(data["knowledge_bases"]).items():
        knowledge_base = _restore(KnowledgeBase, value)
        knowledge_base.facts = [
            _restore(KnowledgeFact, fact, {"fact_type": KnowledgeType})
            for fact in knowledge_base.facts
        ]
        knowledge_bases[npc_id] = knowledge_base

    return SimulationState(
        time=GameTime(data["time"]["hour"]),
        rng=rng,
        sectors={
            key: _restore(Sector, value)
            for key, value in _decode(data["sectors"]).items()
        },
        humans=humans,
        stationary_humans=stationary_humans,
        human_groups={
            key: _restore(HumanGroup, value)
            for key, value in _decode(data["human_groups"]).items()
        },
        monsters=[_restore_monster(value) for value in _decode(data["monsters"])],
        monster_groups={
            key: _restore(MonsterGroup, value)
            for key, value in _decode(data["monster_groups"]).items()
        },
        anomalies=anomalies,
        artifacts=artifacts,
        corpses=[_restore(Corpse, value) for value in _decode(data["corpses"])],
        items={
            key: _restore(Item, value, {"type": ItemType})
            for key, value in _decode(data["items"]).items()
        },
        contracts=contracts,
        import_export=import_export,
        personal_relations=_restore(PersonalRelations, data["personal_relations"]),
        faction_relations=_restore(FactionRelations, data["faction_relations"]),
        development=development,
        exile_manager=_restore(ExileManager, data["exile_manager"]),
        faction_change_manager=_restore(FactionChangeManager, data["faction_change_manager"]),
        news_manager=news_manager,
        knowledge_bases=knowledge_bases,
        stashs=[_restore(Stash, value) for value in _decode(data["stashs"])],
        shelter_count=data["shelter_count"],
        migration_state=_restore(MigrationState, data["migration_state"]),
        monster_migration=_restore(MonsterMigrationManager, data["monster_migration"]),
        next_human_id=data["next_human_id"],
        next_monster_id=data["next_monster_id"],
        next_group_id=data["next_group_id"],
        next_monster_group_id=data["next_monster_group_id"],
        next_anomaly_id=data["next_anomaly_id"],
        next_stash_id=data["next_stash_id"],
        next_corpse_id=data["next_corpse_id"],
        next_item_id=data["next_item_id"],
        visit_memory=_decode(data["visit_memory"]),
        config=_decode(data["config"]),
    )
