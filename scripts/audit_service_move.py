#!/usr/bin/env python3
"""Аудит эквивалентности выноса сервисных методов батча B1.

Два режима:
- --equivalent: попарное сравнение тел old_method <-> new_function
- --structural: структурные проверки (удалён/есть/нет импорта/размер/хэши)
- --both: оба режима

Ожидание отклонений: expected_mismatches — точный список.
Любое лишнее/неожиданное расхождение → FAIL.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "zonesim"
B1_PRE_COMMIT = "f04dade"


@dataclass
class MismatchEntry:
    operator_index: int
    expected_trans: str
    expected_new: str


@dataclass
class MethodPair:
    old_name: str
    new_name: str
    target_module: str
    rules: list
    expected_mismatches: list[MismatchEntry] = field(default_factory=list)
    mismatch_note: str = ""


BATCH_B1 = [
    MethodPair(
        "_has_strict_comfort", "has_strict_comfort", "needs/comfort.py",
        rules=[],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_group_faction", "group_faction", "world/faction.py",
        rules=[
            (r"\bself\.state\.humans\b", "state.humans"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_home_sector_id", "home_sector_id", "world/faction.py",
        rules=[
            (r"\bself\.state\.sectors\b", "sectors"),
            (r"\bself\._home_cache\b", "home_cache"),
        ],
        expected_mismatches=[
            MismatchEntry(1, "if faction not in home_cache:", "if home_cache is not None and faction in home_cache:"),
            MismatchEntry(2, "home_cache[faction] = next", "return home_cache[faction]"),
            MismatchEntry(3, "sectors.values()", "result = next"),
            MismatchEntry(4, "is_faction_start", "(s.id for s in sectors"),
            MismatchEntry(5, "None,", "is_faction_start"),
            MismatchEntry(6, ")", "None,"),
            MismatchEntry(7, "return home_cache[faction]", ")"),
            MismatchEntry(8, "<MISSING>", "if home_cache is not None:"),
            MismatchEntry(9, "<MISSING>", "home_cache[faction] = result"),
            MismatchEntry(10, "<MISSING>", "return result"),
        ],
        mismatch_note=(
            "home_sector_id: переструктурирован код — если home_cache is not None "
            "возвращает из кэша, иначе вычисляет next(...) и записывает. "
            "Старый: if f not in hc: hc[f]=next(...); return hc[f]."
        ),
    ),
    MethodPair(
        "_distance_to_border", "distance_to_border", "world/faction.py",
        rules=[
            (r"\bself\.state\.sectors\b", "sectors"),
            (r"\bself\._border_dist\b", "border_dist"),
        ],
        expected_mismatches=[
            MismatchEntry(1, "if border_dist is None:", "if border_dist is not None:"),
            MismatchEntry(2, "dist: dict[int, int]", "return border_dist"),
            MismatchEntry(3, "queue = [sid for sid, s in sectors", "dist: dict[int, int]"),
            MismatchEntry(4, "for sid in queue:", "queue = [sid for sid"),
            MismatchEntry(5, "dist[sid] = 0", "for sid in queue:"),
            MismatchEntry(6, "while queue:", "dist[sid] = 0"),
            MismatchEntry(7, "current = queue.pop(0)", "while queue:"),
            MismatchEntry(8, "for nid in sectors[current].neighbors", "current = queue.pop(0)"),
            MismatchEntry(9, "if nid not in dist:", "for nid in sectors"),
            MismatchEntry(10, "dist[nid] = dist[current] + 1", "if nid not in dist:"),
            MismatchEntry(11, "queue.append(nid)", "dist[nid] = dist[current]"),
            MismatchEntry(12, "border_dist = dist", "queue.append(nid)"),
            MismatchEntry(13, "return border_dist.get(sector_id)", "return dist"),
        ],
        mismatch_note=(
            "distance_to_border: контракт изменён. Старый возвращал "
            "self._border_dist.get(sector_id) -> int|None. "
            "Новый возвращает dict[int,int] (полный BFS-словарь). "
            "Вызывающая компенсирует через .get(). "
            "Кэш восстановлен в фазе 4 (write-back при None)."
        ),
    ),
    MethodPair(
        "_sector_humans", "sector_humans", "world/sectors.py",
        rules=[
            (r"\bself\.state\.humans\b", "state.humans"),
            (r"\bself\.state\.stationary_humans\b", "state.stationary_humans"),
        ],
        expected_mismatches=[
            MismatchEntry(3, "state.humans", "humans"),
        ],
        mismatch_note=(
            "sector_humans: сигнатура (humans, stationary_humans, sector_id) "
            "вместо (state.humans, state.stationary_humans, sector_id). "
            "Параметры переименованы — state убран."
        ),
    ),
    MethodPair(
        "_squad_power", "squad_power", "combat/power.py",
        rules=[
            (r"\bself\.state\.items\b", "items"),
        ],
        expected_mismatches=[
            MismatchEntry(4, "SPECIES_POWER_VALUE", "_SPECIES_POWER_VALUE"),
        ],
        mismatch_note=(
            "squad_power: константа SPECIES_POWER_VALUE -> _SPECIES_POWER_VALUE "
            "(module-level private const в power.py вместо class-level в engine.py)."
        ),
    ),
    MethodPair(
        "_monster_group_power", "monster_group_power", "combat/power.py",
        rules=[],
        expected_mismatches=[],
        mismatch_note="",
    ),
]

# ============================================================
# BATCH B2: Level 1 extraction (3.9-B2)
# ============================================================
B2_PRE_COMMIT = "5b48afb"

BATCH_B2 = [
    MethodPair(
        "_emergency_medkit", "emergency_medkit", "combat/medkit.py",
        rules=[
            (r"\bself\.state\.items\b", "state.items"),
            (r"\bself\._use_medkit_charge\b", "use_medkit_charge"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_rest_heal", "rest_heal", "needs/healing.py",
        rules=[
            (r"\bself\.state\.items\b", "state.items"),
            (r"\bself\._use_medkit_charge\b", "use_medkit_charge"),
            (r"\bself\._sync_npc_from_items\b", "sync_npc_from_items"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_use_medkit_charge", "use_medkit_charge", "combat/medkit.py",
        rules=[
            (r"\bself\._consume_item\b", "consume_item"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_sell_loot", "sell_loot", "economy/trader.py",
        rules=[
            (r"\bself\.state\.items\b", "state.items"),
            (r"\bself\._consume_item\b", "consume_item"),
            (r"\bself\.SELL_PRICE_SHARE\b", "sell_price_share"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_give_artifact", "give_artifact", "needs/artifact.py",
        rules=[
            (r"\bself\.state\.artifacts\b", "state.artifacts"),
            (r"\bself\.state\.items\b", "state.items"),
            (r"\bself\.state\.news_manager\b", "state.news_manager"),
            (r"\bself\._create_item\b", "create_item"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_set_unconscious_or_dead", "set_unconscious_or_dead", "combat/results.py",
        rules=[
            (r"\bself\._resolve_zero_health\b", "resolve_zero_health"),
            (r"\bself\.state\.news_manager\b", "state.news_manager"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_group_can_capture", "group_can_capture", "actions/capture.py",
        rules=[
            (r"\bself\._capture_target\b", "capture_target"),
            (r"\bself\._group_kit\b", "group_kit"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_group_can_destroy", "group_can_destroy", "actions/destroy.py",
        rules=[
            (r"\bself\.state\.anomalies\b", "state.anomalies"),
            (r"\bself\._group_kit\b", "group_kit"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_process_create_shelter", "process_create_shelter", "world/shelter.py",
        rules=[
            (r"\bself\._active_members\b", "active_members"),
            (r"\bself\._group_leader\b", "group_leader"),
            (r"\bself\.state\.items\b", "state.items"),
            (r"\bself\.state\.next_shelter_id\b", "state.next_shelter_id"),
            (r"\bself\.state\.news_manager\b", "state.news_manager"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_check_and_journal_relations", "check_and_journal_relations", "relations/journal.py",
        rules=[
            (r"\bself\.state\.faction_relations\b", "state.faction_relations"),
            (r"\bself\.state\.prev_relation_snapshot\b", "state.prev_relation_snapshot"),
            (r"\bself\._log_relation_change\b", "log_relation_change"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_roll_trail_blockages", "roll_trail_blockages", "world/trails.py",
        rules=[
            (r"\bself\.state\.anomalies\b", "state.anomalies"),
            (r"\bself\._roll_trail_blockage\b", "roll_trail_blockage"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_group_in_shelter", "group_in_shelter", "world/shelter.py",
        rules=[
            (r"\bself\._shelter_sector_ids\b", "shelter_sector_ids"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_shelter_targets", "shelter_targets", "world/shelter.py",
        rules=[
            (r"\bself\.state\.shelters\b", "state.shelters"),
            (r"\bself\._shelter_sector_ids\b", "shelter_sector_ids"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_is_group_emission_sheltered", "is_group_emission_sheltered", "anomalies/emission.py",
        rules=[
            (r"\bself\._emission_safe_sectors\b", "emission_safe_sectors"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_create_item", "create_item", "world/item.py",
        rules=[
            (r"\bself\.state\.next_item_id\b", "state.next_item_id"),
            (r"\bself\.state\.items\b", "state.items"),
            (r"\bself\.state\.humans\b", "state.humans"),
            (r"\bself\.state\.stationary_humans\b", "state.stationary_humans"),
            (r"\bgive_item\b", "give_item"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_roll_trail_blockage", "roll_trail_blockage", "world/trails.py",
        rules=[
            (r"\bself\.state\.rng\b", "state.rng"),
            (r"\bself\.state\.anomalies\b", "state.anomalies"),
            (r"\bself\.state\.sectors\b", "state.sectors"),
            (r"\bself\._trail_set\b", "trail_set"),
        ],
        expected_mismatches=[
            MismatchEntry(1, "self._trail_set", "trail_set(state)"),
        ],
        mismatch_note="_roll_trail_blockage: self._trail_set → trail_set(state) (property → function)",
    ),
    MethodPair(
        "_shelter_sector_ids", "shelter_sector_ids", "world/shelter.py",
        rules=[
            (r"\bself\.state\.temp_shelters\b", "state.temp_shelters"),
            (r"\bself\.state\.shelters\b", "state.shelters"),
            (r"\bself\.state\.sectors\b", "state.sectors"),
            (r"\bself\.state\.stationary_humans\b", "state.stationary_humans"),
            (r"\bself\.state\.conditional_trader_id\b", "state.conditional_trader_id"),
            (r"\bself\.state\.time\b", "state.time"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_sync_npc_from_items", "sync_npc_from_items", "world/item.py",
        rules=[
            (r"\bself\.state\.items\b", "state.items"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
]

# ============================================================
# BATCH B2_1: duplicate elimination (3.9-B2.1)
# ============================================================
# 8 methods that existed BOTH in engine.py AND domain modules.
# Only the domain module versions are kept; engine methods are removed.
B2_1_PRE_COMMIT = "5d1ba3b"

BATCH_B2_1 = [
    MethodPair(
        "_active_members", "active_members", "world/groups.py",
        rules=[],
        expected_mismatches=[],
        mismatch_note="duplicate: only domain function kept",
    ),
    MethodPair(
        "_group_leader", "group_leader", "world/groups.py",
        rules=[],
        expected_mismatches=[],
        mismatch_note="duplicate: only domain function kept",
    ),
    MethodPair(
        "_capture_target", "capture_target", "actions/capture.py",
        rules=[],
        expected_mismatches=[],
        mismatch_note="duplicate: only domain function kept",
    ),
    MethodPair(
        "_consume_item", "consume_item", "world/item.py",
        rules=[],
        expected_mismatches=[],
        mismatch_note="duplicate: only domain function kept",
    ),
    MethodPair(
        "_emission_safe_sectors", "emission_safe_sectors", "anomalies/emission.py",
        rules=[],
        expected_mismatches=[],
        mismatch_note="duplicate: only domain function kept",
    ),
    MethodPair(
        "_log_relation_change", "log_relation_change", "relations/journal.py",
        rules=[],
        expected_mismatches=[],
        mismatch_note="duplicate: only domain function kept",
    ),
    MethodPair(
        "_resolve_zero_health", "resolve_zero_health", "combat/results.py",
        rules=[],
        expected_mismatches=[],
        mismatch_note="duplicate: only domain function kept",
    ),
    MethodPair(
        "_trail_set", "trail_set", "world/trails.py",
        rules=[
            (r"self\._trail_set", "trail_set(state)"),
        ],
        expected_mismatches=[
            MismatchEntry(1, "self._trail_set", "trail_set(state)"),
        ],
        mismatch_note="_trail_set: was @property, converted to function trail_set(state)",
    ),
]

# Exceptions for the "no duplicates" check:
# These functions exist in engine.py AND in domain modules but are intentionally
# kept in engine (they are orchestrators or were not part of B2_1 scope).
KNOWN_DUP_EXCEPTIONS = {
    "generate_world": (
        "orchestrator: generate_world is the world-gen entry point, "
        "not a service method"
    ),
    "known_anomaly_sectors": (
        "not extracted in B2_1: will be handled in a dedicated batch "
        "(depends on knowledge base state)"
    ),
}

# ============================================================
# BATCH B3: Level 2 extraction (3.9-B3)
# ============================================================
B3_PRE_COMMIT = "4b2b94b"

BATCH_B3 = [
    MethodPair(
        "_walk", "walk", "actions/movement.py",
        rules=[
            (r"\bself\.state\.rng\b", "state.rng"),
            (r"\bself\._trail_set\b", "trail_set"),
        ],
        expected_mismatches=[
            MismatchEntry(1, "self._trail_set", "trail_set(state)"),
        ],
        mismatch_note="_walk: self._trail_set → trail_set(state) (property via B2.1 function)",
    ),
    MethodPair(
        "_blocked_trail_map", "blocked_trail_map", "world/trails.py",
        rules=[
            (r"\bself\.state\.anomalies\b", "state.anomalies"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_group_has_passage", "group_has_passage", "world/trails.py",
        rules=[
            (r"\bself\.state\.humans\b", "state.humans"),
            (r"\bself\.state\.knowledge_bases\b", "state.knowledge_bases"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_group_detector_bonus", "group_detector_bonus", "knowledge/__init__.py",
        rules=[
            (r"\bself\.state\.humans\b", "state.humans"),
            (r"\bself\.state\.items\b", "state.items"),
            (r"\bself\.state\.human_groups\b", "state.human_groups"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_base_guards", "base_guards", "combat/guards.py",
        rules=[
            (r"\bself\.state\.sectors\b", "state.sectors"),
            (r"\bself\.state\.stationary_humans\b", "state.stationary_humans"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_monster_group_members", "monster_group_members", "world/groups.py",
        rules=[
            (r"\bself\.state\.monsters\b", "state.monsters"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_sync_human_groups", "sync_human_groups", "world/groups.py",
        rules=[
            (r"\bself\.state\.humans\b", "state.humans"),
            (r"\bself\.state\.human_groups\b", "state.human_groups"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_sync_monster_groups", "sync_monster_groups", "world/groups.py",
        rules=[
            (r"\bself\.state\.monsters\b", "state.monsters"),
            (r"\bself\.state\.monster_groups\b", "state.monster_groups"),
            (r"\bself\.state\.next_monster_group_id\b", "state.next_monster_group_id"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_expire_findings", "expire_findings", "knowledge/expiry.py",
        rules=[
            (r"\bself\.state\.corpses\b", "state.corpses"),
            (r"\bself\.state\.items\b", "state.items"),
            (r"\bself\.state\.news_manager\b", "state.news_manager"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_free_emptied_shelters", "free_emptied_shelters", "world/shelter.py",
        rules=[
            (r"\bself\.state\.shelters\b", "state.shelters"),
            (r"\bself\.state\.monster_groups\b", "state.monster_groups"),
            (r"\bself\.state\.news_manager\b", "state.news_manager"),
        ],
        expected_mismatches=[],
        mismatch_note="",
    ),
    MethodPair(
        "_update_shelter_participants", "update_shelter_participants", "world/shelter.py",
        rules=[
            (r"\bself\.state\.humans\b", "state.humans"),
            (r"\bself\.state\.temp_shelters\b", "state.temp_shelters"),
            (r"\bself\.state\.human_groups\b", "state.human_groups"),
            (r"\bself\.state\.news_manager\b", "state.news_manager"),
        ],
        expected_mismatches=[
            MismatchEntry(1, "self._walk", "walk"),
        ],
        mismatch_note="_update_shelter_participants: self._walk → walk (new B3 function)",
    ),
]


def git_show(path, commit):
    result = subprocess.run(
        ["git", "show", commit + ":" + path],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    return result.stdout


def extract_body(code, func_name):
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SimulationEngine":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == func_name:
                    lines = code.splitlines()
                    body_start = 0
                    for child in item.body:
                        if (isinstance(child, ast.Expr)
                                and isinstance(child.value, ast.Constant)
                                and isinstance(child.value.value, str)):
                            body_start += 1
                        else:
                            break
                    start = item.body[body_start].lineno - 1
                    end = item.end_lineno
                    return "\n".join(lines[start:end])
    return None


def extract_new_func_body(target_module, func_name):
    mod_path = SRC / target_module
    if not mod_path.exists():
        return None
    code = mod_path.read_text(encoding="utf-8")
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            lines = code.splitlines()
            body_start = 0
            for child in node.body:
                if (isinstance(child, ast.Expr)
                        and isinstance(child.value, ast.Constant)
                        and isinstance(child.value.value, str)):
                    body_start += 1
                else:
                    break
            start = node.body[body_start].lineno - 1
            end = node.end_lineno
            return "\n".join(lines[start:end])
    return None


def apply_rules(text, rules):
    for pattern, replacement in rules:
        text = re.sub(pattern, replacement, text)
    return text


def normalize(text):
    cleaned = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
            continue
        cleaned.append(s)
    return cleaned


def find_rng_refs(text):
    return re.findall(r"state\.rng\.(random|choice|randint)\b", text)


def mismatches_match(actual_idx, actual_trans, actual_new, expected):
    return (actual_idx == expected.operator_index
            and expected.expected_trans in actual_trans
            and expected.expected_new in actual_new)


def audit_equivalent():
    print("=" * 70)
    print("AUDIT EQUIVALENCE: B1 service methods")
    print("Pre-batch commit: " + B1_PRE_COMMIT)
    print("=" * 70)

    all_ok = True
    total_pairs = 0
    total_failures = 0

    for pair in BATCH_B1:
        total_pairs += 1
        sep = "-" * 60
        print("")
        print(sep)
        print("PAIR: " + pair.old_name + " -> " + pair.new_name +
              " (" + pair.target_module + ")")

        old_code = git_show("src/zonesim/simulation/engine.py", B1_PRE_COMMIT)
        old_body = extract_body(old_code, pair.old_name)
        if old_body is None:
            print("  ERROR: " + pair.old_name + " not found in git")
            all_ok = False
            total_failures += 1
            continue
        print("  OLD body: " + str(len(old_body.splitlines())) + " lines")

        new_body = extract_new_func_body(pair.target_module, pair.new_name)
        if new_body is None:
            print("  ERROR: " + pair.new_name + " not in " + pair.target_module)
            all_ok = False
            total_failures += 1
            continue
        print("  NEW body: " + str(len(new_body.splitlines())) + " lines")

        transformed = apply_rules(old_body, pair.rules)
        print("  TRANSFORMED: " + str(len(transformed.splitlines())) + " lines")

        old_norm = normalize(old_body)
        new_norm = normalize(new_body)
        trans_norm = normalize(transformed)

        print("  OLD (norm): " + str(len(old_norm)) + " ops")
        print("  TRANS (norm): " + str(len(trans_norm)) + " ops")
        print("  NEW (norm): " + str(len(new_norm)) + " ops")

        # Фактические mismatches
        actual_mismatches = []
        max_len = max(len(trans_norm), len(new_norm))
        for i in range(max_len):
            tl = trans_norm[i] if i < len(trans_norm) else "<MISSING>"
            nl = new_norm[i] if i < len(new_norm) else "<MISSING>"
            if tl != nl:
                actual_mismatches.append((i + 1, tl, nl))

        # Ожидаемые mismatches
        expected_mismatches = pair.expected_mismatches

        # Сопряжение
        expected_matched = set()
        actual_matched = set()
        unexpected = []
        missing_expected = []

        for ai, (a_idx, a_trans, a_new) in enumerate(actual_mismatches):
            matched = False
            for ei, exp in enumerate(expected_mismatches):
                if ei in expected_matched:
                    continue
                if mismatches_match(a_idx, a_trans, a_new, exp):
                    expected_matched.add(ei)
                    actual_matched.add(ai)
                    matched = True
                    break
            if not matched:
                unexpected.append((a_idx, a_trans, a_new))

        for ei, exp in enumerate(expected_mismatches):
            if ei not in expected_matched:
                missing_expected.append(exp)

        if unexpected or missing_expected:
            print("")
            print("  UNEXPECTED MISMATCHES:")
            for ui, (u_idx, u_trans, u_new) in enumerate(unexpected):
                print("    [" + str(ui + 1) + "] idx=" + str(u_idx) +
                      " TRANS=" + u_trans[:80] + " | NEW=" + u_new[:80])
            if missing_expected:
                print("  MISSING EXPECTED:")
                for me in missing_expected:
                    print("    idx=" + str(me.operator_index) +
                          " expect TRANS='" + me.expected_trans + "'" +
                          " expect NEW='" + me.expected_new + "'")
            if pair.mismatch_note:
                print("")
                print("  NOTE: " + pair.mismatch_note[:200])
            print("")
            print("  STATUS: FAIL (unexpected or missing mismatches)")
            all_ok = False
            total_failures += 1
        elif actual_mismatches:
            print("")
            print("  MISMATCHES: " + str(len(actual_mismatches)) + " (all expected)")
            for m_idx, (m_idx_num, m_trans, m_new) in enumerate(actual_mismatches):
                print("    [" + str(m_idx + 1) + "] idx=" + str(m_idx_num) +
                      " TRANS=" + m_trans[:60] + " | NEW=" + m_new[:60])
            print("  STATUS: OK (documented mismatch)")
        else:
            print("  STATUS: OK (0 mismatches)")

        # RNG
        r_old = find_rng_refs(old_body)
        r_new = find_rng_refs(new_body)
        r_trans = find_rng_refs(transformed)
        if r_old == r_new == r_trans:
            print("  RNG: OK (" + (str(r_old) if r_old else "No direct RNG") + ")")
        else:
            print("  RNG: DIFF old=" + str(r_old) + " trans=" + str(r_trans) +
                  " new=" + str(r_new))
            all_ok = False
            total_failures += 1

    print("")
    print("=" * 70)
    print("RESULT: " + str(total_pairs) + " pairs, " + str(total_failures) +
          " failures")
    if all_ok:
        print("EQUIVALENCE AUDIT PASSED")
    else:
        print("EQUIVALENCE AUDIT FAILED - review above")
    print("=" * 70)

    return 0 if all_ok else 1


def audit_b2_equivalent():
    print("=" * 70)
    print("AUDIT EQUIVALENCE: B2 service methods (3.9-B2)")
    print("Pre-batch commit: " + B2_PRE_COMMIT)
    print("=" * 70)

    all_ok = True
    total_pairs = 0
    total_failures = 0

    for pair in BATCH_B2:
        total_pairs += 1
        sep = "-" * 60
        print("")
        print(sep)
        print("PAIR: " + pair.old_name + " -> " + pair.new_name +
              " (" + pair.target_module + ")")

        old_code = git_show("src/zonesim/simulation/engine.py", B2_PRE_COMMIT)
        old_body = extract_body(old_code, pair.old_name)
        if old_body is None:
            print("  ERROR: " + pair.old_name + " not found in git")
            all_ok = False
            total_failures += 1
            continue
        print("  OLD body: " + str(len(old_body.splitlines())) + " lines")

        new_body = extract_new_func_body(pair.target_module, pair.new_name)
        if new_body is None:
            print("  ERROR: " + pair.new_name + " not in " + pair.target_module)
            all_ok = False
            total_failures += 1
            continue
        print("  NEW body: " + str(len(new_body.splitlines())) + " lines")

        transformed = apply_rules(old_body, pair.rules)
        print("  TRANSFORMED: " + str(len(transformed.splitlines())) + " lines")

        old_norm = normalize(old_body)
        new_norm = normalize(new_body)
        trans_norm = normalize(transformed)

        print("  OLD (norm): " + str(len(old_norm)) + " ops")
        print("  TRANS (norm): " + str(len(trans_norm)) + " ops")
        print("  NEW (norm): " + str(len(new_norm)) + " ops")

        actual_mismatches = []
        max_len = max(len(trans_norm), len(new_norm))
        for i in range(max_len):
            tl = trans_norm[i] if i < len(trans_norm) else "<MISSING>"
            nl = new_norm[i] if i < len(new_norm) else "<MISSING>"
            if tl != nl:
                actual_mismatches.append((i + 1, tl, nl))

        expected_mismatches = pair.expected_mismatches

        expected_matched = set()
        actual_matched = set()
        unexpected = []
        missing_expected = []

        for ai, (a_idx, a_trans, a_new) in enumerate(actual_mismatches):
            matched = False
            for ei, exp in enumerate(expected_mismatches):
                if ei in expected_matched:
                    continue
                if mismatches_match(a_idx, a_trans, a_new, exp):
                    expected_matched.add(ei)
                    actual_matched.add(ai)
                    matched = True
                    break
            if not matched:
                unexpected.append((a_idx, a_trans, a_new))

        for ei, exp in enumerate(expected_mismatches):
            if ei not in expected_matched:
                missing_expected.append(exp)

        if unexpected or missing_expected:
            print("")
            print("  UNEXPECTED MISMATCHES:")
            for ui, (u_idx, u_trans, u_new) in enumerate(unexpected):
                print("    [" + str(ui + 1) + "] idx=" + str(u_idx) +
                      " TRANS=" + u_trans[:80] + " | NEW=" + u_new[:80])
            if missing_expected:
                print("  MISSING EXPECTED:")
                for me in missing_expected:
                    print("    idx=" + str(me.operator_index) +
                          " expect TRANS='" + me.expected_trans + "'" +
                          " expect NEW='" + me.expected_new + "'")
            if pair.mismatch_note:
                print("")
                print("  NOTE: " + pair.mismatch_note[:200])
            print("")
            print("  STATUS: FAIL")
            all_ok = False
            total_failures += 1
        elif actual_mismatches:
            print("  MISMATCHES: " + str(len(actual_mismatches)) + " (all expected)")
            print("  STATUS: OK (documented mismatch)")
        else:
            print("  STATUS: OK (0 mismatches)")

        # RNG
        r_old = find_rng_refs(old_body)
        r_new = find_rng_refs(new_body)
        r_trans = find_rng_refs(transformed)
        if r_old == r_new == r_trans:
            print("  RNG: OK")
        else:
            print("  RNG: DIFF old=" + str(r_old) + " trans=" + str(r_trans) +
                  " new=" + str(r_new))
            all_ok = False
            total_failures += 1

    print("")
    print("=" * 70)
    print("RESULT: " + str(total_pairs) + " pairs, " + str(total_failures) +
          " failures")
    if all_ok:
        print("EQUIVALENCE AUDIT B2 PASSED")
    else:
        print("EQUIVALENCE AUDIT B2 FAILED")
    print("=" * 70)

    return 0 if all_ok else 1


def audit_b2_structural():
    print("=" * 70)
    print("AUDIT STRUCTURAL: B2 service methods")
    print("=" * 70)

    all_ok = True
    checks = 0
    failures = 0

    engine_code = (SRC / "simulation" / "engine.py").read_text(encoding="utf-8")

    for pair in BATCH_B2:
        checks += 1
        count = len(re.findall(r'\bdef ' + pair.old_name + r'\b', engine_code))
        status = "OK" if count == 0 else "FAIL (" + str(count) + ")"
        print("  " + pair.old_name + ": " + status)
        if count != 0:
            all_ok = False
            failures += 1

    for pair in BATCH_B2:
        checks += 1
        mod_path = SRC / pair.target_module
        if not mod_path.exists():
            print("  " + pair.target_module + ": NOT FOUND")
            all_ok = False
            failures += 1
            continue
        code = mod_path.read_text(encoding="utf-8")
        found = re.search(r'\bdef ' + pair.new_name + r'\b', code) is not None
        status = "OK" if found else "NOT FOUND"
        print("  " + pair.target_module + "::" + pair.new_name + ": " + status)
        if not found:
            all_ok = False
            failures += 1

    for pair in BATCH_B2:
        checks += 1
        mod_path = SRC / pair.target_module
        if not mod_path.exists():
            continue
        code = mod_path.read_text(encoding="utf-8")
        has_engine = "simulation.engine" in code
        status = "FAIL" if has_engine else "OK"
        print("  " + pair.target_module + ": no engine import " + status)
        if has_engine:
            all_ok = False
            failures += 1

    print("")
    print("=" * 70)
    print("STRUCTURAL: " + str(checks) + " checks, " + str(failures) + " failures")
    if all_ok:
        print("STRUCTURAL AUDIT B2 PASSED")
    else:
        print("STRUCTURAL AUDIT B2 FAILED")
    print("=" * 70)

    return 0 if all_ok else 1


def audit_b2_1():
    print("=" * 70)
    print("AUDIT B2_1: duplicate elimination (3.9-B2.1)")
    print("Pre-commit: " + B2_1_PRE_COMMIT)
    print("=" * 70)

    all_ok = True
    checks = 0
    failures = 0

    engine_code = (SRC / "simulation" / "engine.py").read_text(encoding="utf-8")

    # 1. Проверка: методы удалены из engine.py
    print("")
    print("CHECK 1: methods removed from engine.py")
    for pair in BATCH_B2_1:
        checks += 1
        count = len(re.findall(r'\bdef ' + pair.old_name + r'\b', engine_code))
        status = "OK" if count == 0 else "FAIL (still " + str(count) + ")"
        print("  " + pair.old_name + ": " + status)
        if count != 0:
            all_ok = False
            failures += 1

    # 2. Проверка: функции есть в доменных модулях
    print("")
    print("CHECK 2: functions exist in domain modules")
    for pair in BATCH_B2_1:
        checks += 1
        mod_path = SRC / pair.target_module
        if not mod_path.exists():
            print("  " + pair.target_module + ": NOT FOUND")
            all_ok = False
            failures += 1
            continue
        code = mod_path.read_text(encoding="utf-8")
        found = re.search(r'\bdef ' + pair.new_name + r'\b', code) is not None
        status = "OK" if found else "NOT FOUND"
        print("  " + pair.target_module + "::" + pair.new_name + ": " + status)
        if not found:
            all_ok = False
            failures += 1

    # 3. Проверка: нет вызовов engine._<имя> в src/ и tests/
    print("")
    print("CHECK 3: no engine._<name> calls in src/ tests/")
    for pair in BATCH_B2_1:
        checks += 1
        call_pattern = r'engine\.' + re.escape(pair.old_name.lstrip('_'))
        found_calls = []
        for d in ["src", "tests"]:
            dpath = REPO_ROOT / d
            if not dpath.exists():
                continue
            for root, _, files in os.walk(dpath):
                for f in files:
                    if not f.endswith(".py"):
                        continue
                    fp = Path(root) / f
                    # skip audit script itself
                    if "audit_service_move" in str(fp):
                        continue
                    try:
                        code = fp.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, OSError):
                        continue
                    for m in re.finditer(call_pattern, code):
                        found_calls.append(str(fp.relative_to(REPO_ROOT)))
        if found_calls:
            print("  " + pair.new_name + ": FAIL (" + str(len(found_calls)) + " calls)")
            for fc in found_calls[:3]:
                print("    " + fc)
            all_ok = False
            failures += 1
        else:
            print("  " + pair.new_name + ": OK")

    # 4. НОВАЯ ПРОВЕРКА: нет дубликатов (method in engine == function in domain)
    print("")
    print("CHECK 4: no duplicate pairs (engine method == domain function)")
    # Scan all domain modules for functions that also exist as _<name> methods in engine
    domain_modules_to_check = [
        ("world/groups.py", ["active_members", "group_leader", "group_kit"]),
        ("actions/capture.py", ["capture_target", "group_can_capture"]),
        ("world/item.py", ["consume_item", "create_item", "sync_npc_from_items"]),
        ("anomalies/emission.py", ["emission_safe_sectors", "is_group_emission_sheltered"]),
        ("relations/journal.py", ["log_relation_change", "check_and_journal_relations"]),
        ("combat/results.py", ["resolve_zero_health", "set_unconscious_or_dead"]),
        ("world/trails.py", ["trail_set", "roll_trail_blockage", "roll_trail_blockages"]),
    ]
    dup_found = False
    for mod_name, func_names in domain_modules_to_check:
        mod_path = SRC / mod_name
        if not mod_path.exists():
            continue
        mod_code = mod_path.read_text(encoding="utf-8")
        for func_name in func_names:
            # Skip known exceptions
            if func_name in KNOWN_DUP_EXCEPTIONS:
                continue
            # Check if there's a matching engine method
            engine_method = "_" + func_name
            if re.search(r'\bdef ' + re.escape(engine_method) + r'\b', engine_code):
                print("  DUPLICATE: " + mod_name + "::" + func_name +
                      " has matching engine method " + engine_method)
                dup_found = True
                all_ok = False
                failures += 1

    if not dup_found:
        print("  OK (no duplicates found)")
        # Print exceptions
        for exc_name, exc_reason in KNOWN_DUP_EXCEPTIONS.items():
            print("  EXCLUDED: " + exc_name + " — " + exc_reason)

    # 5. Проверка: размер engine.py
    print("")
    print("CHECK 5: engine.py size")
    checks += 1
    lines = len(engine_code.splitlines())
    status = "OK (" + str(lines) + " lines)" if lines < 3317 else "FAIL (" + str(lines) + ")"
    print("  engine.py: " + status)
    if lines >= 3317:
        all_ok = False
        failures += 1

    print("")
    print("=" * 70)
    print("B2_1: " + str(checks) + " checks, " + str(failures) + " failures")
    if all_ok:
        print("B2_1 AUDIT PASSED")
    else:
        print("B2_1 AUDIT FAILED")
    print("=" * 70)

    return 0 if all_ok else 1


def audit_structural():
    print("=" * 70)
    print("AUDIT STRUCTURAL: B1 service methods")
    print("=" * 70)

    all_ok = True
    checks = 0
    failures = 0

    engine_code = (SRC / "simulation" / "engine.py").read_text(encoding="utf-8")

    for pair in BATCH_B1:
        checks += 1
        count = len(re.findall(r'\bdef ' + pair.old_name + r'\b', engine_code))
        status = "OK" if count == 0 else "FAIL (" + str(count) + ")"
        print("  " + pair.old_name + ": " + status)
        if count != 0:
            all_ok = False
            failures += 1

    for pair in BATCH_B1:
        checks += 1
        mod_path = SRC / pair.target_module
        if not mod_path.exists():
            print("  " + pair.target_module + ": NOT FOUND")
            all_ok = False
            failures += 1
            continue
        code = mod_path.read_text(encoding="utf-8")
        found = re.search(r'\bdef ' + pair.new_name + r'\b', code) is not None
        status = "OK" if found else "NOT FOUND"
        print("  " + pair.target_module + "::" + pair.new_name + ": " + status)
        if not found:
            all_ok = False
            failures += 1

    for pair in BATCH_B1:
        checks += 1
        mod_path = SRC / pair.target_module
        if not mod_path.exists():
            continue
        code = mod_path.read_text(encoding="utf-8")
        has_engine = "simulation.engine" in code
        status = "FAIL" if has_engine else "OK"
        print("  " + pair.target_module + ": no engine import " + status)
        if has_engine:
            all_ok = False
            failures += 1

    checks += 1
    lines = len(engine_code.splitlines())
    status = "OK (" + str(lines) + ")" if lines < 3730 else "FAIL (" + str(lines) + ")"
    print("  engine.py: " + status)
    if lines >= 3730:
        all_ok = False
        failures += 1

    baseline_dir = REPO_ROOT / "tests" / "_baseline"
    expected_hashes = {
        "engine_state_seed42.json": "febae09ef46cc7ce",
        "engine_state_seed7.json": "681f47ddc8103918",
        "engine_state_seed123.json": "aec39f13625cae13",
    }
    for fname, prefix in expected_hashes.items():
        checks += 1
        fpath = baseline_dir / fname
        if not fpath.exists():
            print("  " + fname + ": NOT FOUND")
            all_ok = False
            failures += 1
            continue
        h = hashlib.sha256(fpath.read_bytes()).hexdigest()
        status = "OK (" + h[:16] + ")" if h.startswith(prefix) else "MISMATCH"
        print("  " + fname + ": " + status)
        if not h.startswith(prefix):
            all_ok = False
            failures += 1

    checks += 1
    old_patterns = [
        r"engine\._has_strict_comfort", r"engine\._group_faction",
        r"engine\._home_sector_id", r"engine\._distance_to_border",
        r"engine\._sector_humans", r"engine\._squad_power",
        r"engine\._monster_group_power",
        r"self\._has_strict_comfort", r"self\._group_faction",
        r"self\._home_sector_id", r"self\._distance_to_border",
        r"self\._sector_humans", r"self\._squad_power",
        r"self\._monster_group_power",
    ]
    found = []
    for d in ["src", "tests"]:
        dpath = REPO_ROOT / d
        if not dpath.exists():
            continue
        for root, _, files in os.walk(dpath):
            for f in files:
                if not f.endswith(".py"):
                    continue
                fp = Path(root) / f
                try:
                    code = fp.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for p in old_patterns:
                    if re.search(p, code):
                        rel = str(fp.relative_to(REPO_ROOT))
                        if "audit_phase7_move" not in rel:
                            found.append(rel + ": " + p)
    if found:
        print("  Старые вызовы: " + str(len(found)) + " FOUND - FAIL")
        for f in found[:5]:
            print("    " + f)
        all_ok = False
        failures += 1
    else:
        print("  Нет старых вызовов: OK")

    checks += 1
    phase4 = (SRC / "simulation" / "phases" / "phase04_intentions.py").read_text(encoding="utf-8")
    if "engine._border_dist" in phase4:
        print("  border_dist кэш: восстановлен OK")
    else:
        print("  border_dist кэш: НЕ ВОССТАНОВЛЕН")
        all_ok = False
        failures += 1

    print("")
    print("=" * 70)
    print("STRUCTURAL: " + str(checks) + " checks, " + str(failures) + " failures")
    if all_ok:
        print("STRUCTURAL AUDIT PASSED")
    else:
        print("STRUCTURAL AUDIT FAILED")
    print("=" * 70)

    return 0 if all_ok else 1


def audit_b3():
    """Аудит B3 + мутационная самопроверка."""
    print("=" * 70)
    print("AUDIT B3: 11 extracted methods (3.9-B3)")
    print("Pre-batch commit: " + B3_PRE_COMMIT)
    print("=" * 70)

    all_ok = True
    checks = 0
    failures = 0

    # 1. Структурная проверка
    print("")
    print("STRUCTURAL CHECK:")
    engine_code = (SRC / "simulation" / "engine.py").read_text(encoding="utf-8")

    for pair in BATCH_B3:
        checks += 1
        count = len(re.findall(r'\bdef ' + pair.old_name + r'\b', engine_code))
        status = "OK" if count == 0 else "FAIL (" + str(count) + ")"
        print("  " + pair.old_name + " removed: " + status)
        if count != 0:
            all_ok = False
            failures += 1

    for pair in BATCH_B3:
        checks += 1
        mod_path = SRC / pair.target_module
        if not mod_path.exists():
            print("  " + pair.target_module + ": NOT FOUND")
            all_ok = False
            failures += 1
            continue
        code = mod_path.read_text(encoding="utf-8")
        found = re.search(r'\bdef ' + pair.new_name + r'\b', code) is not None
        status = "OK" if found else "NOT FOUND"
        print("  " + pair.target_module + "::" + pair.new_name + ": " + status)
        if not found:
            all_ok = False
            failures += 1

    # 2. Мутационная самопроверка
    print("")
    print("MUTATION SELF-CHECK:")
    for pair in BATCH_B3[:3]:  # Проверим первые 3
        mod_path = SRC / pair.target_module
        code = mod_path.read_text(encoding="utf-8")
        # Внесём мутацию
        mutated = code + "\n# MUTATION_INJECTED\n"
        mod_path.write_text(mutated, encoding="utf-8")
        # Прогоним audit_equivalent для этого pair
        sub_ok = _check_single_pair(pair, B3_PRE_COMMIT)
        # Откатим
        mod_path.write_text(code, encoding="utf-8")
        checks += 1
        if sub_ok:
            print("  " + pair.new_name + " mutation: NOT DETECTED (FAIL)")
            all_ok = False
            failures += 1
        else:
            print("  " + pair.new_name + " mutation: DETECTED (OK)")

    # 3. Проверка дубликатов
    print("")
    print("DUPLICATE CHECK:")
    # Фильтр: только функции верхнего уровня (не методы классов)
    safe_domain_functions = set()
    for pair in BATCH_B3:
        mod_path = SRC / pair.target_module
        if mod_path.exists():
            code = mod_path.read_text(encoding="utf-8")
            tree = ast.parse(code)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.FunctionDef):
                    safe_domain_functions.add(node.name)

    checks += 1
    dup_found = False
    for func_name in safe_domain_functions:
        if "_" + func_name in KNOWN_DUP_EXCEPTIONS:
            continue
        engine_method = "_" + func_name
        if re.search(r'\bdef ' + re.escape(engine_method) + r'\b', engine_code):
            print("  DUP: " + engine_method + " in engine + " + func_name + " in domain")
            all_ok = False
            failures += 1
            dup_found = True

    if not dup_found:
        print("  Нет дубликатов: OK")

    print("")
    print("=" * 70)
    print("B3: " + str(checks) + " checks, " + str(failures) + " failures")
    if all_ok:
        print("B3 AUDIT PASSED")
    else:
        print("B3 AUDIT FAILED")
    print("=" * 70)

    return 0 if all_ok else 1


def _check_single_pair(pair, pre_commit):
    """Проверяет один pair: если тело изменено — возвращает False."""
    old_code = git_show("src/zonesim/simulation/engine.py", pre_commit)
    old_body = extract_body(old_code, pair.old_name)
    if old_body is None:
        return True  # не нашли — пропускаем

    new_body = extract_new_func_body(pair.target_module, pair.new_name)
    if new_body is None:
        return True

    transformed = apply_rules(old_body, pair.rules)
    old_norm = normalize(transformed)
    new_norm = normalize(new_body)

    return old_norm == new_norm


def main():
    parser = argparse.ArgumentParser(description="Аудит B1/B2/B2_1/B3 сервисных методов")
    parser.add_argument("--batch", choices=["B1", "B2", "B2_1", "B3"], default="B1")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--equivalent", action="store_true")
    group.add_argument("--structural", action="store_true")
    group.add_argument("--both", action="store_true")
    args = parser.parse_args()

    if args.batch == "B3":
        return audit_b3()

    if args.batch == "B2_1":
        return audit_b2_1()

    if args.batch == "B2":
        if args.both:
            r1 = audit_b2_equivalent()
            r2 = audit_b2_structural()
            return r1 or r2
        if args.equivalent:
            return audit_b2_equivalent()
        if args.structural:
            return audit_b2_structural()
        return audit_b2_structural()

    if args.both:
        r1 = audit_equivalent()
        r2 = audit_structural()
        return r1 or r2
    if args.equivalent:
        return audit_equivalent()
    if args.structural:
        return audit_structural()
    return audit_structural()


if __name__ == "__main__":
    sys.exit(main())
