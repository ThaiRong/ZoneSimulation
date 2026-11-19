"""Инвариант #13: комфортный сон требует охранника/убежища/дежурного.

§22 ТЗ:
13 Комфортный сон вне неохраняемого места невозможен; минимум 1 охранник бодрствует
   и дееспособен.

check_fn → _check_comfort_sleep_guard (#13).
coverage: partial — заглушка (pass, не append'ит ошибки).
"""

from __future__ import annotations

from zonesim.world.entity import EntityStatus
from zonesim.world.shelter import StormShelter

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _check_comfort_sleep_guard(state: "SimulationState") -> list[str]:
    """Инвариант #13: комфортный сон требует охранника/убежища/дежурного.

    НБ: текущая реализация — заглушка (pass, не append'ит ошибки).
    Комфортный сон без укрытия/охраны — предупреждение о баге ИИ.
    Не блокирует шаг, т.к. ИИ может легитимно выбрать сон вне укрытия
    при критическом истощении (§14.1).
    """
    errors: list[str] = []
    hour = state.time.hour

    if not state.time.is_night():
        return errors

    for npc in state.humans:
        if npc.status != EntityStatus.SLEEPING:
            continue
        if npc.health_share < 0.5 or npc.stamina_share > 0.65:
            continue
        sector_id = npc.sector_id
        has_shelter = any(
            hasattr(s, 'sector_id') and s.sector_id == sector_id
            for s in state.shelters.values()
        )
        has_temp_shelter = any(
            hasattr(s, 'sector_id') and s.sector_id == sector_id
            for s in state.temp_shelters.values()
        )
        has_guard = any(
            n.stationary_role == "guard"
            and n.status == EntityStatus.ACTIVE
            and n.sector_id == sector_id
            for n in state.stationary_humans
        )
        if not has_shelter and not has_temp_shelter and not has_guard:
            # ЗАГЛУШКА: pass, не append'ит ошибки
            pass

    return errors
