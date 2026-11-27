"""Временные убежища (Shelter) и стационарные укрытия (StormShelter).

Основано на §7.10 и §7.16 ТЗ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from zonesim.world.entity import EntityStatus
from zonesim.anomalies.emission import (
    EMISSION_MONSTER_SHELTER_CHANCE, EMISSION_MONSTER_STAY_MIN, EMISSION_MONSTER_STAY_MAX,
)

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState
    from zonesim.world.group import HumanGroup


@dataclass
class Shelter:
    """Временное убежище в секторе. (§7.10)

    Может использоваться группами одной фракции.
    Передается между группами.
    Разрушается через 4 часа без использования.
    Максимум 10 человек.
    Монстры не занимают.
    """
    id: int
    sector_id: int
    owner_group_id: int
    owner_faction: str = ""
    created_hour: int = 0
    last_used_hour: int = 0  # последний кто использовал
    quality: int = 50  # качество от 1-100
    destroyed: bool = False

    # Участники: group_id -> list[npc_id]
    participants: dict[int, list[int]] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return not self.destroyed

    @property
    def participant_count(self) -> int:
        return sum(len(npcs) for npcs in self.participants.values())

    @property
    def remaining_hours(self) -> int:
        """Оставшиеся часы жизни (6 часов по умолчанию, +4 за каждое использование)."""
        age = 0  # caller должен передать current_hour
        return 6 + (self.last_used_hour - self.created_hour)

    def can_accept_group(self, group_id: int, faction: str) -> bool:
        """Можно ли принять группу?"""
        if not self.is_active:
            return False
        if self.participant_count >= 10:
            return False
        # Та же фракция или нейтральная
        if self.owner_faction and faction and faction != self.owner_faction:
            return False
        # Проверка что группа ещё не участвует
        if group_id in self.participants:
            return False
        return True

    def add_group(self, group_id: int, npc_ids: list[int]) -> bool:
        """Добавить группу в убежище."""
        if not self.can_accept_group(group_id, ""):
            return False
        self.participants[group_id] = npc_ids
        self.last_used_hour = self.last_used_hour  # caller должен передать current_hour
        return True

    def remove_group(self, group_id: int) -> bool:
        """Убрать группу из убежища."""
        if group_id in self.participants:
            del self.participants[group_id]
            return True
        return False

    def expire(self, current_hour: int) -> bool:
        """Проверяет, истёк ли срок. Возвращает True если уничтожено."""
        if not self.is_active:
            return True
        # Если участники есть — shelter не expire (разбудит их и лишит укрытия)
        if self.participant_count > 0:
            return False
        # 4 часа без использования
        if current_hour - self.last_used_hour >= 4:
            self.destroyed = True
            return True
        # Максимум 6 часов жизни (только если нет участников)
        if current_hour - self.created_hour >= 6:
            self.destroyed = True
            return True
        return False

    @property
    def concealment_bonus(self) -> int:
        """Бонус к скрытности. (§7.10)"""
        return int(self.quality * 0.3)

    @property
    def defense_bonus(self) -> int:
        """Ограниченный защитный бонус при нападении. (§7.10)"""
        return int(self.quality * 0.15)

    @property
    def recovery_bonus(self) -> float:
        """Улучшение отдыха и лечения. (§7.10)"""
        return 1.0 + (self.quality / 100.0) * 0.5  # +до 50% к восстановлению

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sector_id": self.sector_id,
            "owner_group_id": self.owner_group_id,
            "owner_faction": self.owner_faction,
            "created_hour": self.created_hour,
            "last_used_hour": self.last_used_hour,
            "quality": self.quality,
            "destroyed": self.destroyed,
            "participants": dict(self.participants),
        }


@dataclass
class StormShelter:
    """Стационарное укрытие от выброса — неподвижный объект ландшафта. (§7.16)

    ВМЕСТИМОСТЬ (условие A): для постоянных укрытий (StormShelter) вместимость БЕСКОНЕЧНА.
    Поле capacity хранится ТОЛЬКО для отображения в UI (§21). Все группы, зачистившие
    или укрывшиеся в StormShelter, входят без ограничения.
    """
    id: int
    sector_id: int
    capacity: int = 4        # только для UI; постоянные укрытия имеют безлимитную вместимость
    condition: int = 100     # в MVP только для отображения
    occupied_by: int | None = None   # id группы монстров (§13.7)
    occupied_until: int = 0          # час окончания занятия

    @property
    def is_occupied(self) -> bool:
        return self.occupied_by is not None


def shelter_sector_ids(state) -> set[int]:
    """Сектора, дающие защиту: временные убежища, стационарные, базы, торговцы. (§12.7)"""
    # Временные убежища — любые активные (не только с participant_count > 0)
    ids = {s.sector_id for s in state.temp_shelters.values() if s.is_active}
    ids |= {s.sector_id for s in state.shelters.values()}
    ids |= {s.id for s in state.sectors.values() if s.is_faction_start}
    ids |= {
        npc.sector_id for npc in state.stationary_humans
        if npc.stationary_role == "trader" and npc.status == EntityStatus.ACTIVE
    }
    # Временная база ситуативного торговца — только REST (не SLEEP)
    if (
        state.conditional_trader_id is not None
        and state.conditional_trader_sector >= 0
        and state.conditional_trader_start_hour >= 0
        and state.conditional_trader_end_hour >= 0
    ):
        current_hour = state.time.hour
        if state.conditional_trader_start_hour <= current_hour < state.conditional_trader_end_hour:
            ids.add(state.conditional_trader_sector)
    return ids


def group_in_shelter(state, group: HumanGroup) -> bool:
    """Проверяет, находится ли группа в укрытии."""
    return group.sector_id in shelter_sector_ids(state)


def shelter_targets(state, group: HumanGroup, hour: int) -> set[int]:
    """Доступные укрытия: занятые монстрами не считаются. (§12.7, §13.7)"""
    occupied = {
        shelter.sector_id
        for shelter in state.shelters.values()
        if shelter.is_occupied and shelter.occupied_until > hour
    }
    targets = shelter_sector_ids(state) - occupied
    return targets or shelter_sector_ids(state)


def process_create_shelter(state, group: HumanGroup, hour: int) -> bool:
    """Создаёт временное убежище (§7.10)."""
    from zonesim.world.groups import active_members, group_leader
    from zonesim.world.item import ItemType

    members = active_members(state, group)
    if not members:
        return False

    # Проверка: хотя бы один NPC имеет набор — не расходуется
    leader = group_leader(group, members)
    has_kit = any(
        state.items.get(item_id) and state.items[item_id].type is ItemType.SHELTER_KIT
        for npc in members
        for item_id in npc.inventory
    )
    if not has_kit:
        return False

    # Создать Shelter — материал не тратится
    shelter_id = state.next_shelter_id
    state.next_shelter_id += 1
    shelter = Shelter(
        id=shelter_id,
        sector_id=group.sector_id,
        owner_group_id=group.id,
        owner_faction=members[0].faction if members else "",
        created_hour=hour,
        last_used_hour=hour,
        quality=50,
    )
    shelter.add_group(group.id, [m.id for m in members if m.status == EntityStatus.ACTIVE])
    state.temp_shelters[shelter_id] = shelter

    # Кулдаун на уровне группы
    group.last_shelter_hour = hour

    state.news_manager.create_event(
        hour=hour, minute=0, sector_id=group.sector_id,
        event_type="shelter_created",
        participants=[m.id for m in members[:1]],
        result="created",
        importance=30,
        summary=f"Группа {group.id} создала временное убежище в секторе {group.sector_id}",
        details={"shelter_id": shelter_id, "sector_id": group.sector_id},
    )
    return True


def free_emptied_shelters(state, hour: int) -> None:
    """Освобождает укрытия, если монстры ушли из сектора. (§13.7, #23)"""
    from zonesim.world.entity import EntityStatus

    for shelter in state.shelters.values():
        if not shelter.is_occupied or shelter.occupied_by is None:
            continue
        group = state.monster_groups.get(shelter.occupied_by)
        if group is None or group.sector_id != shelter.sector_id:
            shelter.occupied_by = None
            state.news_manager.create_event(
                hour=hour, minute=0, sector_id=shelter.sector_id,
                event_type="shelter", participants=[], result="freed_emptied",
                importance=15,
                summary=f"Укрытие {shelter.id} освобождено (монстры ушли)",
                details={"shelter_id": shelter.id},
            )


def update_shelter_participants(state, hour: int) -> None:
    """Обновляет участников Shelter и удаляет пустые группы. (§7.10, #20)"""
    from zonesim.world.entity import EntityStatus

    # Импортируем тут, чтобы избежать циклического импорта
    from zonesim.ai import REST

    npcs = {npc.id: npc for npc in state.humans}

    for shelter_id, shelter in list(state.temp_shelters.items()):
        if not shelter.is_active:
            continue

        # Обновляем участников
        for group_id, npc_ids in list(shelter.participants.items()):
            group = state.human_groups.get(group_id)
            if group is None:
                shelter.remove_group(group_id)
                continue

            # Проверяем что группа жива и в том же секторе
            active_members_shelter = [
                mid for mid in group.members
                if mid in npcs and npcs[mid].sector_id == shelter.sector_id
                and npcs[mid].status not in (EntityStatus.DEAD, EntityStatus.EXILED)
            ]

            if not active_members_shelter:
                shelter.remove_group(group_id)
            else:
                shelter.participants[group_id] = active_members_shelter

        # Проверяем экспирацию
        if shelter.expire(hour):
            # Эвакуируем участников из разрушенного убежища (§12.7, #20)
            from zonesim.world.shelter import shelter_sector_ids
            from zonesim.actions.movement import walk

            shelter_ids = shelter_sector_ids(state)
            for group_id, npc_ids in list(shelter.participants.items()):
                group = state.human_groups.get(group_id)
                if group is None or not npc_ids:
                    continue
                # Перемещаем к ближайшему Shelter
                path = walk(state, group.sector_id, shelter_ids, set(), points=1.0)
                if path and len(path) >= 2:
                    for npc_id in npc_ids:
                        npc = None
                        for n in state.humans:
                            if n.id == npc_id:
                                npc = n
                                break
                        if npc:
                            npc.sector_id = path[1]
                            group.sector_id = path[1]
                            # Разбуживаем спящих участников (#13 invariant)
                            if npc.status == EntityStatus.SLEEPING:
                                npc.status = EntityStatus.ACTIVE
                                npc.intention = REST
                                group.comfort = False  # сбросим comfort
            state.news_manager.create_event(
                hour=hour, minute=0, sector_id=shelter.sector_id,
                event_type="shelter_expired", participants=[], result="expired",
                importance=5,
                summary=f"Убежище {shelter_id} в секторе {shelter.sector_id} разрушено",
                details={"shelter_id": shelter_id},
            )
            del state.temp_shelters[shelter_id]


def process_shelter_occupation(state, hour: int) -> None:
    from zonesim.world.groups import monster_group_members

    """Обрабатывает занятие/освобождение укрытий монстрами. (§13.7)"""
    # истечение занятия проверяется каждый час
    for shelter in state.shelters.values():
        if shelter.is_occupied and hour >= shelter.occupied_until:
            shelter.occupied_by = None
            state.news_manager.create_event(
                hour=hour, minute=0, sector_id=shelter.sector_id,
                event_type="shelter", participants=[], result="freed",
                importance=15,
                summary=f"Монстры покинули укрытие в секторе {shelter.sector_id}",
                details={"shelter_id": shelter.id},
            )
    if hour % 24 != 0:
        return
    candidates = [
        group for group in state.monster_groups.values()
        if any(m.status == EntityStatus.ACTIVE for m in monster_group_members(state, group))
    ]
    if not candidates:
        return
    used_groups: set[int] = set()
    for shelter in state.shelters.values():
        if shelter.is_occupied:
            continue
        free_groups = [g for g in candidates if g.id not in used_groups]
        if not free_groups:
            break
        if state.rng.random() >= EMISSION_MONSTER_SHELTER_CHANCE:
            continue
        group = state.rng.choice(free_groups)
        members = monster_group_members(state, group)
        if not members:
            continue
        used_groups.add(group.id)
        shelter.occupied_by = group.id
        shelter.occupied_until = hour + state.rng.randint(
            EMISSION_MONSTER_STAY_MIN, EMISSION_MONSTER_STAY_MAX,
        )
        group.sector_id = shelter.sector_id
        for monster in members:
            monster.sector_id = shelter.sector_id
        state.news_manager.create_event(
            hour=hour, minute=0, sector_id=shelter.sector_id,
            event_type="shelter", participants=[m.id for m in members],
            result="occupied", importance=30,
            summary=f"Монстры заняли укрытие в секторе {shelter.sector_id}",
            details={"shelter_id": shelter.id, "group_id": group.id},
        )
        # Условие D: знание о занятом убежище = информация (§17)
        create_shelter_occupied_knowledge(state, shelter.id, shelter.sector_id, group.id, hour)


def create_shelter_occupied_knowledge(state, shelter_id: int, sector_id: int,
                                      monster_group_id: int, hour: int) -> None:
    """Условие D: создаёт KnowledgeFact при обнаружении занятого монстрами убежища (§17)."""
    from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType

    for npc in state.humans:
        if npc.status in (EntityStatus.DEAD, EntityStatus.EXILED):
            continue
        kb = state.knowledge_bases.setdefault(npc.id, KnowledgeBase())
        # Добавляем факт для каждого NPC (все члены группы получают общие знания)
        kb.add_manual(
            npc.id,
            KnowledgeType.SHELTER_OCCUPIED,
            subject_id=shelter_id,
            payload={
                "sector_id": sector_id,
                "monster_group_id": monster_group_id,
                "shelter_id": shelter_id,
            },
            hour=hour,
            source="observation",
        )


def process_emission_shelter_assault(state, hour: int,
                                      pending_battles: list) -> None:
    """Штурм людьми убежищ, занятых монстрами (§12.7, условие B).

    Во время выброса:
    - Группа людей в секторе с убежищем, занятым монстрами (StormShelter.occupied_by),
      И сама не укрытая (не в permanent shelter/bases/trader) → штурмует.
    - Укрытые группы (в permanent shelter секторе, базе, у торговца) НЕ атакуют.
    - Несколько групп атакуют ОДНО убежище одновременно (агрегированный бой).
    """
    from zonesim.world.groups import monster_group_members
    from zonesim.anomalies.emission import emission_active, emission_safe_sectors

    if not emission_active(state, hour):
        # Вне выброса — штурм не происходит
        state.ongoing_shelter_assaults.clear()
        return

    shelter_ids = emission_safe_sectors(state)

    # Находим все укрытия, занятые монстрами
    monster_occupied_shelters = {
        s.id: s for s in state.shelters.values()
        if s.is_occupied and s.occupied_by is not None
    }

    # Для каждого shelter: собираем атакующие группы
    assault_map: dict[int, list[int]] = {}  # shelter_id -> [group_ids]
    for sid, shelter in monster_occupied_shelters.items():
        sector_id = shelter.sector_id
        attacking_group_ids: list[int] = []
        for group in state.human_groups.values():
            if not group.members:
                continue
            members = {
                n.id: n for n in state.humans
                if n.id in group.members
                and n.status not in (EntityStatus.DEAD, EntityStatus.EXILED)
            }
            if not members:
                continue
            # Группа должна быть в секторе убежища
            if group.sector_id != sector_id:
                continue
            # Не атакуют: группа в permanent shelter секторе (shelter_id),
            # но НЕ в faction_start или trader sector
            if group.sector_id in shelter_ids:
                # Проверяем: это permanent shelter или base/trader?
                # Если sector_id == shelter.sector_id и это permanent shelter — группа уже sheltered
                is_base_or_trader = (
                    any(
                        s.id == sector_id and s.is_faction_start
                        for s in state.sectors.values()
                    )
                    or any(
                        npc.sector_id == sector_id
                        and npc.stationary_role == "trader"
                        and npc.status == EntityStatus.ACTIVE
                        for npc in state.stationary_humans
                    )
                )
                if is_base_or_trader:
                    continue
                # Если группа в секторе StormShelter — она sheltered
                continue
            # Не атакуют: уже атакующие в ongoing_assaults на другой shelter
            if group.id in [
                g for gids in assault_map.values() for g in gids
            ]:
                continue
            attacking_group_ids.append(group.id)

        if attacking_group_ids:
            assault_map[sid] = attacking_group_ids

    state.ongoing_shelter_assaults = assault_map

    # Добавляем битвы в pending_battles
    for shelter_id, attacking_group_ids in assault_map.items():
        shelter = state.shelters[shelter_id]
        sector_id = shelter.sector_id
        monster_group = state.monster_groups.get(shelter.occupied_by)
        if monster_group is None:
            continue
        members = monster_group_members(state, monster_group)
        if not members:
            continue

        # Агрегируем всех людей из всех атакующих групп
        all_attackers: list = []
        for gid in attacking_group_ids:
            group = state.human_groups.get(gid)
            if group is None:
                continue
            for member_id in group.members:
                npc = next((n for n in state.humans if n.id == member_id), None)
                if npc and npc.status not in (EntityStatus.DEAD, EntityStatus.EXILED):
                    all_attackers.append(npc)

        if not all_attackers:
            continue

        # Условие C: монстры-защитники в убежище имеют defender_ambush=True
        pending_battles.append({
            "sector_id": sector_id,
            "attackers": all_attackers,
            "defenders": members,
            "attacker_is_monster": False,
            "defender_is_monster": True,
            "attacker_group_id": None,  # агрегированные группы
            "defender_group_id": shelter.occupied_by,
            "attacker_monster_group_id": None,
            "defender_monster_group_id": shelter.occupied_by,
            "attacker_ambush": False,  # люди не в засаде
            "defender_ambush": True,  # условие C: монстры в убежище = засада
            "relation": 0,
            "feed_corpse_id": None,
            "force_no_retreat": True,  # условие B: бой до исхода
            "emission_shelter_assault": True,
            "shelter_id": shelter_id,
        })


def stale_shelter_occupied_knowledge(state, shelter_id: int, hour: int) -> None:
    """Условие D: знание "занято монстрами" устаревает после зачистки (§17.3).
    Не мутируя факт (#16), добавляем новый факт с valid_until = hour.
    """
    from zonesim.knowledge.fact import KnowledgeType

    for kb in state.knowledge_bases.values():
        for fact in kb.facts:
            if (
                fact.fact_type == KnowledgeType.SHELTER_OCCUPIED
                and fact.subject_id == shelter_id
            ):
                # Помечаем как истёкший (не мутируем, ставим valid_until)
                if not fact.valid_until or fact.valid_until > hour:
                    fact.valid_until = hour
                    state.news_manager.create_event(
                        hour=hour, minute=0, sector_id=fact.payload.get("sector_id", 0),
                        event_type="shelter_knowledge", participants=[], result="stale",
                        importance=10,
                        summary=f"Знание об укрытии {shelter_id} устарело (зачищено)",
                        details={"shelter_id": shelter_id},
                    )
                    break


def group_can_create_shelter(state, group, members: list) -> bool:
    """Проверяет наличие набора для убежища (§7.10).

    Нерасходный предмет: базово есть у всех людей, не тратится.
    Кулдаун на уровне группы: не чаще одного убежища за 12 часов.
    """
    from zonesim.world.item import ItemType

    # Проверка: хотя бы один NPC имеет набор
    has_kit = any(
        state.items.get(item_id) and state.items[item_id].type is ItemType.SHELTER_KIT
        for npc in members
        for item_id in npc.inventory
    )
    if not has_kit:
        return False

    # Кулдаун на уровне группы
    if state.time.hour - group.last_shelter_hour < 12:
        return False

    return True
