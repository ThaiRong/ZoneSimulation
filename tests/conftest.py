"""Глобальные фикстуры для тестов сериализации."""

import dataclasses
import pytest

from zonesim.persistence.serialization import state_from_dict, state_to_dict
from zonesim.simulation.engine import SimulationEngine
from zonesim.simulation.state import SimulationState


@pytest.fixture()
def controlled_state() -> SimulationState:
    """Создает контролируемое состояние симуляции для тестов сериализации.

    Запускает 12 часов симуляции с детерминированным сидом, чтобы состояние
    содержало нетривиальные данные (NPC, сектора, группы и т.д.).
    """
    engine = SimulationEngine(seed=2026)
    for _ in range(12):
        engine.simulate_hour()
    return engine.state


@pytest.fixture()
def full_field_names() -> set[str]:
    """Множество имён всех полей SimulationState (56 шт.)."""
    return {f.name for f in dataclasses.fields(SimulationState)}
