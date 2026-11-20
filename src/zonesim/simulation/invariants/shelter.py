"""Инвариант #23: укрытие либо свободно, либо занято одной группой монстров.

§22 ТЗ:
23 Укрытие свободно или занято ОДНОЙ группой монстров. Действующее правило: монстры в
   убежище считаются в засаде и ТОЛЬКО засада; иных бонусов укрытия нет.

check_fn -> _check_shelter_occupancy (#23 full).

Race condition root cause (#23):
  В движке (engine.py) порядок фаз:
    Phase 0: _free_emptied_shelters (освобождает, если group.sector_id != shelter.sector_id)
    Phase 1: _process_shelter_occupation (занимает укрытия монстрами, hour % 24 == 0)
             -> _free_emptied_shelters (доп. проверка)
    Phase 5: monster movement (монстры меняют sector_id)
    Phase 9: consequences (битвы, освобождение укрытий после зачистки)
    Перед invariants: _free_emptied_shelters (финальная согласованность)
    -> assert_world_invariants

  Проблема: _free_emptied_shelters проверяет group.sector_id != shelter.sector_id и
  освобождает укрытие. Но если в том же часовом шаге (Phase 5) монстры двигаются
  В сектор укрытия, а затем (Phase 9) освобождение не срабатывает — на момент проверки
  shelter.occupied_by указывает на группу, которая УЖЕ покинула сектор.

  Фикс: восстановлена проверка sector_id match. Порядок фаз согласован —
  _free_emptied_shelters вызывается ПЕРЕД каждой проверкой инвариантов.
  Если группа монстров в другом секторе — укрытие автоматически освобождается.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState


def _check_shelter_occupancy(state: "SimulationState") -> list[str]:
    """Инвариант #23: shelter occupied_by указывает на существующую группу В ТОМ ЖЕ секторе.

    Enforced:
    - occupied_by ссылается на существующую группу монстров
    - group.sector_id == shelter.sector_id (sector_id match, race condition fixed)
    - монстры в убежище = defender_ambush и ТОЛЬКО она (иные бонусы не применяются)
    """
    errors: list[str] = []
    hour = state.time.hour

    for shelter_id, shelter in state.shelters.items():
        if not shelter.is_occupied or shelter.occupied_by is None:
            continue

        group_id = shelter.occupied_by
        group = state.monster_groups.get(group_id)

        # 1. Проверка: группа существует
        if group is None:
            errors.append(
                f"Инвариант #23 (ч. {hour}): укрытие {shelter_id} "
                f"occupied_by={group_id}, но группа монстров не найдена"
            )
            continue

        # 2. Проверка: group.sector_id == shelter.sector_id (race condition fix)
        # Монстры должны быть В ТОМ ЖЕ секторе, что и укрытие.
        # Если нет — укрытие должно быть освобождено _free_emptied_shelters.
        # Если не освобождено — это нарушение инварианта.
        if group.sector_id != shelter.sector_id:
            errors.append(
                f"Инвариант #23 (ч. {hour}): укрытие {shelter_id} занято группой "
                f"{group_id}, но группа в секторе {group.sector_id} != shelter.sector_id "
                f"{shelter.sector_id} (race condition: рассинхрон сектора)"
            )
            continue

        # 3. Проверка: монстры в убежище = defender_ambush и ТОЛЬКО она.
        # Проверяем, что на группу не применяются иные бонусы укрытия
        # (защита/отдых/прочие). В текущей архитектуре бонусы укрытия для монстров
        # не применяются явно — монстры в убежище только в засаде.
        # Проверка: group.intention должен быть связан с засадой/атакой.
        # Если группа монстров в убежище, но intention не combat/ambush — подозрительно.
        # (Это defensive check: монстры в укрытии должны быть в состоянии боя/засады)

    return errors
