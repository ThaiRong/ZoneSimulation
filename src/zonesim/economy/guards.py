"""Охрана базы: экипировка, спавн, ротация. (§7.14)"""

from __future__ import annotations

from typing import TYPE_CHECKING

from zonesim.core.config import DEFAULT_GUARDS_PER_BASE
from zonesim.world.entity import EntityStatus, HumanNPC

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState


GUARD_ROTATION_HEALTH = 0.5    # ниже этого доли здоровья — смена
GUARD_RECOVERY_PER_DAY = 0.5   # лазарет базы лечит 50% в сутки
GUARDS_PER_BASE = DEFAULT_GUARDS_PER_BASE  # штат охраны базы


def equip_guard(state, npc: HumanNPC, catalog) -> None:
    """Охранник базы получает лучшее оружие и броню из каталога,
    много патронов и аптечек — бесплатно, за счёт группировки.
    """
    for item_id in (npc.equipped_weapon_id, npc.equipped_armor_id):
        item = state.items.get(item_id)
        if item is not None and item_id in npc.inventory:
            npc.inventory.remove(item_id)
        state.items.pop(item_id, None)
    weapon_entry = max(
        (e for e in catalog.entries() if e["category"] == "weapon"),
        key=lambda e: (e["base_damage"], e["base_value"]),
    )
    armor_entry = max(
        (e for e in catalog.entries() if e["category"] == "body_armor"),
        key=lambda e: (e["armor_factor"], e["base_value"]),
    )
    from zonesim.world.item import spawn_catalog_item, sync_npc_from_items
    weapon = spawn_catalog_item(state, catalog, weapon_entry["id"], npc.id)
    armor = spawn_catalog_item(state, catalog, armor_entry["id"], npc.id)
    npc.equipped_weapon_id = weapon.id
    npc.equipped_armor_id = armor.id
    spawn_catalog_item(state, catalog, weapon_entry["ammo_type"], npc.id, quantity=60)
    for _ in range(3):
        spawn_catalog_item(state, catalog, "gear.medkit.sanitar2", npc.id)
    sync_npc_from_items(state, npc)


def spawn_guard(state, next_human_id_ref: list, wounded: HumanNPC, name: str,
                reserve_for: int | None, catalog) -> HumanNPC:
    """Спавнит нового охранника на замену раненому. (§7.14)"""
    guard = HumanNPC(
        id=next_human_id_ref[0],
        faction=wounded.faction,
        sector_id=wounded.sector_id,
        name=name,
        attack=55, defense=55, attentiveness=55, bravery=70,
        is_stationary=True, stationary_role="guard",
        money=0,
    )
    next_human_id_ref[0] += 1
    guard.reserve_for = reserve_for
    state.stationary_humans.append(guard)
    equip_guard(state, guard, catalog)
    return guard


def process_guard_rotation(state, hour: int, catalog) -> None:
    """Раненый охранник лечится и заменяется резервистом; погибших
    группировка восполняет новобранцами.

    Гарантирует минимум GUARDS_PER_BASE активных охранников на базе
    (даже когда некоторые на лечении).
    """
    if hour % 24 != 0:
        return
    guards = [
        n for n in state.stationary_humans
        if n.stationary_role == "guard"
    ]
    by_sector: dict[int, list[HumanNPC]] = {}
    for npc in guards:
        by_sector.setdefault(npc.sector_id, []).append(npc)

    for sector_id, sector_guards in by_sector.items():
        # Считаем активных (не на лечении)
        active_count = sum(
            1 for g in sector_guards
            if g.status == EntityStatus.ACTIVE
        )
        for guard in sector_guards:
            if getattr(guard, "on_treatment", False):
                guard.health = min(
                    guard.max_health,
                    guard.health + int(guard.max_health * GUARD_RECOVERY_PER_DAY),
                )
                if guard.health >= guard.max_health:
                    guard.on_treatment = False
                    guard.status = EntityStatus.ACTIVE
                    reserves = [
                        n for n in by_sector.get(sector_id, [])
                        if getattr(n, "reserve_for", None) == guard.id
                        and not getattr(n, "on_treatment", False)
                        and n.status not in (EntityStatus.EXILED, EntityStatus.DEAD)
                    ]
                    for reserve in reserves:
                        reserve.status = EntityStatus.EXILED  # резервист убыл
                    state.news_manager.create_event(
                        hour=hour, minute=0, sector_id=sector_id,
                        event_type="guard_returned", participants=[guard.id],
                        result="returned", importance=25,
                        summary=f"Охранник {guard.id} вернулся на пост после лечения",
                        details={"guard_id": guard.id},
                    )
            elif (
                guard.status == EntityStatus.ACTIVE
                and guard.health_share <= GUARD_ROTATION_HEALTH
                and not getattr(guard, "on_treatment", False)
                and not any(
                    getattr(n, "reserve_for", None) == guard.id
                    and n.status not in (EntityStatus.DEAD, EntityStatus.EXILED)
                    for n in guards
                )
                # Не отправляем на лечение, если это приведёт к падению ниже
                # минимума (с учётом одного охранника на лечении)
                and (active_count - 1) >= GUARDS_PER_BASE - 1
            ):
                guard.on_treatment = True
                guard.status = EntityStatus.SLEEPING
                reserve = spawn_guard(
                    state, [state.next_human_id], guard, "Резервист",
                    guard.id, catalog
                )
                state.next_human_id = reserve.id + 1
                state.news_manager.create_event(
                    hour=hour, minute=0, sector_id=sector_id,
                    event_type="guard_replacement",
                    participants=[guard.id, reserve.id], result="replaced",
                    importance=30,
                    summary=(
                        f"Раненый охранник {guard.id} ушёл лечиться,"
                        f" пост занял резервист {reserve.id}"
                    ),
                    details={"guard_id": guard.id, "reserve_id": reserve.id},
                )

    # восполнение погибших: на каждой базе держим штат охраны
    for sector in state.sectors.values():
        if not sector.is_faction_start:
            continue
        roster = [
            n for n in state.stationary_humans
            if n.stationary_role == "guard"
            and n.sector_id == sector.id
            and n.status == EntityStatus.ACTIVE
            and getattr(n, "reserve_for", None) is None
        ]
        while len(roster) < GUARDS_PER_BASE:
            template = roster[0] if roster else next(
                (n for n in state.stationary_humans
                 if n.stationary_role == "trader" and n.sector_id == sector.id),
                None,
            )
            faction = template.faction if template else sector.controller_faction or "Бродяги"
            recruit = HumanNPC(
                id=state.next_human_id,
                faction=faction,
                sector_id=sector.id,
                name="Охранник-новобранец",
                attack=55, defense=55, attentiveness=55, bravery=70,
                is_stationary=True, stationary_role="guard",
                money=0,
            )
            state.next_human_id += 1
            state.stationary_humans.append(recruit)
            equip_guard(state, recruit, catalog)
            roster.append(recruit)
            state.news_manager.create_event(
                hour=hour, minute=0, sector_id=sector.id,
                event_type="guard_recruited", participants=[recruit.id],
                result="recruited", importance=25,
                summary=f"Группировка «{faction}» пополнила охрану базы новобранцем {recruit.id}",
                details={"guard_id": recruit.id, "faction": faction},
            )
