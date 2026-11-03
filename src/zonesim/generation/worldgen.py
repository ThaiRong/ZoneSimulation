"""Генерация мира по seed. Основано на §6.2 и §20.3 ТЗ."""

from __future__ import annotations

from typing import Any

from zonesim.anomalies.core import Anomaly, AnomalyType
from zonesim.core.time import SeededRNG
from zonesim.world.entity import HumanNPC, Monster
from zonesim.world.sector import Sector, get_distance


def generate_world(seed: int = 42, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Генерирует мир, возвращая словарь с ключами:
    - sectors: dict[int, Sector]
    - humans: list[HumanNPC]
    - monsters: list[Monster]
    - anomalies: list[Anomaly]
    """
    rng = SeededRNG(seed)
    cfg = config or {}
    sectors_count = cfg.get("world", {}).get("sectors_count", 20)
    humans_count = cfg.get("world", {}).get("mobile_humans_count", 40)
    monsters_count = cfg.get("world", {}).get("monsters_count", 28)
    anomalies_count = cfg.get("world", {}).get("anomalies_count", 30)

    sectors = _generate_graph(sectors_count, rng)
    start_ids = _assign_start_sectors(sectors, rng, min_dist=4)
    _assign_border_sectors(sectors)
    _ensure_start_proximity_to_border(sectors, start_ids, rng)

    humans = _spawn_humans(sectors, start_ids, humans_count, rng)
    monsters = _spawn_monsters(sectors, start_ids, monsters_count, rng)
    anomalies = _spawn_anomalies(sectors, start_ids, anomalies_count, rng)

    return {
        "sectors": sectors,
        "humans": humans,
        "monsters": monsters,
        "anomalies": anomalies,
    }


def _generate_graph(count: int, rng: SeededRNG) -> dict[int, Sector]:
    """Генерирует связный граф секторов с большим диаметром для размещения стартов."""
    sectors: dict[int, Sector] = {}
    for i in range(count):
        sectors[i] = Sector(id=i, name=f"Сектор-{i+1}", map_x=rng.randint(-50, 50), map_y=rng.randint(-50, 50))

    # 1. Строим "линию" (путь) для гарантии большого диаметра
    path = list(sectors.keys())
    rng.shuffle(path)
    for i in range(count - 1):
        u, v = path[i], path[i+1]
        sectors[u].neighbors.append(v)
        sectors[v].neighbors.append(u)

    # 2. Добавляем случайные рёбра для "кляксообразности" (до 3-4 соседей в среднем)
    max_new_edges = count // 2 
    added_edges = 0
    while added_edges < max_new_edges:
        u = rng.randint(0, count - 1)
        v = rng.randint(0, count - 1)
        if u != v and v not in sectors[u].neighbors and u not in sectors[v].neighbors:
            sectors[u].neighbors.append(v)
            sectors[v].neighbors.append(u)
            added_edges += 1

    return sectors


def _assign_border_sectors(sectors: dict[int, Sector]) -> None:
    """Граничные сектора — те, у кого 1-3 соседа или крайние по координатам."""
    # Сначала маркируем листья и почти листья
    for sid, s in sectors.items():
        if len(s.neighbors) <= 2:
            s.is_border = True
    
    # Если гранов нет совсем или их мало, маркируем самые крайние
    border_count = sum(1 for s in sectors.values() if s.is_border)
    if border_count < len(sectors) * 0.2:
        sorted_by_deg = sorted(sectors.values(), key=lambda x: len(x.neighbors))
        for s in sorted_by_deg[:max(3, len(sectors) // 5)]:
            s.is_border = True


def _assign_start_sectors(sectors: dict[int, Sector], rng: SeededRNG, min_dist: int = 4) -> list[int]:
    """Выбирает 3 стартовых сектора с расстоянием >= min_dist."""
    candidates = list(sectors.keys())
    rng.shuffle(candidates)
    starts: list[int] = []

    for c in candidates:
        if len(starts) >= 3:
            break
        # Проверка дистанции до всех уже выбранных стартов
        distances = [get_distance(sectors, c, s) for s in starts]
        if all(d is not None and d >= min_dist for d in distances):
            starts.append(c)
    
    # Fallback: если не удалось найти 3 с расстоянием 4 (например, на маленьком графе), берём максимально удалённые
    if len(starts) < 3:
        # Сортируем кандидатов по среднему расстоянию до уже выбранных
        remaining = [c for c in candidates if c not in starts]
        for _ in range(3 - len(starts)):
            if not remaining:
                break
            # Ищем самый удалённый от всех текущих стартов
            best_c = max(remaining, key=lambda x: min((get_distance(sectors, x, s) or 0) for s in starts))
            starts.append(best_c)
            remaining.remove(best_c)

    for sid in starts:
        sectors[sid].is_faction_start = True

    return starts


def _ensure_start_proximity_to_border(sectors: dict[int, Sector], start_ids: list[int], rng: SeededRNG) -> None:
    """Убеждается, что стартовые сектора близко к границе (<= 1 ребро)."""
    border_ids = [sid for sid, s in sectors.items() if s.is_border]
    if not border_ids:
        # На всякий случай маркируем некоторые сектора граничными
        _assign_border_sectors(sectors)
        border_ids = [sid for sid, s in sectors.items() if s.is_border]

    for sid in start_ids:
        dist_to_border = min((get_distance(sectors, sid, n) or 999) for n in border_ids)
        if dist_to_border > 1:
            # Если далеко, делаем его граничным (упрощение для MVP)
            sectors[sid].is_border = True


def _spawn_humans(sectors: dict[int, Sector], start_ids: list[int], count: int, rng: SeededRNG) -> list[HumanNPC]:
    factions = ["Бродяги", "Борзые", "Серая лига"]
    humans: list[HumanNPC] = []
    sector_ids = list(sectors.keys())

    for i in range(count):
        faction = factions[i % len(factions)]
        sec_id = rng.choice(sector_ids)
        humans.append(HumanNPC(
            id=i,
            sector_id=sec_id,
            faction=faction,
            name=f"Человек-{i+1}",
        ))
    return humans


def _spawn_monsters(sectors: dict[int, Sector], start_ids: list[int], count: int, rng: SeededRNG) -> list[Monster]:
    species = ["TerritorialPredator", "ScavengerPack", "LargeMigrator"]
    monsters: list[Monster] = []
    sector_ids = [s for s in sectors if s not in start_ids] # Не спавним монстров на стартах

    for i in range(count):
        sec_id = rng.choice(sector_ids) if sector_ids else rng.choice(list(sectors.keys()))
        monsters.append(Monster(
            id=i + 1000,
            sector_id=sec_id,
            species=rng.choice(species),
            home_sector_id=sec_id,
        ))
    return monsters


def _spawn_anomalies(sectors: dict[int, Sector], start_ids: list[int], count: int, rng: SeededRNG) -> list[Anomaly]:
    types = list(AnomalyType)
    anomalies: list[Anomaly] = []
    sector_ids = [s for s in sectors if s not in start_ids]

    for i in range(count):
        sec_id = rng.choice(sector_ids) if sector_ids else rng.choice(list(sectors.keys()))
        anomalies.append(Anomaly.create_from_type(
            id=i + 2000,
            sector_id=sec_id,
            atype=rng.choice(types),
            rng=rng,
        ))
    return anomalies
