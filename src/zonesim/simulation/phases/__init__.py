"""Фазы симуляции — извлечённые методы из engine.py.

Этап 3, Промпт 3.4: каждая фаза — standalone функция,
принимающая SimulationContext и вызывающая вспомогательные
методы через context.engine_ref.
"""

from __future__ import annotations

from zonesim.simulation.phases.phase00_check import run_phase0_check  # noqa: F401
from zonesim.simulation.phases.phase01_scheduled import run_phase1_scheduled  # noqa: F401
from zonesim.simulation.phases.phase02_environment import run_phase2_environment  # noqa: F401

__all__ = [
    "run_phase0_check",
    "run_phase1_scheduled",
    "run_phase2_environment",
]
