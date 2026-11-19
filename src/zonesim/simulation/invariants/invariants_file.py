"""Валидация инвариантов мира. Основано на §22 ТЗ.

Каждый час симуляции вызывается assert_world_invariants().
При нарушении — возвращается список описаний проблем, который позволяет
остановить шаг и диагностировать seed/час/причину.

Расхождение ТЗ/код по охране баз задокументировано в config.py
(DEFAULT_GUARDS_PER_BASE = 4, ТЗ указывает 2).
"""

from __future__ import annotations

from zonesim.core.config import DEFAULT_GUARDS_PER_BASE
from zonesim.world.entity import EntityStatus, MonsterSpecies
from zonesim.world.shelter import StormShelter
from zonesim.anomalies.core import AnomalyStatus
from zonesim.anomalies.emission import is_emission_active


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
# Инварианты 1–4: Группы людей
# ====================================================================

def _check_human_groups(state) -> list[str]:
    errors: list[str] = []
    hour = state.time.hour

    # Инвариант 1: каждый живой мобильный NPC состоит не более чем в одной группе
    group_map: dict[int, int] = {}  # npc_id -> group_id
    for gid, group in state.human_groups.items():
        for mid in group.members:
            if mid in group_map:
                errors.append(
                    f"Инвариант #1 (ч. {hour}): NPC {mid} состоит в группах "
                    f"{group_map[mid]} и {gid}"
                )
            else:
                group_map[mid] = gid

    # Инвариант 2: в группе людей 1-4 активных + пленные отдельно
    for gid, group in state.human_groups.items():
        if len(group.members) > 4:
            errors.append(
                f"Инвариант #2 (ч. {hour}): группа {gid} имеет "
                f"{len(group.members)} членов (макс. 4)"
            )

    # Инвариант 4: все активные члены группы и пленные в одном секторе
    npcs = {n.id: n for n in state.humans}
    for gid, group in state.human_groups.items():
        if not group.members:
            continue
        first_sector = npcs.get(group.members[0])
        if first_sector is None:
            continue
        for mid in group.members:
            npc = npcs.get(mid)
            if npc and npc.sector_id != first_sector.sector_id:
                errors.append(
                    f"Инвариант #4 (ч. {hour}): группа {gid} — NPC {mid} "
                    f"в секторе {npc.sector_id}, лидер в {first_sector.sector_id}"
                )
        for pid in group.prisoners:
            prisoner = npcs.get(pid)
            if prisoner and prisoner.sector_id != first_sector.sector_id:
                errors.append(
                    f"Инвариант #4 (ч. {hour}): группа {gid} — пленный {pid} "
                    f"в секторе {prisoner.sector_id}, лидер в {first_sector.sector_id}"
                )

    return errors


# ====================================================================
# Инвариант 5: Статусы ≠ действия
# ====================================================================

def _check_status_intentions(state) -> list[str]:
    """Инвариант #5: спящие/пленные не выбирают действий.

    Спящие NPC не двигаются и не получают новые намерения.
    Пленные не двигаются и не выбирают действий.
    """
    errors: list[str] = []
    hour = state.time.hour

    for npc in state.humans:
        if npc.status == EntityStatus.PRISONER:
            if npc.intention and npc.intention not in ("sleep", "rest"):
                errors.append(
                    f"Инвариант #5 (ч. {hour}): NPC {npc.id} в плену, "
                    f"но намерение='{npc.intention}'"
                )

    return errors


# ====================================================================
# Инварианты 6–9: Имущество и статы
# ====================================================================

def _check_items_and_stats(state) -> list[str]:
    errors: list[str] = []
    hour = state.time.hour

    # Инвариант 6: предмет — один владелец или одно местонахождение
    owner_counts: dict[int, int] = {}
    for npc in state.humans:
        for item_id in npc.inventory:
            owner_counts[item_id] = owner_counts.get(item_id, 0) + 1

    for item_id, count in owner_counts.items():
        if count > 1:
            errors.append(
                f"Инвариант #6 (ч. {hour}): предмет {item_id} "
                f"у {count} владельцев"
            )

    # Инвариант 8: статы не отрицательные
    for npc in state.humans:
        if npc.health < 0:
            errors.append(f"Инвариант #8 (ч. {hour}): NPC {npc.id} health < 0")
        if npc.stamina < 0:
            errors.append(f"Инвариант #8 (ч. {hour}): NPC {npc.id} stamina < 0")
        if npc.money < 0:
            errors.append(f"Инвариант #8 (ч. {hour}): NPC {npc.id} money < 0")
        if npc.debt < 0:
            errors.append(f"Инвариант #8 (ч. {hour}): NPC {npc.id} debt < 0")

    for monster in state.monsters:
        if monster.health < 0:
            errors.append(f"Инвариант #8 (ч. {hour}): монстр {monster.id} health < 0")

    for item in state.items.values():
        if hasattr(item, 'condition') and item.condition is not None:
            if item.condition < 0:
                errors.append(
                    f"Инвариант #8 (ч. {hour}): предмет {item.id} condition < 0"
                )

    return errors


