"""Инвариант #23: укрытие либо свободно, либо занято одной группой монстров.

§22 ТЗ:
23 Укрытие свободно или занято ОДНОЙ группой монстров. Действующее правило: монстры в
   убежище считаются в засаде и ТОЛЬКО засада; иных бонусов укрытия нет.

check_fn → _check_shelter_occupancy (#23 частично).
coverage: partial (только occupied_by reference check, НЕ group count).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _check_shelter_occupancy(state: "SimulationState") -> list[str]:
    """Инвариант #23: shelter occupied_by указывает на существующую группу.

    НБ: проверяет только что occupied_by ссылается на существующую группу.
    НЕ проверяет:
    - "либо свободно ИЛИ одна группа" (group count = 1 max)
    - статус засады (monster status == AnomalyStatus.SABOTAGE)
    - sector_id match (race condition в движке)
    """
    errors: list[str] = []
    hour = state.time.hour

    for shelter_id, shelter in state.shelters.items():
        if shelter.is_occupied and shelter.occupied_by is not None:
            group_id = shelter.occupied_by
            group = state.monster_groups.get(group_id)
            if group is None:
                errors.append(
                    f"Инвариант #23 (ч. {hour}): укрытие {shelter_id} "
                    f"occupied_by={group_id}, но группа монстров не найдена"
                )

    return errors
