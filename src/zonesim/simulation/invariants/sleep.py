"""Инвариант #13: комфортный сон требует укрытия/охраны/базы.

§22 ТЗ:
13 Комфортный сон вне неохраняемого места невозможен; минимум 1 охранник бодрствует
   и дееспособен.

check_fn -> _check_comfort_sleep_guard (#13 full).

Логика:
- comfort=False → не-комфортный сон легален где угодно.
- comfort=True → легален ТОЛЬКО если одно из:
  (a) StormShelter в секторе ИЛИ active temp_shelter с participant_count>0;
  (b) база фракции (is_faction_start=True) в секторе;
  (c) стационарный guard ACTIVE в секторе;
  (d) guard_schedule: entry["npc_id"] в members И член группы ACTIVE в секторе.
- Иначе → errors.append.
- «Все спят без защиты» → НАРУШЕНИЕ (ловить).
- БЕЗ TOCTOU/has_structure/all_sleeing — только РАБОТАЮЩАЯ защита.
"""

from __future__ import annotations

from zonesim.world.entity import EntityStatus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState


def _check_comfort_sleep_guard(state: "SimulationState") -> list[str]:
    """Инвариант #13: комфортный сон требует shelter/guard/base.

    Строгая проверка: только работающая защита (active/действующая).
    Не использовать «structure exist» (пустую/неактивную) как защиту.
    """
    errors: list[str] = []
    hour = state.time.hour

    for npc in state.humans:
        if npc.status != EntityStatus.SLEEPING:
            continue

        group = state.human_groups.get(npc.group_id)
        if group is None:
            continue

        # comfort=False → не-комфортный сон, легален где угодно
        if not group.comfort:
            continue

        # comfort=True → строгая проверка условий
        sector_id = npc.sector_id
        faction = npc.faction

        strict_comfort = False

        # (a) StormShelter в секторе
        if not strict_comfort:
            for shelter in state.shelters.values():
                if (hasattr(shelter, 'sector_id') and shelter.sector_id == sector_id
                        and type(shelter).__name__ == "StormShelter"):
                    strict_comfort = True
                    break

        # (a) Active temp_shelter с participant_count>0 в секторе
        if not strict_comfort:
            for shelter in state.temp_shelters.values():
                if (hasattr(shelter, 'sector_id') and shelter.sector_id == sector_id
                        and hasattr(shelter, 'is_active') and shelter.is_active):
                    if hasattr(shelter, 'participant_count') and shelter.participant_count > 0:
                        strict_comfort = True
                        break

        # (b) База фракции в секторе
        if not strict_comfort and faction:
            for sid, sector in state.sectors.items():
                if sid == sector_id and getattr(sector, "is_faction_start", False):
                    ctrl = getattr(sector, "controller_faction", None)
                    if ctrl is None or ctrl == faction:
                        strict_comfort = True
                        break

        # (c) Стационарный guard ACTIVE в секторе
        if not strict_comfort:
            for n in state.stationary_humans:
                if (n.stationary_role == "guard" and n.status == EntityStatus.ACTIVE
                        and n.sector_id == sector_id):
                    strict_comfort = True
                    break

        # (d) Guard schedule: член группы ACTIVE в секторе
        if not strict_comfort:
            for entry in group.guard_schedule:
                if entry.get("npc_id") in group.members:
                    for m in state.humans:
                        if m.id == entry["npc_id"] and m.status == EntityStatus.ACTIVE and m.sector_id == sector_id:
                            strict_comfort = True
                            break

        if strict_comfort:
            continue  # есть работающая защита — сон легален

        # Нет рабочей защиты → violation
        errors.append(
            f"Инвариант #13 (ч. {hour}): NPC {npc.id} ({npc.faction}) "
            f"спит с комфортом (group.comfort=True) в секторе {sector_id} "
            f"без shelter/guard/base/дежурного "
            f"(§22.13)"
        )

    return errors
