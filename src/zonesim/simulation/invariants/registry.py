"""Реестр 25 инвариантов мира §22.

Каждый инвариант зарегистрирован:
- id: int (1–25)
- sec_ref: str — ссылка на параграф ТЗ
- description: str — описание ДОСЛОВНО из ТЗ «Техническое задание — Симуляция Зоны.md», §22
- check_fn: callable | None — функция проверки (runtime) или None (static)
- kind: str — "runtime" или "static"

Runtime-инварианты вызываются из assert_world_invariants() каждый час.
Static-инварианты проверяются на уровне архитектуры/импортов.

Эталонные формулировки §22 — ДОСЛОВНО из ТЗ (источник — ТЗ «Техническое задание — Симуляция Зоны.md»).
Любое расхождение — bug реестра, не bug инварианта.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


# ---------------------------------------------------------------------------
# Регистрация
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class InvariantInfo:
    """Метаданные одного инварианта."""
    id: int
    sec_ref: str  # §ref
    description: str
    check_fn: Callable | None  # None для static-инвариантов
    kind: str  # "runtime" | "static"
    coverage: str  # "full" | "partial" | "missing" | "static"


_INVARIANT_REGISTRY: list[InvariantInfo] = []


def register_invariant(
    invariant_id: int,
    sec_ref: str,
    description: str,
    check_fn: Callable | None = None,
    kind: str = "runtime",
    coverage: str = "missing",
) -> None:
    """Зарегистрировать инвариант.

    coverage: "full" | "partial" | "missing" | "static"
    - full: check_fn реально enforcing (есть достижимый errors.append, ловит нарушение)
    - partial: check_fn есть, но покрывает инвариант не полностью
    - missing: проверки нет ИЛИ функция-заглушка (никогда не append'ит ошибки)
    - static: architecture-тест
    """
    _INVARIANT_REGISTRY.append(InvariantInfo(
        id=invariant_id,
        sec_ref=sec_ref,
        description=description,
        check_fn=check_fn,
        kind=kind,
        coverage=coverage,
    ))


def get_invariant(inv_id: int) -> InvariantInfo:
    """Получить метаинформацию по id."""
    for info in _INVARIANT_REGISTRY:
        if info.id == inv_id:
            return info
    raise KeyError(f"Инвариант {inv_id} не зарегистрирован")


def all_invariant_ids() -> list[int]:
    """Все зарегистрированные id."""
    return [info.id for info in _INVARIANT_REGISTRY]


def runtime_invariant_ids() -> list[int]:
    """Runtime-инварианты."""
    return [info.id for info in _INVARIANT_REGISTRY if info.kind == "runtime"]


def static_invariant_ids() -> list[int]:
    """Static-инварианты."""
    return [info.id for info in _INVARIANT_REGISTRY if info.kind == "static"]


def invariant_kind(inv_id: int) -> str:
    """Kind инварианта по id."""
    info = get_invariant(inv_id)
    return info.kind


def invariant_id(inv_id: int) -> int:
    """Возвращает id инварианта (identity)."""
    return get_invariant(inv_id).id


def invariant_coverage(inv_id: int) -> str:
    """Coverage инварианта по id."""
    info = get_invariant(inv_id)
    return info.coverage


def full_invariant_ids() -> list[int]:
    """Runtime-инварианты с coverage=full."""
    return [info.id for info in _INVARIANT_REGISTRY
            if info.kind == "runtime" and info.coverage == "full"]


def partial_invariant_ids() -> list[int]:
    """Runtime-инварианты с coverage=partial."""
    return [info.id for info in _INVARIANT_REGISTRY
            if info.kind == "runtime" and info.coverage == "partial"]


def missing_invariant_ids() -> list[int]:
    """Runtime-инварианты с coverage=missing."""
    return [info.id for info in _INVARIANT_REGISTRY
            if info.kind == "runtime" and info.coverage == "missing"]


# ---------------------------------------------------------------------------
# Эталонные формулировки §22 — ДОСЛОВНО из ТЗ
# ---------------------------------------------------------------------------

# ИСТОЧНИК: ТЗ «Техническое задание — Симуляция Зоны.md», §22 (25 инвариантов).
# КАЖДОЕ описание ниже — ДОСЛОВНАЯ КОПИЯ из ТЗ, БЕЗ изменений/перефразировок.
# Если описание отличается — это BUG реестра, не bug инварианта.

CANONICAL_DESCRIPTIONS: dict[int, str] = {
    1: (
        "Живой мобильный человек состоит не более чем в одной группе."
    ),
    2: (
        "В группе людей 1–4 активных живых участника; пленные отдельно и в лимит не входят."
    ),
    3: (
        "Размер группы монстров соответствует ограничениям вида или объясняется временным "
        "состоянием после боя и исправляется при реорганизации."
    ),
    4: (
        "Все активные участники группы и её пленные после шага находятся в одном секторе."
    ),
    5: (
        "Погибшие/покинувшие Зону/спящие/без сознания/пленные не выбирают новых "
        "самостоятельных действий."
    ),
    6: (
        "Предмет имеет только одного владельца или одно физическое местонахождение."
    ),
    7: (
        "Один и тот же предмет не может одновременно быть продан, находиться в тайнике и "
        "оставаться у прежнего владельца."
    ),
    8: (
        "Деньги/боеприпасы/запасы/прочность не отрицательны; неоплаченный штраф — "
        "отдельный долг."
    ),
    9: (
        "Здоровье/выносливость/состояние предметов/отношения остаются в установленных границах."
    ),
    10: (
        "Аномалия не в стартовом секторе фракции; не разрушается без исправного импортированного "
        "средства."
    ),
    11: (
        "Каждая база: стационарный торговец + 2 охранника, не перемещаются, не входят в лимит "
        "мобильных NPC. (DEFAULT_GUARDS_PER_BASE=4 — расхождение задокументировано; "
        "описание реестра = канон §22 «2», расхождение отметить отдельно.)"
    ),
    12: (
        "Стартовый сектор не далее 1 ребра от границы и не ближе 4 рёбер к другому стартовому."
    ),
    13: (
        "Комфортный сон вне неохраняемого места невозможен; минимум 1 охранник бодрствует "
        "и дееспособен."
    ),
    14: (
        "Недоступный по времени ситуативный торговец не может участвовать в сделке."
    ),
    15: (
        "Труп нельзя одновременно разграбить и считать съеденным; после поедания содержимое "
        "недоступно."
    ),
    16: (
        "Знание — неизменный снимок наблюдения, не обновляется само при изменении мира."
    ),
    17: (
        "Смена отношений фракции только при соответствующем известном ей событии."
    ),
    18: (
        "Каждое событие: час, минута, тип, корректные ссылки на участников/"
        "архивные записи."
    ),
    19: (
        "UI не вызывает команд изменения мира, кроме продвижения времени и управления "
        "сохранениями."
    ),
    20: (
        "В час выброса группы людей не перемещаются; каждая в стационарном укрытии/базе/"
        "торговце либо получает урон открытого пребывания; временное убежище от выброса не "
        "защищает."
    ),
    21: (
        "Находка не дольше срока жизни, одно местонахождение, один владелец содержимого; "
        "после разграбления исчезает."
    ),
    22: (
        "Сведения о выбросе не устаревают до его завершения; после выброса координаты аномалий "
        "и безопасные тропы обрабатываются как устаревшие."
    ),
    23: (
        "Укрытие свободно или занято ОДНОЙ группой монстров. Действующее правило: монстры в "
        "убежище считаются в засаде и ТОЛЬКО засада; иных бонусов укрытия нет."
    ),
    24: (
        "Перекрытая тропа связана ровно с одной блокирующей аномалией; после перемещения "
        "аномалии знание прохода устаревшее, блокировка старой тропы снимается."
    ),
    25: (
        "Знание, полученное любым членом группы, доступно всем её текущим членам для решений "
        "в этом же часу."
    ),
}


# ---------------------------------------------------------------------------
# Регистрация всех 25 инвариантов §22 — ДОСЛОВНЫЕ описания из ТЗ
# ---------------------------------------------------------------------------

# АУДИТ check_fn: для каждого инварианта проверяем, какая _check_* функция покрывает
# его содержание на 100%. Если проверки нет — check_fn=None + честное описание.

# Инвариант #1: NPC ≤1 группа → _check_human_groups (part 1, group_map)
register_invariant(1, "§22.1",
    CANONICAL_DESCRIPTIONS[1],
    check_fn=None,  # через _check_human_groups
    kind="runtime",
    coverage="full")  # group_map check → errors.append

# Инвариант #2: группа 1-4 активных → _check_human_groups (part 2, len > 4)
register_invariant(2, "§22.2",
    CANONICAL_DESCRIPTIONS[2],
    check_fn=None,  # через _check_human_groups
    kind="runtime",
    coverage="full")  # len > 4 check → errors.append

# Инвариант #3: размер группы монстров → ❌ ПРОВЕРКА ОТСУТСТВУЕТ
register_invariant(3, "§22.3",
    CANONICAL_DESCRIPTIONS[3],
    check_fn=None,  # ❌ нет проверки
    kind="runtime",
    coverage="missing")

# Инвариант #4: все активные участники и пленные в одном секторе
# → _check_human_groups (part 3, sector check)
register_invariant(4, "§22.4",
    CANONICAL_DESCRIPTIONS[4],
    check_fn=None,  # через _check_human_groups
    kind="runtime",
    coverage="full")  # sector check → errors.append

# Инвариант #5: спящие/пленные ≠ действия → _check_status_intentions
# ⚠️ Проверяет ТОЛЬКО prisoner, НЕ проверяет sleepers
register_invariant(5, "§22.5",
    CANONICAL_DESCRIPTIONS[5],
    check_fn=None,  # через _check_status_intentions
    kind="runtime",
    coverage="partial")  # только prisoner, не все статусы

# Инвариант #6: один владелец/местонахождение предмета
# → _check_items_and_stats (owner_counts)
register_invariant(6, "§22.6",
    CANONICAL_DESCRIPTIONS[6],
    check_fn=None,  # через _check_items_and_stats
    kind="runtime",
    coverage="full")  # owner_counts check → errors.append

# Инвариант #7: предмет не продан + в тайнике + владелец одновременно
# → ❌ ПРОВЕРКА ОТСУТСТВУЕТ
register_invariant(7, "§22.7",
    CANONICAL_DESCRIPTIONS[7],
    check_fn=None,  # ❌ нет проверки
    kind="runtime",
    coverage="missing")

# Инвариант #8: деньги/боеприпасы/запасы/прочность ≥ 0
# → _check_items_and_stats (health/stamina/money/debt/condition < 0)
register_invariant(8, "§22.8",
    CANONICAL_DESCRIPTIONS[8],
    check_fn=None,  # через _check_items_and_stats
    kind="runtime",
    coverage="full")  # negative check → errors.append

# Инвариант #9: здоровье/выносливость/состояние в границах
# → _check_items_and_stats (только lower bounds)
register_invariant(9, "§22.9",
    CANONICAL_DESCRIPTIONS[9],
    check_fn=None,  # через _check_items_and_stats (только lower bounds)
    kind="runtime",
    coverage="partial")  # НЕ проверяет upper bounds и relations

# Инвариант #10: аномалия не в стартовом секторе
# → _check_anomalies_and_bases (part 1)
register_invariant(10, "§22.10",
    CANONICAL_DESCRIPTIONS[10],
    check_fn=None,  # через _check_anomalies_and_bases
    kind="runtime",
    coverage="full")  # start_ids check → errors.append

# Инвариант #11: база: торговец + охранники
# → _check_anomalies_and_bases (part 2)
register_invariant(11, "§22.11",
    CANONICAL_DESCRIPTIONS[11],
    check_fn=None,  # через _check_anomalies_and_bases
    kind="runtime",
    coverage="full")  # traders + guards check → errors.append

# Инвариант #12: расстояния стартовых секторов
# → ❌ ПРОВЕРКА ОТСУТСТВУЕТ
register_invariant(12, "§22.12",
    CANONICAL_DESCRIPTIONS[12],
    check_fn=None,  # ❌ нет проверки
    kind="runtime",
    coverage="missing")

# Инвариант #13: комфортный сон = охранник/убежище/дежурный
# → _check_comfort_sleep_guard (real check, not stub)
register_invariant(13, "§22.13",
    CANONICAL_DESCRIPTIONS[13],
    check_fn=None,  # через _check_comfort_sleep_guard (real check)
    kind="runtime",
    coverage="full")  # full: comfort sleep without shelter/guard → errors.append

# Инвариант #14: ситуативный торговец ≠ сделка
# → ❌ ПРОВЕРКА ОТСУТСТВУЕТ
register_invariant(14, "§22.14",
    CANONICAL_DESCRIPTIONS[14],
    check_fn=None,  # ❌ нет проверки
    kind="runtime",
    coverage="missing")

# Инвариант #15: труп ≠ looted + eaten одновременно
# → _check_corpses (status check + items check)
register_invariant(15, "§22.15",
    CANONICAL_DESCRIPTIONS[15],
    check_fn=None,  # через _check_corpses
    kind="runtime",
    coverage="full")  # looted/eaten check → errors.append

# Инвариант #16: знание = снимок (неизменность)
# → _check_knowledge_immutability (observed_hour > hour + 24)
register_invariant(16, "§22.16",
    CANONICAL_DESCRIPTIONS[16],
    check_fn=None,  # через _check_knowledge_immutability
    kind="runtime",
    coverage="full")  # future observed_hour → errors.append

# Инвариант #17: отношения = известное событие
# → _check_faction_relation_events (journal + news check)
register_invariant(17, "§22.17",
    CANONICAL_DESCRIPTIONS[17],
    check_fn=None,  # через _check_faction_relation_events
    kind="runtime",
    coverage="full")  # journal/event check → errors.append

# Инвариант #18: корректные ссылки в событиях (hour, type, refs)
# → _check_event_links (только hour check)
register_invariant(18, "§22.18",
    CANONICAL_DESCRIPTIONS[18],
    check_fn=None,  # через _check_event_links (только hour)
    kind="runtime",
    coverage="partial")  # только hour, НЕ type/entity refs

# Инвариант #19: UI не мутирует мир → STATIC
register_invariant(19, "§22.19",
    CANONICAL_DESCRIPTIONS[19],
    check_fn=None,  # static
    kind="static",
    coverage="static")

# Инвариант #20: выброс = только shelter
# → _check_emission_movement (emission active + shelter_ids + emission_exposed)
register_invariant(20, "§22.20",
    CANONICAL_DESCRIPTIONS[20],
    check_fn=None,  # через _check_emission_movement
    kind="runtime",
    coverage="full")  # shelter check → errors.append

# Инвариант #21: находка ≤24ч, одно местонахождение, один владелец
# → _check_finding_expiry (только age check)
register_invariant(21, "§22.21",
    CANONICAL_DESCRIPTIONS[21],
    check_fn=None,  # через _check_finding_expiry (только age)
    kind="runtime",
    coverage="partial")  # только age, НЕ ownership/loc

# Инвариант #22: выброс-знания не стареют
# → _check_emission_knowledge_staleness (только during emission)
register_invariant(22, "§22.22",
    CANONICAL_DESCRIPTIONS[22],
    check_fn=None,  # через _check_emission_knowledge_staleness (только during)
    kind="runtime",
    coverage="partial")  # только during emission, НЕ after

# Инвариант #23: shelter free OR 1 monster group
# → _check_shelter_occupancy (occupied_by ref + sector_id match, race condition fixed)
register_invariant(23, "§22.23",
    CANONICAL_DESCRIPTIONS[23],
    check_fn=None,  # через _check_shelter_occupancy (occupied_by + sector_id)
    kind="runtime",
    coverage="full")  # full: occupied_by + sector_id match enforced

# Инвариант #24: одна аномалия = одна тропа
# → _check_trail_blockages (active anomalies on same trail_id)
register_invariant(24, "§22.24",
    CANONICAL_DESCRIPTIONS[24],
    check_fn=None,  # через _check_trail_blockages
    kind="runtime",
    coverage="full")  # trail anomaly count → errors.append

# Инвариант #25: знания группы — общие
# → _check_group_knowledge (union facts check)
register_invariant(25, "§22.25",
    CANONICAL_DESCRIPTIONS[25],
    check_fn=None,  # через _check_group_knowledge
    kind="runtime",
    coverage="full")  # union_facts vs used_facts → errors.append


# ---------------------------------------------------------------------------
# Wiring: check_fn → actual check functions from modules
# ---------------------------------------------------------------------------

# Import check functions from modules
from zonesim.simulation.invariants.groups import (
    _check_human_groups as _fn_human_groups,
    _check_status_intentions as _fn_status_intentions,
)
from zonesim.simulation.invariants.items import (
    _check_items_and_stats as _fn_items_and_stats,
)
from zonesim.simulation.invariants.knowledge import (
    _check_knowledge_immutability as _fn_knowledge_immutability,
    _check_group_knowledge as _fn_group_knowledge,
)
from zonesim.simulation.invariants.anomalies_bases import (
    _check_anomalies_and_bases as _fn_anomalies_and_bases,
)
from zonesim.simulation.invariants.sleep import (
    _check_comfort_sleep_guard as _fn_comfort_sleep_guard,
)
from zonesim.simulation.invariants.corpses import (
    _check_corpses as _fn_corpses,
    _check_finding_expiry as _fn_finding_expiry,
)
from zonesim.simulation.invariants.relations import (
    _check_faction_relation_events as _fn_faction_relation_events,
)
from zonesim.simulation.invariants.events import (
    _check_event_links as _fn_event_links,
)
from zonesim.simulation.invariants.emission import (
    _check_emission_movement as _fn_emission_movement,
    _check_emission_knowledge_staleness as _fn_emission_knowledge_staleness,
)
from zonesim.simulation.invariants.shelter import (
    _check_shelter_occupancy as _fn_shelter_occupancy,
)
from zonesim.simulation.invariants.trails import (
    _check_trail_blockages as _fn_trail_blockages,
)

# Wire check_fn for all registered invariants
_FN_MAP: dict[int, Any] = {
    1: _fn_human_groups,    # full: groups
    2: _fn_human_groups,    # full: groups
    3: None,                # missing
    4: _fn_human_groups,    # full: groups
    5: _fn_status_intentions,  # full: prisoner check (partial: doesn't check sleepers)
    6: _fn_items_and_stats,  # full
    7: None,                # missing
    8: _fn_items_and_stats,  # full
    9: _fn_items_and_stats,  # partial: only lower bounds
    10: _fn_anomalies_and_bases,  # full
    11: _fn_anomalies_and_bases,  # full
    12: None,               # missing
    13: _fn_comfort_sleep_guard,  # partial: stub
    14: None,               # missing
    15: _fn_corpses,        # full
    16: _fn_knowledge_immutability,  # full
    17: _fn_faction_relation_events,  # full
    18: _fn_event_links,    # partial: only hour check
    20: _fn_emission_movement,  # full
    21: _fn_finding_expiry, # partial: only age check
    22: _fn_emission_knowledge_staleness,  # partial: only during emission
    23: _fn_shelter_occupancy,  # partial: only occupied_by ref
    24: _fn_trail_blockages,  # full
    25: _fn_group_knowledge,  # full
}

for inv_id, fn in _FN_MAP.items():
    info = get_invariant(inv_id)
    info.check_fn = fn  # type: ignore[assignment]

# Export check functions
__all__ = [
    "INVARIANT_REGISTRY",
    "InvariantInfo",
    "CANONICAL_DESCRIPTIONS",
    "register_invariant",
    "get_invariant",
    "all_invariant_ids",
    "runtime_invariant_ids",
    "static_invariant_ids",
    "invariant_kind",
    # check functions
    "_check_human_groups",
    "_check_status_intentions",
    "_check_items_and_stats",
    "_check_anomalies_and_bases",
    "_check_comfort_sleep_guard",
    "_check_corpses",
    "_check_knowledge_immutability",
    "_check_faction_relation_events",
    "_check_event_links",
    "_check_emission_movement",
    "_check_finding_expiry",
    "_check_emission_knowledge_staleness",
    "_check_shelter_occupancy",
    "_check_trail_blockages",
    "_check_group_knowledge",
]

# Set module-level names
import sys as _sys
_mod = _sys.modules[__name__]
_mod._check_human_groups = _fn_human_groups
_mod._check_status_intentions = _fn_status_intentions
_mod._check_items_and_stats = _fn_items_and_stats
_mod._check_anomalies_and_bases = _fn_anomalies_and_bases
_mod._check_comfort_sleep_guard = _fn_comfort_sleep_guard
_mod._check_corpses = _fn_corpses
_mod._check_knowledge_immutability = _fn_knowledge_immutability
_mod._check_faction_relation_events = _fn_faction_relation_events
_mod._check_event_links = _fn_event_links
_mod._check_emission_movement = _fn_emission_movement
_mod._check_finding_expiry = _fn_finding_expiry
_mod._check_emission_knowledge_staleness = _fn_emission_knowledge_staleness
_mod._check_shelter_occupancy = _fn_shelter_occupancy
_mod._check_trail_blockages = _fn_trail_blockages
_mod._check_group_knowledge = _fn_group_knowledge

# Export for other modules
INVARIANT_REGISTRY = _INVARIANT_REGISTRY
