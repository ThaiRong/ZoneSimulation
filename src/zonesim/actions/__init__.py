"""Действия: обнаружение, перемещение, исследование, выслеживание."""

from __future__ import annotations

from zonesim.actions.stalk import (
    StalkResult,
    calculate_stalk_check,
    calculate_stalking_check,
    create_stalk_knowledge,
)
from zonesim.actions.detection import (
    calculate_ambush_chance,
    calculate_detection_check,
    calculate_stalking_check,
    check_anomaly_detection,
    create_ambush_action,
)
from zonesim.actions.movement import (
    calculate_move_target,
    check_border_exit,
    get_move_distance,
    move_entity,
    move_group,
)
from zonesim.actions.research import (
    add_knowledge_to_npc,
    get_research_cost,
    research_anomaly,
    research_sector,
)

__all__ = [
    "StalkResult",
    "calculate_stalk_check",
    "calculate_stalking_check",
    "create_stalk_knowledge",
    "calculate_ambush_chance",
    "calculate_detection_check",
    "check_anomaly_detection",
    "create_ambush_action",
    "calculate_move_target",
    "check_border_exit",
    "get_move_distance",
    "move_entity",
    "move_group",
    "add_knowledge_to_npc",
    "get_research_cost",
    "research_anomaly",
    "research_sector",
]
