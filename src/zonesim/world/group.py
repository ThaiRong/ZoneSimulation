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
    last_shelter_hour: int = -100  # последнее создание убежища (§7.10, кулдаун 12ч)
    target_sector_id: int | None = None  # целевой сектор для RESEARCH/HELP/EXIT

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

    def is_comfort_sleep_possible(
        self,
        npcs: dict[int, HumanNPC],
        stationary: dict[int, HumanNPC],
        shelters: dict[int, object],
        temp_shelters: dict[int, object],
        sectors: dict[int, object],
        sector_id: int,
        faction: str | None = None,
    ) -> bool:
        """Комфортный сон: группа в убежище/базе или есть охранник/дежурный. (§14.1)

        Условия комфорта (любое из):
        1. Группа находится в секторе базы своей/союзной/нейтральной фракции
           (постоянное убежище)
        2. Есть активный Shelter (временное) в секторе группы
        3. Есть активный StormShelter в секторе
        4. Есть активный стационарный охранник в секторе
        5. Есть член группы, дежурящий (guard_schedule, бодрствует)
        """
        # 1. Проверка базы фракции
        if faction:
            for sid, sector in sectors.items():
                if sid == sector_id and getattr(sector, "is_faction_start", False):
                    # Это стартовый сектор — проверяем контроллера
                    controller = getattr(sector, "controller_faction", None)
                    if controller is None or controller == faction:
                        return True

        # 2. Проверка Shelter (временных убежищ) в секторе
        for shelter in temp_shelters.values():
            if hasattr(shelter, "sector_id") and shelter.sector_id == sector_id:
                if hasattr(shelter, "destroyed") and shelter.destroyed:
                    continue
                if hasattr(shelter, "is_active") and not shelter.is_active:
                    continue
                if hasattr(shelter, "participant_count") and shelter.participant_count > 0:
                    return True

        # 3. Проверка StormShelter (стационарных убежищ) в секторе
        for shelter in shelters.values():
            if hasattr(shelter, "sector_id") and shelter.sector_id == sector_id:
                # StormShelter доступен всем
                if type(shelter).__name__ == "StormShelter":
                    return True

        # 4. Стационарные охранники в секторе
        for npc_id, npc in stationary.items():
            if (
                npc.stationary_role == "guard"
                and npc.status == EntityStatus.ACTIVE
                and npc.sector_id == sector_id
            ):
                return True

        # 5. Дежурный из группы (guard_schedule)
        for entry in self.guard_schedule:
            if entry.get("npc_id") in self.members:
                npc = npcs.get(entry["npc_id"])
                if npc and npc.status == EntityStatus.ACTIVE and npc.sector_id == sector_id:
                    return True

        # 6. Бодрствующий член группы (охраняет)
        for mid in self.members:
            npc = npcs.get(mid)
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
