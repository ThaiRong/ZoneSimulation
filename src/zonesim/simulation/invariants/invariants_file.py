"""Фасад инвариантов (§22).

Этот файл — тонкий wrapper: InvariantViolation и assert_world_invariants
определены здесь для обратной совместимости. Все check-функции теперь
размещены в модулях пакета simulation/invariants/.

Модули:
- groups.py: #1, #2, #4, #5
- items.py: #6, #8, #9
- knowledge.py: #16, #25
- anomalies_bases.py: #10, #11
- sleep.py: #13
- corpses.py: #15, #21
- relations.py: #17
- events.py: #18
- emission.py: #20, #22
- shelter.py: #23
- trails.py: #24

ПРОБЕЛЫ (проверок нет): #3, #7, #12, #14.
"""

from __future__ import annotations


class InvariantViolation(Exception):
    """Выбрасывается при обнаружении нарушения инварианта."""
    pass


def assert_world_invariants(state) -> list[str]:
    """
    Проверяет инварианты мира (§22 ТЗ).
    Возвращает список описаний нарушений (пусто — всё ОК).
    """
    errors: list[str] = []

    # Инварианты 1–4: группы людей
    errors.extend(_check_human_groups(state))

    # Инвариант 5: спящие/бессознательные/пленные не выбирают действий
    errors.extend(_check_status_intentions(state))

    # Инварианты 6–9: имущество и статы
    errors.extend(_check_items_and_stats(state))

    # Инвариант 16: знание = снимок (неизменность payload после создания)
    errors.extend(_check_knowledge_immutability(state))

    # Инварианты 10–12: аномалии и базы
    errors.extend(_check_anomalies_and_bases(state))

    # Инвариант 13: комфортный сон требует охранника
    errors.extend(_check_comfort_sleep_guard(state))

    # Инвариант 15: труп — не разграблен и не съеден одновременно
    errors.extend(_check_corpses(state))

    # Инвариант 17: смена отношений фракции требует известного события
    errors.extend(_check_faction_relation_events(state))

    # Инвариант 18: корректные ссылки в событиях
    errors.extend(_check_event_links(state))

    # Инвариант 20: в час выброса люди только в укрытии
    errors.extend(_check_emission_movement(state))

    # Инвариант 21: находки не старше срока
    errors.extend(_check_finding_expiry(state))

    # Инвариант 22: сведения о выбросе не стареют до завершения
    errors.extend(_check_emission_knowledge_staleness(state))

    # Инвариант 23: укрытие либо свободно, либо занято одной группой монстров
    errors.extend(_check_shelter_occupancy(state))

    # Инвариант 24: перекрытая тропа — одна аномалия
    errors.extend(_check_trail_blockages(state))

    # Инвариант 25: знания группы — общие
    errors.extend(_check_group_knowledge(state))

    return errors


# ====================================================================
# Re-export check functions from modular files
# ====================================================================

from zonesim.simulation.invariants.groups import (
    _check_human_groups,
    _check_status_intentions,
)
from zonesim.simulation.invariants.items import _check_items_and_stats
from zonesim.simulation.invariants.knowledge import (
    _check_knowledge_immutability,
    _check_group_knowledge,
)
from zonesim.simulation.invariants.anomalies_bases import _check_anomalies_and_bases
from zonesim.simulation.invariants.sleep import _check_comfort_sleep_guard
from zonesim.simulation.invariants.corpses import (
    _check_corpses,
    _check_finding_expiry,
)
from zonesim.simulation.invariants.relations import _check_faction_relation_events
from zonesim.simulation.invariants.events import _check_event_links
from zonesim.simulation.invariants.emission import (
    _check_emission_movement,
    _check_emission_knowledge_staleness,
)
from zonesim.simulation.invariants.shelter import _check_shelter_occupancy
from zonesim.simulation.invariants.trails import _check_trail_blockages
