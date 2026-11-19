"""Инвариант #18: корректные ссылки в событиях.

§22 ТЗ:
18 Каждое событие: час, минута, тип, корректные ссылки на участников/архивные записи.

check_fn → _check_event_links (#18 частично).
coverage: partial (только hour check, НЕ проверяет type и entity refs).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _check_event_links(state: "SimulationState") -> list[str]:
    """Инвариант #18: корректные ссылки в событиях.

    НБ: проверяет только evt_hour >= 0. НЕ проверяет:
    - event_type корректен
    - ссылки на участников существуют
    - архивные записи валидны
    """
    errors: list[str] = []
    hour = state.time.hour

    events = state.news_manager.events if hasattr(state.news_manager, 'events') else []
    for i, evt in enumerate(events):
        evt_hour = getattr(evt, 'hour', -1)
        evt_type = getattr(evt, 'event_type', None) or getattr(evt, 'type', None)

        if evt_hour < 0:
            errors.append(
                f"Инвариант #18 (ч. {hour}): событие #{i} имеет неверный час={evt_hour}"
            )

    return errors
