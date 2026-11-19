"""Пакет реестра инвариантов §22."""

# Export from registry (main source of truth)
from zonesim.simulation.invariants.registry import (
    INVARIANT_REGISTRY,
    CANONICAL_DESCRIPTIONS,
    invariant_id,
    invariant_kind,
    register_invariant,
    get_invariant,
    all_invariant_ids,
    runtime_invariant_ids,
    static_invariant_ids,
)

# Re-export check functions from registry for backward compatibility
# (they are now imported from the modular files)
from zonesim.simulation.invariants.registry import (
    _check_human_groups,
    _check_status_intentions,
    _check_items_and_stats,
    _check_anomalies_and_bases,
    _check_comfort_sleep_guard,
    _check_corpses,
    _check_knowledge_immutability,
    _check_faction_relation_events,
    _check_event_links,
    _check_emission_movement,
    _check_finding_expiry,
    _check_emission_knowledge_staleness,
    _check_shelter_occupancy,
    _check_trail_blockages,
    _check_group_knowledge,
)

# InvariantViolation — keep in invariants_file.py for backward compat
from zonesim.simulation.invariants.invariants_file import (
    InvariantViolation,
    assert_world_invariants,
)

__all__ = [
    # Core
    "InvariantViolation",
    "assert_world_invariants",
    "INVARIANT_REGISTRY",
    "CANONICAL_DESCRIPTIONS",
    "invariant_id",
    "invariant_kind",
    "register_invariant",
    "get_invariant",
    "all_invariant_ids",
    "runtime_invariant_ids",
    "static_invariant_ids",
    # Check functions (backward compatibility)
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
