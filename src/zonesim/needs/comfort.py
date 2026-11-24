"""Проверки комфорта группировок. Основано на §7.5, invariant #13 ТЗ."""

from __future__ import annotations

from zonesim.world.entity import EntityStatus


def has_strict_comfort(
    group,
    all_npcs: dict[int, 'HumanNPC'],  # noqa: F forward-ref
    stationary: dict[int, 'HumanNPC'],  # noqa: F forward-ref
    shelters: dict[int, object],
    temp_shelters: dict[int, object],
    sectors: dict[int, object],
    sector_id: int,
    faction: str | None,
) -> bool:
    """Strict comfort check для invariant #13 (без condition 6 awake_member).

    Возвращает True только если есть РАБОТАЮЩАЯ защита:
    (a) StormShelter в секторе ИЛИ active temp_shelter с participant_count>0;
    (b) база фракции (is_faction_start=True) в секторе;
    (c) stationary guard ACTIVE в секторе;
    (d) guard_schedule: entry в members И член группы ACTIVE в секторе.
    """
    # (a) StormShelter в секторе
    for shelter in shelters.values():
        if (hasattr(shelter, 'sector_id') and shelter.sector_id == sector_id
                and type(shelter).__name__ == "StormShelter"):
            return True

    # (a) Active temp_shelter с participant_count>0 в секторе
    for shelter in temp_shelters.values():
        if (hasattr(shelter, 'sector_id') and shelter.sector_id == sector_id
                and hasattr(shelter, 'is_active') and shelter.is_active):
            if hasattr(shelter, 'participant_count') and shelter.participant_count > 0:
                return True

    # (b) База фракции в секторе
    if faction:
        for sid, sector in sectors.items():
            if sid == sector_id and getattr(sector, "is_faction_start", False):
                ctrl = getattr(sector, "controller_faction", None)
                if ctrl is None or ctrl == faction:
                    return True

    # (c) Stationary guard ACTIVE в секторе
    for n in stationary.values():
        if (n.stationary_role == "guard" and n.status == EntityStatus.ACTIVE
                and n.sector_id == sector_id):
            return True

    # (d) Guard schedule: член группы ACTIVE в секторе
    for entry in group.guard_schedule:
        if entry.get("npc_id") in group.members:
            for m in all_npcs.values():
                if m.id == entry["npc_id"] and m.status == EntityStatus.ACTIVE and m.sector_id == sector_id:
                    return True

    return False