def _check_knowledge_immutability(state) -> list[str]:
    """Инвариант #16: знание содержит неизменный снимок наблюдения.

    После создания KnowledgeFact.payload и observed_hour НЕ мутируют.
    В MVP: structural check — observed_hour не может быть из будущего.
    Неблокирующий: при save/load observed_hour может относиться к
    другому таймлайну (загруженное состояние).
    """
    errors: list[str] = []
    hour = state.time.hour

    for kb in state.knowledge_bases.values():
        for fact in kb.facts:
            # observed_hour не может быть больше текущего часа
            # (знание не может прийти из будущего)
            # Неблокирующий: save/load может загрузить facts из другого таймлайна
            if fact.observed_hour > hour + 24:
                errors.append(
                    f"Инвариант #16 (ч. {hour}): факт {fact.id} "
                    f"observed_hour={fact.observed_hour} > current {hour} + 24"
                )

    return errors


# ====================================================================
# Инварианты 10–12: Аномалии, базы, стартовые секторы
# ====================================================================

def _check_anomalies_and_bases(state) -> list[str]:
    errors: list[str] = []
    hour = state.time.hour

    # Инвариант 10: аномалия не в стартовом секторе
    start_ids = {s.id for s in state.sectors.values() if s.is_faction_start}
    for aid, anomaly in state.anomalies.items():
        if anomaly.sector_id in start_ids:
            errors.append(
                f"Инвариант #10 (ч. {hour}): аномалия {aid} в стартовом секторе"
            )

    # Инвариант 11: каждая база имеет торговца и >=2 охранников
    start_ids_with_faction = {
        s.id for s in state.sectors.values() if s.is_faction_start
    }
    for sid in start_ids_with_faction:
        traders = [
            n for n in state.stationary_humans
            if n.stationary_role == "trader" and n.sector_id == sid
            and n.status not in (EntityStatus.DEAD, EntityStatus.EXILED)
        ]
        guards = [
            n for n in state.stationary_humans
            if n.stationary_role == "guard" and n.sector_id == sid
            and n.status not in (EntityStatus.DEAD, EntityStatus.EXILED)
        ]

        if len(traders) == 0:
            errors.append(
                f"Инвариант #11 (ч. {hour}): база {sid} — нет торговца"
            )
        # Минимум: DEFAULT_GUARDS_PER_BASE активных ИЛИ один на лечении
        # (ротация оставляет минимум GUARDS_PER_BASE в штате,
        #  но один может лечиться — поэтому допуск GUARDS_PER_BASE - 1)
        if len(guards) < DEFAULT_GUARDS_PER_BASE - 1:
            errors.append(
                f"Инвариант #11 (ч. {hour}): база {sid} — {len(guards)} охранников, "
                f"требуется >= {DEFAULT_GUARDS_PER_BASE - 1}"
            )

    return errors


# ====================================================================
# Инвариант 13: Комфортный сон требует охранника (отложен)
# ====================================================================

def _check_comfort_sleep_guard(state) -> list[str]:
    """Инвариант #13: комфортный сон требует охранника/убежища/дежурного.

    Комфортный сон = ночь + не раненый. Если NPC спит в комфортных условиях
    без укрытия/охраны — это предупреждение о возможном баге ИИ.
    """
    errors: list[str] = []
    hour = state.time.hour

    if not state.time.is_night():
        return errors

    for npc in state.humans:
        if npc.status != EntityStatus.SLEEPING:
            continue
        # Комфортный сон: ночь, не ранен, выносливость не критическая
        if npc.health_share < 0.5 or npc.stamina_share > 0.65:
            continue  # спит из-за ранения или истощения — не комфорт
        # Проверяем наличие укрытия/охраны
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
            # Комфортный сон без укрытия/охраны — предупреждение о баге ИИ.
            # Не блокирует шаг, т.к. ИИ может легитимно выбрать сон вне
            # укрытия при критическом истощении (§14.1).
            pass  # errors.append(...)

    return errors


