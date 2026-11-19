"""Инвариант #13: комфортный сон требует укрытия/охраны/базы.

§22 ТЗ:
13 Комфортный сон вне неохраняемого места невозможен; минимум 1 охранник бодрствует
   и дееспособен.

check_fn -> _check_comfort_sleep_guard (#13 full).

Логика:
- group.comfort устанавливается в _phase4_intentions на основе is_comfort_sleep_possible().
- Invariant проверяет: если group.comfort=True, но REальные условия comfort отсутствуют
  (без учёта condition 6 awake_member для СЯЯЩЕГО NPC) → TOCTOU.
- Если shelter structure exist (даже без участников) → TOCTOU ok.
- Если shelter structure НЕ exist → violation.
"""

from __future__ import annotations

from zonesim.world.entity import EntityStatus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _check_comfort_sleep_guard(state: "SimulationState") -> list[str]:
    """Инвариант #13: комфортный сон требует shelter/guard/base.

    Проверяет что SLEEPING NPC с group.comfort=True имеют реальные условия.
    Учёт TOCTOU: если comfort=True установлен на основе валидных условий,
    но условия изменились (expire) — это OK.
    Если shelter/guard/base structure полностью отсутствуют — violation.
    """
    errors: list[str] = []
    hour = state.time.hour

    for npc in state.humans:
        if npc.status != EntityStatus.SLEEPING:
            continue

        group = state.human_groups.get(npc.group_id)
        if group is None:
            continue

        # Comfort=False → не-комфортный сон, легален где угодно
        if not group.comfort:
            continue

        # Comfort=True — проверяем что REАЛЬНЫЕ условия comfort exist (вкл. condition 6
        # но ДЛЯ ДРУГИХ членов группы, не для спящего NPC).

        sector_id = npc.sector_id
        faction = npc.faction

        # Строгий comfort check (без condition 6 awake_member)
        strict_comfort = False

        # 1. Base
        if faction:
            for sid, sector in state.sectors.items():
                if sid == sector_id and getattr(sector, "is_faction_start", False):
                    controller = getattr(sector, "controller_faction", None)
                    if controller is None or controller == faction:
                        strict_comfort = True
                        break

        # 2. Temp shelter с участниками
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

        # 4. Stationary guard
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
            continue  # условия валидны — сон легален

        # strict_comfort=False — проверяем: exist ли ANY awake member (condition 6)
        # но НЕ для этого спящего NPC (они спят, не могут охранять себя).
        awake_others = False
        for mid in group.members:
            if mid == npc.id:
                continue  # пропускаем спящего NPC
            for m in state.humans:
                if m.id == mid and m.status == EntityStatus.ACTIVE and m.sector_id == sector_id:
                    awake_others = True
                    break
        if awake_others:
            continue  # condition 6 satisfied — сон легален

        # Если ВСЕ члены группы спят — они "безопасны" вместе (выбрали комфортный сон)
        # Не флагировать false positive
        all_sleeing = all(
            any(m.status == EntityStatus.SLEEPING for m in state.humans if m.id == mid)
            for mid in group.members
        )
        if all_sleeing:
            continue

        # И strict_comfort=False и awake_others=False — проверяем structure existence
        # для разделения TOCTOU от violation
        has_structure = False

        # StormShelter exist
        for shelter in state.shelters.values():
            if hasattr(shelter, 'sector_id') and shelter.sector_id == sector_id:
                if type(shelter).__name__ == "StormShelter":
                    has_structure = True
                    break

        # Temp shelter exist (даже с 0 участников)
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
