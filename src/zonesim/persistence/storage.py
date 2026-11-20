"""SQLite-слоты сохранения с атомарной заменой файлов."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING

from zonesim.persistence.schema import (
    SCHEMA_FINGERPRINT,
    is_migration_needed,
    apply_migration,
    MIGRATION_TARGETS,
)
from zonesim.persistence.serialization import state_from_dict, state_to_dict

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState

# Текущая версия формата — инкрементируется при изменении структуры SimulationState
# Fingerprint вычисляется автоматически из FIELD_TYPES в schema.py
FORMAT_VERSION = 13


class SaveError(Exception):
    pass


class SaveNotFoundError(SaveError, FileNotFoundError):
    pass


class SaveFormatError(SaveError, ValueError):
    pass


class SaveManager:
    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)

    def _path(self, slot: str) -> Path:
        if not slot or slot in {".", ".."} or Path(slot).name != slot:
            raise ValueError("Недопустимое имя слота сохранения")
        return self.directory / f"{slot}.sqlite"

    def save(self, slot: str, state: SimulationState) -> Path:
        path = self._path(slot)
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            state_to_dict(state),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.directory,
            prefix=f".{path.stem}_",
            suffix=".tmp",
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            with closing(sqlite3.connect(temporary_path)) as connection:
                connection.execute(
                    "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE world_state (id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL)"
                )
                connection.executemany(
                    "INSERT INTO metadata (key, value) VALUES (?, ?)",
                    [
                        ("format_version", str(FORMAT_VERSION)),
                        ("schema_fingerprint", SCHEMA_FINGERPRINT),
                        ("seed", str(state.rng.seed)),
                        ("hour", str(state.time.hour)),
                    ],
                )
                connection.execute(
                    "INSERT INTO world_state (id, payload) VALUES (1, ?)",
                    (payload,),
                )
                connection.commit()
            os.replace(temporary_path, path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return path

    def load(self, slot: str) -> SimulationState:
        path = self._path(slot)
        if not path.is_file():
            raise SaveNotFoundError(f"Сохранение не найдено: {slot}")
        try:
            with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
                metadata = dict(connection.execute("SELECT key, value FROM metadata"))
                payload = connection.execute(
                    "SELECT payload FROM world_state WHERE id = 1"
                ).fetchone()
        except sqlite3.DatabaseError as error:
            raise SaveFormatError(f"Повреждённый файл сохранения: {slot}") from error

        try:
            version = int(metadata["format_version"])
        except (KeyError, ValueError) as error:
            raise SaveFormatError(
                f"Некорректная версия сохранения: {slot}. "
                f"Файл повреждён или имеет неизвестный формат."
            ) from error

        # Получаем fingerprint (может отсутствовать в очень старых сейвах)
        saved_fingerprint = metadata.get("schema_fingerprint")

        # Проверка: не старше ли сейв чем поддерживаемые версии для миграции
        if version > FORMAT_VERSION:
            raise SaveFormatError(
                f"Несовместимая версия сохранения: {version}; "
                f"поддерживается {FORMAT_VERSION}. "
                f"Обновите ZoneSimulation до последней версии."
            )

        # Проверка fingerprint и миграция
        if is_migration_needed(version, saved_fingerprint):
            if saved_fingerprint is None:
                raise SaveFormatError(
                    f"Несовместимая версия сохранения: {version}. "
                    f"Требуется сохранение версии {MIGRATION_TARGETS + 1} или новее. "
                    f"Пожалуйста, сохраните игру в текущей версии ZoneSimulation."
                )
            # Fingerprint не совпадает, но версия <= MIGRATION_TARGETS — пробуем миграцию
            try:
                data = json.loads(payload[0])
                data = apply_migration(data, version)
            except (ValueError, TypeError) as error:
                raise SaveFormatError(
                    f"Повреждено состояние мира в сохранении: {slot}"
                ) from error
        else:
            # Совместимая версия — загружаем напрямую
            if payload is None:
                raise SaveFormatError(
                    f"В сохранении отсутствует состояние мира: {slot}"
                )
            try:
                data = json.loads(payload[0])
            except (ValueError, TypeError) as error:
                raise SaveFormatError(
                    f"Повреждено состояние мира в сохранении: {slot}"
                ) from error

        return state_from_dict(data)