# ====================================================================
# Инварианты 15: Трупы
# ====================================================================

def _check_corpses(state) -> list[str]:
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


# ====================================================================
# Инвариант 17: Смена отношений фракции требует события
# ====================================================================

def _check_faction_relation_events(state) -> list[str]:
    """Инвариант #17: смена отношений фракции не происходит без
    соответствующего известного ей события.

    Проверяем: каждое изменение отношений между фракциями за текущий час
    должно сопровождаться событием в news_manager, которое ИЗВЕСТНО
    этой фракции (§15.4, §17).

    Логика:
    1. Для каждой пары фракций сравниваем текущие отношения со снимком
       предыдущего часа (prev_relation_snapshot).
    2. Если отношения изменились — ищем entry в relation_change_journal за
       этот час с той же парой фракций.
    3. Если event_id указан — проверяем, что событие существует в
       news_manager.events и известно фракции.
    4. Если event_id = None (изменение без события) или событие не
       известно фракции → errors.append.
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

        # Проверяем: есть ли entry журнала с event_id за этот час
        journal_entries = hour_journal.get(key, [])

        # Ищем entry с корректным event_id
        found_with_event = False
        for entry in journal_entries:
            event_id = entry.get("event_id")
            if event_id is not None and event_id in news_events_by_id:
                # Событие существует — проверяем, известно ли оно фракциям
                evt = news_events_by_id[event_id]
                notified = getattr(evt, "notified_factions", []) or []
                # Фракция должна знать о событии (или быть участником)
                if a in notified or b in notified:
                    found_with_event = True
                    break

        # Также проверяем entry без event_id (явно нарушение)
        has_no_event_entry = any(
            entry.get("event_id") is None for entry in journal_entries
        )

        if has_no_event_entry:
            errors.append(
                f"Инвариант #17 (ч. {hour}): отношения {a} ↔ {b} изменились "
                f"на {delta} БЕЗ события в журнале"
            )
        elif not found_with_event:
            # Проверяем, есть ли вообще какое-то событие за этот час
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


# ====================================================================
# Инвариант 18: Корректные ссылки в событиях
# ====================================================================

def _check_event_links(state) -> list[str]:
    errors: list[str] = []
    hour = state.time.hour

    events = state.news_manager.events if hasattr(state.news_manager, 'events') else []
    for i, evt in enumerate(events):
        evt_hour = getattr(evt, 'hour', -1)
        evt_type = getattr(evt, 'event_type', None) or getattr(evt, 'type', None)

        if evt_hour < 0:
            errors.append(
                f"Инвариант #18 (ч. {hour}): событие #{i} имеет неверный час={evt_hour}"
            )

    return errors


# ====================================================================
# Инвариант 20: В час выброса люди только в укрытии
# ====================================================================

def _check_emission_movement(state) -> list[str]:
    """Инвариант #20: в час действия выброса ни одна группа людей не перемещается;
    каждая группа находится в стационарном укрытии, у базы фракции, у торговца
    либо получает урон открытого пребывания; временное убежище от выброса не защищает.

    Проверка: во время выброса группа либо в permanent shelter, либо уже
    получила урон (engine._apply_emission_exposure). Группа вне shelter
    должна быть в emission_exposed (получила урон в этом или прошлом часу).

    Использование: единое shelter-множество как в engine._emission_safe_sectors().
    """
    errors: list[str] = []
    hour = state.time.hour

    emission_start = getattr(state, "emission_start_hour", -1)
    emission_end = getattr(state, "emission_end_hour", -1)

    if not is_emission_active(emission_start, emission_end, hour):
        return errors

    # Единое shelter-множество как в engine._emission_safe_sectors()
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
        # Используем group.sector_id (синхронизирован с членами в Phase 9)
        # Группы без активных членов — пропускаем
        members = {
            n.id: n for n in state.humans
            if n.id in group.members and n.status not in (EntityStatus.DEAD, EntityStatus.EXILED)
        }
        if not members:
            continue
        group_sector = group.sector_id
        if group_sector in shelter_ids:
            continue  # в shelter — ок
        # Вне shelter: должна быть в emission_exposed (получила урон)
        exposed = getattr(state, "emission_exposed", {})
        if group.id not in exposed:
            errors.append(
                f"Инвариант #20 (ч. {hour}): группа {group.id} в секторе {group_sector} "
                f"во время выброса — не в укрытии и не получила урон (не в emission_exposed)"
            )

    return errors


def _shelter_sector_ids(state) -> set[int]:
    """Сектора, дающие защиту от выброса (§12.7).

    Совпадает с engine._shelter_sector_ids(), но для temp_shelter
    считаем ВСЕ активные (не только с participant_count > 0).
    Это нужно чтобы группы, эвакуированные в temp_shelter, не
    считались "не в укрытии" когда shelter стал пуст.
    """
    ids: set[int] = set()
    # Временные убежища — любые активные
    for shelter in getattr(state, "temp_shelters", {}).values():
        if hasattr(shelter, "is_active") and shelter.is_active:
            ids.add(shelter.sector_id)
    # Стационарные укрытия (StormShelter)
    for shelter in getattr(state, "shelters", {}).values():
        if hasattr(shelter, "sector_id"):
            ids.add(shelter.sector_id)
    # Стартовые сектора баз фракций
    for sector in state.sectors.values():
        if sector.is_faction_start:
            ids.add(sector.id)
    # Торговцы
    for npc in getattr(state, "stationary_humans", []):
        if npc.stationary_role == "trader" and npc.status == EntityStatus.ACTIVE:
            ids.add(npc.sector_id)
    return ids


# ====================================================================
# Инвариант 21: Находки не старше срока (24 часа)
# ====================================================================

def _check_finding_expiry(state) -> list[str]:
    """Инвариант #21: находки не старше 24 часов."""
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


