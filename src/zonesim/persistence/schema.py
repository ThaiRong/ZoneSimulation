"""Schema-driven сериализация: реестр типов + адаптеры.

Цель: новое поле невозможно забыть — типы поля определяют стратегию
кодирования/декодирования. Production-код сериализации (serialization.py)
НЕ изменяется; schema.py работает автономно и подключается позже по флагу.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Реестр адаптеров: type → (encode_fn, decode_fn, display_name)
# ---------------------------------------------------------------------------

_adapter_registry: dict[type, tuple[Callable[[Any], Any], Callable[[Any], Any], str]] = {}


def register_type(type_cls: type, encode_fn: Callable, decode_fn: Callable, name: str = "") -> None:
    """Зарегистрировать адаптер для типа.

    Args:
        type_cls: тип, для которого работает адаптер
        encode_fn: encode_python(obj) -> json-safe
        decode_fn: decode_json(data) -> obj
        name: имя типа для отладки
    """
    adapter_name = name or type_cls.__name__
    _adapter_registry[type_cls] = (encode_fn, decode_fn, adapter_name)


def get_adapter(type_cls: type) -> tuple[Callable, Callable, str] | None:
    """Вернуть (encode, decode, name) для типа, или None."""
    return _adapter_registry.get(type_cls)  # type: ignore


def get_adapter_name(type_cls: type) -> str | None:
    entry = _adapter_registry.get(type_cls)
    return entry[2] if entry else None


# ---------------------------------------------------------------------------
# Примитивы
# ---------------------------------------------------------------------------

def _is_primitive(value: Any) -> bool:
    if value is None:
        return True
    # bool ДО int, т.к. bool <- int
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return True
    if isinstance(value, str):
        return True
    return False


# ---------------------------------------------------------------------------
# Core encode / decode
# ---------------------------------------------------------------------------

def encode_value(value: Any) -> Any:
    """Кодировать любое значение в JSON-safe структуру.

    Порядок проверки (совпадает с serialization.py):
    1. None, bool, int, float, str  →  as-is
    2. Enum  →  .value
    3. Dataclass  →  {"__kind__":"dataclass","__type__":name,"fields":{…}}
    4. Кастомные адаптеры (реестр)
    5. list  →  [...]
    6. tuple  →  {"__kind__":"tuple","items":[...]}
    7. set  →  {"__kind__":"set","items":[...]}
    8. dict  →  {"__kind__":"dict","items":[[k,v],...]}
    """
    # 1. Примитивы
    if _is_primitive(value):
        return value

    # 2. Enum
    if isinstance(value, Enum):
        return value.value

    # 3. Dataclass
    if hasattr(value, "__dataclass_fields__"):
        return {
            "__kind__": "dataclass",
            "__type__": value.__class__.__name__,
            "fields": {
                f.name: encode_value(getattr(value, f.name))
                for f in dataclasses.fields(value)
            },
        }

    # 4. Кастомные адаптеры
    adapter = get_adapter(type(value))
    if adapter is not None:
        enc_fn, _, _ = adapter
        return {"__kind__": "adapter", "__type__": adapter[2], "data": enc_fn(value)}

    # 5. list
    if isinstance(value, list):
        return [encode_value(item) for item in value]

    # 6. tuple
    if isinstance(value, tuple):
        return {"__kind__": "tuple", "items": [encode_value(item) for item in value]}

    # 7. set
    if isinstance(value, set):
        return {"__kind__": "set", "items": [encode_value(item) for item in sorted(value)]}

    # 8. dict
    if isinstance(value, dict):
        return {
            "__kind__": "dict",
            "items": [[encode_value(k), encode_value(v)] for k, v in value.items()],
        }

    raise TypeError(f"Неподдерживаемый тип для кодирования: {type(value).__name__}")


def decode_value(data: Any) -> Any:
    """Декодировать JSON-safe структуру обратно в Python-объекты."""
    # list — рекурсивно декодируем элементы
    if isinstance(data, list):
        return [decode_value(item) for item in data]

    if not isinstance(data, dict):
        return data

    kind = data.get("__kind__")

    if kind == "tuple":
        return tuple(decode_value(item) for item in data["items"])

    if kind == "set":
        return {decode_value(item) for item in data["items"]}

    if kind == "dict":
        pairs = data["items"]
        return {decode_value(k): decode_value(v) for k, v in pairs}

    if kind == "dataclass":
        # Декодируем все поля dataclass рекурсивно
        decoded_fields = {k: decode_value(v) for k, v in data["fields"].items()}
        return _restore_dataclass(data["__type__"], decoded_fields)

    if kind == "adapter":
        type_name = data["__type__"]
        return _restore_adapter(type_name, data["data"])

    # Плоский dict (без __kind__) — рекурсивно декодируем значения
    return {k: decode_value(v) for k, v in data.items()}


# ---------------------------------------------------------------------------
# Dataclass reconstruction
# ---------------------------------------------------------------------------

def _restore_dataclass(cls_name: str, fields_data: dict[str, Any]) -> Any:
    """Восстановить dataclass из декодированных полей."""
    import zonesim.world.entity
    import zonesim.world.group
    import zonesim.world.item
    import zonesim.world.stash
    import zonesim.world.shelter
    import zonesim.world.sector
    import zonesim.anomalies.artifact
    import zonesim.anomalies.core
    import zonesim.combat.loot
    import zonesim.relations.news
    import zonesim.knowledge.fact

    _cls_map: dict[str, type] = {
        # Entity types
        "StatsMixin": zonesim.world.entity.StatsMixin,
        "BaseEntity": zonesim.world.entity.BaseEntity,
        "HumanNPC": zonesim.world.entity.HumanNPC,
        "Monster": zonesim.world.entity.Monster,
        # Groups
        "GroupMembership": zonesim.world.group.GroupMembership,
        "HumanGroup": zonesim.world.group.HumanGroup,
        "MonsterGroup": zonesim.world.group.MonsterGroup,
        # Items / world
        "Item": zonesim.world.item.Item,
        "Stash": zonesim.world.stash.Stash,
        "Shelter": zonesim.world.shelter.Shelter,
        "StormShelter": zonesim.world.shelter.StormShelter,
        "Sector": zonesim.world.sector.Sector,
        # Anomalies
        "Artifact": zonesim.anomalies.artifact.Artifact,
        "Anomaly": zonesim.anomalies.core.Anomaly,
        # Combat
        "Corpse": zonesim.combat.loot.Corpse,
        "EquipmentDamage": zonesim.combat.loot.EquipmentDamage,
        # Relations / news
        "WorldEvent": zonesim.relations.news.WorldEvent,
        "PracticeProgress": zonesim.relations.development.PracticeProgress,
        # Knowledge
        "KnowledgeFact": zonesim.knowledge.fact.KnowledgeFact,
        "KnowledgeBase": zonesim.knowledge.fact.KnowledgeBase,
        # Economy
        "Contract": zonesim.economy.contracts.Contract,
        "ExportRecord": zonesim.economy.trade.ExportRecord,
        "ImportRecord": zonesim.economy.trade.ImportRecord,
    }

    cls = _cls_map.get(cls_name)
    if cls is None:
        raise LookupError(f"Не найден dataclass для имени: {cls_name}")

    obj = cls.__new__(cls)
    # fields_data уже декодирован decode_value → fields_data → _decode_dataclass_fields
    # Присваиваем явно через setattr чтобы гарантировать типизацию
    for key, value in fields_data.items():
        setattr(obj, key, value)
    return obj


def _restore_adapter(type_name: str, data: Any) -> Any:
    """Восстановить объект по имени адаптера и декодированным данным."""
    for type_cls, (_, dec_fn, adv_name) in _adapter_registry.items():
        if adv_name == type_name:
            return dec_fn(data)
    raise LookupError(f"Не найден адаптер для имени: {type_name}")


# ---------------------------------------------------------------------------
# Адаптеры для кастомных типов
# ---------------------------------------------------------------------------

# --- SeededRNG (non-dataclass, хранит random.Random) ---

def _encode_seeded_rng(rng: Any) -> dict[str, Any]:
    return {"seed": rng.seed, "state": encode_value(rng.get_state())}


def _decode_seeded_rng(data: dict[str, Any]) -> Any:
    from zonesim.core.time import SeededRNG
    rng = SeededRNG(data["seed"])
    rng.set_state(decode_value(data["state"]))
    return rng


# --- GameTime (non-dataclass, хранит int.hour) ---

def _encode_game_time(gt: Any) -> dict[str, int]:
    return {"hour": gt.hour}


def _decode_game_time(data: dict[str, int]) -> Any:
    from zonesim.core.time import GameTime
    return GameTime(data["hour"])


# --- Non-dataclass менеджеры (vars-based) ---

def _encode_manager(obj: Any) -> dict[str, Any]:
    """Для менеджеров без dataclass: vars(obj) рекурсивно."""
    return vars(obj)


def _decode_manager(obj: Any) -> Any:
    """Менеджеры восстанавливаются через vars-данные в SchemaEncoder.decode_state."""
    # Это не direct-адаптер, manager decode происходит в SchemaEncoder
    raise NotImplementedError("Менеджеры декодируются через SchemaEncoder.decode_state")


# ---------------------------------------------------------------------------
# SchemaEncoder — state-level encode/decode
# ---------------------------------------------------------------------------

class SchemaEncoder:
    """Кодирует/декодирует SimulationState полностью, включая 4 теряемых поля."""

    def __init__(self) -> None:
        pass

    # --- ENCODE ---

    def encode_state(self, state: Any) -> dict[str, Any]:
        """Кодировать SimulationState в dict (schema-driven, все 56 полей)."""
        from zonesim.simulation.engine import SimulationState

        # type: name-ignore
        s: SimulationState = state

        result: dict[str, Any] = {}

        # Поля, которые можно закодировать через encode_value:
        result["time"] = _encode_game_time(s.time)
        result["rng"] = _encode_seeded_rng(s.rng)

        result["sectors"] = {k: encode_value(v) for k, v in s.sectors.items()}
        result["humans"] = [encode_value(h) for h in s.humans]
        result["stationary_humans"] = [encode_value(h) for h in s.stationary_humans]
        result["human_groups"] = {k: encode_value(v) for k, v in s.human_groups.items()}
        result["monsters"] = [encode_value(m) for m in s.monsters]
        result["monster_groups"] = {k: encode_value(v) for k, v in s.monster_groups.items()}
        result["anomalies"] = {k: encode_value(v) for k, v in s.anomalies.items()}

        # Managers (non-dataclass) — кодируем vars
        result["artifacts"] = _encode_manager(s.artifacts)
        result["contracts"] = _encode_manager(s.contracts)
        result["import_export"] = _encode_manager(s.import_export)
        result["personal_relations"] = _encode_manager(s.personal_relations)
        result["faction_relations"] = _encode_manager(s.faction_relations)
        result["development"] = _encode_manager(s.development)
        result["exile_manager"] = _encode_manager(s.exile_manager)
        result["faction_change_manager"] = _encode_manager(s.faction_change_manager)
        result["news_manager"] = _encode_manager(s.news_manager)
        result["migration_state"] = _encode_manager(s.migration_state)
        result["monster_migration"] = _encode_manager(s.monster_migration)
        result["knowledge_bases"] = {k: encode_value(v) for k, v in s.knowledge_bases.items()}

        result["stashs"] = [encode_value(sh) for sh in s.stashs]
        result["corpses"] = [encode_value(c) for c in s.corpses]
        result["items"] = {k: encode_value(v) for k, v in s.items.items()}

        # Integers
        result["shelter_count"] = s.shelter_count
        result["next_shelter_id"] = s.next_shelter_id
        result["next_emission_hour"] = s.next_emission_hour
        result["emission_start_hour"] = s.emission_start_hour
        result["emission_end_hour"] = s.emission_end_hour
        result["emission_warning_hour"] = s.emission_warning_hour
        result["next_conditional_spawn_hour"] = s.next_conditional_spawn_hour
        result["conditional_trader_id"] = s.conditional_trader_id
        result["conditional_trader_sector"] = s.conditional_trader_sector
        result["conditional_trader_start_hour"] = s.conditional_trader_start_hour
        result["conditional_trader_end_hour"] = s.conditional_trader_end_hour
        result["conditional_trader_knowledge_hour"] = s.conditional_trader_knowledge_hour

        # Collections с ключами str/int
        result["trader_stock"] = {str(k): v for k, v in s.trader_stock.items()}
        result["trails"] = s.trails
        result["shelters"] = {k: encode_value(v) for k, v in s.shelters.items()}
        result["emission_exposed"] = {str(k): v for k, v in s.emission_exposed.items()}

        # ID generators
        result["next_human_id"] = s.next_human_id
        result["next_monster_id"] = s.next_monster_id
        result["next_group_id"] = s.next_group_id
        result["next_monster_group_id"] = s.next_monster_group_id
        result["next_anomaly_id"] = s.next_anomaly_id
        result["next_stash_id"] = s.next_stash_id
        result["next_corpse_id"] = s.next_corpse_id
        result["next_item_id"] = s.next_item_id

        # visit_memory, config
        result["visit_memory"] = encode_value(s.visit_memory)
        result["config"] = encode_value(s.config)

        # Ongoing shelter assaults
        result["ongoing_shelter_assaults"] = encode_value(s.ongoing_shelter_assaults)

        # Temp shelters — кастомный to_dict()
        result["temp_shelters"] = {
            str(k): (v.to_dict() if hasattr(v, "to_dict") else encode_value(v))
            for k, v in s.temp_shelters.items()
        }

        # --- 4 ранее теряемых поля (теперь сериализуются!) ---
        result["prev_relation_snapshot"] = encode_value(s.prev_relation_snapshot)
        result["relation_change_journal"] = encode_value(s.relation_change_journal)
        result["intention_knowledge_used"] = encode_value(s.intention_knowledge_used)
        result["knowledge_snapshot_at_intention"] = encode_value(s.knowledge_snapshot_at_intention)

        return result

    # --- DECODE ---

    def decode_state(self, data: dict[str, Any]) -> Any:
        """Декодировать dict обратно в SimulationState."""
        from zonesim.simulation.engine import SimulationState
        from zonesim.core.time import GameTime, SeededRNG

        # --- time ---
        time = GameTime(data["time"]["hour"])

        # --- rng ---
        rng = SeededRNG(data["rng"]["seed"])
        rng.set_state(decode_value(data["rng"]["state"]))

        # --- basic collections ---
        sectors = {k: decode_value(v) for k, v in data["sectors"].items()}
        humans = [decode_value(h) for h in data["humans"]]
        stationary_humans = [decode_value(h) for h in data["stationary_humans"]]
        human_groups = {k: decode_value(v) for k, v in data["human_groups"].items()}
        monsters = [decode_value(m) for m in data["monsters"]]
        monster_groups = {k: decode_value(v) for k, v in data["monster_groups"].items()}
        anomalies = {k: decode_value(v) for k, v in data["anomalies"].items()}
        corpses = [decode_value(c) for c in data["corpses"]]
        items = {k: decode_value(v) for k, v in data["items"].items()}
        stashs = [decode_value(sh) for sh in data["stashs"]]
        shelters = {k: decode_value(v) for k, v in data["shelters"].items()}

        # --- managers ---
        artifacts = decode_manager_data(data["artifacts"])
        contracts = decode_manager_data(data["contracts"])
        import_export = decode_manager_data(data["import_export"])
        personal_relations = decode_manager_data(data["personal_relations"])
        faction_relations = decode_manager_data(data["faction_relations"])
        development = decode_development_manager(data["development"])
        exile_manager = decode_manager_data(data["exile_manager"])
        faction_change_manager = decode_manager_data(data["faction_change_manager"])
        news_manager = decode_news_manager(data["news_manager"])
        knowledge_bases = {k: decode_value(v) for k, v in data["knowledge_bases"].items()}
        migration_state = decode_manager_data(data["migration_state"])
        monster_migration = decode_manager_data(data["monster_migration"])

        # --- integers ---
        shelter_count = data["shelter_count"]
        next_shelter_id = data["next_shelter_id"]
        next_emission_hour = data["next_emission_hour"]
        emission_start_hour = data["emission_start_hour"]
        emission_end_hour = data["emission_end_hour"]
        emission_warning_hour = data["emission_warning_hour"]
        next_conditional_spawn_hour = data["next_conditional_spawn_hour"]
        conditional_trader_id = data["conditional_trader_id"]
        conditional_trader_sector = data["conditional_trader_sector"]
        conditional_trader_start_hour = data["conditional_trader_start_hour"]
        conditional_trader_end_hour = data["conditional_trader_end_hour"]
        conditional_trader_knowledge_hour = data["conditional_trader_knowledge_hour"]

        # collections with str/int keys
        trader_stock = {int(k): v for k, v in data["trader_stock"].items()}
        trails = data["trails"]
        emission_exposed = {int(k): v for k, v in data["emission_exposed"].items()}

        # ID generators
        next_human_id = data["next_human_id"]
        next_monster_id = data["next_monster_id"]
        next_group_id = data["next_group_id"]
        next_monster_group_id = data["next_monster_group_id"]
        next_anomaly_id = data["next_anomaly_id"]
        next_stash_id = data["next_stash_id"]
        next_corpse_id = data["next_corpse_id"]
        next_item_id = data["next_item_id"]

        visit_memory = decode_value(data["visit_memory"])
        config = decode_value(data["config"])
        ongoing_shelter_assaults = decode_value(data["ongoing_shelter_assaults"])

        # temp shelters — Shelter (не StormShelter, как в serialization.py)
        temp_shelters = {}
        for k, v in data["temp_shelters"].items():
            temp_shelters[int(k)] = _restore_shelter_from_dict(v)

        # --- 4 ранее теряемых поля (теперь восстанавливаются!) ---
        prev_relation_snapshot = decode_value(data.get("prev_relation_snapshot", {}))
        relation_change_journal = decode_value(data.get("relation_change_journal", []))
        intention_knowledge_used = decode_value(data.get("intention_knowledge_used", {}))
        knowledge_snapshot_at_intention = decode_value(data.get("knowledge_snapshot_at_intention", []))

        return SimulationState(
            time=time,
            rng=rng,
            sectors=sectors,
            humans=humans,
            stationary_humans=stationary_humans,
            human_groups=human_groups,
            monsters=monsters,
            monster_groups=monster_groups,
            anomalies=anomalies,
            artifacts=artifacts,
            corpses=corpses,
            items=items,
            contracts=contracts,
            import_export=import_export,
            personal_relations=personal_relations,
            faction_relations=faction_relations,
            development=development,
            exile_manager=exile_manager,
            faction_change_manager=faction_change_manager,
            news_manager=news_manager,
            knowledge_bases=knowledge_bases,
            stashs=stashs,
            shelter_count=shelter_count,
            next_shelter_id=next_shelter_id,
            trader_stock=trader_stock,
            trails=trails,
            shelters=shelters,
            next_emission_hour=next_emission_hour,
            emission_start_hour=emission_start_hour,
            emission_end_hour=emission_end_hour,
            emission_warning_hour=emission_warning_hour,
            emission_exposed=emission_exposed,
            migration_state=migration_state,
            monster_migration=monster_migration,
            next_human_id=next_human_id,
            next_monster_id=next_monster_id,
            next_group_id=next_group_id,
            next_monster_group_id=next_monster_group_id,
            next_anomaly_id=next_anomaly_id,
            next_stash_id=next_stash_id,
            next_corpse_id=next_corpse_id,
            next_item_id=next_item_id,
            visit_memory=visit_memory,
            config=config,
            next_conditional_spawn_hour=next_conditional_spawn_hour,
            conditional_trader_id=conditional_trader_id,
            conditional_trader_sector=conditional_trader_sector,
            conditional_trader_start_hour=conditional_trader_start_hour,
            conditional_trader_end_hour=conditional_trader_end_hour,
            conditional_trader_knowledge_hour=conditional_trader_knowledge_hour,
            ongoing_shelter_assaults=ongoing_shelter_assaults,
            temp_shelters=temp_shelters,
            prev_relation_snapshot=prev_relation_snapshot,
            relation_change_journal=relation_change_journal,
            intention_knowledge_used=intention_knowledge_used,
            knowledge_snapshot_at_intention=knowledge_snapshot_at_intention,
        )


# ---------------------------------------------------------------------------
# Менеджер-специфичные декодеры
# ---------------------------------------------------------------------------

def _restore_obj(cls: type, data: dict[str, Any]) -> Any:
    """Восстановить объект класса без __init__ из декодированного словаря."""
    obj = cls.__new__(cls)
    obj.__dict__.update(data)
    return obj


def decode_manager_data(data: dict[str, Any]) -> Any:
    """Декодировать данные non-dataclass менеджера (vars-based)."""
    # Managers are just flat dicts of lists/dicts — decode_value handles them
    # We need to reconstruct the manager class from the data
    if not data:
        # Empty manager — return default instance (will be replaced by encoder on write)
        return None  # type: ignore

    # Managers have no type tag in the encoded data — decode as plain dict
    # The caller is responsible for knowing which manager class this is.
    # For SchemaEncoder we do special handling below.
    return data


def decode_manager_with_class(manager_cls: type, data: dict[str, Any]) -> Any:
    """Восстановить менеджер конкретного класса из vars-данных."""
    obj = manager_cls.__new__(manager_cls)
    obj.__dict__.update(decode_value(data))
    return obj


def decode_development_manager(data: dict[str, Any]) -> Any:
    """DevelopmentManager имеет особую структуру (nested dict)."""
    from zonesim.relations.development import DevelopmentManager
    dm = DevelopmentManager.__new__(DevelopmentManager)
    dm.progress = decode_value(data.get("progress", {}))
    return dm


def decode_news_manager(data: dict[str, Any]) -> Any:
    """NewsManager — воссоздать события."""
    from zonesim.relations.news import NewsManager
    nm = NewsManager.__new__(NewsManager)
    decoded = decode_value(data)
    nm.events = decoded.get("events", [])
    nm.hourly_summaries = decoded.get("hourly_summaries", [])
    return nm


# ---------------------------------------------------------------------------
# Shelter decoder
# ---------------------------------------------------------------------------

def _restore_shelter_from_dict(data: dict[str, Any]) -> Any:
    """Восстановить Shelter из to_dict-формата (как в serialization.py)."""
    from zonesim.world.shelter import Shelter
    obj = Shelter.__new__(Shelter)
    obj.__dict__.update(data)
    return obj


# ---------------------------------------------------------------------------
# Запуск — регистрация типов
# ---------------------------------------------------------------------------

def _register_type(type_cls: type, encode_fn, decode_fn, name: str = "") -> None:
    register_type(type_cls, encode_fn, decode_fn, name)


def init_schema() -> None:
    """Инициализация реестра типов (вызывается один раз при импорте)."""
    # Импортируем лениво чтобы избежать circular imports
    from zonesim.core.time import GameTime, SeededRNG
    _register_type(SeededRNG, _encode_seeded_rng, _decode_seeded_rng, "SeededRNG")
    _register_type(GameTime, _encode_game_time, _decode_game_time, "GameTime")


# Автоинициализация при импорте
init_schema()


# ---------------------------------------------------------------------------
# Module-level: выписать типы всех 56 полей
# ---------------------------------------------------------------------------

FIELD_TYPES: list[tuple[str, str]] = [
    ("time", "GameTime"),
    ("rng", "SeededRNG"),
    ("sectors", "dict[int, Sector]"),
    ("humans", "list[HumanNPC]"),
    ("stationary_humans", "list[HumanNPC]"),
    ("human_groups", "dict[int, HumanGroup]"),
    ("monsters", "list[Monster]"),
    ("monster_groups", "dict[int, MonsterGroup]"),
    ("anomalies", "dict[int, AnomalyEntity]"),
    ("artifacts", "ArtifactManager"),
    ("corpses", "list[Corpse]"),
    ("items", "dict[int, Item]"),
    ("contracts", "ContractManager"),
    ("import_export", "ImportExportManager"),
    ("personal_relations", "PersonalRelations"),
    ("faction_relations", "FactionRelations"),
    ("development", "DevelopmentManager"),
    ("exile_manager", "ExileManager"),
    ("faction_change_manager", "FactionChangeManager"),
    ("news_manager", "NewsManager"),
    ("knowledge_bases", "dict[int, KnowledgeBase]"),
    ("stashs", "list[Stash]"),
    ("shelter_count", "int"),
    ("next_shelter_id", "int"),
    ("trader_stock", "dict[int, dict[str, int]]"),
    ("trails", "list[list[int]]"),
    ("shelters", "dict[int, StormShelter]"),
    ("next_emission_hour", "int"),
    ("emission_start_hour", "int"),
    ("emission_end_hour", "int"),
    ("emission_warning_hour", "int"),
    ("emission_exposed", "dict[int, int]"),
    ("migration_state", "MigrationState"),
    ("monster_migration", "MonsterMigrationManager"),
    ("next_human_id", "int"),
    ("next_monster_id", "int"),
    ("next_group_id", "int"),
    ("next_monster_group_id", "int"),
    ("next_anomaly_id", "int"),
    ("next_stash_id", "int"),
    ("next_corpse_id", "int"),
    ("next_item_id", "int"),
    ("visit_memory", "dict[int, dict[int, int]]"),
    ("config", "dict"),
    ("prev_relation_snapshot", "dict[tuple[str, str], int]"),
    ("relation_change_journal", "list[dict]"),
    ("intention_knowledge_used", "dict[int, list[dict]]"),
    ("knowledge_snapshot_at_intention", "dict[int, list[dict]]"),
    ("next_conditional_spawn_hour", "int"),
    ("conditional_trader_id", "int | None"),
    ("conditional_trader_sector", "int"),
    ("conditional_trader_start_hour", "int"),
    ("conditional_trader_end_hour", "int"),
    ("conditional_trader_knowledge_hour", "int"),
    ("ongoing_shelter_assaults", "dict[int, dict]"),
    ("temp_shelters", "dict[int, Shelter]"),
]


# ---------------------------------------------------------------------------
# Экспорт
# ---------------------------------------------------------------------------

__all__ = [
    "encode_value",
    "decode_value",
    "SchemaEncoder",
    "register_type",
    "get_adapter",
    "FIELD_TYPES",
]
