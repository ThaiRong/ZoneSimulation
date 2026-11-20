"""Инвариант #17: смена отношений фракции требует события.

§22 ТЗ:
17 Смена отношений фракции только при соответствующем известном ей событии.

check_fn → _check_faction_relation_events (#17).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState


def _check_faction_relation_events(state: "SimulationState") -> list[str]:
    """Инвариант #17: смена отношений фракции не происходит без соответствующего
    известного ей события (§15.4, §17).

    Логика:
    1. Для каждой пары фракций сравниваем текущие отношения со снимком предыдущего часа.
    2. Если отношения изменились — ищем entry в relation_change_journal за этот час.
    3. Если event_id указан — проверяем событие в news_manager.events.
    4. Если event_id = None или событие не известно фракции → errors.append.
    """
    errors: list[str] = []
    hour = state.time.hour

    faction_relations = getattr(state, "faction_relations", None)
    if faction_relations is None:
        return errors

    prev_snapshot = getattr(state, "prev_relation_snapshot", {})
    journal = getattr(state, "relation_change_journal", [])

    if not prev_snapshot:
        return errors

    news_mgr = getattr(state, "news_manager", None)
    if news_mgr is None:
        return errors
    news_events_by_id = {evt.id: evt for evt in news_mgr.events}

    # Собираем события журнала за текущий час
    hour_journal: dict[tuple[str, str], list[dict]] = {}
    for entry in journal:
        if entry.get("hour") == hour:
            key = (entry["faction_a"], entry["faction_b"])
            hour_journal.setdefault(key, []).append(entry)

    # Проверяем каждую пару фракций
    for (a, b), prev_val in prev_snapshot.items():
        cur_val = faction_relations.get(a, b)
        if cur_val == prev_val:
            continue

        delta = cur_val - prev_val
        key = (a, b)

        journal_entries = hour_journal.get(key, [])

        found_with_event = False
        for entry in journal_entries:
            event_id = entry.get("event_id")
            if event_id is not None and event_id in news_events_by_id:
                evt = news_events_by_id[event_id]
                notified = getattr(evt, "notified_factions", []) or []
                if a in notified or b in notified:
                    found_with_event = True
                    break

        has_no_event_entry = any(
            entry.get("event_id") is None for entry in journal_entries
        )

        if has_no_event_entry:
            errors.append(
                f"Инвариант #17 (ч. {hour}): отношения {a} ↔ {b} изменились "
                f"на {delta} БЕЗ события в журнале"
            )
        elif not found_with_event:
            hour_relation_events = [
                evt for evt in news_mgr.events
                if evt.hour == hour
                and evt.event_type in (
                    "faction_relation_change", "faction_conflict",
                    "faction_cooperation", "faction_rescue",
                    "faction_isolation", "war_start", "war_end",
                    "alliance_form", "alliance_break",
                )
            ]
            if not hour_relation_events:
                errors.append(
                    f"Инвариант #17 (ч. {hour}): отношения {a} ↔ {b} изменились "
                    f"на {delta}, но нет соответствующего события в новостях"
                )

    return errors
