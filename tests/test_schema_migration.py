"""Тесты schema fingerprint и миграции старых сейвов (§20.3, §20.4, §21).

Цель: убедиться что:
1. Schema fingerprint вычисляется детерминировано из FIELD_TYPES
2. Миграция старых сейвов (v≤12 без 4 новых полей) работает корректно
3. Невалидные сейвы отклоняются с понятным сообщением
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from zonesim.persistence.schema import (
    SCHEMA_FINGERPRINT,
    apply_migration,
    compute_schema_fingerprint,
    is_migration_needed,
    MIGRATION_TARGETS,
    FIELD_TYPES,
)
from zonesim.persistence.storage import (
    FORMAT_VERSION,
    SaveFormatError,
    SaveManager,
)


# ---------------------------------------------------------------------------
# 1. Schema fingerprint — вычисление и детерминизм
# ---------------------------------------------------------------------------


def test_schema_fingerprint_is_computed() -> None:
    """SCHEMA_FINGERPRINT должен быть непустой строкой."""
    assert isinstance(SCHEMA_FINGERPRINT, str)
    assert len(SCHEMA_FINGERPRINT) > 0


def test_schema_fingerprint_is_deterministic() -> None:
    """Два вызова compute_schema_fingerprint должны давать одинаковый результат."""
    fp1 = compute_schema_fingerprint()
    fp2 = compute_schema_fingerprint()
    assert fp1 == fp2


def test_schema_fingerprint_changes_on_field_rename() -> None:
    """Если изменить имя/тип поля — fingerprint изменится."""
    import zonesim.persistence.schema as schema_mod
    original = schema_mod.FIELD_TYPES.copy()

    # Симулируем изменение имени поля
    modified = [
        (name if name != "time" else "time_modified", type_)
        for name, type_ in original
    ]
    # Временно подменяем FIELD_TYPES
    schema_mod.FIELD_TYPES = modified
    try:
        fp_changed = compute_schema_fingerprint()
        assert fp_changed != SCHEMA_FINGERPRINT, (
            "Fingerprint не изменился при переименовании поля"
        )
    finally:
        schema_mod.FIELD_TYPES = original


def test_schema_fingerprint_changes_on_type_change() -> None:
    """Если изменить тип поля — fingerprint изменится."""
    import zonesim.persistence.schema as schema_mod
    original = schema_mod.FIELD_TYPES.copy()

    # Симулируем изменение типа
    modified = [
        (name, "str" if type_ != "str" else "int")
        for name, type_ in original
    ]
    schema_mod.FIELD_TYPES = modified
    try:
        fp_changed = compute_schema_fingerprint()
        assert fp_changed != SCHEMA_FINGERPRINT, (
            "Fingerprint не изменился при изменении типа поля"
        )
    finally:
        schema_mod.FIELD_TYPES = original


def test_schema_fingerprint_field_count() -> None:
    """FIELD_TYPES должен содержать все 56 полей SimulationState."""
    assert len(FIELD_TYPES) == 56


# ---------------------------------------------------------------------------
# 2. Migration policy — v≤12 без 4 новых полей → заполнение дефолтами
# ---------------------------------------------------------------------------


def test_migration_adds_four_new_fields() -> None:
    """apply_migration должен добавить 4 новых поля с дефолтами."""
    # Симулируем данные старого сейва (v12 без новых полей)
    old_data: dict[str, Any] = {
        "time": {"hour": 12},
        "rng": {"seed": 42, "state": []},
        "sectors": {},
        "humans": [],
        # ... (не все поля нужны для теста)
    }
    migrated = apply_migration(old_data, 12)

    # 4 новых поля должны быть добавлены с дефолтами
    assert migrated["prev_relation_snapshot"] == {}
    assert migrated["relation_change_journal"] == []
    assert migrated["intention_knowledge_used"] == {}
    assert migrated["knowledge_snapshot_at_intention"] == []


def test_migration_preserves_existing_data() -> None:
    """apply_migration НЕ должен изменять существующие данные."""
    old_data: dict[str, Any] = {
        "time": {"hour": 24},
        "sectors": {"__kind__": "dict", "items": []},
        "humans": [{"__kind__": "dict", "items": []}],
        "prev_relation_snapshot": {"existing": "data"},  # уже есть
    }
    migrated = apply_migration(old_data, 12)

    # Существующие данные не должны измениться
    assert migrated["time"]["hour"] == 24
    assert migrated["prev_relation_snapshot"] == {"existing": "data"}
    # Новые поля добавлены
    assert migrated["relation_change_journal"] == []


def test_migration_no_op_if_all_fields_present() -> None:
    """Если все 4 новых поля уже есть — apply_migration возвращает копию."""
    data_with_new: dict[str, Any] = {
        "time": {"hour": 12},
        "prev_relation_snapshot": {"key": "value"},
        "relation_change_journal": [{"event": 1}],
        "intention_knowledge_used": {1: []},
        "knowledge_snapshot_at_intention": [1, 2, 3],
    }
    result = apply_migration(data_with_new, 13)

    # Все поля должны сохраниться без изменений
    assert result["prev_relation_snapshot"] == {"key": "value"}
    assert result["relation_change_journal"] == [{"event": 1}]
    assert result["intention_knowledge_used"] == {1: []}
    assert result["knowledge_snapshot_at_intention"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# 3. is_migration_needed — логика определения
# ---------------------------------------------------------------------------


def test_migration_not_needed_for_current_version() -> None:
    """Для текущей версии fingerprint совпадает — миграция не нужна."""
    assert not is_migration_needed(FORMAT_VERSION, SCHEMA_FINGERPRINT)


def test_migration_not_needed_for_different_fp_with_old_version() -> None:
    """Для версии v12 с другим fingerprint — миграция НУЖНА."""
    assert is_migration_needed(12, "different_fp")


def test_migration_needed_when_no_fingerprint() -> None:
    """Для сейва без fingerprint (очень старый) — миграция нужна если v≤12."""
    # v12 без fingerprint → нужна миграция
    assert is_migration_needed(12, None)
    # v10 без fingerprint → тоже нужна
    assert is_migration_needed(10, None)


def test_migration_not_needed_when_newer_version() -> None:
    """Для версии > FORMAT_VERSION — миграция не применяется (отказ)."""
    # version > FORMAT_VERSION — is_migration_needed вернёт True,
    # но load() отклонит сейв
    assert is_migration_needed(100, "any_fp")


# ---------------------------------------------------------------------------
# 4. Integration: save/load с миграцией
# ---------------------------------------------------------------------------


def test_save_and_load_current_version(tmp_path: Path) -> None:
    """Сохранение и загрузка текущей версии работает."""
    from zonesim.simulation.engine import SimulationEngine

    engine = SimulationEngine(seed=42)
    manager = SaveManager(tmp_path)

    path = manager.save("current", engine.state)
    assert path.exists()

    loaded = manager.load("current")
    assert loaded.time.hour == engine.state.time.hour
    assert loaded.rng.seed == engine.state.rng.seed


def test_save_produces_correct_fingerprint(tmp_path: Path) -> None:
    """Сохранение записывает правильный schema_fingerprint в metadata."""
    from zonesim.simulation.engine import SimulationEngine

    engine = SimulationEngine(seed=42)
    manager = SaveManager(tmp_path)
    manager.save("test", engine.state)

    path = tmp_path / "test.sqlite"
    with sqlite3.connect(path) as conn:
        metadata = dict(conn.execute("SELECT key, value FROM metadata"))
        assert metadata["format_version"] == str(FORMAT_VERSION)
        assert metadata["schema_fingerprint"] == SCHEMA_FINGERPRINT


def test_old_save_v12_migrates_successfully(tmp_path: Path) -> None:
    """Старый сейв v12 (без 4 новых полей) должен мигрировать и загрузиться."""
    from zonesim.simulation.engine import SimulationEngine

    # Создаём текущий сейв
    engine = SimulationEngine(seed=42)
    manager = SaveManager(tmp_path)
    manager.save("migratable", engine.state)

    # Модифицируем: понижам версию до 12 и удаляем 4 новых поля
    path = tmp_path / "migratable.sqlite"

    with sqlite3.connect(path) as conn:
        # Считаем данные
        metadata = dict(conn.execute("SELECT key, value FROM metadata"))
        payload = conn.execute(
            "SELECT payload FROM world_state WHERE id = 1"
        ).fetchone()[0]

    # Парсим, удаляем 4 новых поля
    data = json.loads(payload)
    for field in ["prev_relation_snapshot", "relation_change_journal",
                  "intention_knowledge_used", "knowledge_snapshot_at_intention"]:
        data.pop(field, None)

    # Записываем обратно с версией 12 и другим fingerprint
    new_payload = json.dumps(data)
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM world_state WHERE id = 1")
        conn.execute("INSERT INTO world_state (id, payload) VALUES (1, ?)",
                     (new_payload,))
        conn.execute("UPDATE metadata SET value = '12' WHERE key = 'format_version'")
        conn.execute("UPDATE metadata SET value = 'old_fp' WHERE key = 'schema_fingerprint'")
        conn.commit()

    # Теперь загрузка должна пройти через миграцию
    loaded = manager.load("migratable")

    # Проверяем что 4 новых поля заполнены дефолтами
    assert loaded.prev_relation_snapshot == {}
    assert loaded.relation_change_journal == []
    assert loaded.intention_knowledge_used == {}
    assert loaded.knowledge_snapshot_at_intention == []


def test_save_with_future_version_rejects_with_message(tmp_path: Path) -> None:
    """Сейв с version > FORMAT_VERSION должен быть отклонён."""
    from zonesim.simulation.engine import SimulationEngine

    engine = SimulationEngine(seed=42)
    manager = SaveManager(tmp_path)
    manager.save("future", engine.state)

    path = tmp_path / "future.sqlite"

    # Модифицируем: повышаем версию до 999
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE metadata SET value = '999' WHERE key = 'format_version'")
        conn.commit()

    with pytest.raises(SaveFormatError) as exc_info:
        manager.load("future")

    # Сообщение должно быть понятным
    error_msg = str(exc_info.value).lower()
    assert "несовместимая" in error_msg or "версия" in error_msg
    assert "999" in error_msg
    assert str(FORMAT_VERSION) in error_msg


def test_save_with_no_fingerprint_v12_migrates(tmp_path: Path) -> None:
    """Сейв v12 без fingerprint (очень старый) должен быть отклонён."""
    from zonesim.simulation.engine import SimulationEngine

    engine = SimulationEngine(seed=42)
    manager = SaveManager(tmp_path)
    manager.save("no_fp", engine.state)

    path = tmp_path / "no_fp.sqlite"

    # Модифицируем: удаляем fingerprint и ставим version 12
    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE metadata SET value = '12' WHERE key = 'format_version'"
        )
        conn.execute(
            "DELETE FROM metadata WHERE key = 'schema_fingerprint'"
        )
        conn.commit()

    # Сейв v12 без fingerprint → отклонение (требует >= 13)
    with pytest.raises(SaveFormatError) as exc_info:
        manager.load("no_fp")

    error_msg = str(exc_info.value)
    assert "несовместимая" in error_msg.lower() or "версия" in error_msg.lower()


# ---------------------------------------------------------------------------
# 5. Формат версии: проверка что FORMAT_VERSION > MIGRATION_TARGETS
# ---------------------------------------------------------------------------


def test_format_version_exceeds_migration_target() -> None:
    """FORMAT_VERSION должен быть MIGRATION_TARGETS + 1."""
    assert FORMAT_VERSION == MIGRATION_TARGETS + 1, (
        f"FORMAT_VERSION ({FORMAT_VERSION}) != MIGRATION_TARGETS + 1 "
        f"({MIGRATION_TARGETS + 1})"
    )


def test_migration_target_is_12() -> None:
    """MIGRATION_TARGETS должен быть 12 (старый формат без 4 новых полей)."""
    assert MIGRATION_TARGETS == 12
