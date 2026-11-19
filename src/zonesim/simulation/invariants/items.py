"""Инварианты #6, #8, #9: имущество и статы.

§22 ТЗ:
6  Предмет имеет только одного владельца или одно физическое местонахождение.
8  Деньги/боеприпасы/запасы/прочность не отрицательны; неоплаченный штраф — отдельный долг.
9  Здоровье/выносливость/состояние предметов/отношения остаются в установленных границах.

check_fn → _check_items_and_stats (#6, #8, #9 частично).
coverage: full для #6 и #8, partial для #9 (только lower bounds).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _check_items_and_stats(state: "SimulationState") -> list[str]:
    """Инварианты #6, #8, #9: имущество и статы.

    #6  — один владелец/местонахождение предмета (owner_counts).
    #8  — статы не отрицательные (health, stamina, money, debt, condition).
    #9  — health/stamina/condition в границах (только lower bounds, NOT upper bounds).
    """
    errors: list[str] = []
    hour = state.time.hour

    # Инвариант 6: предмет — один владелец или одно местонахождение
    owner_counts: dict[int, int] = {}
    for npc in state.humans:
        for item_id in npc.inventory:
            owner_counts[item_id] = owner_counts.get(item_id, 0) + 1

    for item_id, count in owner_counts.items():
        if count > 1:
            errors.append(
                f"Инвариант #6 (ч. {hour}): предмет {item_id} "
                f"у {count} владельцев"
            )

    # Инвариант 8: статы не отрицательные
    for npc in state.humans:
        if npc.health < 0:
            errors.append(f"Инвариант #8 (ч. {hour}): NPC {npc.id} health < 0")
        if npc.stamina < 0:
            errors.append(f"Инвариант #8 (ч. {hour}): NPC {npc.id} stamina < 0")
        if npc.money < 0:
            errors.append(f"Инвариант #8 (ч. {hour}): NPC {npc.id} money < 0")
        if npc.debt < 0:
            errors.append(f"Инвариант #8 (ч. {hour}): NPC {npc.id} debt < 0")

    for monster in state.monsters:
        if monster.health < 0:
            errors.append(f"Инвариант #8 (ч. {hour}): монстр {monster.id} health < 0")

    for item in state.items.values():
        if hasattr(item, 'condition') and item.condition is not None:
            if item.condition < 0:
                errors.append(
                    f"Инвариант #8 (ч. {hour}): предмет {item.id} condition < 0"
                )

    # NOTE: #9 (upper bounds) НЕ проверяется — это partial coverage.
    # Полная реализация #9 потребовала бы проверки max health/stamina/etc.

    return errors
