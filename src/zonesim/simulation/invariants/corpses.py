"""Инварианты #15, #21: трупы и находки.

§22 ТЗ:
15 Труп нельзя одновременно разграбить и считать съеденным; после поедания содержимое недоступно.
21 Находка не дольше срока жизни, одно местонахождение, один владелец содержимого;
   после разграбления исчезает.

check_fn → _check_corpses (#15) и _check_finding_expiry (#21 частично).
coverage: full для #15, partial для #21 (только age check).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState


def _check_corpses(state: "SimulationState") -> list[str]:
    """Инвариант #15: труп не разграблен и не съеден одновременно."""
    errors: list[str] = []
    hour = state.time.hour

    for corpse in state.corpses:
        if corpse.status == "available" and getattr(corpse, "looted", False):
            errors.append(
                f"Инвариант #15 (ч. {hour}): труп {corpse.id} available + looted"
            )
        elif corpse.status in ("eaten", "looted") and getattr(corpse, "items", None):
            errors.append(
                f"Инвариант #15 (ч. {hour}): труп {corpse.id} {corpse.status} + items"
            )

    return errors


def _check_finding_expiry(state: "SimulationState") -> list[str]:
    """Инвариант #21: находки не старше 24 часов.

    НБ: проверяет только age >= 24. НЕ проверяет:
    - одно местонахождение
    - один владелец содержимого
    - исчезновение после разграбления
    """
    errors: list[str] = []
    hour = state.time.hour

    for corpse in state.corpses:
        if corpse.status == "available":
            age = hour - getattr(corpse, 'created_hour', 0)
            if age >= 24:
                errors.append(
                    f"Инвариант #21 (ч. {hour}): находка {corpse.id} старше 24 часов"
                )

    return errors
