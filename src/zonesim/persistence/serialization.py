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

# Импорт schema-driven функций для state_from_dict
from zonesim.persistence.schema import decode_value  # noqa: F401

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _encode(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    # Dataclass → кодировать с __kind__='dataclass' чтобы decode_value мог восстановить
    if hasattr(value, "__dataclass_fields__"):
        import dataclasses
        return {
            "__kind__": "dataclass",
            "__type__": value.__class__.__name__,
            "fields": {f.name: _encode(getattr(value, f.name))
                       for f in dataclasses.fields(value)},
        }
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
    "sectors", "human_groups", "monster_groups", "items", "knowledge_bases",
}
# Anomalies требуют enum-восстановления
_DATACLASS_DICT_NAMES_WITH_ENUM: set[str] = {"anomalies"}
# Маппинг: field_name → dataclass class для dict values
_DATACLASS_DICT_CLASS_MAP: dict[str, type] = {
    "sectors": Sector,
    "human_groups": HumanGroup,
    "monster_groups": MonsterGroup,
    "items": Item,
    "knowledge_bases": KnowledgeBase,
}
# Маппинг enum-полей для Item
_ITEM_ENUM_FIELDS: dict[str, type[Enum]] = {"type": ItemType}


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


# --- restore_dict_keys ---
# При кодировании JSON ключи dict stringifyруются → при декодировании нужно
# восстановить типы ключей по аннотациям полей SimulationState.


def _restore_dict_keys(data: Any, field_type: Any, field_name: str) -> Any:
    """Восстановить типы ключей dict и элементов коллекций по аннотации типа.

    КРИТИЧНО: проверяем тип ДАННЫХ, затем аннотацию field_type.
    Иначе _restore_dict_keys({"id": 1}, list[dict], ...) → origin=list →
    for item in data → итерация по ключам dict → превращение в ["id", ...].
    """
    try:
        from typing import get_origin, get_args
        origin = get_origin(field_type)
        args = get_args(field_type)
    except Exception:
        origin, args = None, ()

    # ДАННЫЕ — dict, аннотация — dict[key_type, value_type] → восстанавливаем ключи
    if isinstance(data, dict) and origin is dict and args and len(args) >= 2:
        key_type = args[0]
        value_type = args[1]
        result: dict[Any, Any] = {}
        for k, v in data.items():
            restored_key = _convert_key(k, key_type, field_name)
            restored_val = _restore_dict_keys(v, value_type, f"{field_name}#{k}")
            result[restored_key] = restored_val
        return result

    # ДАННЫЕ — list, аннотация — list[element_type] → восстанавливаем элементы
    if isinstance(data, list) and origin is list and args:
        elem_type = args[0]
        return [_restore_dict_keys(item, elem_type, field_name) for item in data]

    # ДАННЫЕ — dict, но аннотация не dict → рекурсивно декодируем значения
    if isinstance(data, dict):
        return {k: _restore_dict_keys(v, field_type, field_name) for k, v in data.items()}

    # ДАННЫЕ — list, но аннотация не list → рекурсивно декодируем элементы
    if isinstance(data, list):
        return [_restore_dict_keys(item, field_type, field_name) for item in data]

    return data


def _convert_key(raw_key: Any, key_type: type, field_name: str) -> Any:
    """Конвертировать raw_key (str из JSON) в key_type."""
    # Параметризованные generics (tuple[str, str]) нельзя использовать в isinstance
    try:
        from typing import get_origin
        base_type = get_origin(key_type) or key_type
    except Exception:
        base_type = key_type

    # Проверка на уже восстановленный тип
    if isinstance(raw_key, base_type):
        return raw_key

    # key_type = int
    if base_type is int:
        try:
            return int(raw_key)
        except (ValueError, TypeError):
            return raw_key

    # key_type = tuple[str, str] или другой tuple
    if base_type is tuple:
        if isinstance(raw_key, str):
            try:
                import json
                parsed = json.loads(raw_key)
                if isinstance(parsed, list):
                    return tuple(parsed)
            except (json.JSONDecodeError, ValueError):
                pass
            if ',' in raw_key:
                parts = raw_key.split(',', 1)
                return tuple(parts)
            return raw_key

    # key_type = str
    if base_type is str:
        return str(raw_key)

    return raw_key


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


