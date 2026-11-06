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
    last_combat_hour: int = -100  # последний бой группы (передышка §11.1)
    last_distress_hour: int = -100  # последний сигнал бедствия (§16.10)

    @property
    def active_member_ids(self) -> list[int]:
        """Члены группы; пленные хранятся отдельно и сюда не входят."""
        return list(self.members)

    @property
    def member_count(self) -> int:
        return len(self.members)

    def add_member(self, npc_id: int) -> None:
        if npc_id not in self.members and self.member_count < 4:
            self.members.append(npc_id)

    def remove_member(self, npc_id: int) -> None:
        if npc_id in self.members:
            self.members.remove(npc_id)
            if self.leader_id == npc_id:
                self.leader_id = None

    def select_leader(self, npcs: dict[int, HumanNPC]) -> None:
        """Выбирает лидера по храбрости и внимательности (§7.5)."""
        candidates = [
            mid for mid in self.members
            if mid in npcs and getattr(npcs[mid], "status", EntityStatus.ACTIVE)
            not in (EntityStatus.DEAD, EntityStatus.EXILED, EntityStatus.PRISONER)
        ]
        awake = [
            mid for mid in candidates
            if getattr(npcs[mid], "status", EntityStatus.ACTIVE) == EntityStatus.ACTIVE
        ]
        if awake:
            candidates = awake
        if not candidates:
            self.leader_id = None
            return
        self.leader_id = max(
            candidates,
            key=lambda mid: npcs[mid].bravery + npcs[mid].attentiveness,
        )

    def is_comfort_sleep_possible(self, npcs: dict[int, HumanNPC], sector_id: int) -> bool:
        """Комфортный сон: база с охранником или убежище. (§14.1)
        
        Охранник может быть как членом группы, так и внешним NPC 
        (например, стационарным охранником базы).
        """
        # Проверяем членов группы
        for mid in self.members:
            npc = npcs.get(mid)
            if npc and npc.status == EntityStatus.ACTIVE and npc.sector_id == sector_id:
                return True

        # Если все спят/бессознательны — проверяем внешних NPC в том же секторе
        for npc_id, npc in npcs.items():
            if npc_id in self.members:
                continue
            if npc and npc.status == EntityStatus.ACTIVE and npc.sector_id == sector_id:
                return True

        return False

    def has_awake_member(self, npcs: dict[int, HumanNPC]) -> bool:
        return any(
            mid in npcs and npcs[mid].status == EntityStatus.ACTIVE
            for mid in self.members
        )


@dataclass
class MonsterGroup:
    """Группа монстров. Размер ограничен видом. (§13)"""
    id: int
    members: list[int] = field(default_factory=list)  # id Monster
    sector_id: int = 0
    species: str = ""
    intention: str = "roam"
    target_id: int | None = None
    target_sector_id: int | None = None
    target_memory_hour: int = 0
    home_sector_id: int | None = None
    status: str = "active"  # active, dispersing
    last_combat_hour: int = -100  # последний бой группы (передышка §11.1)

    @property
    def member_count(self) -> int:
        return len(self.members)
