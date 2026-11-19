"""Инварианты #20, #22: выброс и знания о выбросе.

§22 ТЗ:
20 В час выброса группы людей не перемещаются; каждая в стационарном укрытии/базе/торговце
   либо получает урон открытого пребывания; временное убежище от выброса не защищает.
22 Сведения о выбросе не устаревают до его завершения; после выброса координаты аномалий
   и безопасные тропы обрабатываются как устаревшие.

check_fn → _check_emission_movement (#20) и _check_emission_knowledge_staleness (#22 частично).
"""

from __future__ import annotations

from zonesim.anomalies.core import AnomalyStatus
from zonesim.anomalies.emission import is_emission_active
from zonesim.world.entity import EntityStatus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.engine import SimulationState


def _check_emission_movement(state: "SimulationState") -> list[str]:
    """Инвариант #20: в час выброса люди только в укрытии."""
    errors: list[str] = []
    hour = state.time.hour

    emission_start = getattr(state, "emission_start_hour", -1)
    emission_end = getattr(state, "emission_end_hour", -1)

    if not is_emission_active(emission_start, emission_end, hour):
        return errors

    shelter_ids = {
        s.sector_id for s in getattr(state, "shelters", {}).values()
    } | {
        s.id for s in state.sectors.values() if s.is_faction_start
    } | {
        npc.sector_id for npc in getattr(state, "stationary_humans", [])
        if npc.stationary_role == "trader" and npc.status == EntityStatus.ACTIVE
    }

    for group in state.human_groups.values():
        if not group.members:
            continue
        members = {
            n.id: n for n in state.humans
            if n.id in group.members and n.status not in (EntityStatus.DEAD, EntityStatus.EXILED)
        }
        if not members:
            continue
        group_sector = group.sector_id
        if group_sector in shelter_ids:
            continue
        exposed = getattr(state, "emission_exposed", {})
        if group.id not in exposed:
            errors.append(
                f"Инвариант #20 (ч. {hour}): группа {group.id} в секторе {group_sector} "
                f"во время выброса — не в укрытии и не получила урон (не в emission_exposed)"
            )

    return errors


def _check_emission_knowledge_staleness(state: "SimulationState") -> list[str]:
    """Инвариант #22: сведения о выбросе не стареют до завершения.

    НБ: проверяет только valid_until во время выброса. НЕ проверяет:
    - после выброса — координаты аномалий помечаются устаревшими
    - safe_path устаревание
    """
    errors: list[str] = []
    hour = state.time.hour
    emission_start = getattr(state, "emission_start_hour", -1)
    emission_end = getattr(state, "emission_end_hour", -1)

    # 1. Во время выброса — знания о выбросе не стареют
    if emission_start >= 0 and hour >= emission_start and hour < emission_end:
        for npc_id, kb in state.knowledge_bases.items():
            for fact in kb.facts:
                if fact.fact_type.value == "event" and fact.payload.get("type") == "emission":
                    valid_until = fact.valid_until
                    if valid_until is not None and valid_until <= hour:
                        errors.append(
                            f"Инвариант #22 (ч. {hour}): NPC {npc_id} — "
                            f"знание о выбросе истекло (valid_until={valid_until}) "
                            f"во время действия выброса (до {emission_end})"
                        )

    # 2. После выброса — знания о координатах аномалий помечаются устаревшими
    if emission_end > 0 and hour >= emission_end:
        for npc_id, kb in state.knowledge_bases.items():
            for fact in kb.facts:
                if fact.fact_type.value == "anomaly":
                    if not fact.valid_until or fact.valid_until > hour:
                        pass  # будет помечено при обновлении знаний

    # 3. Безопасные тропы: после выброса устаревают
    if emission_end > 0 and hour >= emission_end:
        for npc_id, kb in state.knowledge_bases.items():
            for fact in kb.facts:
                if fact.fact_type.value == "safe_path":
                    if not fact.valid_until or fact.valid_until > hour:
                        pass

    return errors
