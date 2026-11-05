"""Тесты сохранения, загрузки и продолжения симуляции (§20.3-20.4 ТЗ)."""

import sqlite3

import pytest

from zonesim.economy.contracts import ContractStatus, ContractType
from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType
from zonesim.persistence import SaveFormatError, SaveManager, SaveNotFoundError
from zonesim.persistence.serialization import state_to_dict
from zonesim.relations.development import PracticeProgress, StatType
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.stash import Stash


def test_complex_state_roundtrip(tmp_path):
    engine = SimulationEngine(seed=123)
    for _ in range(24):
        engine.simulate_hour()
    state = engine.state
    npc = state.humans[0]

    state.personal_relations.set(state.humans[0].id, state.humans[1].id, 73)
    state.faction_relations.set("Бродяги", "Борзые", -61)
    state.development.progress[npc.id] = {
        StatType.ATTACK: PracticeProgress(StatType.ATTACK, 4.5, 20)
    }
    contract = state.contracts.create_contract(
        1, ContractType.ARTIFACT, "artifact", 1, 200.0, current_hour=24
    )
    state.contracts.accept_contract(contract.id, npc.id, npc.sector_id, 24)
    state.import_export.process_daily_export(1, 1, {"artifacts": 1})
    state.import_export.process_daily_import(1, 1, {"medkits": 2}, 100.0)
    state.stashs.append(Stash(
        id=state.next_stash_id,
        sector_id=npc.sector_id,
        owner_id=npc.id,
        items=[{"type": "medkit", "value": 20}],
        money=125,
        known_by=[npc.id],
        created_hour=24,
    ))
    knowledge = state.knowledge_bases.setdefault(npc.id, KnowledgeBase())
    knowledge.add_manual(
        npc.id, KnowledgeType.STASH, state.stashs[-1].id,
        {"sector_id": npc.sector_id, "money": 125}, 24,
    )
    npc.custom_timer = 17
    npc.custom_history = [(npc.sector_id, 24)]

    SaveManager(tmp_path).save("manual", state)
    loaded = SimulationEngine.load("manual", tmp_path).state

    assert state_to_dict(loaded) == state_to_dict(state)
    assert loaded.rng.seed == state.rng.seed
    assert loaded.rng.get_state() == state.rng.get_state()
    assert loaded.personal_relations.get(state.humans[0].id, state.humans[1].id) == 73
    assert loaded.faction_relations.get("Бродяги", "Борзые") == -61
    progress = loaded.development.progress[npc.id][StatType.ATTACK]
    assert isinstance(progress, PracticeProgress)
    assert progress.stat_type is StatType.ATTACK
    assert loaded.contracts.contracts[contract.id].status is ContractStatus.ACCEPTED
    assert loaded.knowledge_bases[npc.id].facts[-1].fact_type is KnowledgeType.STASH
    assert loaded.humans[0].custom_history == [(npc.sector_id, 24)]


def test_save_load_continuation_is_identical(tmp_path):
    original = SimulationEngine(seed=42, save_directory=tmp_path)
    for _ in range(48):
        original.simulate_hour()
    original.save("manual")
    restored = SimulationEngine.load("manual", tmp_path)

    assert state_to_dict(restored.state) == state_to_dict(original.state)
    for _ in range(24):
        original.simulate_hour()
        restored.simulate_hour()
        assert state_to_dict(restored.state) == state_to_dict(original.state)


def test_autosave_rotation_keeps_three_latest_slots(tmp_path):
    engine = SimulationEngine(seed=7, save_directory=tmp_path)
    for _ in range(42):
        engine.simulate_hour()

    assert sorted(path.name for path in tmp_path.glob("*.sqlite")) == [
        "autosave_0.sqlite", "autosave_1.sqlite", "autosave_2.sqlite"
    ]
    hours = {
        slot: SimulationEngine.load(slot, tmp_path).state.time.hour
        for slot in ("autosave_0", "autosave_1", "autosave_2")
    }
    assert hours == {"autosave_0": 42, "autosave_1": 48, "autosave_2": 36}


def test_autosave_can_be_disabled(tmp_path):
    engine = SimulationEngine(
        seed=7,
        config={"persistence": {"autosave_enabled": False}},
        save_directory=tmp_path,
    )
    for _ in range(12):
        engine.simulate_hour()
    assert list(tmp_path.glob("*.sqlite")) == []


def test_failed_atomic_replace_preserves_previous_save(tmp_path, monkeypatch):
    engine = SimulationEngine(seed=5)
    manager = SaveManager(tmp_path)
    manager.save("manual", engine.state)
    expected = state_to_dict(manager.load("manual"))
    engine.simulate_hour()

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr("zonesim.persistence.storage.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        manager.save("manual", engine.state)

    assert state_to_dict(manager.load("manual")) == expected
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("version", ["999", "broken"])
def test_incompatible_or_invalid_format_version(tmp_path, version):
    engine = SimulationEngine(seed=5)
    manager = SaveManager(tmp_path)
    manager.save("manual", engine.state)
    manager.save("other", engine.state)
    with sqlite3.connect(tmp_path / "manual.sqlite") as connection:
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'format_version'", (version,)
        )
        connection.commit()

    with pytest.raises(SaveFormatError):
        manager.load("manual")
    assert state_to_dict(manager.load("other")) == state_to_dict(engine.state)


def test_corrupt_database_and_missing_slot(tmp_path):
    engine = SimulationEngine(seed=5)
    manager = SaveManager(tmp_path)
    manager.save("valid", engine.state)
    (tmp_path / "broken.sqlite").write_bytes(b"not a sqlite database")

    with pytest.raises(SaveFormatError, match="Повреждённый файл"):
        manager.load("broken")
    with pytest.raises(SaveNotFoundError):
        manager.load("missing")
    assert state_to_dict(manager.load("valid")) == state_to_dict(engine.state)


@pytest.mark.parametrize("slot", ["", ".", "..", "../outside", "nested/slot"])
def test_invalid_slot_name(tmp_path, slot):
    with pytest.raises(ValueError, match="Недопустимое имя слота"):
        SaveManager(tmp_path).load(slot)
