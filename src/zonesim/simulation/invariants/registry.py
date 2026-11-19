"""Реестр 25 инвариантов мира §22.

Каждый инвариант зарегистрирован:
- id: int (1–25)
- §ref: str — ссылка на параграф ТЗ
- description: str — краткое описание
- check_fn: callable | None — функция проверки (runtime) или None (static)
- kind: str — "runtime" или "static"

Runtime-инварианты вызываются из assert_world_invariants() каждый час.
Static-инварианты проверяются на уровне архитектуры/импортов.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


# ---------------------------------------------------------------------------
# Регистрация
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class InvariantInfo:
    """Метаданные одного инварианта."""
    id: int
    sec_ref: str  # §ref
    description: str
    check_fn: Callable | None  # None для static-инвариантов
    kind: str  # "runtime" | "static"


_INVARIANT_REGISTRY: list[InvariantInfo] = []


def register_invariant(
    invariant_id: int,
    sec_ref: str,
    description: str,
    check_fn: Callable | None = None,
    kind: str = "runtime",
) -> None:
    """Зарегистрировать инвариант.

    Если check_fn is None — это static/architecture инвариант.
    """
    _INVARIANT_REGISTRY.append(InvariantInfo(
        id=invariant_id,
        sec_ref=sec_ref,
        description=description,
        check_fn=check_fn,
        kind=kind,
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


# ---------------------------------------------------------------------------
# Регистрация всех 25 инвариантов §22
# ---------------------------------------------------------------------------

# runtime
register_invariant(1, "§22.1",
    "Каждый живой мобильный NPC состоит не более чем в одной группе",
    check_fn=None,  # через _check_human_groups
    kind="runtime")

register_invariant(2, "§22.2",
    "В группе людей 1-4 активных + пленные отдельно",
    check_fn=None,
    kind="runtime")

register_invariant(3, "§22.3",
    "Информация о секторе общая для всех членов группы",
    check_fn=None,
    kind="runtime")

register_invariant(4, "§22.4",
    "Все активные члены группы и пленные в одном секторе",
    check_fn=None,
    kind="runtime")

register_invariant(5, "§22.5",
    "Спящие/бессознательные/пленные не выбирают действий",
    check_fn=None,
    kind="runtime")

register_invariant(6, "§22.6",
    "Предмет — один владелец или одно местонахождение",
    check_fn=None,
    kind="runtime")

register_invariant(7, "§22.7",
    "Монстр не состоит в двух группах одновременно",
    check_fn=None,
    kind="runtime")

register_invariant(8, "§22.8",
    "Статы (health, stamina, money, debt, condition) не отрицательные",
    check_fn=None,
    kind="runtime")

register_invariant(9, "§22.9",
    "NPC состоит в группе только если в одном секторе с группой",
    check_fn=None,
    kind="runtime")

register_invariant(10, "§22.10",
    "Аномалия не может появиться в стартовом секторе фракции",
    check_fn=None,
    kind="runtime")

register_invariant(11, "§22.11",
    "Каждая база имеет торговца и >=2 (DEFAULT_GUARDS_PER_BASE) охранников",
    check_fn=None,
    kind="runtime")

register_invariant(12, "§22.12",
    "Статусы аномалий корректны (ACTIVE → статус AnomalyStatus.ACTIVE)",
    check_fn=None,
    kind="runtime")

register_invariant(13, "§22.13",
    "Комфортный сон требует охранника/убежища/дежурного",
    check_fn=None,
    kind="runtime")

register_invariant(14, "§22.14",
    "Охранник базы не состоит в группе как мобильный NPC",
    check_fn=None,
    kind="runtime")

register_invariant(15, "§22.15",
    "Труп не может быть одновременно разграблен и съеден",
    check_fn=None,
    kind="runtime")

register_invariant(16, "§22.16",
    "Знание = снимок (неизменность payload после создания)",
    check_fn=None,
    kind="runtime")

register_invariant(17, "§22.17",
    "Смена отношений фракции требует известного события в новостях",
    check_fn=None,
    kind="runtime")

register_invariant(18, "§22.18",
    "Корректные ссылки в событиях (valid hour, valid entity refs)",
    check_fn=None,
    kind="runtime")

# static
register_invariant(19, "§22.19",
    "UI-модули не импортируют и не мутируют мир (архитектурный)",
    check_fn=None,
    kind="static")

# runtime
register_invariant(20, "§22.20",
    "В час выброса люди только в укрытии (или получают урон)",
    check_fn=None,
    kind="runtime")

register_invariant(21, "§22.21",
    "Находки (трупы status=available) не старше 24 часов",
    check_fn=None,
    kind="runtime")

register_invariant(22, "§22.22",
    "Сведения о выбросе не стареют до его завершения",
    check_fn=None,
    kind="runtime")

register_invariant(23, "§22.23",
    "Укрытие либо свободно, либо занято одной группой монстров",
    check_fn=None,
    kind="runtime")

register_invariant(24, "§22.24",
    "Одна аномалия = одна тропа (тропа не перекрыта >1 аномалией)",
    check_fn=None,
    kind="runtime")

register_invariant(25, "§22.25",
    "Знания группы — общие (объединение знаний всех членов)",
    check_fn=None,
    kind="runtime")


# ---------------------------------------------------------------------------
# Экспорт
# ---------------------------------------------------------------------------

INVARIANT_REGISTRY = _INVARIANT_REGISTRY

__all__ = [
    "INVARIANT_REGISTRY",
    "InvariantInfo",
    "register_invariant",
    "get_invariant",
    "all_invariant_ids",
    "runtime_invariant_ids",
    "static_invariant_ids",
    "invariant_kind",
]
