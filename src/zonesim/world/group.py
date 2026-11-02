"""Модели групп людей и монстров. Основано на §7.5 и §13 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field

from zonesim.world.entity import EntityStatus, HumanNPC, Monster


@dataclass
class GroupMembership:
    """Информация о членстве сущности в группе."""
    group_id: int
    joined_hour: int = 0


@dataclass
class HumanGroup:
    """Группа людей: 1-4 активных, пленные отдельно. (§7.5)"""
    id: int
    members: list[int] = field(default_factory=list)  # id HumanNPC
    sector_id: int = 0
    intention: str = ""  # выбранное намерение
    leader_id: int | None = None
    prisoners: list[int] = field(default_factory=list)  # id HumanNPC в плену
    guard_schedule: list[dict] = field(default_factory=list)  # [{"npc_id": x, "start_hour": y, "end_hour": z}]
    comfort: bool = False  # комфортный ли сон

    @property
    def active_member_ids(self) -> list[int]:
        return [m for m in self.members if self._is_active(m)]

    @property
    def member_count(self) -> int:
        return len(self.active_member_ids)

    def _is_active(self, npc_id: int) -> bool:
        return True  # placeholder

    def add_member(self, npc_id: int) -> None:
        if npc_id not in self.members and self.member_count < 4:
            self.members.append(npc_id)

    def remove_member(self, npc_id: int) -> None:
        if npc_id in self.members:
            self.members.remove(npc_id)
            if self.leader_id == npc_id:
                self.leader_id = None

    def select_leader(self, npcs: dict[int, HumanNPC]) -> None:
        """Выбирает лидера по храбрости, внимательности и фракции. (§9.2)"""
        active = self.active_member_ids
        if not active:
            self.leader_id = None
            return
        self.leader_id = max(active, key=lambda mid: npcs[mid].bravery + npcs[mid].attentiveness)

    def is_comfort_sleep_possible(self, npcs: dict[int, HumanNPC], sector_id: int) -> bool:
        """Комфортный сон: база с охранником или убежище. (§14.1)
        
        Охранник может быть как членом группы, так и внешним NPC 
        (например, стационарным охранником базы).
        """
        # Проверяем членов группы
        for mid in self.members:
            npc = npcs.get(mid)
            if npc and npc.status not in (EntityStatus.SLEEPING, EntityStatus.UNCONSCIOUS):
                return True

        # Если все спят/бессознательны — проверяем внешних NPC в том же секторе
        for npc_id, npc in npcs.items():
            if npc_id in self.members:
                continue
            if npc and npc.status not in (EntityStatus.SLEEPING, EntityStatus.UNCONSCIOUS):
                return True

        return False

    def has_awake_member(self) -> bool:
        return True  # placeholder


@dataclass
class MonsterGroup:
    """Группа монстров. Размер ограничен видом. (§13)"""
    id: int
    members: list[int] = field(default_factory=list)  # id Monster
    sector_id: int = 0
    species: str = ""
    target_memory_hour: int = 0
    status: str = "active"  # active, dispersing

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def combat_power(self) -> float:
        return sum(m.attack * m.health / m.max_health for m in self.members) if self.members else 0.0
