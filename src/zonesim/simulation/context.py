"""Контекст почасового шага симуляции.

Перенесён для подготовки инфраструктуры извлечения фаз (Этап 3, Промпт 3.2).
БЕЗ изменения логики — тонкая обёртка над SimulationState.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zonesim.simulation.state import SimulationState


@dataclass
class SimulationContext:
    """Контейнер для контекста текущего почасового шага.

    Держит ссылку на SimulationState, информацию о текущем времени
    и временные результаты фаз за один час.
    """

    state: SimulationState
    """Ссылка на текущее состояние симуляции."""

    engine_ref: Any = None
    """Ссылка на SimulationEngine для вызова вспомогательных методов из фаз."""

    hour: int = 0
    """Номер текущего часа (self.state.time.hour)."""

    day: int = 0
    """Номер текущего дня."""

    phase: int = 0
    """Фаза текущего шага (0-10)."""

    is_night: bool = False
    """Ночная ли это фаза."""

    # --- Временные результаты фаз за текущий час ---
    phase_results: dict[str, Any] = field(default_factory=dict)
    """Результаты каждой фазы: {'phase0_check': ..., 'phase1_scheduled': ...}."""

    events: list[dict] = field(default_factory=list)
    """Список событий/решений за текущий час (накапливается фазами)."""

    @property
    def time_hour(self) -> int:
        """Алиас: номер часа из state."""
        return self.state.time.hour

    @property
    def time_day(self) -> int:
        """Алиас: номер дня из state."""
        return self.state.time.day

    @property
    def rng(self) -> Any:
        """Алиас: RNG из state."""
        return self.state.rng

    @property
    def config(self) -> dict[str, Any]:
        """Алиас: конфигурация из state."""
        return self.state.config
