"""Сквозные проверки предметов, инвентаря и добычи (этап 8, часть 1)."""

from zonesim.combat import CombatSystem
from zonesim.combat.base import Combatant
from zonesim.combat.loot import Corpse, LootManager
from zonesim.persistence.serialization import state_to_dict
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.item import Item, ItemType


def _place_on_corpse(engine, corpse, item):
    engine.state.items[item.id] = item
    item.location = f"corpse:{corpse.id}"
    corpse.items.append(item.id)
    engine.state.next_item_id = max(engine.state.next_item_id, item.id + 1)
    return item


def _assert_single_item_location(engine):
    state = engine.state
    humans = {npc.id: npc for npc in state.humans + state.stationary_humans}
    corpses = {corpse.id: corpse for corpse in state.corpses}
    for item in state.items.values():
        assert item.condition >= 0
        assert item.quantity >= 0
        if item.owner_id is not None:
            assert item.location == "inventory"
            assert item.id in humans[item.owner_id].inventory
        elif item.location.startswith("corpse:"):
            corpse_id = int(item.location.split(":", 1)[1])
            assert item.id in corpses[corpse_id].items
        else:
            raise AssertionError(f"У предмета {item.id} нет физического местонахождения")


def test_starting_equipment_has_unique_ids_and_single_owner():
    engine = SimulationEngine(seed=11)
    humans = engine.state.humans + engine.state.stationary_humans
    guards = [n for n in humans if n.stationary_role == "guard"]

    expected_items = (len(humans) - len(guards)) * 5 + len(guards) * 9
    assert len(engine.state.items) == expected_items
    assert len({item.id for item in engine.state.items.values()}) == len(engine.state.items)
    for npc in humans:
        if npc.stationary_role == "guard":
            # стандартные 5 базовых (было 4) + доп. выдача охраны
            assert len(npc.inventory) == 9
            assert npc.ammo == 60 + 12  # стандартные 12 + выдача 60
            assert npc.medicines == 1 + 3
        else:
            assert len(npc.inventory) == 5  # +shelter.kit.basic
            assert npc.ammo == 12
            assert npc.medicines == 1
        assert npc.money == 100
        weapon = engine.state.items[npc.equipped_weapon_id]
        armor = engine.state.items[npc.equipped_armor_id]
        assert weapon.type is ItemType.WEAPON
        assert armor.type is ItemType.ARMOR
        assert weapon.owner_id == npc.id
        assert armor.owner_id == npc.id
    _assert_single_item_location(engine)


def test_death_moves_all_property_to_corpse_without_duplicates():
    engine = SimulationEngine(seed=12)
    npc = engine.state.humans[0]
    original_items = set(npc.inventory)
    engine._create_item(ItemType.ARTIFACT, "Артефакт", 300.0, npc.id)
    original_items.update(npc.inventory)

    corpse = engine._create_corpse(npc, hour=9)

    assert npc.inventory == []
    assert npc.money == 0
    assert npc.equipped_weapon_id is None
    assert npc.equipped_armor_id is None
    assert corpse.money == 100
    assert set(corpse.items) == original_items
    assert corpse.monster_parts == []
    for item_id in corpse.items:
        item = engine.state.items[item_id]
        assert item.owner_id is None
        assert item.location == f"corpse:{corpse.id}"
    _assert_single_item_location(engine)