# --- Маппинг менеджеров: имя поля → класс менеджера ---
# Это НЕ ручное перечисление полей в state_from_dict — это метаданные
# для восстановления типа менеджера по имени поля (аналогично _MANAGER_NAMES).
_MANAGER_FIELD_CLASS: dict[str, type] = {
    "artifacts": ArtifactManager,
    "contracts": ContractManager,
    "import_export": ImportExportManager,
    "personal_relations": PersonalRelations,
    "faction_relations": FactionRelations,
    "development": DevelopmentManager,
    "exile_manager": ExileManager,
    "faction_change_manager": FactionChangeManager,
    "news_manager": NewsManager,
    "migration_state": MigrationState,
    "monster_migration": MonsterMigrationManager,
}


def _decode_raw(value: Any) -> Any:
    """Простой рекурсивный decode без __kind__ обработки (для vars-данных)."""
    if isinstance(value, list):
        return [_decode_raw(item) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value.get("__kind__")
    if kind == "tuple":
        return tuple(_decode_raw(item) for item in value["items"])
    if kind == "set":
        return {_decode_raw(item) for item in value["items"]}
    if kind == "dict":
        pairs = value["items"]
        return {_decode_raw(k): _decode_raw(v) for k, v in pairs}
    return {k: _decode_raw(v) for k, v in value.items()}


def _restore_dataclass(cls: type, data: dict[str, Any],
                        enum_fields: dict[str, type[Enum]] | None = None) -> Any:
    """Восстановить dataclass-объект (или менеджер) из vars-словаря.

    decode_value из schema.py знает про __kind__='dataclass' и реконструирует
    вложенные dataclass-объекты (Artifact, Contract и т.д.).
    """
    decoded = decode_value(data)
    obj = cls.__new__(cls)
    obj.__dict__.update(decoded)
    if enum_fields:
        for field_name, enum_type in enum_fields.items():
            value = getattr(obj, field_name, None)
            if value is not None:
                setattr(obj, field_name, enum_type(value))
    return obj


def _decode_with_key_restore(name: str, data: Any, field_type: Any,
                              manager_map: dict[str, type]) -> Any:
    """Декодировать поле с восстановлением типов ключей по аннотации."""
    decoded = _decode_raw(data)
    # Если это менеджер — восстановим класс
    if name in manager_map:
        manager_cls = manager_map[name]
        decoded = _restore_dataclass(manager_cls, decoded)
    # Восстановим типы ключей по аннотации
    return _restore_dict_keys(decoded, field_type, name)


def state_from_dict(data: dict[str, Any]) -> SimulationState:
    """Рефлексивная десериализация SimulationState через dataclasses.fields.

    Никакого ручного перечисления полей — поля перебираются рефлексией,
    стратегия декодирования определяется по типу поля и имени.
    Для менеджеров используется _MANAGER_FIELD_CLASS маппинг.
    Для dataclass dict/list полей — decode + restore via class.
    Для остальных — decode + restore_dict_keys по аннотации типа.
    """
    import dataclasses
    from typing import get_type_hints, Any as typing_Any
    from zonesim.simulation.engine import SimulationState

    # Получаем аннотации типов из SimulationState
    hints = get_type_hints(SimulationState, localns=dict(globals()))

    result: dict[str, Any] = {}
    for field in dataclasses.fields(SimulationState):
        name = field.name
        field_type = hints.get(name, typing_Any)
        raw = data.get(name)

        if raw is None:
            result[name] = None
            continue

        strategy = _FIELD_ENCODE_STRATEGY.get(name)

        if strategy is not None:
            decoded = decode_value(raw)

            # time/rng — специальные типы
            if name == "time":
                result[name] = GameTime(decoded["hour"])
                continue
            elif name == "rng":
                rng = SeededRNG(decoded["seed"])
                rng.set_state(decode_value(decoded["state"]))
                result[name] = rng
                continue

            # Менеджеры: decode_value → dataclass объекты + restore_dict_keys для ключей
            if name in _MANAGER_FIELD_CLASS:
                manager_cls = _MANAGER_FIELD_CLASS[name]
                decoded = _restore_dataclass(manager_cls, decoded)
                # Для managers с enum-полями нужно дообработать
                # decode_value из _restore_dataclass уже восстановил вложенные dataclass
                # Поэтому проверяем: если v уже объект нужного типа — не вызывать _restore
                if name == "contracts":
                    new_contracts = {}
                    for k, v in decoded.contracts.items():
                        if isinstance(v, Contract):
                            # Уже восстановлен из __kind__='dataclass'
                            # Но нужно восстановить enum-поля
                            if hasattr(v, 'contract_type') and not isinstance(v.contract_type, ContractType):
                                v.contract_type = ContractType(v.contract_type)
                            if hasattr(v, 'status') and not isinstance(v.status, ContractStatus):
                                v.status = ContractStatus(v.status)
                            new_contracts[k] = v
                        else:
                            new_contracts[k] = _restore(Contract, v,
                                        {"contract_type": ContractType,
                                         "status": ContractStatus})
                    decoded.contracts = new_contracts
                elif name == "development":
                    dm = decoded
                    if hasattr(dm, 'progress') and dm.progress:
                        new_progress = {}
                        for npc_id, stats in dm.progress.items():
                            new_stats = {}
                            for st, p in stats.items():
                                if isinstance(p, PracticeProgress):
                                    if hasattr(p, 'stat_type') and not isinstance(p.stat_type, StatType):
                                        p.stat_type = StatType(p.stat_type)
                                    new_stats[st] = p
                                else:
                                    new_stats[st] = _restore(PracticeProgress, p,
                                                             {"stat_type": StatType})
                            dm.progress[npc_id] = new_stats
                elif name == "news_manager":
                    nm = decoded
                    if hasattr(nm, 'events') and nm.events:
                        new_events = []
                        for e in nm.events:
                            if isinstance(e, WorldEvent):
                                new_events.append(e)
                            else:
                                new_events.append(_restore(WorldEvent, e))
                        nm.events = new_events
                    if hasattr(nm, 'hourly_summaries'):
                        nm.hourly_summaries = _decode_raw(
                            data.get("news_manager", {}).get("hourly_summaries", []))
                elif name == "knowledge_bases":
                    # KnowledgeBase — dataclass, decode_value восстановил через schema
                    pass
                elif name in ("personal_relations", "faction_relations"):
                    pass

                result[name] = decoded
                continue

            # Dataclass dict fields (vars-based encoding): decode_value → dict,
            # нужно восстановить dataclass объекты + restore int-ключи
            if name in _DATACLASS_DICT_NAMES_WITH_ENUM:
                # anomalies: Anomaly с AnomalyType/AnomalyStatus
                # decode_value уже восстановил Anomaly из __kind__='dataclass'
                # Если v уже Anomaly — использовать напрямую, иначе _restore
                restored = {}
                for k, v in decoded.items():
                    if isinstance(v, Anomaly):
                        restored[k] = v
                    else:
                        restored[k] = _restore(Anomaly, v,
                                               {"anomaly_type": AnomalyType,
                                                "status": AnomalyStatus})
                result[name] = restored
                result[name] = _restore_dict_keys(result[name], field_type, name)
                continue

            if name in _DATACLASS_DICT_NAMES:
                cls = _DATACLASS_DICT_CLASS_MAP[name]
                enum_fields = _ITEM_ENUM_FIELDS if name == "items" else None
                restored = {}
                for k, v in decoded.items():
                    # vars-based encoding: decoded fields are raw dicts
                    # Для knowledge_bases — facts нужно дополнительно восстановить KnowledgeFact
                    if name == "knowledge_bases" and isinstance(v, dict):
                        facts = v.get("facts", [])
                        if facts and isinstance(facts, list):
                            v = dict(v)  # copy
                            v["facts"] = [
                                _restore(KnowledgeFact, f, {"fact_type": KnowledgeType})
                                if isinstance(f, dict) else f
                                for f in facts
                            ]
                    if enum_fields:
                        restored[k] = _restore(cls, v, enum_fields)
                    else:
                        restored[k] = _restore(cls, v)
                result[name] = restored
                # restore_dict_keys для int-ключей
                result[name] = _restore_dict_keys(result[name], field_type, name)
                continue

            # shelters/temp_shelters: vars-based encoding → restore StormShelter/Shelter
            if name == "shelters":
                decoded_dict = decode_value(raw)
                result[name] = {
                    int(k): _restore(StormShelter, v)
                    for k, v in decoded_dict.items()
                }
                continue
            if name == "temp_shelters":
                decoded_dict = decode_value(raw)
                result[name] = {
                    int(k): _restore(Shelter, v)
                    for k, v in decoded_dict.items()
                }
                continue

            # List dataclass fields: decode_value → list[dict], restore objects
            if name in _DATACLASS_LIST_NAMES:
                restored = []
                for v in decoded:
                    if name == "humans" or name == "stationary_humans":
                        restored.append(_restore(HumanNPC, v,
                                    {"status": EntityStatus, "type": EntityType})
                                        if isinstance(v, dict) else v)
                    elif name == "monsters":
                        restored.append(_restore_monster(v) if isinstance(v, dict) else v)
                    elif name == "corpses":
                        restored.append(_restore(Corpse, v) if isinstance(v, dict) else v)
                    elif name == "stashs":
                        restored.append(_restore(Stash, v) if isinstance(v, dict) else v)
                result[name] = restored
                continue

            # Остальные поля: decode_value → restore_dict_keys
            result[name] = _restore_dict_keys(decoded, field_type, name)
        else:
            # Поле НЕ в _FIELD_ENCODE_STRATEGY
            if name == "anomalies":
                decoded = decode_value(raw)
                # decode_value уже восстановил Anomaly из __kind__='dataclass'
                restored = {}
                for k, v in decoded.items():
                    if isinstance(v, Anomaly):
                        restored[k] = v
                    else:
                        restored[k] = _restore(Anomaly, v,
                                               {"anomaly_type": AnomalyType,
                                                "status": AnomalyStatus})
                result[name] = restored
            elif name == "relation_change_journal":
                # list[dict] encoded через _encode → list of {"__kind__": "dict", ...}
                # decode_value восстанавливает list of dict
                decoded = decode_value(raw)
                result[name] = decoded if isinstance(decoded, list) else []
            elif name == "knowledge_snapshot_at_intention":
                # dict[int, list[dict]] — restore int keys
                decoded = decode_value(raw)
                result[name] = _restore_dict_keys(decoded, field_type, name)
            elif name == "intention_knowledge_used":
                # dict[int, list[dict]] — restore int keys
                decoded = decode_value(raw)
                result[name] = _restore_dict_keys(decoded, field_type, name)
            elif name == "prev_relation_snapshot":
                # dict[tuple[str,str], int] — restore tuple keys
                decoded = decode_value(raw)
                result[name] = _restore_dict_keys(decoded, field_type, name)
            else:
                result[name] = _decode_with_key_restore(
                    name, raw, field_type, _MANAGER_FIELD_CLASS)

    return SimulationState(**result)
