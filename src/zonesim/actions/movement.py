"""Перемещение сущностей по графу секторов. Основано на §6.2, §10.1, §13 ТЗ."""

from __future__ import annotations

from zonesim.world.sector import get_shortest_path

# Виды монстров и их скорость (рёбер за час)
MONSTER_SPEED = {
    "TerritorialPredator": 2,  # территориальный хищник — до 2 рёбер/час (§6.2)
    "ScavengerPack": 1,  # стайный падальщик — 1 ребро/час
    "LargeMigrator": 1,  # крупный всеядный мигрант — 1 ребро/час
}


def calculate_move_target(
    sector_id: int,
    sectors: dict[int, object],
    avoid_anomalies: bool = False,
    known_anomalies: dict[int, list[int]] | None = None,
    rng=None,
) -> int | None:
    """
    Выбирает целевой сектор для перемещения.
    Возвращает id сектора или None если нельзя уйти.
    """
    sector = sectors.get(sector_id)
    if not sector:
        return None

    neighbors = sector.neighbors

    if not neighbors:
        return None  # тупик — некуда идти

    if avoid_anomalies and known_anomalies:
        # Исключаем сектора с известными аномалиями
        safe_neighbors = [
            n for n in neighbors
            if n not in known_anomalies or len(known_anomalies[n]) == 0
        ]
        if safe_neighbors:
            neighbors = safe_neighbors

    if rng:
        return rng.choice(neighbors)
    return neighbors[0] if neighbors else None


def move_entity(
    entity,
    sectors: dict[int, object],
    target_sector_id: int,
    max_edges: int = 1,
) -> int:
    """
    Перемещает сущность по кратчайшему пути.
    Возвращает фактически пройденное количество рёбер.
    """
    if entity.sector_id == target_sector_id:
        return 0

    path = get_shortest_path(sectors, entity.sector_id, target_sector_id)
    if not path or len(path) < 2:
        return 0

    # Пройдяем максимум max_edges рёбер
    steps = min(max_edges, len(path) - 1)
    new_sector_id = path[steps]
    entity.sector_id = new_sector_id

    return steps


def move_group(
    group,
    sectors: dict[int, object],
    target_sector_id: int,
    max_edges: int = 1,
    species: str | None = None,
) -> int:
    """
    Перемещает группу сущностей.
    Возвращает пройденные рёбра.
    """
    if group.sector_id == target_sector_id:
        return 0

    path = get_shortest_path(sectors, group.sector_id, target_sector_id)
    if not path or len(path) < 2:
        return 0

    steps = min(max_edges, len(path) - 1)
    new_sector_id = path[steps]
    group.sector_id = new_sector_id

    # Обновляем sector_id у всех членов группы
    for member_id in group.members:
        if hasattr(member_id, "sector_id"):
            member_id.sector_id = new_sector_id

    return steps


def check_border_exit(
    entity_or_group,
    sectors: dict[int, object],
    is_group: bool = False,
) -> bool:
    """
    Проверяет, находится ли сущность/группа на границе для выхода из Зоны.
    Возвращает True если можно попытаться выйти.
    """
    if is_group:
        return sectors.get(entity_or_group.sector_id, None) and \
               sectors[entity_or_group.sector_id].is_border
    return hasattr(entity_or_group, "sector_id") and \
           sectors.get(entity_or_group.sector_id, None) and \
           sectors[entity_or_group.sector_id].is_border


def get_move_distance(species: str = "Human", max_stamina_pct: float = 0.0) -> int:
    """
    Определяет сколько рёбер может пройти сущность за час.
    """
    if species == "Human":
        return 1
    return MONSTER_SPEED.get(species, 1)
