"""Инвариант #13: комфортный сон требует укрытия/охраны/базы.

§22 ТЗ:
13 Комфортный сон вне неохраняемого места невозможен; минимум 1 охранник бодрствует
   и дееспособен.

check_fn -> _check_comfort_sleep_guard (#13 full).

Логика:
- comfort=False → не-комфортный сон легален где угодно.
- comfort=True → легален если:
  1. Strict comfort (base/shelter с участниками/StormShelter/guard/guard_schedule) ИЛИ
  2. ДРУГОЙ член группы ACTIVE в секторе (awake guard).
- Иначе → violation (even if all_sleeing — это real violation).
- TOCTOU exception: если structure exist (даже с 0 участников) → shelter expire → ok.
"""

from __future__ import annotations

from zonesim.world.entity import EntityStatus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _check_comfort_sleep_guard(state: "SimulationState") -> list[str]:
    """Инвариант #13: комфортный сон требует shelter/guard/base.

    Строгая проверка без all_sleeing skip:
    - comfort=False → легален где угодно
    - comfort=True → strict comfort OR awake guard (другой член группы)
    - если structure exist но comfort=False → TOCTOU (shelter expire) → ok
    - иначе → violation
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

        # comfort=True → строгая проверка
        sector_id = npc.sector_id
        faction = npc.faction

        # Strict comfort check (без condition 6 awake_member)
        strict_comfort = False

        # 1. База фракции
        if faction:
            for sid, sector in state.sectors.items():
                if sid == sector_id and getattr(sector, "is_faction_start", False):
                    ctrl = getattr(sector, "controller_faction", None)
                    if ctrl is None or ctrl == faction:
                        strict_comfort = True
                        break

        # 2. Active Shelter с участниками
        if not strict_comfort:
            for shelter in state.temp_shelters.values():
                if (hasattr(shelter, 'sector_id') and shelter.sector_id == sector_id
                        and hasattr(shelter, 'is_active') and shelter.is_active):
                    if hasattr(shelter, 'participant_count') and shelter.participant_count > 0:
                        strict_comfort = True
                        break

        # 3. StormShelter
        if not strict_comfort:
            for shelter in state.shelters.values():
                if (hasattr(shelter, 'sector_id') and shelter.sector_id == sector_id
                        and type(shelter).__name__ == "StormShelter"):
                    strict_comfort = True
                    break

        # 4. Стационарный охранник
        if not strict_comfort:
            for n in state.stationary_humans:
                if (n.stationary_role == "guard" and n.status == EntityStatus.ACTIVE
                        and n.sector_id == sector_id):
                    strict_comfort = True
                    break

        # 5. Guard schedule
        if not strict_comfort:
            for entry in group.guard_schedule:
                if entry.get("npc_id") in group.members:
                    for m in state.humans:
                        if m.id == entry["npc_id"] and m.status == EntityStatus.ACTIVE and m.sector_id == sector_id:
                            strict_comfort = True
                            break

        if strict_comfort:
            continue

        # strict_comfort=False → awake guard (другой член группы ACTIVE)
        for mid in group.members:
            if mid == npc.id:
                continue
            for m in state.humans:
                if m.id == mid and m.status == EntityStatus.ACTIVE and m.sector_id == sector_id:
                    break
            else:
                continue
            break
        else:
            # Ни strict, ни awake guard → TOCTOU check
            # Если shelter/guard/base structure exist (даже с 0 участников) → ok
            has_structure = False
            for shelter in state.shelters.values():
                if hasattr(shelter, 'sector_id') and shelter.sector_id == sector_id:
                    if type(shelter).__name__ == "StormShelter":
                        has_structure = True
                        break
            if not has_structure:
                for shelter in state.temp_shelters.values():
                    if hasattr(shelter, 'sector_id') and shelter.sector_id == sector_id:
                        has_structure = True
                        break
            if not has_structure and faction:
                for sid, sector in state.sectors.items():
                    if sid == sector_id and getattr(sector, "is_faction_start", False):
                        has_structure = True
                        break
            if not has_structure:
                for n in state.stationary_humans:
                    if (n.stationary_role == "guard" and n.status == EntityStatus.ACTIVE
                            and n.sector_id == sector_id):
                        has_structure = True
                        break
            if not has_structure:
                for entry in group.guard_schedule:
                    if entry.get("npc_id") in group.members:
                        has_structure = True
                        break
            if not has_structure:
                errors.append(
                    f"Инвариант #13 (ч. {hour}): NPC {npc.id} ({npc.faction}) "
                    f"спит с комфортом (group.comfort=True) в секторе {sector_id} "
                    f"без shelter/guard/base/дежурного "
                    f"(§22.13)"
                )

    return errors
