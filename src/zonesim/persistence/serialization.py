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
from zonesim.world.shelter import Shelter, StormShelter
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


def _encode_simple(value: Any) -> Any:
    """Простая кодировка: _encode(value) без special handling."""
    return _encode(value)


# Strategy mapping: имя поля → функция кодирования
# Используется рефлексией по dataclasses.fields — поля НЕ перечисляются вручную.
_FIELD_ENCODE_STRATEGY: dict[str, Any] = {}


def _register_field_strategy(name: str, encoder: Any) -> None:
    _FIELD_ENCODE_STRATEGY[name] = encoder


# GameTime — special format {"hour": int}
def _encode_time(name: str, value: Any) -> dict[str, int]:
    return {"hour": value.hour}


# SeededRNG — special format {"seed": int, "state": tuple}
def _encode_rng(name: str, value: Any) -> dict[str, Any]:
    return {"seed": value.seed, "state": _encode(value.get_state())}


# temp_shelters — to_dict() для Shelter
def _encode_temp_shelters(name: str, value: dict) -> dict[str, Any]:
    return _encode({str(k): v.to_dict() for k, v in value.items()})


# Managers (non-dataclass) — vars() + _encode
_MANAGER_NAMES: set[str] = {
    "artifacts", "contracts", "import_export", "personal_relations",
    "faction_relations", "development", "exile_manager",
    "faction_change_manager", "news_manager", "migration_state",
    "monster_migration",
}


def _encode_manager_field(name: str, value: Any) -> Any:
    return _encode(vars(value))


# Dataclass dict fields — vars() + _encode (ключи int остаются int)
_DATACLASS_DICT_NAMES: set[str] = {
    "sectors", "human_groups", "monster_groups", "anomalies", "items", "knowledge_bases",
}


def _encode_dict_dataclass(name: str, value: dict) -> Any:
    return _encode({k: vars(v) for k, v in value.items()})


# Dataclass dict fields — vars() + _encode (ключи int → str)
_DATACLASS_DICT_STR_KEY_NAMES: set[str] = {"shelters"}


def _encode_dict_dataclass_str_key(name: str, value: dict) -> Any:
    return _encode({str(k): vars(v) for k, v in value.items()})


# Dataclass list fields — vars() + _encode
_DATACLASS_LIST_NAMES: set[str] = {
    "humans", "stationary_humans", "monsters", "corpses", "stashs",
}


def _encode_list_dataclass(name: str, value: list) -> Any:
    return _encode([vars(v) for v in value])


# Collections with str keys
_STR_KEY_DICT_NAMES: set[str] = {"trader_stock", "emission_exposed"}


def _encode_str_key_dict(name: str, value: dict) -> Any:
    return _encode({str(k): v for k, v in value.items()})


# Register all strategies
for _fname in _MANAGER_NAMES:
    _register_field_strategy(_fname, _encode_manager_field)
for _fname in _DATACLASS_DICT_NAMES:
    _register_field_strategy(_fname, _encode_dict_dataclass)
for _fname in _DATACLASS_DICT_STR_KEY_NAMES:
    _register_field_strategy(_fname, _encode_dict_dataclass_str_key)
for _fname in _DATACLASS_LIST_NAMES:
    _register_field_strategy(_fname, _encode_list_dataclass)
for _fname in _STR_KEY_DICT_NAMES:
    _register_field_strategy(_fname, _encode_str_key_dict)

# Special names with unique handlers
register_field_strategy = _register_field_strategy  # alias для читаемости
register_field_strategy("time", _encode_time)
register_field_strategy("rng", _encode_rng)
register_field_strategy("temp_shelters", _encode_temp_shelters)


def state_to_dict(state: SimulationState) -> dict[str, Any]:
    """Рефлексивная сериализация SimulationState через dataclasses.fields.

    Никакого ручного перечисления полей — поля перебираются рефлексией,
    стратегия кодирования определяется стратегией, зарегистрированной для имени поля.
    """
    import dataclasses

    result: dict[str, Any] = {}
    for field in dataclasses.fields(state):
        name = field.name
        value = getattr(state, name)
        strategy = _FIELD_ENCODE_STRATEGY.get(name)
        if strategy is not None:
            result[name] = strategy(name, value)
        else:
            result[name] = _encode_simple(value)
    return result


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
        trader_stock={
            int(key): value for key, value in _decode(data["trader_stock"]).items()
        },
        trails=data["trails"],
        shelters={
            int(key): _restore(StormShelter, value)
            for key, value in _decode(data["shelters"]).items()
        },
        next_emission_hour=data["next_emission_hour"],
        emission_start_hour=data["emission_start_hour"],
        emission_end_hour=data["emission_end_hour"],
        emission_warning_hour=data["emission_warning_hour"],
        emission_exposed={
            int(key): value for key, value in _decode(data["emission_exposed"]).items()
        },
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
        # Ситуативный торговец (§16.6)
        next_conditional_spawn_hour=data["next_conditional_spawn_hour"],
        conditional_trader_id=data["conditional_trader_id"],
        conditional_trader_sector=data["conditional_trader_sector"],
        conditional_trader_start_hour=data["conditional_trader_start_hour"],
        conditional_trader_end_hour=data["conditional_trader_end_hour"],
        conditional_trader_knowledge_hour=data["conditional_trader_knowledge_hour"],
        # Штурм убежищ в выброс (§12.7)
        ongoing_shelter_assaults=_decode(data.get("ongoing_shelter_assaults", {})),
        # Временные убежища (§7.10)
        temp_shelters={
            int(key): _restore(Shelter, value)
            for key, value in _decode(data["temp_shelters"]).items()
        },
        next_shelter_id=data["next_shelter_id"],
        # Журнал изменений отношений (§21 — теперь сериализуются)
        prev_relation_snapshot=_decode(data.get("prev_relation_snapshot", {})),
        relation_change_journal=_decode(data.get("relation_change_journal", [])),
        intention_knowledge_used=_decode(data.get("intention_knowledge_used", {})),
        knowledge_snapshot_at_intention=_decode(data.get("knowledge_snapshot_at_intention", [])),
    )
