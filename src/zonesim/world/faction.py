"""Фракционная логика: определение фракции группы, домашние базы, расстояние до границы.

Основано на §7.5, §6.2 ТЗ.
"""

from __future__ import annotations

from typing import Any


def group_faction(group, state) -> str | None:
    """Возвращает фракцию лидера группы (§7.5)."""
    npcs = {npc.id: npc for npc in state.humans}
    leader = npcs.get(group.leader_id)
    return leader.faction if leader is not None else None


def home_sector_id(
    sectors: dict[int, Any],
    faction: str,
    home_cache: dict[str, int | None] | None = None,
) -> int | None:
    """Домашняя база фракции (§6.2).

    Если передан home_cache — используется для кэширования результатов.
    """
    if home_cache is not None and faction in home_cache:
        return home_cache[faction]

    result = next(
        (s.id for s in sectors.values()
         if s.is_faction_start and s.controller_faction == faction),
        None,
    )

    if home_cache is not None:
        home_cache[faction] = result
    return result


def distance_to_border(
    sectors: dict[int, Any],
    border_dist: dict[int, int] | None = None,
) -> dict[int, int] | None:
    """Расстояние в рёбрах до ближайшего граничного сектора (§6.2).

    Возвращает полный словарь расстояний. Если передан border_dist —
    используется как кэш (BFS уже выполнен).
    """
    if border_dist is not None:
        return border_dist

    dist: dict[int, int] = {}
    queue = [sid for sid, s in sectors.items() if s.is_border]
    for sid in queue:
        dist[sid] = 0
    while queue:
        current = queue.pop(0)
        for nid in sectors[current].neighbors:
            if nid not in dist:
                dist[nid] = dist[current] + 1
                queue.append(nid)
    return dist
