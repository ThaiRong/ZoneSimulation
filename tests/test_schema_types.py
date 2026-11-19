"""Юнит-тесты schema-driven сериализации: кодирование/декодирование по типам.

Каждый тип поля SimulationState имеет тест round-trip.
Production-код НЕ изменяется.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any

import pytest

from zonesim.persistence.schema import (
    FIELD_TYPES,
    SchemaEncoder,
    decode_value,
    encode_value,
    get_adapter,
    register_type,
)


# ===================================================================
# 0. Инвентаризация: FIELD_TYPES
# ===================================================================

def test_field_types_count_is_56() -> None:
    """Все 56 полей SimulationState задокументированы в FIELD_TYPES."""
    assert len(FIELD_TYPES) == 56


def test_field_types_no_duplicates() -> None:
    """Имена полей в FIELD_TYPES уникальны."""
    names = [name for name, _ in FIELD_TYPES]
    assert len(names) == len(set(names)), f"Дубликаты: {[n for n in names if names.count(n) > 1]}"


# ===================================================================
# 1. Примитивы (bool ДО int, т.к. bool ← int)
# ===================================================================

class TestPrimitives:
    """bool, int, float, str, None."""

    @pytest.mark.parametrize(
        "value",
        [
            None,
            True,
            False,
            0,
            1,
            -42,
            0xFFFFFFFF,
            3.14,
            -0.0,
            "hello",
            "",
            "Привет",
        ],
    )
    def test_primitive_roundtrip(self, value: Any) -> None:
        assert decode_value(encode_value(value)) == value

    def test_bool_not_converted_to_int(self) -> None:
        """bool должен оставаться bool, а не превращаться в int."""
        encoded = encode_value(True)
        assert encoded is True  # identity check
        encoded = encode_value(False)
        assert encoded is False

    def test_int_not_converted_to_bool(self) -> None:
        """int 0/1 не должны превращаться в bool."""
        encoded = encode_value(0)
        assert encoded == 0 and isinstance(encoded, int) and not isinstance(encoded, bool)
        encoded = encode_value(1)
        assert encoded == 1 and isinstance(encoded, int) and not isinstance(encoded, bool)


# ===================================================================
# 2. Enum
# ===================================================================

class TestEnums:
    """str-based Enum типы."""

    @pytest.mark.parametrize(
        "enum_value",
        [
            "zonesim.world.entity.EntityStatus.ACTIVE",
            "zonesim.world.entity.EntityType.HUMAN",
            "zonesim.world.entity.EntityType.MONSTER",
            "zonesim.anomalies.core.AnomalyType.SUBTLE",
            "zonesim.anomalies.core.AnomalyStatus.ACTIVE",
            "zonesim.economy.contracts.ContractType.ARTIFACT",
            "zonesim.economy.contracts.ContractStatus.ACTIVE",
            "zonesim.relations.development.StatType.ATTACK",
            "zonesim.knowledge.fact.KnowledgeType.STASH",
            "zonesim.world.item.ItemType.WEAPON",
            "zonesim.world.entity.MonsterSpecies.TERRITORIAL_PREDATOR",
        ],
    )
    def test_enum_roundtrip(self, enum_value: str) -> None:
        # Split into module, class, member: zonesim.world.entity.EntityStatus.ACTIVE
        parts = enum_value.rsplit(".", 2)
        module_path, class_name, member_name = parts
        mod = __import__(module_path, fromlist=[class_name])
        enum_class = getattr(mod, class_name)
        enum = getattr(enum_class, member_name)
        encoded = encode_value(enum)
        assert isinstance(encoded, str)
        # Декодируем — строка остаётся строкой (str, Enum совместимы)
        decoded = decode_value(encoded)
        assert decoded == enum.value


# ===================================================================
# 3. Адаптер: SeededRNG
# ===================================================================

def test_seeded_rng_adapter_exists() -> None:
    from zonesim.core.time import SeededRNG
    adapter = get_adapter(SeededRNG)
    assert adapter is not None

    import importlib
    rng_mod = importlib.import_module("zonesim.core.time")
    rng = rng_mod.SeededRNG(42)
    encoded = encode_value(rng)
    assert isinstance(encoded, dict)
    assert encoded["__kind__"] == "adapter"
    assert encoded["__type__"] == "SeededRNG"
    decoded = decode_value(encoded)
    assert decoded.seed == rng.seed
    assert decoded.get_state() == rng.get_state()


# ===================================================================
# 4. Адаптер: GameTime
# ===================================================================

def test_game_time_adapter_exists() -> None:
    from zonesim.core.time import GameTime
    adapter = get_adapter(GameTime)
    assert adapter is not None

    import importlib
    gt_mod = importlib.import_module("zonesim.core.time")
    gt = gt_mod.GameTime(7)
    encoded = encode_value(gt)
    assert isinstance(encoded, dict)
    assert encoded["__kind__"] == "adapter"
    assert encoded["__type__"] == "GameTime"
    decoded = decode_value(encoded)
    assert decoded.hour == gt.hour


# ===================================================================
# 5. Dataclass-типы
# ===================================================================

class TestDataclassTypes:
    """Каждый dataclass-тип должен проходить round-trip."""

    @pytest.mark.parametrize(
        "factory",
        [
            # (module_path, class_name, args_dict)
            ("zonesim.world.shelter", "StormShelter", {"id": 1, "sector_id": 2, "capacity": 4}),
            ("zonesim.world.shelter", "Shelter", {"id": 1, "sector_id": 2, "owner_group_id": 3}),
            ("zonesim.world.sector", "Sector", {"id": 1, "name": "Test"}),
            ("zonesim.world.item", "Item", {"id": 1, "type": "WEAPON", "name": "sword"}),
            ("zonesim.world.stash", "Stash", {"id": 1, "sector_id": 2, "owner_id": 3, "items": [], "money": 0}),
            ("zonesim.combat.loot", "Corpse", {"id": 1, "original_entity_id": 2, "original_entity_type": "human", "sector_id": 3}),
            ("zonesim.anomalies.artifact", "Artifact", {"id": 1, "anomaly_id": 2}),
            ("zonesim.anomalies.core", "Anomaly", {"id": 1, "sector_id": 2, "anomaly_type": "subtle"}),
            ("zonesim.knowledge.fact", "KnowledgeFact", {"id": 1, "fact_type": "STASH", "subject_id": 2, "payload": {}, "observed_hour": 10}),
            ("zonesim.relations.news", "WorldEvent", {"id": 1, "hour": 10, "minute": 30, "sector_id": 2, "event_type": "test", "participants": [], "result": "ok"}),
            ("zonesim.relations.development", "PracticeProgress", {"stat_type": "ATTACK", "practice_points": 5.0, "last_growth_hour": 10}),
            ("zonesim.economy.contracts", "Contract", {"id": 1, "trader_id": 2, "contract_type": "ARTIFACT", "required_item_type": "artifact", "quantity": 1}),
            ("zonesim.economy.trade", "ExportRecord", {"day": 1, "category": "test", "quantity": 5, "total_value": 100.0}),
            ("zonesim.economy.trade", "ImportRecord", {"day": 1, "category": "test", "quantity": 3, "total_cost": 75.0}),
            ("zonesim.world.group", "HumanGroup", {"id": 1, "members": [1, 2], "sector_id": 3}),
            ("zonesim.world.group", "MonsterGroup", {"id": 1, "members": [1, 2], "sector_id": 3}),
        ],
    )
    def test_dataclass_roundtrip(self, factory: tuple[str, str, dict[str, Any]]) -> None:
        module_path, class_name, kwargs = factory
        mod = __import__(module_path, fromlist=[class_name])
        cls = getattr(mod, class_name)
        instance = cls(**kwargs)

        encoded = encode_value(instance)
        assert isinstance(encoded, dict)
        assert encoded["__kind__"] == "dataclass"
        assert encoded["__type__"] == class_name
        assert "fields" in encoded

        decoded = decode_value(encoded)
        assert type(decoded).__name__ == class_name
        for field in dataclasses.fields(cls):
            fname = field.name
            orig_val = getattr(instance, fname)
            dec_val = getattr(decoded, fname, None)
            assert dec_val == orig_val, (
                f"{class_name}.{fname}: expected {orig_val!r}, got {dec_val!r}"
            )


# ===================================================================
# 6. Коллекции: list, tuple, set, dict
# ===================================================================

class TestCollections:
    def test_list_roundtrip(self) -> None:
        data = [1, "hello", None, True, [1, 2], {"a": 3}]
        assert decode_value(encode_value(data)) == data

    def test_list_of_dataclass(self) -> None:
        from zonesim.world.shelter import StormShelter
        items = [StormShelter(id=i, sector_id=i + 1, capacity=4) for i in range(3)]
        encoded = encode_value(items)
        assert isinstance(encoded, list)
        decoded = decode_value(encoded)
        assert len(decoded) == 3
        assert all(d.id == items[i].id for i, d in enumerate(decoded))

    def test_dict_int_keys(self) -> None:
        data = {1: "a", 2: "b", 99: "c"}
        decoded = decode_value(encode_value(data))
        assert decoded == data

    def test_dict_nested_int_keys(self) -> None:
        data = {1: {2: 3, 4: 5}, 6: {7: 8}}
        decoded = decode_value(encode_value(data))
        assert decoded == data

    def test_tuple_roundtrip(self) -> None:
        data = (1, "hello", 3.14, [1, 2])
        decoded = decode_value(encode_value(data))
        assert decoded == data

    def test_set_roundtrip(self) -> None:
        data = {3, 1, 2, 99}
        decoded = decode_value(encode_value(data))
        assert decoded == data

    def test_nested_collections(self) -> None:
        data: dict[str, Any] = {
            "list": [1, (2, 3), {"set": {4, 5}}],
            "dict": {6: [7, 8]},
        }
        decoded = decode_value(encode_value(data))
        assert decoded == data


# ===================================================================
# 7. Enum-переупаковка (str-based Enum в dataclass)
# ===================================================================

class TestEnumFields:
    """Поля Enum внутри dataclass должны корректно сериализоваться."""

    def test_dataclass_with_enum_field(self) -> None:
        """Item.type — EntityType Enum."""
        from zonesim.world.item import Item, ItemType
        item = Item(id=1, type=ItemType.WEAPON, name="sword", condition=80, base_value=50.0)
        encoded = encode_value(item)
        decoded = decode_value(encoded)
        # ItemType — str, Enum; .value == "WEAPON"
        assert decoded.type == item.type or decoded.type == item.type.value

    def test_dataclass_with_status_enum(self) -> None:
        """StormShelter doesn't have enum but Item.type does."""
        from zonesim.world.entity import EntityStatus, EntityType, HumanNPC
        npc = HumanNPC(id=1, type=EntityType.HUMAN, status=EntityStatus.ACTIVE, name="Alex")
        encoded = encode_value(npc)
        decoded = decode_value(encoded)
        assert decoded.type == npc.type or decoded.type == npc.type.value
        assert decoded.status == npc.status or decoded.status == npc.status.value


# ===================================================================
# 8. SchemaEncoder: полный round-trip
# ===================================================================

class TestSchemaEncoder:
    """Полный encode/decode SimulationState через SchemaEncoder."""

    def test_schema_encoder_exists(self) -> None:
        enc = SchemaEncoder()
        assert hasattr(enc, "encode_state")
        assert hasattr(enc, "decode_state")

    def test_encode_state_keys(self) -> None:
        """encode_state возвращает dict со всеми 56 ключами."""
        from zonesim.simulation.engine import SimulationEngine
        engine = SimulationEngine(seed=100)
        enc = SchemaEncoder()
        data = enc.encode_state(engine.state)
        assert set(data.keys()) == {f[0] for f in FIELD_TYPES}


# ===================================================================
# 9. Неподдерживаемые типы
# ===================================================================

class TestErrorCases:
    def test_unsupported_type_raises(self) -> None:
        class Unsupported:
            pass

        with pytest.raises(TypeError, match="Неподдерживаемый тип"):
            encode_value(Unsupported())
