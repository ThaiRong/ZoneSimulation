"""Модель сектора и базовая графовая логика. Основано на §7.2 и §6.2 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Sector:
    id: int
    name: str
    neighbors: list[int] = field(default_factory=list)
    map_x: int = 0
    map_y: int = 0
    terrain: str = "default"
    concealment: int = 50
    shelter_quality: int = 50
    is_faction_start: bool = False
    is_border: bool = False
    controller_faction: str | None = None

    @property
    def neighbor_ids(self) -> list[int]:
        return self.neighbors


def get_shortest_path(graph: dict[int, Sector], start_id: int, end_id: int) -> list[int] | None:
    """BFS поиск кратчайшего пути между двумя секторами."""
    if start_id == end_id:
        return [start_id]

    visited: set[int] = {start_id}
    queue: list[tuple[int, list[int]]] = [(start_id, [start_id])]

    while queue:
        current_id, path = queue.pop(0)
        current_sector = graph.get(current_id)
        if not current_sector:
            continue

        for neighbor_id in current_sector.neighbors:
            if neighbor_id == end_id:
                return path + [neighbor_id]
            if neighbor_id not in visited:
                visited.add(neighbor_id)
                queue.append((neighbor_id, path + [neighbor_id]))

    return None


def get_distance(graph: dict[int, Sector], start_id: int, end_id: int) -> int | None:
    """Расстояние в рёбрах."""
    path = get_shortest_path(graph, start_id, end_id)
    return len(path) - 1 if path else None


def is_connected(graph: dict[int, Sector]) -> bool:
    """Проверка связности графа."""
    if not graph:
        return True
    start_id = next(iter(graph))
    visited: set[int] = set()
    queue: list[int] = [start_id]

    while queue:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)
        sector = graph.get(current_id)
        if sector:
            queue.extend(sector.neighbors)

    return len(visited) == len(graph)
