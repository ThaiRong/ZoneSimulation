"""Группы: логика работы с комплектами и лидерами. Основано на §7.5 ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zonesim.world.item import ItemType

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState
    from zonesim.world.entity import HumanNPC, Monster
    from zonesim.world.group import HumanGroup, MonsterGroup
    from zonesim.world.item import Item


def group_kit(state, members, item_type: ItemType, predicate=None):
    """Первый подходящий исправный комплект в инвентарях членов группы."""
    for npc in members:
        for item_id in npc.inventory:
            item = state.items.get(item_id)
            if item is None or item.type is not item_type or item.condition <= 0:
                continue
            if predicate is None or predicate(item):
                return npc, item
    return None, None


def active_members(state, group: HumanGroup) -> list[HumanNPC]:
    """Активные члены группы (без мёртвых/пленных/бессознательных)."""
    npcs = {npc.id: npc for npc in state.humans}
    from zonesim.world.entity import EntityStatus
    return [
        npcs[mid] for mid in group.members
        if mid in npcs and npcs[mid].status == EntityStatus.ACTIVE
    ]


def group_leader(group: HumanGroup, members: list[HumanNPC]) -> HumanNPC:
    """Лидер группы из активных членов."""
    return next((npc for npc in members if npc.id == group.leader_id), members[0])


def monster_group_members(
    state, group: "MonsterGroup", active_only: bool = True
) -> list["Monster"]:
    """Члены монстр-группы. (§7.6)"""
    monsters = {monster.id: monster for monster in state.monsters}
    members = [monsters[member_id] for member_id in group.members if member_id in monsters]
    if active_only:
        from zonesim.world.entity import EntityStatus
        members = [monster for monster in members if monster.status == EntityStatus.ACTIVE]
    return members


def sync_human_groups(state) -> None:
    """Убирает выбывших и удаляет пустые группы, сохраняя инварианты §7.5."""
    from zonesim.world.entity import EntityStatus

    npcs = {npc.id: npc for npc in state.humans}
    for group_id, group in list(state.human_groups.items()):
        for member_id in list(group.members):
            npc = npcs.get(member_id)
            if npc is None or npc.status in (EntityStatus.DEAD, EntityStatus.EXILED):
                group.remove_member(member_id)
                if npc is not None:
                    npc.group_id = None
        if not group.members:
            del state.human_groups[group_id]
            continue
        group.sector_id = npcs[group.members[0]].sector_id
        if group.leader_id not in group.members:
            group.select_leader(npcs)


def sync_monster_groups(state) -> None:
    """Синхронизирует монстр-группы с реальным составом. (§7.6)"""
    from zonesim.monsters.behavior import species_value
    from zonesim.world.entity import EntityStatus
    from zonesim.world.group import MonsterGroup

    monsters = {monster.id: monster for monster in state.monsters}
    gone = (EntityStatus.DEAD, EntityStatus.EXILED)
    for group_id, group in list(state.monster_groups.items()):
        group.members = [
            member_id for member_id in group.members
            if member_id in monsters and monsters[member_id].status not in gone
        ]
        if not group.members:
            del state.monster_groups[group_id]
            continue
        members = [monsters[member_id] for member_id in group.members]
        group.sector_id = members[0].sector_id
        group.species = species_value(members[0])
        if group.home_sector_id is None:
            group.home_sector_id = members[0].home_sector_id

    for monster in state.monsters:
        if monster.status in gone:
            monster.group_id = None
            continue
        if monster.group_id in state.monster_groups:
            continue
        monster.group_id = None
        species = species_value(monster)
        max_size = monster.species_params.get("normal_group_size", (1, 1))[1]
        group = next(
            (
                candidate
                for candidate in state.monster_groups.values()
                if candidate.species == species
                and candidate.sector_id == monster.sector_id
                and candidate.member_count < max_size
            ),
            None,
        )
        if group is None:
            group = MonsterGroup(
                id=state.next_monster_group_id,
                sector_id=monster.sector_id,
                species=species,
                home_sector_id=monster.home_sector_id,
            )
            state.next_monster_group_id += 1
            state.monster_groups[group.id] = group
        group.members.append(monster.id)
        monster.group_id = group.id

