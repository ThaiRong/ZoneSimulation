"""Инвариант #13: комфортный сон требует охранника/убежища/дежурного.

§22 ТЗ:
13 Комфортный сон вне неохраняемого места невозможен; минимум 1 охранник бодрствует
   и дееспособен.

check_fn -> _check_comfort_sleep_guard (#13 full).

Механика comfort sleep (group.py, is_comfort_sleep_possible):
  Комфортный сон возможен, если:
  1. Группа в секторе базы своей/союзной/нейтральной фракции
  2. Есть активный Shelter (временное) в секторе
  3. Есть активный StormShelter в секторе
  4. Есть активный стационарный охранник в секторе
  5. Есть дежурный из группы (guard_schedule)
  
Инвариант #13 проверяет обратное: если NPC спит с комфортом (здоровье >= 50%,
выносливость не критическая), но нет укрытия/охраны в секторе — это нарушение.
"""

from __future__ import annotations

from zonesim.world.entity import EntityStatus
from zonesim.world.shelter import StormShelter

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _check_comfort_sleep_guard(state: "SimulationState") -> list[str]:
    """Инвариант #13: комфортный сон требует охранника/убежища/дежурного.

    Комфортный сон вне неохраняемого места невозможен; минимум 1 охранник
    бодрствует и дееспособен.

    Проверка работает ВСЕГДА (не только ночью), т.к. сон без укрытия опасен
    в любое время суток (§22.13).
    """
    errors: list[str] = []
    hour = state.time.hour

    for npc in state.humans:
        if npc.status != EntityStatus.SLEEPING:
            continue
        # Комфортный сон: здоровье >= 50% и stamina не на исходе
        if npc.health_share < 0.5 or npc.stamina_share > 0.65:
            continue

        sector_id = npc.sector_id

        # Проверяем наличие укрытия/охраны в секторе
        has_shelter = any(
            hasattr(s, 'sector_id') and s.sector_id == sector_id
            for s in state.shelters.values()
        )
        has_temp_shelter = any(
            hasattr(s, 'sector_id') and s.sector_id == sector_id
            for s in state.temp_shelters.values()
        )
        has_guard = any(
            n.stationary_role == "guard"
            and n.status == EntityStatus.ACTIVE
            and n.sector_id == sector_id
            for n in state.stationary_humans
        )

        if not has_shelter and not has_temp_shelter and not has_guard:
            errors.append(
                f"Инвариант #13 (ч. {hour}): NPC {npc.id} ({npc.faction}) "
                f"спит с комфортом (health={npc.health_share:.2f}, "
                f"stamina={npc.stamina_share:.2f}) в секторе {sector_id} "
                f"без укрытия/временного убежища/охранника (§22.13)"
            )

    return errors