def test_leader_distributes_equipment_by_need_and_keeps_money():
    engine = SimulationEngine(seed=13)
    group = next(group for group in engine.state.human_groups.values() if group.member_count >= 2)
    members = [npc for npc in engine.state.humans if npc.id in group.members]
    leader = next(npc for npc in members if npc.id == group.leader_id)
    next(npc for npc in members if npc.id != leader.id)
    weak_member = min(members, key=lambda npc: engine.state.items[npc.equipped_weapon_id].condition)
    for npc in members:
        engine.state.items[npc.equipped_weapon_id].condition = 30 if npc is weak_member else 100
    ammo_owner = min(
        members,
        key=lambda npc: sum(
            engine.state.items[item_id].quantity for item_id in npc.inventory
            if engine.state.items[item_id].type is ItemType.AMMO
        ),
    )
    for npc in members:
        for item_id in npc.inventory:
            item = engine.state.items[item_id]
            if item.type is ItemType.AMMO:
                item.quantity = 2 if npc is ammo_owner else 8

    corpse = Corpse(900, 9999, "human", group.sector_id, money=77)
    engine.state.corpses = [corpse]
    weapon = _place_on_corpse(engine, corpse, Item(
        9000, ItemType.WEAPON, "Хорошее оружие", base_value=300,
        properties={"damage": 30},
    ))
    ammo = _place_on_corpse(engine, corpse, Item(
        9001, ItemType.AMMO, "Боеприпасы", base_value=5, quantity=6,
    ))
    _place_on_corpse(engine, corpse, Item(
        9002, ItemType.ARTIFACT, "Артефакт", base_value=250,
    ))

    result = engine._process_corpse_action(group, hour=10)

    assert result["success"] is True
    assert leader.money == 177
    assert weapon.id in weak_member.inventory
    assert weak_member.equipped_weapon_id == weapon.id
    assert ammo.id in ammo_owner.inventory
    assert 9002 in leader.inventory
    assert corpse.items == []
    assert corpse.money == 0
    assert corpse.status == "looted"
    _assert_single_item_location(engine)


def test_harvesting_monster_parts_takes_hour_and_preserves_condition():
    engine = SimulationEngine(seed=14)
    group = next(engine.state.human_groups.values().__iter__())
    members = [npc for npc in engine.state.humans if npc.id in group.members]
    leader = next(npc for npc in members if npc.id == group.leader_id)
    corpse = Corpse(
        900, 1000, "LargeMigrator", group.sector_id,
        monster_parts=LootManager.available_monster_parts(engine.state.monsters[0]),
        body_condition=42,
    )
    corpse.monster_parts = LootManager.PARTS_BY_SPECIES["LargeMigrator"][0] * [
        {"type": "monster_parts_rare", "base_value": 100.0}
    ]
    engine.state.corpses = [corpse]
    stamina_before = {npc.id: npc.stamina for npc in members}
    inventory_before = len(leader.inventory)

    engine._phase7_actions(engine.state.time.hour, is_night=False)

    parts = [
        engine.state.items[item_id] for item_id in leader.inventory
        if engine.state.items[item_id].type is ItemType.MONSTER_PART
    ]
    assert len(parts) == 3
    assert len(leader.inventory) == inventory_before + 3
    assert all(part.condition == 42 for part in parts)
    assert all(part.properties["part_type"] == "monster_parts_rare" for part in parts)
    assert corpse.monster_parts == []
    assert corpse.status == "looted"
    assert all(npc.stamina == stamina_before[npc.id] for npc in members)
    assert any(event.event_type == "harvest" for event in engine.state.news_manager.events)
    _assert_single_item_location(engine)


def test_human_corpse_has_no_exportable_parts():
    engine = SimulationEngine(seed=15)
    npc = engine.state.humans[0]
    corpse = engine._create_corpse(npc, hour=10)
    result = LootManager.harvest_monster_parts(
        corpse, npc, engine.state.items, engine.state.next_item_id
    )
    assert result["success"] is False
    assert result["reason"] == "parts_unavailable"


def test_armor_condition_decreases_after_damage():
    attacker = Combatant(1, "A", True, attack=100, weapon_damage=40, ammo=10, bravery=100)
    defender = Combatant(2, "D", True, defense=1, health=100, ammo=10, bravery=100)
    result = CombatSystem([attacker], [defender], max_rounds=1).fight(lambda: 0.1)

    armor_wear = next(
        entry for entry in result.equipment_wear
        if entry["item_type"] == "armor" and entry["id"] == defender.id
    )
    assert armor_wear["new_condition"] < armor_wear["old_condition"]
    assert defender.armor_condition == armor_wear["new_condition"]


def test_items_and_corpse_survive_save_load(tmp_path):
    engine = SimulationEngine(seed=16, save_directory=tmp_path)
    npc = engine.state.humans[0]
    engine._create_corpse(npc, hour=7)
    engine.save("items")

    loaded = SimulationEngine.load("items", tmp_path)

    assert state_to_dict(loaded.state) == state_to_dict(engine.state)
    assert all(isinstance(item.type, ItemType) for item in loaded.state.items.values())
    assert loaded.state.next_item_id == engine.state.next_item_id
    _assert_single_item_location(loaded)
