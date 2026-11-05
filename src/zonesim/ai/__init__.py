"""AI: выбор намерений и маршрутизация NPC."""

from zonesim.ai.intentions import (
    ALL_ACTIONS,
    CAPTURE,
    DESTROY,
    EXIT,
    EXPLORE,
    FACTION_FLAVOR,
    RESEARCH,
    REST,
    SLEEP,
    IntentionContext,
    choose_explore_target,
    choose_intention,
    evaluate_actions,
    known_anomaly_sectors,
    next_step_towards,
)

__all__ = [
    "ALL_ACTIONS",
    "CAPTURE",
    "DESTROY",
    "EXIT",
    "EXPLORE",
    "FACTION_FLAVOR",
    "RESEARCH",
    "REST",
    "SLEEP",
    "IntentionContext",
    "choose_explore_target",
    "choose_intention",
    "evaluate_actions",
    "known_anomaly_sectors",
    "next_step_towards",
]
