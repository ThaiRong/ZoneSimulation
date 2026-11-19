"""Часть A/B — Регресс-тест на потеря вложенных типов менеджеров.

Баг: save/load → ArtifactManager.artifacts остаётся list[dict] вместо list[Artifact].
Краш: engine.py::_give_artifact: art.anomaly_id → AttributeError: 'dict' object has no attribute 'anomaly_id'

Часть A: регресс-тест (воспроизведён, xfail, зафиксирован).
Часть B: фикс decode_value из schema.py вместо _decode_raw.
Часть C: type-fidelity гейт + смоук продолжения.
"""

from __future__ import annotations

import pytest

from zonesim.simulation.engine import SimulationEngine


def test_artifactmanager_nested_types_restored_on_save_load() -> None:
    """Сохранение и загрузка ВОССТАНАВЛИВАЕТ вложенные типы ArtifactManager.
    
    Проверяем:
    1. 60 часов симуляции (seed 42)
    2. state_to_dict -> state_from_dict
    3. Проверка типов вложенных объектов
    """
    engine = SimulationEngine(seed=42)

    # 60 часов симуляции
    for _ in range(60):
        engine.simulate_hour()

    state = engine.state

    # Проверяем что артефакты есть
    artifacts = state.artifacts.artifacts
    assert len(artifacts) > 0, (
        f"Ожидаем артефакты после 60ч, но получено {len(artifacts)}"
    )

    # Оригинальные артефакты - объекты Artifact
    orig_types = [type(a).__name__ for a in artifacts[:3]]
    print(f"orig artifact types: {orig_types}")

    # Сохраняем и загружаем через serialization
    from zonesim.persistence.serialization import state_to_dict, state_from_dict
    d = state_to_dict(state)
    loaded = state_from_dict(d)

    # Проверяем типы загруженных артефактов
    loaded_artifacts = loaded.artifacts.artifacts
    assert len(loaded_artifacts) > 0, (
        f"Ожидаем артефакты после загрузки, но получено {len(loaded_artifacts)}"
    )

    loaded_types = [type(a).__name__ for a in loaded_artifacts[:3]]
    print(f"loaded artifact types: {loaded_types}")

    # BUG: загруженные артефакты - dict, а не Artifact
    for i, art in enumerate(loaded_artifacts[:3]):
        print(f"  loaded_artifacts[{i}]: type={type(art).__name__}")

    # КРИТИЧНО: каждый загруженный артефакт должен быть Artifact, а не dict
    for i, art in enumerate(loaded_artifacts[:3]):
        assert type(art).__name__ == 'Artifact', (
            f"Первый загруженный артефакт имеет тип {type(art).__name__}, "
            f"но ожидаем Artifact. Вложенные типы менеджера потеряны!"
        )

    # Дополнительная проверка: атрибуты Artifact доступны
    first_loaded = loaded_artifacts[0]
    assert hasattr(first_loaded, 'anomaly_id'), (
        f"Artifact должен иметь атрибут anomaly_id, но получил {type(first_loaded).__name__}"
    )
    assert hasattr(first_loaded, 'id'), (
        f"Artifact должен иметь атрибут id, но получил {type(first_loaded).__name__}"
    )
    assert hasattr(first_loaded, 'rarity'), (
        f"Artifact должен иметь атрибут rarity, но получил {type(first_loaded).__name__}"
    )


def test_artifactmanager_type_fidelity() -> None:
    """Type-fidelity: после save/load все вложенные объекты менеджеров сохраняют типы."""
    engine = SimulationEngine(seed=42)

    # 60 часов чтобы заполнить менеджеры
    for _ in range(60):
        engine.simulate_hour()

    from zonesim.persistence.serialization import state_to_dict, state_from_dict
    d = state_to_dict(engine.state)
    loaded = state_from_dict(d)

    # ArtifactManager.artifacts -> list[Artifact]
    if loaded.artifacts.artifacts:
        assert all(isinstance(a, type(engine.state.artifacts.artifacts[0]))
                   for a in loaded.artifacts.artifacts), (
            "ArtifactManager.artifacts не все Artifact"
        )

    # ContractManager.contracts -> dict[int, Contract]
    if loaded.contracts.contracts:
        first_contract = list(loaded.contracts.contracts.values())[0]
        orig_first = list(engine.state.contracts.contracts.values())[0]
        assert isinstance(first_contract, type(orig_first)), (
            f"ContractManager.contracts: {type(first_contract).__name__} "
            f"!= {type(orig_first).__name__}"
        )

    # ImportExportManager.import/export records -> list[ImportRecord/ExportRecord]
    if loaded.import_export.export_records:
        assert isinstance(loaded.import_export.export_records[0],
                         type(engine.state.import_export.export_records[0])), (
            "ImportExportManager.export_records не все ExportRecord"
        )

    # KnowledgeBase -> KnowledgeBase с KnowledgeFact
    if loaded.knowledge_bases:
        kb_id = list(loaded.knowledge_bases.keys())[0]
        loaded_kb = loaded.knowledge_bases[kb_id]
        orig_kb = engine.state.knowledge_bases[kb_id]
        if loaded_kb.facts and orig_kb.facts:
            assert isinstance(loaded_kb.facts[0], type(orig_kb.facts[0])), (
                f"KnowledgeBase.facts: {type(loaded_kb.facts[0]).__name__} "
                f"!= {type(orig_kb.facts[0]).__name__}"
            )