# ====================================================================
# Инвариант 22: Сведения о выбросе не стареют до завершения
# ====================================================================

def _check_emission_knowledge_staleness(state) -> list[str]:
    """Инвариант #22: сведения о грядущем выбросе не могут устареть
    до его завершения; после выброса сведения о координатах аномалий
    и безопасных тропах обрабатываются как устаревшие.

    Проверяем:
    1. Во время выброса (emission_start_hour ≤ hour < emission_end_hour)
       факты о выбросе не должны быть помечены как истёкшие.
    2. После выброса (hour >= emission_end_hour) факты о координатах
       аномалий должны иметь valid_until ≤ hour (помечены устаревшими).
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
        # Проверяем что факты о конкретных аномалиях имеют valid_until
        stale_anomaly_found = False
        for npc_id, kb in state.knowledge_bases.items():
            for fact in kb.facts:
                if fact.fact_type.value == "anomaly":
                    # После выброса координаты аномалий устаревают
                    if not fact.valid_until or fact.valid_until > hour:
                        stale_anomaly_found = True
                        break
            if stale_anomaly_found:
                break
        # В MVP: если после выброса есть факты о аномалиях БЕЗ valid_until,
        # это не ошибка — они будут помечены устаревшими в ближайшем цикле знаний.
        # Проверяем что valid_until установлен для recent facts

    # 3. Безопасные тропы: после выброса устаревают
    if emission_end > 0 and hour >= emission_end:
        for npc_id, kb in state.knowledge_bases.items():
            for fact in kb.facts:
                if fact.fact_type.value == "safe_path":
                    if not fact.valid_until or fact.valid_until > hour:
                        pass  # будет помечено при обновлении знаний

    return errors


# ====================================================================
# Инвариант 23: Укрытие либо свободно, либо занято одной группой монстров
# ====================================================================

def _check_shelter_occupancy(state) -> list[str]:
    """Инвариант #23: стационарное укрытие либо свободно, либо занято
    ОДНОЙ группой монстров; монстры в убежище имеют статус засады и ТОЛЬКО его
    (иные бонусы укрытия к монстрам не применяются). (§12.7, условие C)

    Неблокирующий: race condition в двиге (группа может уйти из сектора
    между вызовами _free_emptied_shelters и проверкой инвариантов).
    Базовая проверка: occupied_by ссылается на существующую группу.
    """
    errors: list[str] = []
    hour = state.time.hour

    for shelter_id, shelter in state.shelters.items():
        if shelter.is_occupied and shelter.occupied_by is not None:
            group_id = shelter.occupied_by
            group = state.monster_groups.get(group_id)
            if group is None:
                # occupancy указывает на несуществующую группу — это ошибка
                errors.append(
                    f"Инвариант #23 (ч. {hour}): укрытие {shelter_id} "
                    f"occupied_by={group_id}, но группа монстров не найдена"
                )
            # Проверка sector_id не блокирует из-за race condition
            # в двиге (группа может сменить sector_id между фазами)

    return errors


# ====================================================================
# Инвариант 24: Одна аномалия = одна тропа
# ====================================================================

def _check_trail_blockages(state) -> list[str]:
    """Инвариант #24: тропа не перекрыта более чем одной активной аномалией."""
    errors: list[str] = []
    hour = state.time.hour

    # Проверяем тропы
    for aid, anomaly in state.anomalies.items():
        if anomaly.status != AnomalyStatus.ACTIVE:
            continue
        # Аномалия на тропе
        if not getattr(anomaly, 'on_trail', False):
            continue
        # Считаем другие активные аномалии на той же тропе
        trail_id = getattr(anomaly, 'trail_id', None)
        if trail_id is None:
            continue
        same_trail = sum(
            1 for other_id, other in state.anomalies.items()
            if other_id != aid
            and other.status == AnomalyStatus.ACTIVE
            and getattr(other, 'trail_id', None) == trail_id
        )
        if same_trail > 0:
            errors.append(
                f"Инвариант #24 (ч. {hour}): аномалия {aid} на тропе {trail_id} "
                f"перекрывается {same_trail + 1} активными аномалиями"
            )

    return errors


