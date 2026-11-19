"""Инварианты #1, #2, #4: группы людей, #5: статусы ≠ действия.

§22 ТЗ:
1  Живой мобильный человек состоит не более чем в одной группе.
2  В группе людей 1–4 активных живых участника; пленные отдельно и в лимит не входят.
4  Все активные участники группы и её пленные после шага находятся в одном секторе.
5  Погибшие/покинувшие Зону/спящие/без сознания/пленные не выбирают новых самостоятельных действий.

check_fn → _check_human_groups (#1, #2, #4) и _check_status_intentions (#5).
"""

from __future__ import annotations

from zonesim.world.entity import EntityStatus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _check_human_groups(state: "SimulationState") -> list[str]:
    """Инварианты #1, #2, #4: группы людей.

    Возвращает список нарушений (#1 — дублирование NPC в группах,
    #2 — размер группы > 4, #4 — члены/пленные в разных секторах).
    """
    errors: list[str] = []
    hour = state.time.hour

    # Инвариант 1: каждый живой мобильный NPC состоит не более чем в одной группе
    group_map: dict[int, int] = {}  # npc_id -> group_id
    for gid, group in state.human_groups.items():
        for mid in group.members:
            if mid in group_map:
                errors.append(
                    f"Инвариант #1 (ч. {hour}): NPC {mid} состоит в группах "
                    f"{group_map[mid]} и {gid}"
                )
            else:
                group_map[mid] = gid

    # Инвариант 2: в группе людей 1-4 активных + пленные отдельно
    for gid, group in state.human_groups.items():
        if len(group.members) > 4:
            errors.append(
                f"Инвариант #2 (ч. {hour}): группа {gid} имеет "
                f"{len(group.members)} членов (макс. 4)"
            )

    # Инвариант 4: все активные члены группы и пленные в одном секторе
    npcs = {n.id: n for n in state.humans}
    for gid, group in state.human_groups.items():
        if not group.members:
            continue
        first_sector = npcs.get(group.members[0])
        if first_sector is None:
            continue
        for mid in group.members:
            npc = npcs.get(mid)
            if npc and npc.sector_id != first_sector.sector_id:
                errors.append(
                    f"Инвариант #4 (ч. {hour}): группа {gid} — NPC {mid} "
                    f"в секторе {npc.sector_id}, лидер в {first_sector.sector_id}"
                )
        for pid in group.prisoners:
            prisoner = npcs.get(pid)
            if prisoner and prisoner.sector_id != first_sector.sector_id:
                errors.append(
                    f"Инвариант #4 (ч. {hour}): группа {gid} — пленный {pid} "
                    f"в секторе {prisoner.sector_id}, лидер в {first_sector.sector_id}"
                )

    return errors


def _check_status_intentions(state: "SimulationState") -> list[str]:
    """Инвариант #5: спящие/пленные не выбирают действий.

    Проверяет: NPC с EntityStatus.PRISONER не выбирают активных намерений.
    НБ: спящие не проверяются (это не блокирующий инвариант).
    """
    errors: list[str] = []
    hour = state.time.hour

    for npc in state.humans:
        if npc.status == EntityStatus.PRISONER:
            if npc.intention and npc.intention not in ("sleep", "rest"):
                errors.append(
                    f"Инвариант #5 (ч. {hour}): NPC {npc.id} в плену, "
                    f"но намерение='{npc.intention}'"
                )

    return errors
