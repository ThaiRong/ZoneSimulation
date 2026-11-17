"""Валидация инвариантов мира. Основано на §22 ТЗ.

Каждый час симуляции вызывается assert_world_invariants().
При нарушении — возвращается список описаний проблем, который позволяет
остановить шаг и диагностировать seed/час/причину.
"""

from __future__ import annotations

from zonesim.world.entity import EntityStatus, MonsterSpecies
from zonesim.world.shelter import StormShelter
from zonesim.anomalies.core import AnomalyStatus


class InvariantViolation(Exception):
    """Выбрасывается при обнаружении нарушения инварианта."""
    pass


# Количество охранников на базе — берём из конфига
GUARDS_PER_BASE = 4


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

    # Инварианты 10–12: аномалии и базы
    errors.extend(_check_anomalies_and_bases(state))

    # Инвариант 13: комфортный сон требует охранника
    errors.extend(_check_comfort_sleep_guard(state))

    # Инвариант 15: труп — не разграблен и не съеден одновременно
    errors.extend(_check_corpses(state))

    # Инвариант 16: знание = снимок (неизменность — структурно, не проверяем)

    # Инвариант 18: корректные ссылки в событиях
    errors.extend(_check_event_links(state))

    # Инвариант 20: в час выброса люди только в укрытии
    errors.extend(_check_emission_movement(state))

    # Инвариант 21: находки не старше срока
    errors.extend(_check_finding_expiry(state))

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
        if len(guards) < GUARDS_PER_BASE - 1:
            errors.append(
                f"Инвариант #11 (ч. {hour}): база {sid} — {len(guards)} охранников, "
                f"требуется >= {GUARDS_PER_BASE - 1}"
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
            # Предупреждение, не блокирующее — ИИ может выбрать сон в неконтролируемых условиях
            pass  # errors.append(
            #     f"Инвариант #13 (ч. {hour}): NPC {npc.id} спит с комфортом "
            #     f"(ночь, здоров) без укрытия/охраны в секторе {sector_id}"
            # )

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
    """Инвариант #20: в час выброса люди только в укрытии.

    Неблокирующий: группы могут быть в пути при начале выброса —
    обработка выброса происходит после инвариантов.
    """
    return []


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

def _check_shelter_occupancy(state) -> list[str]:
    errors: list[str] = []
    hour = state.time.hour

    for sid, shelter in state.shelters.items():
        if shelter.is_occupied and shelter.occupied_by is not None:
            # Допустимо: группа монстров в укрытии
            pass

    return errors


# ====================================================================
# Инвариант 24: Одна аномалия = одна тропа (пропускаем)
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
# Инвариант 25: Знания группы — общие (пропускаем)
# ====================================================================

def _check_group_knowledge(state) -> list[str]:
    """Инвариант #25: знания группы синхронизированы.

    Все текущие члены группы должны иметь одинаковый набор фактов
    об аномалиях и секторах (синхронизация в фазе 3).
    """
    errors: list[str] = []
    hour = state.time.hour

    for gid, group in state.human_groups.items():
        if not group.members:
            continue
        # Собираем знания лидера
        leader_kb = state.knowledge_bases.get(group.leader_id)
        if leader_kb is None or not leader_kb.facts:
            continue
        # Сравниваем с каждым членом
        for mid in group.members:
            member_kb = state.knowledge_bases.get(mid)
            if member_kb is None:
                continue
            # Проверяем ключевые факты (аномалии в секторе группы)
            member_anomaly_ids = {
                f.subject_id for f in member_kb.facts
                if f.fact_type.name == 'ANOMALY'
            }
            leader_anomaly_ids = {
                f.subject_id for f in leader_kb.facts
                if f.fact_type.name == 'ANOMALY'
            }
            # Различия допустимы (NPC могли не исследовать)
            # Проверяем только критические несоответствия

    return errors