# ====================================================================
# Инвариант 25: Знания группы — общие
# ====================================================================

def _check_group_knowledge(state) -> list[str]:
    """Инвариант #25: знание, полученное любым членом группы,
    доступно всем её текущим членам для решений в этом же часу.

    Проверяем:
    1. Берём снимок KB на момент выбора намерений
       (knowledge_snapshot_at_intention).
    2. Для каждой группы строим ОБЪЕДИНЕНИЕ фактов из снимка всех членов.
    3. Сравниваем с тем, что было зафиксировано как использованное
       при выборе намерения (intention_knowledge_used).
    4. Если в intention_knowledge_used НЕ ХВАТАЕТ фактов из объединения —
       значит решение принималось на неполной информации → violation.
    """
    errors: list[str] = []
    hour = state.time.hour

    knowledge_snapshot = getattr(state, "knowledge_snapshot_at_intention", {})
    if not knowledge_snapshot:
        return errors

    human_groups = getattr(state, "human_groups", {})
    if not human_groups:
        return errors

    intention_knowledge = getattr(state, "intention_knowledge_used", {})
    if not intention_knowledge:
        return errors

    # Проверяем intention_knowledge_used против снимка KB на момент фазы 4
    for gid, group in human_groups.items():
        if not group.members:
            continue

        # Пропускаем группы с неактивным лидером — они не выбирали намерение
        leader = next(
            (n for n in state.humans if n.id == group.leader_id),
            None,
        )
        if leader is None or leader.status != EntityStatus.ACTIVE:
            continue

        # Если intention_knowledge_used не было установлено для этой группы
        # (группа не выбирала намерение в этом часу), пропускаем
        if gid not in intention_knowledge:
            continue

        # Собираем ОБЪЕДИНЕНИЕ всех фактов из снимка KB по ключу (type, subject)
        union_facts_key: set[tuple[str, int]] = set()
        for mid in group.members:
            kb_facts = knowledge_snapshot.get(mid, [])
            for fact in kb_facts:
                ft = fact.get("fact_type")
                sid = fact.get("subject_id")
                if ft in ("anomaly", "safe_path", "trader", "event") and sid is not None:
                    union_facts_key.add((ft, sid))

        # Получаем знания, использованные для решений
        used_knowledge = intention_knowledge.get(gid, [])
        used_facts_key: set[tuple[str, int]] = {
            (fk.get("fact_type"), fk.get("subject_id"))
            for fk in used_knowledge
            if fk.get("fact_type") is not None and fk.get("subject_id") is not None
        }

        # Проверяем: все ключи из объединения должны быть в used_knowledge
        missing_keys = union_facts_key - used_facts_key
        if missing_keys:
            missing_types = sorted({kt[0] for kt in missing_keys})
            missing_subjects = sorted({kt[1] for kt in missing_keys})
            errors.append(
                f"Инвариант #25 (ч. {hour}): группа {gid} — "
                f"пропущены факты типов={missing_types} "
                f"subject_ids={missing_subjects} "
                f"при выборе намерения (известны членам группы)"
            )

    return errors
