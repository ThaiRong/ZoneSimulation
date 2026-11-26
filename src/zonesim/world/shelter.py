"""Временные убежища (Shelter) и стационарные укрытия (StormShelter).

Основано на §7.10 и §7.16 ТЗ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from zonesim.world.entity import EntityStatus

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
