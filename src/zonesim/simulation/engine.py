"""Главный движок симуляции. Связывает все модули в почасовой цикл (§8 ТЗ)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zonesim.core.time import GameTime, SeededRNG
from zonesim.world.sector import Sector
from zonesim.world.entity import HumanNPC, Monster, MonsterSpecies, EntityStatus
from zonesim.combat.loot import Corpse, EquipmentManager, LootManager
from zonesim.world.item import Item, ItemType, give_item, place_item_on_corpse

from zonesim.core.config import GameConfig
from zonesim.generation.worldgen import generate_world
from zonesim.generation.migration import MigrationState, process_migration

from zonesim.combat import CombatSystem
from zonesim.combat.base import Combatant, CombatFactory
from zonesim.combat.unconscious import calculate_unconscious_chance, resolve_unconscious_check

from zonesim.actions.detection import check_anomaly_detection

from zonesim.ai import (
    CAPTURE,
    DESTROY,
    EXIT,
    EXPLORE,
    RESEARCH,
    REST,
    SLEEP,
    IntentionContext,
    choose_explore_target,
    choose_intention,
    known_anomaly_sectors,
    next_step_towards,
)

from zonesim.needs.sleep import (
    STAMINA_COST_AWAKE,
    STAMINA_COST_MOVEMENT,
    STAMINA_COST_RESEARCH,
    human_sleep_recover,
    update_stamina,
)

from zonesim.anomalies.research import research_anomaly

from zonesim.world.group import HumanGroup, MonsterGroup
from zonesim.world.catalog import ItemCatalog
from zonesim.monsters.behavior import choose_group_intention, select_weakest_target, species_value
from zonesim.monsters.feed import FeedManager
from zonesim.monsters.hunt import should_pursue

from zonesim.economy.contracts import ContractManager
from zonesim.economy.trade import CaptureManager, ImportExportManager

from zonesim.anomalies.core import Anomaly as AnomalyEntity, AnomalyType, AnomalyStatus
from zonesim.anomalies.damage import apply_anomaly_damage, check_anomaly_contact
from zonesim.anomalies.artifact import ArtifactManager
from zonesim.anomalies.migration import check_anomaly_migration
from zonesim.anomalies.destroy import attempt_destroy_anomaly, get_anomaly_parts_after_destruction

from zonesim.monsters.migration import MonsterMigrationManager
from zonesim.monsters.hunt import calculate_hunt_chance

from zonesim.relations.personal import PersonalRelations
from zonesim.relations.factions import FactionRelations
from zonesim.relations.development import DevelopmentManager, ExileManager, FactionChangeManager
from zonesim.relations.news import NewsManager

from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType
from zonesim.persistence import SaveManager


CAPTURE_KIT_REF = {
    "territorial_predator": "capture.kit.predator",
    "scavenger_pack": "capture.kit.scavenger",
    "large_migrator": "capture.kit.migrator",
}


@dataclass
class SimulationState:
    """Состояние симуляции."""
    time: GameTime = field(default_factory=GameTime)
    rng: SeededRNG = field(default_factory=lambda: SeededRNG(42))
    sectors: dict[int, Sector] = field(default_factory=dict)
    humans: list[HumanNPC] = field(default_factory=list)  # только мобильные NPC
    stationary_humans: list[HumanNPC] = field(default_factory=list)
    human_groups: dict[int, HumanGroup] = field(default_factory=dict)
    monsters: list[Monster] = field(default_factory=list)
    monster_groups: dict[int, MonsterGroup] = field(default_factory=dict)
    anomalies: dict[int, AnomalyEntity] = field(default_factory=dict)
    artifacts: ArtifactManager = field(default_factory=ArtifactManager)
    corpses: list[Corpse] = field(default_factory=list)
    items: dict[int, Item] = field(default_factory=dict)

    contracts: ContractManager = field(default_factory=ContractManager)
    import_export: ImportExportManager = field(default_factory=ImportExportManager)

    personal_relations: PersonalRelations = field(default_factory=PersonalRelations)
    faction_relations: FactionRelations = field(default_factory=FactionRelations)
    development: DevelopmentManager = field(default_factory=DevelopmentManager)
    exile_manager: ExileManager = field(default_factory=ExileManager)
    faction_change_manager: FactionChangeManager = field(default_factory=FactionChangeManager)
    news_manager: NewsManager = field(default_factory=NewsManager)

    knowledge_bases: dict[int, KnowledgeBase] = field(default_factory=dict)

    stashs: list[Stash] = field(default_factory=list)
    shelter_count: int = 0
    trader_stock: dict[int, dict[str, int]] = field(default_factory=dict)  # npc торговца -> item_ref -> количество

    migration_state: MigrationState = field(default_factory=MigrationState)
    monster_migration: MonsterMigrationManager = field(default_factory=MonsterMigrationManager)

    next_human_id: int = 0
    next_monster_id: int = 0
    next_group_id: int = 0
    next_monster_group_id: int = 0
    next_anomaly_id: int = 0
    next_stash_id: int = 0
    next_corpse_id: int = 0
    next_item_id: int = 0

    visit_memory: dict[int, dict[int, int]] = field(default_factory=dict)  # npc_id -> sector -> hour

    config: dict = field(default_factory=dict)


class SimulationEngine:
    """Главный движок симуляции. Интегрирует все модули."""

    def __init__(self, seed: int = 42, config: dict | None = None, save_directory=None):
        self.state = SimulationState(rng=SeededRNG(seed), config=config or {})
        self.save_manager = SaveManager(save_directory) if save_directory is not None else None
        self.catalog = ItemCatalog.load((self.state.config or {}).get("catalog_path"))
        self._home_cache: dict[str, int | None] = {}
        self._border_dist: dict[int, int] | None = None
        self._pending_battles: list[dict] = []
        self._combat_human_ids: set[int] = set()
        self._combat_monster_ids: set[int] = set()
        self._moved_human_ids: set[int] = set()
        self._moved_monster_ids: set[int] = set()
        self._feeding_claims: dict[int, int] = {}
        self._feed_manager = FeedManager()
        self._generate_world()

    @classmethod
    def from_state(cls, state: SimulationState, save_directory=None) -> SimulationEngine:
        engine = cls.__new__(cls)
        engine.state = state
        engine.save_manager = SaveManager(save_directory) if save_directory is not None else None
        engine.catalog = ItemCatalog.load((state.config or {}).get("catalog_path"))
        engine._home_cache = {}
        engine._border_dist = None
        engine._pending_battles = []
        engine._combat_human_ids = set()
        engine._combat_monster_ids = set()
        engine._moved_human_ids = set()
        engine._moved_monster_ids = set()
        engine._feeding_claims = {}
        engine._feed_manager = FeedManager()
        return engine

    @classmethod
    def load(cls, slot: str, directory) -> SimulationEngine:
        manager = SaveManager(directory)
        return cls.from_state(manager.load(slot), save_directory=directory)

    def save(self, slot: str):
        if self.save_manager is None:
            raise RuntimeError("Каталог сохранений не настроен")
        return self.save_manager.save(slot, self.state)

    def _generate_world(self) -> None:
        """Генерирует мир по seed и config."""
        cfg = self.state.config
        result = generate_world(
            seed=self.state.rng.randint(1, 999999),
            config=cfg if cfg else None,
        )

        self.state.sectors = result["sectors"]
        self.state.humans = result["humans"]
        self.state.stationary_humans = result["stationary_humans"]
        self.state.human_groups = result["human_groups"]
        self.state.monsters = result["monsters"]
        self.state.anomalies = {a.id: a for a in result["anomalies"]}

        # Инициализация ID
        all_humans = self.state.humans + self.state.stationary_humans
        self.state.next_human_id = max((h.id for h in all_humans), default=-1) + 1
        self.state.next_monster_id = max((m.id for m in self.state.monsters), default=0) + 1
        self.state.next_anomaly_id = max((a.id for a in self.state.anomalies.values()), default=0) + 1
        self.state.next_group_id = max(self.state.human_groups, default=-1) + 1
        for npc in all_humans:
            self._give_starting_equipment(npc)
        self._init_trader_stock()
        self._sync_monster_groups()

    def _sync_monster_groups(self) -> None:
        monsters = {monster.id: monster for monster in self.state.monsters}
        gone = (EntityStatus.DEAD, EntityStatus.EXILED)
        for group_id, group in list(self.state.monster_groups.items()):
            group.members = [
                member_id for member_id in group.members
                if member_id in monsters and monsters[member_id].status not in gone
            ]
            if not group.members:
                del self.state.monster_groups[group_id]
                continue
            members = [monsters[member_id] for member_id in group.members]
            group.sector_id = members[0].sector_id
            group.species = species_value(members[0])
            if group.home_sector_id is None:
                group.home_sector_id = members[0].home_sector_id

        for monster in self.state.monsters:
            if monster.status in gone:
                monster.group_id = None
                continue
            if monster.group_id in self.state.monster_groups:
                continue
            monster.group_id = None
            species = species_value(monster)
            max_size = monster.species_params.get("normal_group_size", (1, 1))[1]
            group = next(
                (
                    candidate for candidate in self.state.monster_groups.values()
                    if candidate.species == species and candidate.sector_id == monster.sector_id
                    and candidate.member_count < max_size
                ),
                None,
            )
            if group is None:
                group = MonsterGroup(
                    id=self.state.next_monster_group_id,
                    sector_id=monster.sector_id,
                    species=species,
                    home_sector_id=monster.home_sector_id,
                )
                self.state.next_monster_group_id += 1
                self.state.monster_groups[group.id] = group
            group.members.append(monster.id)
            monster.group_id = group.id

    def _monster_group_members(self, group: MonsterGroup, active_only: bool = True) -> list[Monster]:
        monsters = {monster.id: monster for monster in self.state.monsters}
        members = [monsters[member_id] for member_id in group.members if member_id in monsters]
        if active_only:
            members = [monster for monster in members if monster.status == EntityStatus.ACTIVE]
        return members

    # Наценка торговцев поверх каталога
    TRADE_MARKUP = 1.2
    # Стартовое количество в запасе по категориям
    TRADER_START_QTY = {
        "weapon": 2,
        "body_armor": 2,
        "head_armor": 1,
        "outer_layer": 1,
        "medical": 4,
        "optics": 1,
        "capture_kit": 2,
        "anomaly_destruction_kit": 2,
    }
    TRADER_AMMO_QTY = {"ammo.pistol": 40, "ammo.rifle": 60, "ammo.heavy": 20}

    def _init_trader_stock(self) -> None:
        """Стартовый запас торговцев: импортные позиции каталога. (§16)"""
        for trader in self.state.stationary_humans:
            if trader.stationary_role != "trader":
                continue
            stock: dict[str, int] = {}
            for entry in self.catalog.entries():
                if not entry.get("import_required"):
                    continue
                qty = self.TRADER_AMMO_QTY.get(
                    entry["id"], self.TRADER_START_QTY.get(entry["category"], 1),
                )
                if qty > 0:
                    stock[entry["id"]] = qty
            self.state.trader_stock[trader.id] = stock

    def trade_price(self, item_ref: str, quantity: int = 1) -> float:
        """Цена покупки у торговца: каталог × качество × наценку. (§16)"""
        entry = self.catalog.get(item_ref)
        return round(
            entry["base_value"] * entry.get("quality", 1.0) * self.TRADE_MARKUP * quantity, 1,
        )

    # Скупочная цена ценностей (доля базовой стоимости)
    SELL_PRICE_SHARE = 0.6
    # Семейства комплектов для проактивной закупки: (тип, самая дешёвая модель)
    PROACTIVE_KITS = (
        (ItemType.CAPTURE_KIT, "capture.kit.predator"),
        (ItemType.DESTROY_KIT, "anomaly.kit.subtle"),
    )

    def _purchase_plan(
        self, group: HumanGroup, members: list[HumanNPC], stock: dict[str, int],
    ) -> list[tuple[str, int]]:
        """Приоритетный список покупок группы у торговца."""
        plan: list[tuple[str, int]] = []
        has_medkit = any(
            self.state.items[item_id].type is ItemType.MEDICINE
            for npc in members for item_id in npc.inventory
            if item_id in self.state.items
        )
        if not has_medkit and stock.get("gear.medkit.sanitar2", 0) > 0:
            plan.append(("gear.medkit.sanitar2", 1))
        anomaly = next(
            (
                a for a in self.state.anomalies.values()
                if a.sector_id == group.sector_id and a.status == AnomalyStatus.ACTIVE
            ),
            None,
        )
        if anomaly is not None:
            kit_ref = f"anomaly.kit.{anomaly.anomaly_type.value}"
            owned = any(
                item.properties.get("target_anomaly_type") == anomaly.anomaly_type.value
                for npc in members for item_id in npc.inventory
                if (item := self.state.items.get(item_id)) is not None
                and item.type is ItemType.DESTROY_KIT and item.condition > 0
            )
            if not owned and stock.get(kit_ref, 0) > 0:
                plan.append((kit_ref, 1))
        target = self._capture_target(group)
        if target is not None:
            kit_ref = CAPTURE_KIT_REF.get(species_value(target))
            owned = any(
                item.properties.get("target_species") == species_value(target)
                for npc in members for item_id in npc.inventory
                if (item := self.state.items.get(item_id)) is not None
                and item.type is ItemType.CAPTURE_KIT and item.condition > 0
            )
            if kit_ref and not owned and stock.get(kit_ref, 0) > 0:
                plan.append((kit_ref, 1))
        leader = self._group_leader(group, members)
        weapon = self.state.items.get(leader.equipped_weapon_id)
        ammo_ref = weapon.properties.get("ammo_type") if weapon else None
        if ammo_ref:
            total_ammo = sum(
                self.state.items[item_id].quantity
                for npc in members for item_id in npc.inventory
                if item_id in self.state.items
                and self.state.items[item_id].type is ItemType.AMMO
            )
            if total_ammo < 6 and stock.get(ammo_ref, 0) >= 12:
                plan.append((ammo_ref, 12))
        # проактивная закупка комплектов при свободных деньгах
        for kit_type, default_ref in self.PROACTIVE_KITS:
            owned_any = any(
                self.state.items[item_id].type is kit_type and self.state.items[item_id].condition > 0
                for npc in members for item_id in npc.inventory
                if item_id in self.state.items
            )
            if owned_any or stock.get(default_ref, 0) <= 0:
                continue
            price = self.trade_price(default_ref)
            if leader.money >= price * 1.5:
                plan.append((default_ref, 1))
        return plan

    def _sell_loot(self, leader: HumanNPC, trader: HumanNPC) -> float:
        """Скупка ценностей у лидера группы. (§16.3)"""
        sellable = (
            ItemType.ARTIFACT, ItemType.MONSTER_PART,
            ItemType.ANOMALY_PART, ItemType.LIVE_MONSTER,
        )
        total = 0.0
        for item_id in list(leader.inventory):
            item = self.state.items.get(item_id)
            if item is None or item.type not in sellable:
                continue
            price = round(item.base_value * self.SELL_PRICE_SHARE, 1)
            leader.money += price
            total += price
            self._consume_item(item, [leader])
        if total > 0:
            trader.money = getattr(trader, "money", 0.0) - total
        return total

    def _process_npc_trade(self, hour: int) -> None:
        """Покупки и продажи групп у торговцев в общем секторе. (§16.1)"""
        traders = [
            npc for npc in self.state.stationary_humans
            if npc.stationary_role == "trader" and npc.status == EntityStatus.ACTIVE
        ]
        if not traders:
            return
        for group in self.state.human_groups.values():
            members = self._active_members(group)
            if not members:
                continue
            trader = next(
                (t for t in traders if t.sector_id == group.sector_id), None,
            )
            if trader is None:
                continue
            stock = self.state.trader_stock.setdefault(trader.id, {})
            leader = self._group_leader(group, members)
            for item_ref, quantity in self._purchase_plan(group, members, stock):
                price = self.trade_price(item_ref, quantity)
                if leader.money < price or stock.get(item_ref, 0) < quantity:
                    continue
                stock[item_ref] -= quantity
                leader.money -= price
                trader.money = getattr(trader, "money", 0) + price
                item = self.catalog.create_item(
                    self.state.next_item_id, item_ref, quantity=quantity,
                )
                self.state.next_item_id += 1
                self.state.items[item.id] = item
                give_item(item, leader.id, leader.inventory)
                self._sync_npc_from_items(leader)
            self._sell_loot(leader, trader)

    def _create_item(
        self,
        item_type: ItemType,
        name: str,
        base_value: float,
        owner_id: int | None = None,
        quantity: int = 1,
        properties: dict | None = None,
    ) -> Item:
        item = Item(
            id=self.state.next_item_id,
            type=item_type,
            name=name,
            base_value=base_value,
            quantity=quantity,
            properties=properties or {},
        )
        self.state.next_item_id += 1
        self.state.items[item.id] = item
        if owner_id is not None:
            owner = next(
                npc for npc in self.state.humans + self.state.stationary_humans
                if npc.id == owner_id
            )
            give_item(item, owner_id, owner.inventory)
        return item

    def _give_starting_equipment(self, npc: HumanNPC) -> None:
        if npc.inventory:
            return
        npc.money = 100
        if npc.faction == "Серая лига":
            weapon_ref, armor_ref = "weapon.rifle.sokol", "armor.outer.scout"
        else:
            weapon_ref, armor_ref = "weapon.carbine.k20", "armor.uniform.jacket"
        weapon = self._spawn_catalog_item(weapon_ref, npc.id)
        armor = self._spawn_catalog_item(armor_ref, npc.id)
        npc.equipped_weapon_id = weapon.id
        npc.equipped_armor_id = armor.id
        ammo_ref = weapon.properties.get("ammo_type")
        if ammo_ref:
            self._spawn_catalog_item(ammo_ref, npc.id, quantity=12)
        self._spawn_catalog_item("gear.medkit.sanitar2", npc.id)
        self._sync_npc_from_items(npc)

    def _spawn_catalog_item(self, item_ref: str, owner_id: int, quantity: int = 1) -> Item:
        item = self.catalog.create_item(self.state.next_item_id, item_ref, quantity=quantity)
        self.state.next_item_id += 1
        self.state.items[item.id] = item
        owner = next(
            npc for npc in self.state.humans + self.state.stationary_humans
            if npc.id == owner_id
        )
        give_item(item, owner_id, owner.inventory)
        return item

    def _sync_npc_from_items(self, npc: HumanNPC) -> None:
        weapon = self.state.items.get(npc.equipped_weapon_id)
        armor = self.state.items.get(npc.equipped_armor_id)
        npc.weapon_condition = weapon.condition if weapon else 0
        npc.weapon_damage = (
            weapon.properties.get("base_damage", weapon.properties.get("damage", 20))
            if weapon else 5
        )
        npc.armor_condition = armor.condition if armor else 0
        npc.armor_value = (
            armor.properties.get("armor_factor", armor.properties.get("armor", 1.0))
            * EquipmentManager.get_armor_effectiveness(armor.condition)
            if armor else 1.0
        )
        npc.ammo = sum(
            item.quantity for item_id in npc.inventory
            if (item := self.state.items[item_id]).type is ItemType.AMMO
        )
        npc.medicines = sum(
            item.quantity for item_id in npc.inventory
            if (item := self.state.items[item_id]).type is ItemType.MEDICINE
        )

    def _sync_items_from_npc(self, npc: HumanNPC) -> None:
        weapon = self.state.items.get(npc.equipped_weapon_id)
        armor = self.state.items.get(npc.equipped_armor_id)
        if weapon:
            weapon.condition = max(0, min(100, npc.weapon_condition))
        if armor:
            armor.condition = max(0, min(100, npc.armor_condition))
        for item_type, amount in (
            (ItemType.AMMO, getattr(npc, "ammo", 0)),
            (ItemType.MEDICINE, getattr(npc, "medicines", 0)),
        ):
            stacks = [
                self.state.items[item_id] for item_id in npc.inventory
                if self.state.items[item_id].type is item_type
            ]
            for index, item in enumerate(stacks):
                item.quantity = max(0, amount) if index == 0 else 0

    def simulate_hour(self) -> dict[str, Any]:
        """
        Выполняет один час симуляции. (§8 ТЗ)
        Возвращает сводку по событиям часа.
        """
        hour = self.state.time.hour
        day = self.state.time.day
        phase = self.state.time.current_phase
        is_night = self.state.time.is_night()

        events: list[dict] = []

        # Фаза 0: Проверка состояния
        self._phase0_check(hour)

        # Фаза 1: Запланированные события
        self._phase1_scheduled(hour, day)

        # Фаза 2: Окружающая среда и торговля
        self._phase2_environment(hour)

        # Фаза 3: Обнаружение и распространение сведений
        self._phase3_knowledge(hour, is_night)

        # Фаза 4: Выбор намерений
        self._phase4_intentions(hour)

        # Фаза 5: Перемещение
        self._phase5_movement(hour, is_night)

        # Фаза 6: Обнаружение и встречи
        self._phase6_detections(hour)

        # Фаза 7: Основные действия
        self._phase7_actions(hour, is_night)

        # Фаза 8: Воздействие окружающей среды
        self._phase8_environment(hour)

        # Фаза 9: Последствия
        self._phase9_consequences(hour)

        # Фаза 10: сначала фиксируется следующий час, затем выполняется автосохранение
        self.state.time.advance()
        self._phase10_report(hour)

        return {
            "hour": hour,
            "day": day,
            "phase": phase.value,
            "is_night": is_night,
            "events": events,
        }

    def _phase0_check(self, hour: int) -> None:
        """Фаза 0: Проверка состояния мира и состава групп."""
        self._sync_human_groups()
        self._sync_monster_groups()

    def _sync_human_groups(self) -> None:
        """Убирает выбывших и удаляет пустые группы, сохраняя инварианты §7.5."""
        npcs = {npc.id: npc for npc in self.state.humans}
        for group_id, group in list(self.state.human_groups.items()):
            for member_id in list(group.members):
                npc = npcs.get(member_id)
                if npc is None or npc.status in (EntityStatus.DEAD, EntityStatus.EXILED):
                    group.remove_member(member_id)
                    if npc is not None:
                        npc.group_id = None
            if not group.members:
                del self.state.human_groups[group_id]
                continue
            group.sector_id = npcs[group.members[0]].sector_id
            if group.leader_id not in group.members:
                group.select_leader(npcs)

    def _phase1_scheduled(self, hour: int, day: int) -> None:
        """Фаза 1: Запланированные события."""
        # Миграция людей и монстров
        border_ids = {s.id for s in self.state.sectors.values() if s.is_border}
        start_ids = {s.id for s in self.state.sectors.values() if s.is_faction_start}

        new_entities = process_migration(
            self.state.sectors,
            self.state.humans,
            self.state.monsters,
            self.state.time,
            self.state.migration_state,
            self.state.rng,
        )

        for entity in new_entities:
            # ID назначаются детерминированно счётчиками движка (без коллизий)
            if isinstance(entity, Monster):
                entity.id = self.state.next_monster_id
                self.state.next_monster_id += 1
                self.state.monsters.append(entity)
            elif isinstance(entity, HumanNPC):
                entity.id = self.state.next_human_id
                self.state.next_human_id += 1
                group = HumanGroup(
                    id=self.state.next_group_id,
                    members=[entity.id],
                    sector_id=entity.sector_id,
                    leader_id=entity.id,
                )
                self.state.next_group_id += 1
                entity.group_id = group.id
                self.state.human_groups[group.id] = group
                self.state.humans.append(entity)
                self._give_starting_equipment(entity)

        # Монстры: пополнение численности
        active_monsters = sum(1 for m in self.state.monsters if m.status == EntityStatus.ACTIVE)
        new_monsters = self.state.monster_migration.check_and_spawn(
            active_monster_count=active_monsters,
            border_sectors=list(border_ids),
            faction_start_ids=start_ids,
            hour=hour,
            rng=self.state.rng,
        )
        for m in new_monsters:
            m.id = self.state.next_monster_id
            self.state.next_monster_id += 1
        self.state.monsters.extend(new_monsters)
        if new_entities or new_monsters:
            # мигранты сразу получают группу, как и люди
            self._sync_monster_groups()

    def _phase2_environment(self, hour: int) -> None:
        """Фаза 2: Окружающая среда и торговля."""
        # Обработка контрактов
        expired = self.state.contracts.expire_inactive_contracts(hour)
        for cid in expired:
            pass  # просрочка контрактов
        self._process_npc_trade(hour)

    def _phase3_knowledge(self, hour: int, is_night: bool) -> None:
        """Фаза 3: Наблюдение и распространение сведений.

        Бодрствующие NPC получают знания об аномалиях своего сектора только
        при успешной проверке обнаружения (§10.3, §5.1).
        """
        for npc in self.state.humans:
            if npc.status != EntityStatus.ACTIVE:
                continue

            sector = self.state.sectors.get(npc.sector_id)
            terrain_concealment = sector.concealment if sector else 50

            for anomaly in self.state.anomalies.values():
                if anomaly.sector_id != npc.sector_id or anomaly.status != AnomalyStatus.ACTIVE:
                    continue

                detected = check_anomaly_detection(
                    observer_att=npc.attentiveness,
                    anomaly_concealment=anomaly.concealment,
                    terrain_concealment=terrain_concealment,
                    is_night=is_night,
                    rng_value=self.state.rng.random(),
                )
                if not detected:
                    continue

                kb = self.state.knowledge_bases.setdefault(npc.id, KnowledgeBase())
                kb.add_manual(
                    npc_id=npc.id,
                    fact_type=KnowledgeType.ANOMALY,
                    subject_id=anomaly.id,
                    payload={
                        "sector_id": anomaly.sector_id,
                        "anomaly_type": anomaly.anomaly_type.value,
                        "concealment": anomaly.concealment,
                    },
                    hour=hour,
                )

    def _phase4_intentions(self, hour: int) -> None:
        """Фаза 4: лидер выбирает одно намерение для всей группы (§7.5, §9.2)."""
        is_night = self.state.time.is_night()
        npcs = {npc.id: npc for npc in self.state.humans}

        for group in self.state.human_groups.values():
            group.select_leader(npcs)
            leader = npcs.get(group.leader_id) if group.leader_id is not None else None
            if leader is None or leader.status != EntityStatus.ACTIVE:
                continue

            members = [npcs[mid] for mid in group.members if mid in npcs]
            facts = []
            for member in members:
                kb = self.state.knowledge_bases.get(member.id)
                if kb:
                    facts.extend(kb.get_facts(KnowledgeType.ANOMALY))
            here = [f for f in facts if f.payload.get("sector_id") == group.sector_id]
            researchable = [f for f in here if not f.payload.get("researched")]
            home = self._home_sector_id(leader.faction)

            ctx = IntentionContext(
                hour=hour,
                is_night=is_night,
                bravery=round(sum(npc.bravery for npc in members) / len(members)),
                faction=leader.faction,
                health_share=sum(npc.health_share for npc in members) / len(members),
                stamina_share=sum(npc.stamina_share for npc in members) / len(members),
                at_home=(home is not None and group.sector_id == home),
                home_sector_id=home,
                distance_to_border=self._distance_to_border(group.sector_id),
                has_known_anomaly=any(
                    self.state.anomalies[f.subject_id].status == AnomalyStatus.ACTIVE
                    for f in researchable if f.subject_id in self.state.anomalies
                ),
                known_anomaly_concealment=max(
                    (f.payload.get("concealment", 50) for f in researchable), default=0
                ),
                known_has_artifact=any(f.payload.get("has_artifact") for f in researchable),
                can_destroy=self._group_can_destroy(group, members),
                can_capture=self._group_can_capture(group, members),
            )
            group.intention = choose_intention(ctx, self.state.rng)
            for member in members:
                if member.status == EntityStatus.ACTIVE:
                    member.intention = group.intention
        self._phase4_monster_intentions(hour)

    def _phase4_monster_intentions(self, hour: int) -> None:
        entities = {
            entity.id: entity
            for entity in self.state.humans + self.state.stationary_humans + self.state.monsters
        }
        for group in self.state.monster_groups.values():
            members = self._monster_group_members(group)
            if not members:
                continue
            target = None
            for monster in members:
                candidate = entities.get(monster.target_id)
                if candidate is None or candidate.status in (EntityStatus.DEAD, EntityStatus.EXILED):
                    continue
                age = hour - monster.target_memory_hour
                is_large = species_value(monster) == "large_migrator"
                is_scavenger = species_value(monster) == "scavenger_pack"
                if should_pursue(monster, True, age) or (
                    is_scavenger and 0 <= age < 12 and candidate.health_share <= 0.7
                ):
                    target = candidate
                    break
            has_corpse = any(
                corpse.sector_id == group.sector_id and corpse.status == "available"
                for corpse in self.state.corpses
            )
            group.intention = choose_group_intention(
                members, has_corpse, target,
                target_in_sector=target is not None and target.sector_id == group.sector_id,
            )
            if (
                group.intention == "roam" and species_value(members[0]) == "territorial_predator"
                and group.home_sector_id is not None and group.sector_id != group.home_sector_id
            ):
                group.intention = "return_home"
            group.target_id = target.id if target is not None else None
            group.target_sector_id = target.sector_id if target is not None else None
            group.target_memory_hour = max(monster.target_memory_hour for monster in members)

    def _group_kit(self, members, item_type: ItemType, predicate=None):
        """Первый подходящий исправный комплект в инвентарях членов группы."""
        for npc in members:
            for item_id in npc.inventory:
                item = self.state.items.get(item_id)
                if item is None or item.type is not item_type or item.condition <= 0:
                    continue
                if predicate is None or predicate(item):
                    return npc, item
        return None, None

    def _capture_target(self, group: HumanGroup) -> Monster | None:
        """Ослабленный монстр в секторе группы. (§16.8: здоровье ≤ 35%)"""
        candidates = [
            monster for monster in self.state.monsters
            if monster.sector_id == group.sector_id
            and monster.status in (EntityStatus.ACTIVE, EntityStatus.UNCONSCIOUS)
            and monster.health_share <= 0.35
        ]
        if not candidates:
            return None
        # активное сопротивление других монстров рядом запрещает захват
        resisting = any(
            monster.status == EntityStatus.ACTIVE
            for monster in self.state.monsters
            if monster.sector_id == group.sector_id and monster not in candidates
        )
        if resisting:
            return None
        return min(candidates, key=lambda monster: monster.health_share)

    def _group_can_capture(self, group: HumanGroup, members) -> bool:
        target = self._capture_target(group)
        if target is None:
            return False
        _, kit = self._group_kit(
            members, ItemType.CAPTURE_KIT,
            lambda item: item.properties.get("target_species") == species_value(target),
        )
        return kit is not None

    def _group_can_destroy(self, group: HumanGroup, members) -> bool:
        anomaly = next(
            (
                a for a in self.state.anomalies.values()
                if a.sector_id == group.sector_id and a.status == AnomalyStatus.ACTIVE
            ),
            None,
        )
        if anomaly is None:
            return False
        _, kit = self._group_kit(
            members, ItemType.DESTROY_KIT,
            lambda item: item.properties.get("target_anomaly_type") == anomaly.anomaly_type.value,
        )
        return kit is not None

    def _active_members(self, group: HumanGroup) -> list[HumanNPC]:
        npcs = {npc.id: npc for npc in self.state.humans}
        return [
            npcs[mid] for mid in group.members
            if mid in npcs and npcs[mid].status == EntityStatus.ACTIVE
        ]

    def _group_leader(self, group: HumanGroup, members: list[HumanNPC]) -> HumanNPC:
        return next((npc for npc in members if npc.id == group.leader_id), members[0])

    def _consume_item(self, item: Item, members: list[HumanNPC]) -> None:
        """Удаляет израсходованный предмет из инвентаря и реестра."""
        owner = next((npc for npc in members if item.id in npc.inventory), None)
        if owner is not None:
            owner.inventory.remove(item.id)
            if owner.equipped_weapon_id == item.id:
                owner.equipped_weapon_id = None
            if owner.equipped_armor_id == item.id:
                owner.equipped_armor_id = None
        self.state.items.pop(item.id, None)

    def _phase5_movement(self, hour: int, is_night: bool) -> None:
        """Фаза 5: Перемещение по намерениям (1 ребро в час, §6.2)."""
        self._moved_human_ids: set[int] = set()
        border_ids = {s.id for s in self.state.sectors.values() if s.is_border}

        npcs = {npc.id: npc for npc in self.state.humans}
        for group in self.state.human_groups.values():
            leader = npcs.get(group.leader_id) if group.leader_id is not None else None
            if leader is None:
                continue
            members = [npcs[mid] for mid in group.members if mid in npcs]
            if not members or any(npc.status != EntityStatus.ACTIVE for npc in members):
                continue  # группа не оставляет спящих и бессознательных членов

            destination: int | None = None
            if group.intention == EXPLORE:
                memory = self.state.visit_memory.setdefault(leader.id, {})
                destination = choose_explore_target(
                    self.state.sectors, group.sector_id, memory, hour,
                    self._known_anomaly_sectors(leader), self.state.rng,
                )
            elif group.intention == EXIT:
                destination = next_step_towards(
                    self.state.sectors, group.sector_id, border_ids,
                    avoid_ids=self._known_anomaly_sectors(leader),
                )
            elif group.intention == REST:
                home = self._home_sector_id(leader.faction)
                if home is not None and group.sector_id != home:
                    destination = next_step_towards(
                        self.state.sectors, group.sector_id, {home},
                        avoid_ids=self._known_anomaly_sectors(leader),
                    )

            if destination is not None and destination != group.sector_id:
                group.sector_id = destination
                for npc in members:
                    npc.sector_id = destination
                    self._moved_human_ids.add(npc.id)
                    update_stamina(npc, STAMINA_COST_MOVEMENT, "movement", self.state.time)
                    self.state.visit_memory.setdefault(npc.id, {})[destination] = hour
                for prisoner_id in group.prisoners:
                    if prisoner_id in npcs:
                        npcs[prisoner_id].sector_id = destination

        self._move_monster_groups()

    def _move_monster_groups(self) -> None:
        from zonesim.world.sector import get_distance

        self._moved_monster_ids = set()
        for group in self.state.monster_groups.values():
            all_members = self._monster_group_members(group, active_only=False)
            members = [monster for monster in all_members if monster.status == EntityStatus.ACTIVE]
            if not members or len(members) != len(all_members):
                continue
            if group.intention in ("feed", "hunt", "rest"):
                continue
            speed = 2 if group.species == "territorial_predator" else 1
            for _ in range(speed):
                destination = None
                if group.intention == "stalk" and group.target_sector_id is not None:
                    destination = next_step_towards(
                        self.state.sectors, group.sector_id, {group.target_sector_id}
                    )
                elif group.intention == "return_home" and group.home_sector_id is not None:
                    destination = next_step_towards(
                        self.state.sectors, group.sector_id, {group.home_sector_id}
                    )
                elif group.intention == "roam":
                    sector = self.state.sectors[group.sector_id]
                    candidates = list(sector.neighbors)
                    if group.species == "scavenger_pack":
                        corpse_sectors = [
                            sector_id for sector_id in candidates
                            if any(corpse.sector_id == sector_id and corpse.status == "available"
                                   for corpse in self.state.corpses)
                        ]
                        if corpse_sectors:
                            candidates = corpse_sectors
                    if group.species == "territorial_predator" and group.home_sector_id is not None:
                        nearby = []
                        for sector_id in candidates:
                            distance = get_distance(
                                self.state.sectors, sector_id, group.home_sector_id
                            )
                            if distance is not None and distance <= 2:
                                nearby.append(sector_id)
                        if nearby:
                            candidates = nearby
                    if candidates and self.state.rng.random() < 0.4:
                        destination = self.state.rng.choice(candidates)
                if destination is None or destination == group.sector_id:
                    break
                group.sector_id = destination
                for monster in members:
                    monster.sector_id = destination
                    monster.stamina = max(0, monster.stamina - 5)
                    self._moved_monster_ids.add(monster.id)
                if group.intention in ("stalk", "return_home"):
                    target_sector = (
                        group.target_sector_id if group.intention == "stalk" else group.home_sector_id
                    )
                    if destination == target_sector:
                        break

    def _phase6_detections(self, hour: int) -> None:
        """Фаза 6: Обнаружение и встречи.

        Контакт с аномалиями сектора: проверка избегания по внимательности (§12.2),
        при провале урон применяется к здоровью.
        """
        is_night = self.state.time.is_night()

        for npc in self.state.humans:
            # Контакт проверяется при прохождении через сектор (§8, фаза 8)
            if npc.id not in self._moved_human_ids:
                continue
            if npc.status not in (EntityStatus.ACTIVE, EntityStatus.SLEEPING):
                continue

            co_located = [
                a for a in self.state.anomalies.values()
                if a.sector_id == npc.sector_id and a.status == AnomalyStatus.ACTIVE
            ]
            if not co_located:
                continue

            # Одна проверка на вход в сектор — по одной (случайной) аномалии
            anomaly = self.state.rng.choice(co_located)
            kb = self.state.knowledge_bases.get(npc.id)
            known = bool(kb and kb.get_facts(KnowledgeType.ANOMALY, subject_id=anomaly.id))
            contact = check_anomaly_contact(
                entity_sector=npc.sector_id,
                anomaly=anomaly,
                rng_func=self.state.rng.random,
                attentiveness=npc.attentiveness,
                known_bonus=20 if known else 0,
                is_night=is_night,
            )
            if contact["result"] != "hit":
                continue

            start_health = npc.health
            result = apply_anomaly_damage(
                npc.health, npc.max_health, anomaly, self.state.rng.random(),
            )
            npc.health = result["new_health"]

            outcome = "hit"
            if npc.health <= 0:
                outcome = self._resolve_zero_health(npc, start_health)

            self.state.news_manager.create_event(
                hour=hour,
                minute=0,
                sector_id=npc.sector_id,
                event_type="anomaly_hit",
                participants=[npc.id],
                result=outcome,
                importance=60 if outcome == "dead" else 30,
                summary=f"NPC {npc.id} попал в аномалию {anomaly.id} ({outcome})",
                details={"damage": result["damage"], "anomaly_id": anomaly.id},
            )

        self._check_monster_anomaly_contacts(hour, is_night)
        self._schedule_encounters(is_night)

    def _check_monster_anomaly_contacts(self, hour: int, is_night: bool) -> None:
        for monster in self.state.monsters:
            if monster.id not in self._moved_monster_ids or monster.status != EntityStatus.ACTIVE:
                continue
            anomalies = [
                anomaly for anomaly in self.state.anomalies.values()
                if anomaly.sector_id == monster.sector_id and anomaly.status == AnomalyStatus.ACTIVE
            ]
            if not anomalies:
                continue
            anomaly = self.state.rng.choice(anomalies)
            group = self.state.monster_groups.get(monster.group_id)
            group_size = group.member_count if group else 1
            contact = check_anomaly_contact(
                entity_sector=monster.sector_id,
                anomaly=anomaly,
                rng_func=self.state.rng.random,
                attentiveness=max(1, monster.attentiveness - 2 * (group_size - 1)),
                is_night=is_night,
            )
            if contact["result"] != "hit":
                continue
            result = apply_anomaly_damage(
                monster.health, monster.max_health, anomaly, self.state.rng.random()
            )
            monster.health = result["new_health"]
            if monster.health <= 0:
                monster.status = EntityStatus.DEAD
                self._create_corpse(monster, hour)
            self.state.news_manager.create_event(
                hour=hour, minute=5, sector_id=monster.sector_id,
                event_type="anomaly_hit", participants=[monster.id],
                result="dead" if monster.status == EntityStatus.DEAD else "hit",
                importance=60 if monster.status == EntityStatus.DEAD else 30,
                summary=f"Монстр {monster.id} попал в аномалию {anomaly.id}",
                details={"damage": result["damage"], "anomaly_id": anomaly.id},
            )

    def _schedule_encounters(self, is_night: bool) -> None:
        """Определяет боевые встречи; сами бои исполняются в фазе 7 (§8)."""
        self._pending_battles = []
        self._combat_human_ids = set()
        self._combat_monster_ids = set()
        self._feeding_claims = {}
        humans = {npc.id: npc for npc in self.state.humans}
        engaged_groups: set[int] = set()
        engaged_monsters: set[int] = set()

        for sector_id, sector in self.state.sectors.items():
            groups = []
            for group in self.state.human_groups.values():
                if group.sector_id != sector_id or group.id in engaged_groups:
                    continue
                members = [
                    humans[mid] for mid in group.members
                    if mid in humans and humans[mid].status == EntityStatus.ACTIVE
                ]
                if members:
                    groups.append((group, members))
            ordered = sorted(
                groups,
                key=lambda item: max(npc.attentiveness for npc in item[1])
                + self.state.rng.uniform(-10, 10),
                reverse=True,
            )
            monster_groups = []
            for group in self.state.monster_groups.values():
                if group.sector_id != sector_id:
                    continue
                members = [
                    monster for monster in self._monster_group_members(group)
                    if monster.id not in engaged_monsters
                ]
                if members:
                    monster_groups.append((group, members))

            for monster_group, monsters in monster_groups:
                if monster_group.intention in ("feed", "rest"):
                    continue
                candidates = [
                    (group, members) for group, members in ordered
                    if group.id not in engaged_groups
                ]
                if monster_group.target_id is not None:
                    preferred = [
                        (group, members) for group, members in candidates
                        if any(npc.id == monster_group.target_id for npc in members)
                    ]
                    if preferred:
                        candidates = preferred
                if candidates:
                    target_group, target_members = min(
                        candidates,
                        key=lambda item: sum(npc.health_share for npc in item[1]) / len(item[1]),
                    )
                    if self._monsters_attack(monsters, target_members, is_night):
                        guards = self._base_guards(sector_id, target_members[0].faction)
                        self._schedule_monster_attack(
                            monster_group, monsters, target_members + guards,
                            target_group.id, sector_id, False,
                        )
                        engaged_groups.add(target_group.id)
                        engaged_monsters.update(monster.id for monster in monsters)
                        continue
                if not groups:
                    guards = [
                        npc for npc in self.state.stationary_humans
                        if npc.sector_id == sector_id and npc.stationary_role == "guard"
                        and npc.status == EntityStatus.ACTIVE
                    ]
                    if guards and self._monsters_attack(monsters, guards, is_night):
                        self._schedule_monster_attack(
                            monster_group, monsters, guards, None, sector_id, False,
                        )
                        engaged_monsters.update(monster.id for monster in monsters)

            for index, (first_group, first_members) in enumerate(ordered):
                if first_group.id in engaged_groups:
                    continue
                for second_group, second_members in ordered[index + 1:]:
                    if second_group.id in engaged_groups:
                        continue
                    first_faction = first_members[0].faction
                    second_faction = second_members[0].faction
                    relation = self.state.faction_relations.get(first_faction, second_faction)
                    if first_faction == second_faction or relation > -20:
                        continue
                    if self.state.rng.random() >= 0.35:
                        continue

                    attacker_group, attacker_members = first_group, first_members
                    defender_group, defender_members = second_group, second_members
                    if sector.controller_faction == first_faction != second_faction:
                        defender_group, defender_members = first_group, first_members
                        attacker_group, attacker_members = second_group, second_members
                    guards = self._base_guards(sector_id, defender_members[0].faction)
                    self._pending_battles.append({
                        "sector_id": sector_id,
                        "attackers": attacker_members,
                        "defenders": defender_members + guards,
                        "attacker_is_monster": False,
                        "defender_is_monster": False,
                        "attacker_group_id": attacker_group.id,
                        "defender_group_id": defender_group.id,
                        "relation": relation,
                    })
                    engaged_groups.update((attacker_group.id, defender_group.id))
                    break

            for index, (attacker_group, attackers) in enumerate(monster_groups):
                if attacker_group.intention in ("feed", "rest") or any(
                    monster.id in engaged_monsters for monster in attackers
                ):
                    continue
                for defender_group, defenders in monster_groups[index + 1:]:
                    if attacker_group.species == defender_group.species or any(
                        monster.id in engaged_monsters for monster in defenders
                    ):
                        continue
                    if not self._monsters_attack(attackers, defenders, is_night):
                        continue
                    self._schedule_monster_attack(
                        attacker_group, attackers, defenders, None, sector_id, True,
                        defender_monster_group_id=defender_group.id,
                    )
                    engaged_monsters.update(
                        monster.id for monster in attackers + defenders
                    )
                    break

        self._resolve_feeding_competition(engaged_monsters)

    def _schedule_monster_attack(
        self, attacker_group: MonsterGroup, attackers: list[Monster], defenders: list,
        defender_group_id: int | None, sector_id: int, defender_is_monster: bool,
        defender_monster_group_id: int | None = None, feed_corpse_id: int | None = None,
    ) -> None:
        ambush = False
        if attacker_group.species == "scavenger_pack":
            target = select_weakest_target(defenders)
            for monster in attackers:
                monster.target_id = target.id
                monster.target_memory_hour = self.state.time.hour
            attacker_att = max(monster.attentiveness for monster in attackers)
            defender_att = max(target.attentiveness for target in defenders)
            chance = max(10, min(90, 55 + 0.5 * (attacker_att - defender_att)))
            ambush = self.state.rng.random() * 100 < chance
        self._pending_battles.append({
            "sector_id": sector_id,
            "attackers": attackers,
            "defenders": defenders,
            "attacker_is_monster": True,
            "defender_is_monster": defender_is_monster,
            "attacker_group_id": None,
            "defender_group_id": defender_group_id,
            "attacker_monster_group_id": attacker_group.id,
            "defender_monster_group_id": defender_monster_group_id,
            "attacker_ambush": ambush,
            "feed_corpse_id": feed_corpse_id,
        })

    def _monster_group_power(self, members: list[Monster]) -> float:
        total = 0.0
        for monster in members:
            health = 0.35 + 0.65 * monster.health_share
            stamina = 0.5 + 0.5 * monster.stamina_share
            total += monster.species_params.get("species_power", 0.33) * (
                0.5 + monster.attack / 100
            ) * health * stamina
        return total * min(1.15, 1 + 0.03 * (len(members) - 1))

    def _resolve_feeding_competition(self, engaged_monsters: set[int]) -> None:
        claims: dict[int, list[tuple[MonsterGroup, list[Monster]]]] = {}
        for group in self.state.monster_groups.values():
            if group.intention != "feed":
                continue
            members = self._monster_group_members(group)
            if not members or any(monster.id in engaged_monsters for monster in members):
                continue  # частично вовлечённая в бой группа не участвует в борьбе за труп
            corpse = next(
                (
                    corpse for corpse in sorted(self.state.corpses, key=lambda item: item.id)
                    if corpse.sector_id == group.sector_id and corpse.status == "available"
                ),
                None,
            )
            if corpse is not None:
                claims.setdefault(corpse.id, []).append((group, members))

        for corpse_id, competitors in claims.items():
            competitors.sort(key=lambda item: self._monster_group_power(item[1]), reverse=True)
            strongest = competitors[0]
            if len(competitors) > 1:
                challenger = competitors[1]
                strong_power = self._monster_group_power(strongest[1])
                weak_power = self._monster_group_power(challenger[1])
                difference = abs(strong_power - weak_power) / max(strong_power, weak_power, 0.001)
                if difference <= 0.15:
                    self._schedule_monster_attack(
                        strongest[0], strongest[1], challenger[1], None,
                        strongest[0].sector_id, True,
                        defender_monster_group_id=challenger[0].id,
                        feed_corpse_id=corpse_id,
                    )
                    continue
                challenger[0].intention = "roam"
            self._feeding_claims[strongest[0].id] = corpse_id

    def _base_guards(self, sector_id: int, faction: str) -> list[HumanNPC]:
        sector = self.state.sectors[sector_id]
        if not sector.is_faction_start or sector.controller_faction != faction:
            return []
        return [
            npc for npc in self.state.stationary_humans
            if npc.sector_id == sector_id and npc.stationary_role == "guard"
            and npc.status == EntityStatus.ACTIVE
        ]

    def _monsters_attack(self, monsters: list[Monster], prey: list, is_night: bool) -> bool:
        predator = monsters[0]
        species = species_value(predator)
        health_share = sum(target.health_share for target in prey) / len(prey)
        predator_health = sum(monster.health_share for monster in monsters) / len(monsters)
        prey_is_monster = isinstance(prey[0], Monster)
        if predator_health <= 0.2:
            return False
        if species == "territorial_predator" and len(monsters) == 1 and health_share > 0.8:
            return False
        if species == "scavenger_pack" and health_share > 0.6 and len(monsters) <= len(prey):
            return False
        chance = calculate_hunt_chance(
            predator=predator,
            prey_health_share=health_share,
            prey_is_monster=prey_is_monster,
            distance=0,
            is_night=is_night,
            group_advantage=len(monsters) - len(prey),
        )
        return self.state.rng.random() * 100 < chance

    def _resolve_zero_health(self, npc: HumanNPC, start_health: int) -> str:
        """Здоровье 0: бессознательное состояние по шансу §11.10, иначе гибель."""
        start_share = start_health / npc.max_health if npc.max_health > 0 else 0.0
        chance = calculate_unconscious_chance(start_share)
        if resolve_unconscious_check(self.state.rng.random(), chance) == "unconscious":
            npc.status = EntityStatus.UNCONSCIOUS
            npc.unconscious_reason = "health_zero"
            npc.unconscious_start_hour = self.state.time.hour
            return "unconscious"
        npc.status = EntityStatus.DEAD
        return "dead"

    # --- Вспомогательные методы намерений ---

    def _home_sector_id(self, faction: str) -> int | None:
        """Домашняя база фракции (§6.2)."""
        if faction not in self._home_cache:
            self._home_cache[faction] = next(
                (s.id for s in self.state.sectors.values()
                 if s.is_faction_start and s.controller_faction == faction),
                None,
            )
        return self._home_cache[faction]

    def _distance_to_border(self, sector_id: int) -> int | None:
        """Расстояние в рёбрах до ближайшего граничного сектора (§6.2)."""
        if self._border_dist is None:
            dist: dict[int, int] = {}
            queue = [sid for sid, s in self.state.sectors.items() if s.is_border]
            for sid in queue:
                dist[sid] = 0
            while queue:
                current = queue.pop(0)
                for nid in self.state.sectors[current].neighbors:
                    if nid not in dist:
                        dist[nid] = dist[current] + 1
                        queue.append(nid)
            self._border_dist = dist
        return self._border_dist.get(sector_id)

    def _known_anomaly_sectors(self, npc: HumanNPC) -> set[int]:
        kb = self.state.knowledge_bases.get(npc.id)
        if not kb:
            return set()
        return known_anomaly_sectors(kb.get_facts(KnowledgeType.ANOMALY))

    def _sector_humans(self, sector_id: int) -> dict[int, HumanNPC]:
        return {
            npc.id: npc
            for npc in self.state.humans + self.state.stationary_humans
            if npc.sector_id == sector_id
        }

    def _sleep_tick(self, npc: HumanNPC) -> None:
        """Сон: восстановление выносливости по §14.1 (комфорт 4 ч / иначе 6 ч)."""
        group = HumanGroup(id=-(npc.id + 1), members=[npc.id], sector_id=npc.sector_id)
        human_sleep_recover(
            group, self._sector_humans(npc.sector_id), self.state.time, self.state.rng,
        )

    def _unconscious_tick(self, npc: HumanNPC, hour: int) -> None:
        """Бессознательные состояния (§11.10, §14.2)."""
        if getattr(npc, "unconscious_reason", "") == "health_zero":
            # Без медицинской помощи бессознательный с здоровьем 0 становится трупом (§11.10)
            if hour - getattr(npc, "unconscious_start_hour", hour) >= 1:
                npc.status = EntityStatus.DEAD
                self.state.news_manager.create_event(
                    hour=hour, minute=0, sector_id=npc.sector_id,
                    event_type="npc_death", participants=[npc.id], result="dead",
                    importance=60, summary=f"NPC {npc.id} умер от ран без помощи",
                    details={"cause": "unconscious_no_aid"},
                )
            return
        # Истощение: минимум час, затем пробуждение с 10% выносливости (§14.2)
        group = HumanGroup(id=-(npc.id + 1), members=[npc.id], sector_id=npc.sector_id)
        human_sleep_recover(
            group, self._sector_humans(npc.sector_id), self.state.time, self.state.rng,
        )

    def _rest_tick(self, npc: HumanNPC) -> None:
        """Отдых и лечение на базе (§14.3).

        Временная мера до системы медикаментов: медленное восстановление
        с потолком 70% — полное мгновенное восстановление невозможно.
        """
        home = self._home_sector_id(npc.faction)
        if home is None or npc.sector_id != home:
            return
        cap = int(npc.max_health * 0.7)
        if npc.health < cap:
            npc.health = min(cap, npc.health + 2)

    def _research_tick(self, npc: HumanNPC, hour: int) -> None:
        """Исследование известной аномалии — основное действие часа (§12.3)."""
        kb = self.state.knowledge_bases.setdefault(npc.id, KnowledgeBase())
        known = [f for f in kb.get_facts(KnowledgeType.ANOMALY)
                 if f.payload.get("sector_id") == npc.sector_id]
        known_ids = {f.subject_id for f in known}

        target = next(
            (a for a in self.state.anomalies.values()
             if a.id in known_ids and a.sector_id == npc.sector_id
             and a.status == AnomalyStatus.ACTIVE),
            None,
        )
        if target is None:
            return

        update_stamina(npc, STAMINA_COST_RESEARCH, "research", self.state.time)
        outcome = research_anomaly(
            npc, target, hour,
            rng_value=self.state.rng.random(),
            prior_anomaly_knowledge=True,
        )
        result = outcome.get("result", "no_new_info")

        if result == "position_type_found":
            kb.add_manual(npc.id, KnowledgeType.ANOMALY, target.id, {
                "sector_id": npc.sector_id,
                "anomaly_type": target.anomaly_type.value,
                "concealment": target.concealment,
                "stability": target.stability,
                "researched": True,
            }, hour)
            # Сформировавшийся артефакт обнаруживается при исследовании (§12.3)
            self._give_artifact(npc, target, hour)
        elif result == "safe_path_found":
            kb.add_manual(npc.id, KnowledgeType.SAFE_PATH, target.id, {
                "sector_id": npc.sector_id, "active": True,
            }, hour)
        elif result == "artifact_found":
            kb.add_manual(npc.id, KnowledgeType.ANOMALY, target.id, {
                "sector_id": npc.sector_id, "has_artifact": True,
            }, hour)
            self._give_artifact(npc, target, hour)
        elif result == "damage_taken":
            start = npc.health
            npc.health = max(0, npc.health - outcome.get("damage", 0))
            if npc.health <= 0:
                self._set_unconscious_or_dead(npc, start, hour, cause="research")

        if result != "no_new_info":
            self.state.news_manager.create_event(
                hour=hour, minute=30, sector_id=npc.sector_id,
                event_type="research", participants=[npc.id], result=result,
                importance=25, summary=f"NPC {npc.id} исследует аномалию {target.id}: {result}",
                details={"anomaly_id": target.id, "outcome": result},
            )

    def _give_artifact(self, npc: HumanNPC, anomaly, hour: int) -> None:
        for art in self.state.artifacts.artifacts:
            if art.anomaly_id == anomaly.id and not art.discovered:
                art.discovered = True
                npc.artifacts.append(art.id)
                self._create_item(
                    ItemType.ARTIFACT, f"Артефакт ({art.rarity})", art.value, npc.id,
                    properties={"artifact_id": art.id},
                )
                self.state.news_manager.create_event(
                    hour=hour, minute=45, sector_id=npc.sector_id,
                    event_type="artifact_found", participants=[npc.id], result="picked_up",
                    importance=30,
                    summary=f"NPC {npc.id} извлёк артефакт из аномалии {anomaly.id}",
                    details={"artifact_id": art.id, "rarity": art.rarity, "value": art.value},
                )
                return

    def _exit_tick(self, npc: HumanNPC, hour: int) -> None:
        """Попытка покинуть Зону с внешней границы (§14.6)."""
        border_ids = {s.id for s in self.state.sectors.values() if s.is_border}
        if npc.sector_id not in border_ids:
            return
        success, result = self.state.exile_manager.process_exile_attempt(
            npc, npc.sector_id, border_ids, self.state.rng,
        )
        if success:
            self.state.news_manager.create_event(
                hour=hour, minute=0, sector_id=npc.sector_id,
                event_type="exile", participants=[npc.id], result="exiled",
                importance=50, summary=f"NPC {npc.id} покинул Зону",
                details={"result": result},
            )

    def _set_unconscious_or_dead(self, npc: HumanNPC, start_health: int,
                                 hour: int, cause: str) -> None:
        outcome = self._resolve_zero_health(npc, start_health)
        self.state.news_manager.create_event(
            hour=hour, minute=0, sector_id=npc.sector_id,
            event_type="npc_death" if outcome == "dead" else "npc_unconscious",
            participants=[npc.id], result=outcome,
            importance=60 if outcome == "dead" else 40,
            summary=f"NPC {npc.id}: {outcome} ({cause})",
            details={"cause": cause},
        )

    def _execute_battles(self, hour: int) -> None:
        for battle in self._pending_battles:
            for entity in battle["attackers"] + battle["defenders"]:
                if isinstance(entity, HumanNPC):
                    self._sync_npc_from_items(entity)
            attackers = [
                CombatFactory.from_monster(entity) if battle["attacker_is_monster"]
                else CombatFactory.from_human(entity)
                for entity in battle["attackers"]
            ]
            defenders = [
                CombatFactory.from_monster(entity) if battle["defender_is_monster"]
                else CombatFactory.from_human(entity)
                for entity in battle["defenders"]
            ]
            combat = CombatSystem(
                attackers=attackers,
                defenders=defenders,
                sectors=self.state.sectors,
                attacker_is_monster=battle["attacker_is_monster"],
                defender_is_monster=battle["defender_is_monster"],
                battle_sector_id=battle["sector_id"],
                relation=battle.get("relation", 0),
                attacker_ambush=battle.get("attacker_ambush", False),
            )
            result = combat.fight(self.state.rng.random)
            self._apply_battle_result(battle, combat, result, hour)

    def _apply_battle_result(self, battle: dict, combat: CombatSystem, result, hour: int) -> None:
        entities = {
            entity.id: entity
            for entity in self.state.humans + self.state.stationary_humans + self.state.monsters
        }
        for combatant in combat.attackers + combat.defenders:
            entity = entities[combatant.id]
            entity.health = combatant.health
            entity.stamina = combatant.stamina
            for field_name in ("weapon_condition", "armor_condition", "ammo", "medicines"):
                if combatant.is_human:
                    setattr(entity, field_name, getattr(combatant, field_name))
            if combatant.is_human:
                self._sync_items_from_npc(entity)
                self._damage_carried_valuables(entity, combat, result)
            if not combatant.is_alive:
                entity.status = EntityStatus.DEAD
            elif combatant.surrendered:
                entity.status = EntityStatus.PRISONER
            elif combatant.unconscious:
                entity.status = EntityStatus.UNCONSCIOUS
                entity.unconscious_reason = "health_zero"
                entity.unconscious_start_hour = hour
            else:
                entity.status = EntityStatus.ACTIVE

        for combatant in combat.attackers + combat.defenders:
            entity = entities[combatant.id]
            if not isinstance(entity, Monster) or species_value(entity) != "large_migrator":
                continue
            attacks = [
                entry for entry in result.battle_log
                if entry.get("defender_id") == entity.id and entry.get("damage", 0) > 0
            ]
            if attacks:
                entity.target_id = max(attacks, key=lambda entry: entry["damage"])["attacker_id"]
                entity.target_memory_hour = hour

        for side, retreat_sector in (
            ("attackers", result.attacker_retreat_sector),
            ("defenders", result.defender_retreat_sector),
        ):
            if retreat_sector is None:
                continue
            for entity in battle[side]:
                if not getattr(entity, "is_stationary", False) and entity.status != EntityStatus.DEAD:
                    entity.sector_id = retreat_sector
            group_id = battle["attacker_group_id"] if side == "attackers" else battle["defender_group_id"]
            group = self.state.human_groups.get(group_id) if group_id is not None else None
            if group:
                group.sector_id = retreat_sector
                for member_id in group.members + group.prisoners:
                    if member_id in entities and entities[member_id].status != EntityStatus.DEAD:
                        entities[member_id].sector_id = retreat_sector
            monster_group_key = (
                "attacker_monster_group_id" if side == "attackers" else "defender_monster_group_id"
            )
            monster_group_id = battle.get(monster_group_key)
            monster_group = (
                self.state.monster_groups.get(monster_group_id)
                if monster_group_id is not None else None
            )
            if monster_group:
                monster_group.sector_id = retreat_sector

        for prisoner_ids, captor_group_id in (
            (result.attacker_prisoners, battle["defender_group_id"]),
            (result.defender_prisoners, battle["attacker_group_id"]),
        ):
            for npc_id in prisoner_ids:
                npc = entities[npc_id]
                old_group = self.state.human_groups.get(npc.group_id)
                if old_group:
                    old_group.remove_member(npc_id)
                npc.group_id = captor_group_id
                captor = self.state.human_groups.get(captor_group_id) if captor_group_id is not None else None
                if captor and npc_id not in captor.prisoners:
                    captor.prisoners.append(npc_id)

        for combatant in combat.attackers + combat.defenders:
            if not combatant.is_alive:
                self._create_corpse(entities[combatant.id], hour)

        participants = [entity.id for entity in battle["attackers"] + battle["defenders"]]
        self._combat_human_ids.update(
            entity.id for entity in battle["attackers"] + battle["defenders"]
            if isinstance(entity, HumanNPC)
        )
        self._combat_monster_ids.update(
            entity.id for entity in battle["attackers"] + battle["defenders"]
            if not isinstance(entity, HumanNPC)
        )
        self.state.news_manager.create_event(
            hour=hour,
            minute=15,
            sector_id=battle["sector_id"],
            event_type="combat",
            participants=participants,
            result=result.outcome,
            importance=60 if result.attacker_dead or result.defender_dead else 40,
            summary=f"Бой в секторе {battle['sector_id']}: {result.outcome}",
            details={
                "rounds": result.rounds_fought,
                "attacker_dead": result.attacker_dead,
                "defender_dead": result.defender_dead,
                "attacker_prisoners": result.attacker_prisoners,
                "defender_prisoners": result.defender_prisoners,
                "attacker_retreated": result.attacker_retreated,
                "defender_retreated": result.defender_retreated,
                "feed_corpse_id": battle.get("feed_corpse_id"),
            },
        )

    def _damage_carried_valuables(self, npc: HumanNPC, combat: CombatSystem, result) -> None:
        damage = max(
            (entry["damage"] for entry in result.battle_log
             if entry.get("defender_id") == npc.id and entry.get("type") is None),
            default=0,
        )
        valuable_types = {
            ItemType.ARTIFACT, ItemType.MONSTER_PART,
            ItemType.ANOMALY_PART, ItemType.LIVE_MONSTER,
        }
        for item_id in npc.inventory:
            item = self.state.items[item_id]
            if item.type not in valuable_types:
                continue
            damaged, new_condition = EquipmentManager.check_value_damage(
                item.condition, damage, self.state.rng.random()
            )
            if damaged:
                item.condition = new_condition

    def _create_corpse(self, entity, hour: int) -> Corpse:
        species = getattr(entity, "species", "human")
        species = species.value if hasattr(species, "value") else species
        corpse = Corpse(
            id=self.state.next_corpse_id,
            original_entity_id=entity.id,
            original_entity_type="human" if isinstance(entity, HumanNPC) else species,
            sector_id=entity.sector_id,
            created_hour=hour,
            monster_parts=[] if isinstance(entity, HumanNPC) else LootManager.available_monster_parts(entity),
        )
        self.state.next_corpse_id += 1
        self.state.corpses.append(corpse)
        if isinstance(entity, HumanNPC):
            for item_id in list(entity.inventory):
                place_item_on_corpse(self.state.items[item_id], corpse.id, entity.inventory)
                corpse.items.append(item_id)
            corpse.money = max(0, entity.money)
            entity.money = 0
            entity.equipped_weapon_id = None
            entity.equipped_armor_id = None
            entity.artifacts.clear()
        return corpse

    def _process_corpse_action(self, group: HumanGroup, hour: int) -> dict | None:
        npcs = {npc.id: npc for npc in self.state.humans}
        members = [
            npcs[member_id] for member_id in group.members
            if member_id in npcs and npcs[member_id].status == EntityStatus.ACTIVE
        ]
        if not members or any(npc.id in self._combat_human_ids for npc in members):
            return None
        leader = npcs.get(group.leader_id)
        if leader not in members:
            leader = members[0]
        corpses = sorted(
            (
                corpse for corpse in self.state.corpses
                if corpse.sector_id == group.sector_id and corpse.status == "available"
                and (corpse.items or corpse.money > 0 or corpse.monster_parts)
            ),
            key=lambda corpse: corpse.id,
        )
        if not corpses:
            return None
        corpse = corpses[0]
        if corpse.items or corpse.money > 0:
            result = LootManager.loot_corpse(corpse, leader, members, self.state.items)
            action = "loot"
        else:
            result = LootManager.harvest_monster_parts(
                corpse, leader, self.state.items, self.state.next_item_id
            )
            self.state.next_item_id = result.get("next_item_id", self.state.next_item_id)
            action = "harvest"
        if not result["success"]:
            return None
        self.state.news_manager.create_event(
            hour=hour, minute=40, sector_id=group.sector_id,
            event_type=action, participants=[npc.id for npc in members], result="success",
            importance=15,
            summary=f"Группа {group.id} обработала труп {corpse.id} ({action})",
            details=result,
        )
        return result

    def _process_monster_feeding(self, hour: int) -> set[int]:
        fed_groups = set()
        for group_id, corpse_id in self._feeding_claims.items():
            group = self.state.monster_groups.get(group_id)
            corpse = next((item for item in self.state.corpses if item.id == corpse_id), None)
            if group is None or corpse is None or corpse.status != "available":
                continue
            members = self._monster_group_members(group)
            if not members or any(monster.id in self._combat_monster_ids for monster in members):
                continue  # группа не кормится частично: любой бой отменяет кормление всей группы
            result = self._feed_manager.consume(corpse, members[0], hour, self.state.items)
            if not result["success"]:
                continue
            for monster in members[1:]:
                monster.stamina = min(monster.max_stamina, monster.stamina + 30)
            fed_groups.add(group_id)
            self.state.news_manager.create_event(
                hour=hour, minute=45, sector_id=group.sector_id,
                event_type="feeding", participants=[monster.id for monster in members],
                result="consumed", importance=15,
                summary=f"Группа монстров {group.id} съела труп {corpse.id}",
                details=result,
            )
        return fed_groups

    def _process_monster_rest(self, fed_groups: set[int], is_night: bool) -> None:
        for group in self.state.monster_groups.values():
            if group.id in fed_groups:
                continue
            members = self._monster_group_members(group, active_only=False)
            if not members or any(monster.id in self._combat_monster_ids for monster in members):
                continue
            if group.intention == "rest":
                for monster in members:
                    monster.stamina = min(monster.max_stamina, monster.stamina + 20)
                continue
            active = [monster for monster in members if monster.status == EntityStatus.ACTIVE]
            sleeping = [monster for monster in members if monster.status == EntityStatus.SLEEPING]
            unconscious = [monster for monster in members if monster.status == EntityStatus.UNCONSCIOUS]
            for monster in unconscious:
                monster.stamina = min(monster.max_stamina, monster.stamina + 20)
                if monster.stamina >= 10:
                    monster.status = EntityStatus.ACTIVE
            for monster in active:
                if monster.stamina <= 0:
                    monster.status = EntityStatus.UNCONSCIOUS
            if active and is_night and self.state.rng.random() < 0.3:
                for monster in active:
                    monster.status = EntityStatus.SLEEPING
                    monster.stamina = min(monster.max_stamina, monster.stamina + 50)
            elif sleeping and self.state.rng.random() < 0.5:
                for monster in sleeping:
                    monster.status = EntityStatus.ACTIVE
                    monster.stamina = min(monster.max_stamina, monster.stamina + 50)

    def _process_destroy_anomaly(
        self, group: HumanGroup, hour: int, is_night: bool,
    ) -> bool:
        """Разрушение аномалии комплектом — основное действие часа (§12.4)."""
        members = self._active_members(group)
        if not members or any(npc.id in self._combat_human_ids for npc in members):
            return False
        anomaly = next(
            (
                a for a in self.state.anomalies.values()
                if a.sector_id == group.sector_id and a.status == AnomalyStatus.ACTIVE
            ),
            None,
        )
        if anomaly is None:
            return False
        _, kit = self._group_kit(
            members, ItemType.DESTROY_KIT,
            lambda item: item.properties.get("target_anomaly_type") == anomaly.anomaly_type.value,
        )
        if kit is None:
            return False
        leader = self._group_leader(group, members)
        attentiveness = round(sum(npc.attentiveness for npc in members) / len(members))
        result = attempt_destroy_anomaly(
            anomaly,
            base_damage=kit.properties["stability_damage"],
            kit_condition=kit.condition,
            quality=kit.properties.get("quality", 1.0),
            group_attentiveness=attentiveness,
            participants_count=len(members),
        )
        kit.condition = result["kit_new_condition"]
        if kit.condition <= 0:
            self._consume_item(kit, members)
        for member in members:
            update_stamina(member, STAMINA_COST_RESEARCH, "destroy", self.state.time)

        # Каждая попытка сопровождается проверкой воздействия аномалии (§12.4)
        contact = check_anomaly_contact(
            entity_sector=group.sector_id,
            anomaly=anomaly,
            rng_func=self.state.rng.random,
            attentiveness=attentiveness,
            is_night=is_night,
        )
        if contact["result"] == "hit":
            victim = self.state.rng.choice(members)
            start = victim.health
            damage_result = apply_anomaly_damage(
                victim.health, victim.max_health, anomaly, self.state.rng.random(),
            )
            victim.health = damage_result.get("new_health", victim.health)
            if victim.health <= 0:
                self._set_unconscious_or_dead(victim, start, hour, cause="anomaly")

        if result["destroyed"]:
            parts = get_anomaly_parts_after_destruction(anomaly)
            for _ in range(parts["quantity"]):
                self._create_item(
                    ItemType.ANOMALY_PART, "Часть аномалии", 40.0, leader.id,
                    properties={
                        "anomaly_type": anomaly.anomaly_type.value,
                        "source_anomaly_id": anomaly.id,
                    },
                )
            # уже сформировавшийся артефакт может быть извлечён (§12.4)
            self._give_artifact(leader, anomaly, hour)
            self.state.news_manager.create_event(
                hour=hour, minute=40, sector_id=group.sector_id,
                event_type="anomaly_destroyed",
                participants=[npc.id for npc in members],
                result="destroyed", importance=50,
                summary=f"Группа {group.id} разрушила аномалию {anomaly.id}",
                details={"anomaly_id": anomaly.id, "damage_dealt": result["damage_dealt"]},
            )
        else:
            self.state.news_manager.create_event(
                hour=hour, minute=40, sector_id=group.sector_id,
                event_type="anomaly_destroyed",
                participants=[npc.id for npc in members],
                result="damaged", importance=20,
                summary=(
                    f"Группа {group.id} повредила аномалию {anomaly.id}"
                    f" (устойчивость {result['new_stability']})"
                ),
                details={"anomaly_id": anomaly.id, "damage_dealt": result["damage_dealt"]},
            )
        return True

    def _process_capture_monster(self, group: HumanGroup, hour: int) -> bool:
        """Захват живого монстра — основное действие часа (§16.8)."""
        members = self._active_members(group)
        if not members or any(npc.id in self._combat_human_ids for npc in members):
            return False
        target = self._capture_target(group)
        if target is None:
            return False
        _, kit = self._group_kit(
            members, ItemType.CAPTURE_KIT,
            lambda item: item.properties.get("target_species") == species_value(target),
        )
        if kit is None:
            return False
        leader = self._group_leader(group, members)
        chance = CaptureManager.calculate_capture_chance(
            health_share=target.health_share,
            attacker_att=max(npc.attentiveness for npc in members),
            target_att=target.attentiveness,
            num_attackers=min(len(members), 4),
            kit_bonus=kit.properties.get("capture_bonus", 0),
        )
        success = CaptureManager.resolve_capture(self.state.rng.random(), chance)
        species = species_value(target)
        if success:
            rank = kit.properties.get("danger_rank", 1)
            self._create_item(
                ItemType.LIVE_MONSTER, f"Живой монстр ({species})",
                200.0 + 300.0 * rank, leader.id,
                properties={"species": species, "source_monster_id": target.id},
            )
            # монстр выводится из активной популяции, но остаётся в мире
            monster_group = self.state.monster_groups.get(target.group_id)
            if monster_group and target.id in monster_group.members:
                monster_group.members.remove(target.id)
            target.status = EntityStatus.EXILED
            target.group_id = None
            self.state.news_manager.create_event(
                hour=hour, minute=40, sector_id=group.sector_id,
                event_type="monster_captured",
                participants=[npc.id for npc in members] + [target.id],
                result="captured", importance=45,
                summary=f"Группа {group.id} взяла в плен монстра {target.id} ({species})",
                details={
                    "monster_id": target.id, "species": species,
                    "capture_chance": round(chance, 1),
                },
            )
        else:
            wear = self.state.rng.randint(*CaptureManager.get_kit_damage_on_failure())
            kit.condition = max(0, kit.condition - wear)
            if kit.condition <= 0:
                self._consume_item(kit, members)
            if self.state.rng.random() < 0.5:
                victim = self.state.rng.choice(members)
                start = victim.health
                victim.health = max(0, victim.health - max(5, round(target.attack * 0.5)))
                if victim.health <= 0:
                    self._set_unconscious_or_dead(victim, start, hour, cause="capture")
                outcome = "counterattack"
            else:
                sector = self.state.sectors.get(target.sector_id)
                if sector and sector.neighbors:
                    target.sector_id = self.state.rng.choice(list(sector.neighbors))
                outcome = "escaped"
            self.state.news_manager.create_event(
                hour=hour, minute=40, sector_id=group.sector_id,
                event_type="monster_captured",
                participants=[npc.id for npc in members] + [target.id],
                result="failed", importance=20,
                summary=f"Группа {group.id} не смогла взять монстра {target.id}: {outcome}",
                details={
                    "monster_id": target.id, "outcome": outcome,
                    "capture_chance": round(chance, 1),
                },
            )
        return True

    def _phase7_actions(self, hour: int, is_night: bool) -> None:
        """Фаза 7: сначала бои, затем остальные основные действия (§8)."""
        self._execute_battles(hour)
        fed_monster_groups = self._process_monster_feeding(hour)
        acted_groups = set()
        for group in self.state.human_groups.values():
            if self._process_corpse_action(group, hour) is not None:
                acted_groups.add(group.id)
        for group in self.state.human_groups.values():
            if group.id in acted_groups or group.intention not in (DESTROY, CAPTURE):
                continue
            if group.intention == DESTROY:
                done = self._process_destroy_anomaly(group, hour, is_night)
            else:
                done = self._process_capture_monster(group, hour)
            if done:
                acted_groups.add(group.id)
        for npc in self.state.humans:
            if npc.id in self._combat_human_ids or npc.group_id in acted_groups:
                continue
            if npc.status == EntityStatus.SLEEPING:
                self._sleep_tick(npc)
                continue
            if npc.status == EntityStatus.UNCONSCIOUS:
                self._unconscious_tick(npc, hour)
                continue
            if npc.status != EntityStatus.ACTIVE:
                continue

            # Базовый расход выносливости за час бодрствования (§14.1)
            update_stamina(npc, STAMINA_COST_AWAKE, "awake", self.state.time)
            if npc.status != EntityStatus.ACTIVE:
                continue  # истощение → потеря сознания

            if npc.intention == SLEEP:
                npc.status = EntityStatus.SLEEPING
            elif npc.intention == REST:
                self._rest_tick(npc)
            elif npc.intention == RESEARCH:
                self._research_tick(npc, hour)
            elif npc.intention == EXIT:
                self._exit_tick(npc, hour)

        self._process_monster_rest(fed_monster_groups, is_night)

    def _phase8_environment(self, hour: int) -> None:
        """Фаза 8: Воздействие окружающей среды."""
        # Перемещение аномалий каждые 48 часов
        if hour % 48 == 0:
            border_ids = [s.id for s in self.state.sectors.values() if s.is_border]
            start_ids = {s.id for s in self.state.sectors.values() if s.is_faction_start}

            for anomaly in self.state.anomalies.values():
                if anomaly.status == AnomalyStatus.ACTIVE:
                    rng_val = self.state.rng.random()
                    migration = check_anomaly_migration(
                        anomaly, hour,
                        sector_ids=border_ids,
                        faction_start_ids=start_ids,
                        rng_value=rng_val,
                    )
                    if migration["moved"]:
                        self.state.news_manager.create_event(
                            hour=hour,
                            minute=0,
                            sector_id=migration["to_sector"],
                            event_type="anomaly_move",
                            participants=[],
                            result="moved",
                            importance=20,
                            summary=f"Аномалия {anomaly.id} переместилась",
                            details=migration,
                        )

        # Формирование артефактов
        for anomaly in self.state.anomalies.values():
            if anomaly.status == AnomalyStatus.ACTIVE:
                artifact_result = self.state.artifacts.check_artifact_formation(
                    anomaly, hour, rng=self.state.rng,
                )
                if artifact_result["formed"]:
                    self.state.news_manager.create_event(
                        hour=hour,
                        minute=0,
                        sector_id=anomaly.sector_id,
                        event_type="artifact_form",
                        participants=[],
                        result="formed",
                        importance=40,
                        summary=f"Артефакт {artifact_result['rarity']} сформировался",
                        details=artifact_result,
                    )

    def _phase9_consequences(self, hour: int) -> None:
        """Фаза 9: последствия и актуализация состава групп."""
        self._sync_human_groups()

    def _phase10_report(self, hour: int) -> None:
        """Фаза 10: автосохранение после завершённого часа."""
        if self.save_manager is None:
            return
        settings = self.state.config.get("persistence", {})
        if not settings.get("autosave_enabled", True):
            return
        interval = settings.get("autosave_interval", 6)
        slot_count = settings.get("autosave_slots", 3)
        if interval <= 0 or slot_count <= 0 or self.state.time.hour % interval != 0:
            return
        slot_index = (self.state.time.hour // interval - 1) % slot_count
        self.save(f"autosave_{slot_index}")

    def get_state_summary(self) -> dict[str, Any]:
        """Получает сводку текущего состояния."""
        active_humans = sum(1 for h in self.state.humans if h.status == EntityStatus.ACTIVE)
        active_monsters = sum(1 for m in self.state.monsters if m.status == EntityStatus.ACTIVE)
        active_anomalies = sum(1 for a in self.state.anomalies.values() if a.status == AnomalyStatus.ACTIVE)

        return {
            "hour": self.state.time.hour,
            "day": self.state.time.day,
            "phase": self.state.time.current_phase.value,
            "is_night": self.state.time.is_night(),
            "active_humans": active_humans,
            "stationary_humans": len(self.state.stationary_humans),
            "human_groups": len(self.state.human_groups),
            "active_monsters": active_monsters,
            "active_anomalies": active_anomalies,
            "total_events": self.state.news_manager.get_total_count(),
        }
