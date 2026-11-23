"""Фазы симуляции — извлечённые методы из engine.py.

Этап 3, Промпт 3.5: каждая фаза — standalone функция,
принимающая SimulationContext и вызывающая вспомогательные
методы через context.engine_ref.
"""

from __future__ import annotations

from zonesim.simulation.phases.phase00_check import run_phase0_check
from zonesim.simulation.phases.phase01_scheduled import run_phase1_scheduled
from zonesim.simulation.phases.phase02_environment import run_phase2_environment
from zonesim.simulation.phases.phase03_knowledge import run_phase3_knowledge
from zonesim.simulation.phases.phase04_intentions import run_phase4_intentions
from zonesim.simulation.phases.phase05_movement import run_phase5_movement
from zonesim.simulation.phases.phase06_detections import run_phase6_detections

__all__ = [
    "run_phase0_check",
    "run_phase1_scheduled",
    "run_phase2_environment",
    "run_phase3_knowledge",
    "run_phase4_intentions",
    "run_phase5_movement",
    "run_phase6_detections",
]
