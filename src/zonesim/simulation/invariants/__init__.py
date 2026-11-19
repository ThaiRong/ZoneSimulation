"""Пакет реестра инвариантов §22."""

# Экспорт из invariants_file.py (сохраняем обратную совместимость)
# Используем абсолютный импорт чтобы избежать circular import
from zonesim.simulation.invariants.invariants_file import (
    InvariantViolation,
    assert_world_invariants,
    _check_human_groups,
    _check_status_intentions,
    _check_items_and_stats,
    _check_knowledge_immutability,
    _check_anomalies_and_bases,
    _check_comfort_sleep_guard,
    _check_corpses,
    _check_faction_relation_events,
    _check_event_links,
    _check_emission_movement,
    _check_finding_expiry,
    _check_emission_knowledge_staleness,
    _check_shelter_occupancy,
    _check_trail_blockages,
    _check_group_knowledge,
)

from zonesim.simulation.invariants.registry import (
    INVARIANT_REGISTRY,
    invariant_id,
    invariant_kind,
    register_invariant,
    get_invariant,
    all_invariant_ids,
    runtime_invariant_ids,
    static_invariant_ids,
)

__all__ = [
    "InvariantViolation",
    "assert_world_invariants",
    # check functions (экспорт для обратной совместимости)
    "_check_human_groups",
    "_check_status_intentions",
    "_check_items_and_stats",
    "_check_knowledge_immutability",
    "_check_anomalies_and_bases",
    "_check_comfort_sleep_guard",
    "_check_corpses",
    "_check_faction_relation_events",
    "_check_event_links",
    "_check_emission_movement",
    "_check_finding_expiry",
    "_check_emission_knowledge_staleness",
    "_check_shelter_occupancy",
    "_check_trail_blockages",
    "_check_group_knowledge",
    # registry
    "INVARIANT_REGISTRY",
    "invariant_id",
    "invariant_kind",
    "register_invariant",
    "get_invariant",
    "all_invariant_ids",
    "runtime_invariant_ids",
    "static_invariant_ids",
]
