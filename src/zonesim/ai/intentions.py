"""Выбор намерений NPC. Основано на §9 ТЗ.

Реализовано исполнение текущего подмножества действий §9.1:
сон, отдых/лечение, исследование, выслеживание, попытка покинуть Зону,
засада (§10.4). Боевые, торговые и групповые действия дополнятся позже.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

# Намерения
SLEEP = "sleep"
REST = "rest"
RESEARCH = "research_anomaly"
DESTROY = "destroy_anomaly"
CAPTURE = "capture_monster"
EXPLORE = "explore"
EXIT = "exit_zone"
SHELTER = "shelter"        # укрытие от выброса (§12.7)
HELP = "help_distress"     # помощь по сигналу бедствия (§16.10)
AMBUSH = "ambush"          # засада (§10.4)

ALL_ACTIONS = (SLEEP, REST, RESEARCH, DESTROY, CAPTURE, EXPLORE, EXIT, SHELTER, HELP, AMBUSH)

# Фракционные приоритеты F (§7.3). Меняют вероятность, не запрещают действия.
FACTION_FLAVOR: dict[str, dict[str, float]] = {
    "Бродяги": {RESEARCH: 8.0, EXPLORE: 5.0},
    "Борзые": {EXPLORE: 3.0, RESEARCH: 2.0, AMBUSH: 6.0},  # Борзые любят засады
    "Серая лига": {RESEARCH: 4.0, EXPLORE: 4.0, CAPTURE: 4.0, DESTROY: 3.0, AMBUSH: 4.0},
}


@dataclass
class IntentionContext:
    """Входные данные для оценки полезности действий. (§9.2)"""
    hour: int
    is_night: bool
    bravery: int
    faction: str
    health_share: float
    stamina_share: float
    at_home: bool
    home_sector_id: int | None
    distance_to_border: int | None
    has_known_anomaly: bool = False
    known_anomaly_concealment: int = 0
    known_has_artifact: bool = False
    can_destroy: bool = False       # исправный комплект разрушения и цель в секторе
    can_capture: bool = False       # комплект захвата и ослабленная цель в секторе
    can_rest: bool = False          # отдых требует комфорта (§14.3)
    hours_awake: float = 0.0        # часов с последнего пробуждения
    can_help: bool = False          # известен активный сигнал бедствия (§16.10)
    distress_distance: int = 6      # рёбер до сектора сигнала


def evaluate_actions(ctx: IntentionContext) -> dict[str, float]:
    """
    Оценка полезности: U = F + G + E + C + I + N - R × (1,25 - Bravery/200) + J.
    G (цель группы) и C (контракт) пока равны 0 — этих систем ещё нет.
    J добавляется отдельно в choose_intention.
    """
    u: dict[str, float] = {}
    flavor = FACTION_FLAVOR.get(ctx.faction, {})
    risk_factor = 1.25 - ctx.bravery / 200.0  # §9.2

    for action in ALL_ACTIONS:
        F = flavor.get(action, 0.0)
        G = 0.0
        E = 0.0
        C = 0.0
        I = 0.0
        N = 0.0
        R = 0.0

        if action == SLEEP:
            # Низкая выносливость — приоритет сна (§9.4)
            if ctx.stamina_share < 0.35:
                N += 60.0 * (1.0 - ctx.stamina_share)
            if ctx.is_night:
                N += 15.0
            # Сон необходим: бодрствование дольше 24 часов (§14.1)
            if ctx.hours_awake >= 24:
                N += 60.0
            if not ctx.at_home:
                R += 8.0  # сон вне базы опаснее
        elif action == REST:
            # Отдых: ½ темпа комфортного сна, требует комфорта и
            # применяется при выносливости ниже 80% (§14.3)
            if not ctx.can_rest:
                u[action] = float("-inf")
                continue
            if ctx.stamina_share < 0.8:
                N += 40.0 * (0.8 - ctx.stamina_share)
            # Группа старается держать среднее здоровье минимум на 60%:
            # раненые продолжают отдых до восстановления
            if ctx.health_share < 0.6:
                N += 50.0 * (0.6 - ctx.health_share)
            R += 2.0
        elif action == RESEARCH:
            if not ctx.has_known_anomaly:
                u[action] = float("-inf")  # нечего исследовать в секторе
                continue
            I += 8.0  # использование имеющегося знания
            if ctx.known_has_artifact:
                E += 10.0
            E += 4.0  # потенциальная находка: тропа, свежие сведения
            R += ctx.known_anomaly_concealment / 3.0
        elif action == DESTROY:
            # Без исправного комплекта намерение недоступно (§12.4)
            if not ctx.can_destroy:
                u[action] = float("-inf")
                continue
            E += 14.0  # части аномалии и доступ к артефакту — экспортная ценность
            R += 6.0
        elif action == CAPTURE:
            if not ctx.can_capture:
                u[action] = float("-inf")
                continue
            E += 16.0  # живой монстр ценнее частей (§16.8)
            R += 10.0  # опасная добыча может контратаковать
        elif action == EXPLORE:
            E += 2.0  # ценность сведений о неисследованном секторе
            R += 6.0  # базовая неопределённость неисследованного маршрута (§9.3)
        elif action == EXIT:
            if ctx.health_share < 0.15:
                N += 12.0  # тяжёлое состояние — уходить из Зоны (§9.4)
            # Выход имеет самый низкий приоритет: уходят только те, кому
            # нечего больше делать (раненые предпочитают базу и лечение)
            R += (ctx.distance_to_border or 0) / 2.0 + 15.0
        elif action == SHELTER:
            # Принудительное намерение выброса: назначается в фазе 4 (§12.7)
            u[action] = float("-inf")
            continue
        elif action == HELP:
            # Помощь по сигналу бедствия (§16.10)
            if not ctx.can_help:
                u[action] = float("-inf")
                continue
            N += 30.0 - 3.0 * (ctx.distress_distance or 6)
            R += 4.0
        elif action == AMBUSH:
            # Засада требует подготовки (§10.4)
            # Бонус за высокую внимательность группы
            ambush_chance = 55 + 0.5 * ctx.bravery  # упрощённо по ТЗ §10.4
            R += (100 - ambush_chance) / 10.0  # риск провала засады
            E += 10.0  # внезапность даёт ×1.25 атаки в первом раунде
            u[action] = F + E - R * risk_factor
            continue

        u[action] = F + G + E + C + I + N - R * risk_factor

    return u


def choose_intention(ctx: IntentionContext, rng) -> str:
    """Выбор намерения с поправкой J — небольшой случайной добавкой (§9.2)."""
    u = evaluate_actions(ctx)
    for action in u:
        u[action] += rng.uniform(-3.0, 3.0)
    return max(u, key=lambda a: u[a])


def known_anomaly_sectors(knowledge_facts) -> set[int]:
    """Сектора с аномалиями, о которых NPC знает (payload снимков §7.12)."""
    return {
        f.payload["sector_id"]
        for f in knowledge_facts
        if f.payload.get("sector_id") is not None
    }


def edge_key(a: int, b: int) -> tuple[int, int]:
    """Канонический ключ ребра."""
    return (a, b) if a < b else (b, a)


def edge_cost(trails: set[tuple[int, int]] | None, a: int, b: int) -> float:
    """Стоимость ребра: тропа 0,5 пункта, обычное — 1,0. (§10.4)"""
    if trails and edge_key(a, b) in trails:
        return 0.5
    return 1.0


def next_step_towards(sectors: dict[int, object], current_id: int,
                      target_ids: set[int], avoid_ids: set[int] | None = None,
                      trails: set[tuple[int, int]] | None = None) -> int | None:
    """
    Первый шаг маршрута к ближайшей из целевых секторов (§10.1).
    Тропы дешевле; сектора с известными аномалиями обходятся,
    пока есть разумная альтернатива.
    """
    avoid_ids = avoid_ids or set()
    if current_id in target_ids:
        return None

    graph = nx.Graph()
    for sid, sector in sectors.items():
        for nid in sector.neighbors:
            weight = edge_cost(trails, sid, nid)
            if nid in avoid_ids:
                weight += 4.0
            graph.add_edge(sid, nid, weight=weight)

    try:
        _, paths = nx.multi_source_dijkstra(graph, sources=set(target_ids))
    except nx.NodeNotFound:
        return None
    if current_id not in paths:
        return None
    path = paths[current_id]  # маршрут: цель → ... → current_id
    if len(path) < 2:
        return None
    return path[-2]


def choose_explore_target(sectors: dict[int, object], current_id: int,
                          visit_memory: dict[int, int], hour: int,
                          anomaly_sectors: set[int], rng) -> int | None:
    """
    Выбор соседнего сектора для исследования: давно не посещённые
    и без известных аномалий предпочтительнее.
    """
    sector = sectors.get(current_id)
    if not sector or not sector.neighbors:
        return None

    best: int | None = None
    best_score = float("-inf")
    for nid in sector.neighbors:
        age = hour - visit_memory.get(nid, -1000)
        score = float(age)
        if nid in anomaly_sectors:
            score -= 50.0
        score += rng.uniform(0.0, 4.0)
        if score > best_score:
            best, best_score = nid, score
    return best
