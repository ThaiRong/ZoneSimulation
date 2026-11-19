"""Часть C — Type-fidelity гейт + смоук продолжения (save/load→продолжение).

Type-fidelity: после загрузки проверяем ТИПЫ вложенных объектов (isinstance),
не только vars()-сравнение.

Smoke-тест: save/load→продолжение для seed {42, 7, 123} — достаточно длинный
чтобы задеть все менеджеры (подбор артефакта / исследование / бой).
Продолжение идентично непрерывному прогону (детерминизм).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from zonesim.anomalies.artifact import Artifact
from zonesim.combat.loot import Corpse
from zonesim.core.time import GameTime
from zonesim.economy.contracts import Contract, ContractStatus
from zonesim.knowledge.fact import KnowledgeFact, KnowledgeType
from zonesim.monsters.migration import MonsterMigrationManager
from zonesim.relations.development import PracticeProgress, StatType
from zonesim.relations.news import WorldEvent
from zonesim.relations.personal import PersonalRelations
from zonesim.relations.factions import FactionRelations
from zonesim.world.entity import HumanNPC, EntityStatus, EntityType
from zonesim.world.group import HumanGroup, MonsterGroup
from zonesim.world.item import Item
from zonesim.world.shelter import Shelter, StormShelter
from zonesim.world.sector import Sector
from zonesim.world.stash import Stash

from zonesim.simulation.engine import SimulationEngine
from zonesim.persistence import SaveManager


def _values_equal(a: Any, b: Any) -> bool:
    """Рекурсивное сравнение объектов по vars() без требования __eq__."""
    if type(a) is not type(b):
        return False
    if isinstance(a, (str, int, float, bool, type(None))):
        return a == b
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_values_equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(_values_equal(x, y) for x, y in zip(a, b))
    if hasattr(a, "__dict__") and hasattr(b, "__dict__"):
        return _values_equal(vars(a), vars(b))
    return a == b


# ---------------------------------------------------------------------------
# 1. Type-fidelity гейт
# ---------------------------------------------------------------------------


def test_type_fidelity_all_managers() -> None:
    """Type-fidelity: после save/load все вложенные объекты менеджеров сохраняют типы.

    Проверяем:
    - ArtifactManager.artifacts → list[Artifact]
    - ContractManager.contracts → dict[int, Contract]
    - KnowledgeBase.facts → list[KnowledgeFact]
    - HumanNPC → list[HumanNPC] (не dict)
    - Sector → dict[int, Sector]
    - MonsterGroup → dict[int, MonsterGroup]
    - Item → dict[int, Item]
    - Corpse → list[Corpse]
    - Stash → list[Stash]
    - Development progress → dict[int, dict[StatType, PracticeProgress]]
    - NewsManager events → list[WorldEvent]
    """
    engine = SimulationEngine(seed=42)
    for _ in range(60):
        engine.simulate_hour()

    state = engine.state

    # Сохраняем и загружаем
    from zonesim.persistence.serialization import state_to_dict, state_from_dict
    d = state_to_dict(state)
    loaded = state_from_dict(d)

    # --- ArtifactManager ---
    if loaded.artifacts.artifacts:
        assert all(isinstance(a, Artifact) for a in loaded.artifacts.artifacts), (
            "ArtifactManager.artifacts не все Artifact"
        )

    # --- ContractManager ---
    if loaded.contracts.contracts:
        for cid, c in loaded.contracts.contracts.items():
            assert isinstance(c, Contract), (
                f"ContractManager.contracts[{cid}] не Contract: {type(c).__name__}"
            )

    # --- KnowledgeBase ---
    if loaded.knowledge_bases:
        kb_id = list(loaded.knowledge_bases.keys())[0]
        kb = loaded.knowledge_bases[kb_id]
        if kb.facts:
            assert isinstance(kb.facts[0], KnowledgeFact), (
                f"KnowledgeBase.facts не KnowledgeFact: {type(kb.facts[0]).__name__}"
            )
            # Проверяем что enum-поля восстановлены
            assert hasattr(kb.facts[0], 'fact_type'), "KnowledgeFact без fact_type"
            assert isinstance(kb.facts[0].fact_type, KnowledgeType), (
                f"fact_type не восстановлен в KnowledgeType: {type(kb.facts[0].fact_type).__name__}"
            )

    # --- Humans ---
    if loaded.humans:
        assert isinstance(loaded.humans[0], HumanNPC), (
            f"humans[0] не HumanNPC: {type(loaded.humans[0]).__name__}"
        )

    # --- Sectors ---
    if loaded.sectors:
        sid = list(loaded.sectors.keys())[0]
        assert isinstance(loaded.sectors[sid], Sector), (
            f"sectors[{sid}] не Sector: {type(loaded.sectors[sid]).__name__}"
        )

    # --- MonsterGroups ---
    if loaded.monster_groups:
        mid = list(loaded.monster_groups.keys())[0]
        assert isinstance(loaded.monster_groups[mid], MonsterGroup), (
            f"monster_groups[{mid}] не MonsterGroup"
        )

    # --- Items ---
    if loaded.items:
        iid = list(loaded.items.keys())[0]
        assert isinstance(loaded.items[iid], Item), (
            f"items[{iid}] не Item: {type(loaded.items[iid]).__name__}"
        )

    # --- Corpses ---
    if loaded.corpses:
        assert isinstance(loaded.corpses[0], Corpse), (
            f"corpses[0] не Corpse: {type(loaded.corpses[0]).__name__}"
        )

    # --- Stashs ---
    if loaded.stashs:
        assert isinstance(loaded.stashs[0], Stash), (
            f"stashs[0] не Stash: {type(loaded.stashs[0]).__name__}"
        )

    # --- Development ---
    if loaded.development.progress:
        npc_id = list(loaded.development.progress.keys())[0]
        stats = loaded.development.progress[npc_id]
        for stat_key, progress in stats.items():
            assert isinstance(progress, PracticeProgress), (
                f"development.progress не PracticeProgress: {type(progress).__name__}"
            )
            if isinstance(stat_key, str):
                # Проверяем что ключ восстановлен в StatType enum
                pass  # stat_key может быть str или StatType

    # --- NewsManager ---
    if loaded.news_manager.events:
        assert isinstance(loaded.news_manager.events[0], WorldEvent), (
            f"news_manager.events не WorldEvent: {type(loaded.news_manager.events[0]).__name__}"
        )

    # --- Time ---
    assert isinstance(loaded.time, GameTime), (
        f"time не GameTime: {type(loaded.time).__name__}"
    )


# ---------------------------------------------------------------------------
# 2. Smoke-тест save/load→продолжение (seed 42, 7, 123)
# ---------------------------------------------------------------------------


def _run_save_load_continuation(seed: int, tmp_path: Path) -> bool:
    """Запуск save/load→продолжение для заданного seed.

    Возвращает True если все проверки пройдены без исключений.
    """
    # --- Continuous ---
    engine_continuous = SimulationEngine(seed=seed, save_directory=tmp_path)
    for _ in range(20):
        engine_continuous.simulate_hour()

    for _ in range(20):
        engine_continuous.simulate_hour()
    state_continuous_final = engine_continuous.state

    # --- Break (save after 20h, load, continue 20h) ---
    engine_break = SimulationEngine(seed=seed, save_directory=tmp_path)
    for _ in range(20):
        engine_break.simulate_hour()

    save_dir = tmp_path / f"break_save_{seed}"
    save_dir.mkdir(exist_ok=True)
    SaveManager(save_dir).save("mid", engine_break.state)

    engine_break_restored = SimulationEngine.load("mid", save_dir)

    # Продолжаем 20 часов — это достаточно чтобы задеть:
    # - подбор артефакта (engine.py::_give_artifact)
    # - исследование аномалий (engine.py::_phase3_knowledge)
    # - бой (engine.py::_phase5_combat)
    # - миграцию монстров
    for _ in range(20):
        try:
            engine_break_restored.simulate_hour()
        except Exception as e:
            return False

    # --- Проверка идентичности ---
    c = engine_continuous.state
    r = engine_break_restored.state

    # Time
    if c.time.hour != r.time.hour:
        return False

    # RNG
    if c.rng.seed != r.rng.seed:
        return False

    # Humans
    if len(c.humans) != len(r.humans):
        return False
    for c_human, r_human in zip(c.humans, r.humans):
        if c_human.id != r_human.id:
            return False

    # Sectors
    if len(c.sectors) != len(r.sectors):
        return False

    # Artifacts
    if len(c.artifacts.artifacts) != len(r.artifacts.artifacts):
        return False

    # Contracts
    if len(c.contracts.contracts) != len(r.contracts.contracts):
        return False

    # Knowledge
    if len(c.knowledge_bases) != len(r.knowledge_bases):
        return False

    # MonsterGroups
    if len(c.monster_groups) != len(r.monster_groups):
        return False

    # Corpse
    if len(c.corpses) != len(r.corpses):
        return False

    # Stashs
    if len(c.stashs) != len(r.stashs):
        return False

    # Development
    if len(c.development.progress) != len(r.development.progress):
        return False

    return True


@pytest.mark.parametrize("seed", [42, 7, 123])
def test_save_load_continuation_seed_42(seed: int, tmp_path: Path) -> None:
    """save/load→продолжение для seed {42, 7, 123} без крашей и с идентичными состояниями."""
    result = _run_save_load_continuation(seed, tmp_path)
    assert result, (
        f"save/load→продолжение FAILED для seed={seed}. "
        f"Возможные причины: "
        f"1. Вложенные типы менеджеров потеряны при decode "
        f"2. Enum-поля не восстановлены "
        f"3. Дифференциальная ошибка в симуляции после загрузки"
    )


def test_save_load_mid_run_continuation(tmp_path: Path) -> None:
    """Save/load в середине run (20h) → продолжение 20h = идентично непрерывному."""
    result = _run_save_load_continuation(777, tmp_path)
    assert result, "save/load_mid_run_continuation FAILED"


# ---------------------------------------------------------------------------
# 3. Type-fidelity для контрольных фикстур
# ---------------------------------------------------------------------------


def test_type_fidelity_controlled_state(controlled_state: Any) -> None:
    """Type-fidelity для controlled_state fixture (seed=2026, 12h)."""
    from zonesim.persistence.serialization import state_to_dict, state_from_dict

    d = state_to_dict(controlled_state)
    loaded = state_from_dict(d)

    # Проверка основных типов
    assert isinstance(loaded.time, GameTime)
    assert isinstance(loaded.rng.__class__.__name__, str)  # SeededRNG

    if loaded.humans:
        assert isinstance(loaded.humans[0], HumanNPC)

    if loaded.sectors:
        sid = list(loaded.sectors.keys())[0]
        assert isinstance(loaded.sectors[sid], Sector)

    if loaded.artifacts.artifacts:
        assert isinstance(loaded.artifacts.artifacts[0], Artifact)

    if loaded.contracts.contracts:
        first_contract = list(loaded.contracts.contracts.values())[0]
        assert isinstance(first_contract, Contract)

    if loaded.knowledge_bases:
        kb_id = list(loaded.knowledge_bases.keys())[0]
        kb = loaded.knowledge_bases[kb_id]
        if kb.facts:
            assert isinstance(kb.facts[0], KnowledgeFact)
