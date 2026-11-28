"""Главный движок симуляции. Связывает все модули в почасовой цикл (§8 ТЗ)."""

from __future__ import annotations

from dataclasses import field, replace
from typing import Any

from zonesim.core.time import GameTime, SeededRNG
from zonesim.world.entity import HumanNPC, Monster, MonsterSpecies, EntityStatus
from zonesim.combat.loot import EquipmentManager, LootManager
from zonesim.world.item import Item, ItemType, give_item

from zonesim.core.config import GameConfig, DEFAULT_GUARDS_PER_BASE
from zonesim.generation.worldgen import generate_world
from zonesim.generation.migration import process_migration

from zonesim.combat import CombatSystem
from zonesim.combat.base import Combatant, CombatFactory
from zonesim.combat.unconscious import calculate_unconscious_chance, resolve_unconscious_check

from zonesim.actions.detection import check_anomaly_detection
from zonesim.actions.capture import capture_target

from zonesim.ai import (
    ARTIFACT_SEARCH,
    CAPTURE,
    CREATE_SHELTER,
    DESTROY,
    EXIT,
    EXPLORE,
    HELP,
    RESEARCH,
    REST,
    SHELTER,
    SLEEP,
    IntentionContext,
    choose_explore_target,
    choose_intention,
    edge_cost,
    edge_key,
    known_anomaly_sectors,
    next_step_towards,
)

from zonesim.needs.sleep import (
    HUMAN_COMFORT_HOURS,
    STAMINA_COST_AWAKE,
    STAMINA_COST_MOVEMENT,
    STAMINA_COST_RESEARCH,
    human_sleep_recover,
    update_stamina,
)

from zonesim.anomalies.research import research_anomaly

from zonesim.world.group import HumanGroup, MonsterGroup
from zonesim.world.catalog import ItemCatalog
from zonesim.world.shelter import StormShelter, Shelter
from zonesim.monsters.behavior import choose_group_intention, select_weakest_target, species_value
from zonesim.monsters.feed import FeedManager
from zonesim.monsters.hunt import should_pursue
from zonesim.world.faction import group_faction, home_sector_id, distance_to_border
from zonesim.world.sectors import sector_humans
from zonesim.combat.power import squad_power, monster_group_power

from zonesim.combat.medkit import use_medkit_charge, emergency_medkit
from zonesim.combat.results import resolve_zero_health, set_unconscious_or_dead
from zonesim.combat.guards import base_guards

from zonesim.needs.healing import rest_heal
from zonesim.needs.artifact import give_artifact

from zonesim.economy.trader import sell_loot, SELL_PRICE_SHARE, conditional_trader_is_active, conditional_trader_can_sleep, conditional_trader_base_sector
from zonesim.world.groups import group_kit, active_members, group_leader
from zonesim.world.groups import monster_group_members, sync_human_groups, sync_monster_groups
from zonesim.world.shelter import (
    shelter_sector_ids, group_in_shelter, shelter_targets, process_create_shelter,
    free_emptied_shelters, update_shelter_participants,
    process_shelter_occupation, create_shelter_occupied_knowledge,
    process_emission_shelter_assault, stale_shelter_occupied_knowledge,
    group_can_create_shelter,
)
from zonesim.actions.movement import walk
from zonesim.knowledge import group_detector_bonus
from zonesim.knowledge.expiry import expire_findings
from zonesim.world.trails import (
    trail_set, roll_trail_blockage, roll_trail_blockages,
    blocked_trail_map, group_has_passage,
)
from zonesim.world.item import create_item, consume_item, sync_npc_from_items
from zonesim.relations.journal import check_and_journal_relations, log_relation_change
from zonesim.anomalies.emission import (
    emission_safe_sectors, is_group_emission_sheltered, emission_active, emission_known,
    process_emission_schedule, broadcast_emission_warning, mark_group_emission_exposed,
    apply_emission_exposure,
)

from zonesim.economy.contracts import ContractManager
from zonesim.economy.trade import CaptureManager, ImportExportManager, ExportRecord
from zonesim.economy.pricing import calculate_sell_price, get_type_multiplier, calculate_stock_multiplier

from zonesim.anomalies.core import Anomaly as AnomalyEntity, AnomalyType, AnomalyStatus
from zonesim.anomalies.damage import apply_anomaly_damage, check_anomaly_contact
from zonesim.anomalies.artifact import ArtifactManager, Artifact
from zonesim.anomalies.migration import check_anomaly_migration, anomaly_move_candidates, move_all_anomalies
from zonesim.anomalies.destroy import attempt_destroy_anomaly, get_anomaly_parts_after_destruction
from zonesim.anomalies.emission import (
    EMISSION_ARTIFACT_ACCELERATION,
    EMISSION_EXPOSURE_DAMAGE,
    EMISSION_EXPOSURE_KILL_HOUR,
    EMISSION_MONSTER_SHELTER_CHANCE,
    EMISSION_MONSTER_STAY_MAX,
    EMISSION_MONSTER_STAY_MIN,
    EMISSION_TRAIL_BLOCK_CHANCE,
    SHELTER_COUNT,
    is_emission_active,
    is_emission_known,
    roll_duration,
    roll_warning_lead,
    schedule_next_emission,
)

from zonesim.monsters.migration import MonsterMigrationManager
from zonesim.monsters.hunt import calculate_hunt_chance

from zonesim.relations.personal import PersonalRelations
from zonesim.relations.factions import FactionRelations
from zonesim.relations.development import DevelopmentManager, ExileManager, FactionChangeManager
from zonesim.relations.news import NewsManager

from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType
from zonesim.persistence import SaveManager
from zonesim.simulation.invariants import InvariantViolation, assert_world_invariants
from zonesim.simulation.state import SimulationState
from zonesim.simulation.context import SimulationContext
from zonesim.simulation.phases import (
    run_phase0_check,
    run_phase1_scheduled,
    run_phase2_environment,
    run_phase3_knowledge,
    run_phase4_intentions,
    run_phase5_movement,
    run_phase6_detections,
    run_phase7_actions,
    run_phase8_environment,
    run_phase9_consequences,
    run_phase10_report,
)


CAPTURE_KIT_REF = {
    "territorial_predator": "capture.kit.predator",
    "scavenger_pack": "capture.kit.scavenger",
    "large_migrator": "capture.kit.migrator",
}

# Регенерация здоровья монстров, доля макс. здоровья в час (§13, §14.3)
MONSTER_HEALTH_REGEN_PASSIVE = 0.02
MONSTER_HEALTH_REGEN_REST = 0.08
# Передышка между боями для групп, часов (§11.1)
COMBAT_COOLDOWN_HOURS = 6
# Бонус местных видов монстров к обнаружению аномалий (§12.2)
MONSTER_NATIVE_ANOMALY_BONUS = 25
# База — укрепление: бонус защиты обороняющихся (§7.16)
BASE_FORTIFICATION_BONUS = 0.7
# Монстры не атакуют, если конечная сила цели превышает их силу более чем вдвое
MONSTER_ATTACK_POWER_LIMIT = 1.6
# Видовая сила монстров (§11.2), ключи — канонические значения вида
SPECIES_POWER_VALUE = {
    "territorial_predator": 0.33,
    "scavenger_pack": 0.70,
    "large_migrator": 4.00,
}

# Ситуативный торговец «Серой лиги» — константы (§16.6)
CONDITIONAL_TRADER_DURATION = 12          # часов работы
CONDITIONAL_TRADER_KNOWLEDGE_LEAD = 3     # часа за 2-4 до появления


class SimulationEngine:
    """Главный движок симуляции. Интегрирует все модули."""

    def __init__(self, seed: int = 42, config: dict | None = None, save_directory=None):
        self.state = SimulationState(rng=SeededRNG(seed), config=config or {})
        self.context = SimulationContext(self.state)
        self.context.engine_ref = self
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
        engine.context = SimulationContext(state)
        engine.context.engine_ref = engine
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
        for npc in self.state.stationary_humans:
            if npc.stationary_role == "guard":
                self._equip_guard(npc)
        self._init_trader_stock()
        self._init_trails()
        self._init_shelters()
        roll_trail_blockages(self.state)
        self.state.next_emission_hour = schedule_next_emission(self.state.rng)
        sync_monster_groups(self.state)

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
        "detector": 2,
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

    def _init_trails(self) -> None:
        """Тропы: около 40% рёбер графа. (§10.4)"""
        edges = {
            edge_key(sid, nid)
            for sid, sector in self.state.sectors.items()
            for nid in sector.neighbors
        }
        trails = [list(edge) for edge in sorted(edges) if self.state.rng.random() < 0.4]
        self.state.trails = trails

    def _init_shelters(self) -> None:
        """Стационарные укрытия: 8 шт, не более одного в секторе,
        любой сектор в двух рёбрах от укрытия. (§7.16)"""
        from zonesim.world.sector import get_distance

        start_ids = {s.id for s in self.state.sectors.values() if s.is_faction_start}
        candidates = [sid for sid in self.state.sectors if sid not in start_ids]
        chosen: list[int] = []
        all_ids = set(self.state.sectors)
        while len(chosen) < SHELTER_COUNT:
            uncovered = [
                sid for sid in all_ids
                if not any(
                    (dist := get_distance(self.state.sectors, sid, c)) is not None and dist <= 2
                    for c in chosen
                )
            ]
            if not uncovered:
                break
            # жадный выбор: сектор, покрывающий больше всего непокрытых
            best = max(
                candidates,
                key=lambda sid: sum(
                    1 for u in uncovered
                    if (dist := get_distance(self.state.sectors, sid, u)) is not None and dist <= 2
                ),
            )
            chosen.append(best)
            candidates.remove(best)
        # дозаполняем до стартового количества разбросанными укрытиями
        while len(chosen) < SHELTER_COUNT and candidates:
            pick = self.state.rng.choice(candidates)
            chosen.append(pick)
            candidates.remove(pick)
        self.state.shelters = {
            index: StormShelter(
                id=index,
                sector_id=sector_id,
                capacity=self.state.rng.randint(2, 6),
            )
            for index, sector_id in enumerate(chosen)
        }
        self.state.shelter_count = len(self.state.shelters)

    def _schedule_conditional_trader(self, hour: int) -> None:
        """Запланировать следующий появление ситуативного торговца. (§16.6)"""
        if self.state.next_conditional_spawn_hour >= 0:
            return  # уже запланирован
        
        # Интервал 48-96 часов
        self.state.next_conditional_spawn_hour = hour + self.state.rng.randint(48, 96)

    def _process_conditional_trader_schedule(self, hour: int) -> None:
        """Проверяет и создаёт ситуативного торговца. (§16.6)"""
        state = self.state
        
        # Планируем если не запланирован
        if state.next_conditional_spawn_hour < 0:
            self._schedule_conditional_trader(hour)
        
        # Рассылаем знания лиге за 2-4 часа до появления
        if (
            state.next_conditional_spawn_hour >= 0
            and state.conditional_trader_knowledge_hour < 0
            and hour >= state.next_conditional_spawn_hour - CONDITIONAL_TRADER_KNOWLEDGE_LEAD
        ):
            state.conditional_trader_knowledge_hour = hour
            self._broadcast_conditional_trader_info(hour)
        
        # Создаём торговца
        if (
            state.next_conditional_spawn_hour >= 0
            and state.conditional_trader_id is None
            and hour >= state.next_conditional_spawn_hour
        ):
            self._spawn_conditional_trader(hour)

    def _broadcast_conditional_trader_info(self, hour: int) -> None:
        """Рассылает знания о ситуативном торговце NPC «Серой лиги». (§16.6)"""
        # Сектор выбирается случайно
        sector_ids = list(self.state.sectors.keys())
        sector = self.state.rng.choice(sector_ids)
        self.state.conditional_trader_sector = sector
        
        for npc in self.state.humans:
            if npc.faction != "Серая лига":
                continue
            if npc.status in (EntityStatus.DEAD, EntityStatus.EXILED):
                continue
            kb = self.state.knowledge_bases.setdefault(npc.id, KnowledgeBase())
            kb.add_manual(
                npc.id,
                KnowledgeType.TRADER,
                subject_id=self.state.next_conditional_spawn_hour,
                payload={
                    "type": "conditional_trader",
                    "sector_id": sector,
                    "start_hour": self.state.next_conditional_spawn_hour,
                    "end_hour": self.state.next_conditional_spawn_hour + CONDITIONAL_TRADER_DURATION,
                },
                hour=hour,
            )
        
        self.state.news_manager.create_event(
            hour=hour, minute=0, sector_id=0,
            event_type="conditional_trader_schedule",
            participants=[],
            result="scheduled",
            importance=40,
            summary=f"«Серая лига» получила расписание ситуативного торговца: сектор {sector}, начало к часу {self.state.next_conditional_spawn_hour}",
            details={"sector_id": sector, "start_hour": self.state.next_conditional_spawn_hour},
        )

    def _spawn_conditional_trader(self, hour: int) -> None:
        """Создаёт ситуативного торговца. (§16.6)"""
        state = self.state
        
        # Создаём NPC-торговца
        trader = HumanNPC(
            id=state.next_human_id,
            sector_id=state.conditional_trader_sector,
            faction="Серая лига",
            name="Ситуативный торговец",
            attack=40, defense=40, attentiveness=60, bravery=50,
            is_stationary=False,  # мобильный
            stationary_role=None,
            money=1000,
        )
        state.next_human_id += 1
        state.humans.append(trader)
        state.conditional_trader_id = trader.id
        
        # Устанавливаем время работы: 12 часов
        state.conditional_trader_start_hour = hour
        state.conditional_trader_end_hour = hour + CONDITIONAL_TRADER_DURATION
        
        # Даем стартовое снаряжение
        self._give_starting_equipment(trader)
        
        self.state.news_manager.create_event(
            hour=hour, minute=0, sector_id=state.conditional_trader_sector,
            event_type="conditional_trader_appear",
            participants=[trader.id],
            result="appeared",
            importance=60,
            summary=f"Ситуативный торговец «Серой лиги» появился в секторе {state.conditional_trader_sector}",
            details={"trader_id": trader.id, "sector_id": state.conditional_trader_sector},
        )

    def _expire_conditional_trader_if_expired(self, hour: int) -> None:
        """Удаляет ситуативного торговца через 12 часов. (§16.6)"""
        state = self.state
        
        if state.conditional_trader_id is None:
            return
        
        if hour >= state.conditional_trader_end_hour:
            # Торговец уходит
            trader_id = state.conditional_trader_id
            sector = state.conditional_trader_sector
            
            # Находим NPC и помечаем как EXILED
            for npc in state.humans:
                if npc.id == trader_id:
                    npc.status = EntityStatus.EXILED
                    break
            
            self.state.news_manager.create_event(
                hour=hour, minute=0, sector_id=sector,
                event_type="conditional_trader_depart",
                participants=[trader_id],
                result="departed",
                importance=30,
                summary=f"Ситуативный торговец покинул сектор {sector} (истекло 12 часов)",
                details={"trader_id": trader_id},
            )
            
            # Сбрасываем состояние
            state.conditional_trader_id = None
            state.conditional_trader_sector = -1
            state.conditional_trader_start_hour = -1
            state.conditional_trader_end_hour = -1
            state.conditional_trader_knowledge_hour = -1
            
            # Планируем следующее появление
            self._schedule_conditional_trader(hour)


    # --- Выброс (§12.7) — все функции перенесены в anomalies/emission.py

    # --- Находки: срок жизни ~суток (§16.10) ---

    # --- Сигналы бедствия (§16.10) ---

    def _process_distress_signals(self, hour: int) -> None:
        from zonesim.world.sector import get_distance

        for group in self.state.human_groups.values():
            members = active_members(self.state,  group)
            if not members:
                continue
            if hour - getattr(group, "last_distress_hour", -100) < 24:
                continue
            avg_health = sum(m.health_share for m in members) / len(members)
            if avg_health > 0.3 or self.state.rng.random() >= 0.5:
                continue
            group.last_distress_hour = hour
            npcs = {npc.id: npc for npc in self.state.humans}
            faction = npcs[group.leader_id].faction if group.leader_id in npcs else ""
            for npc in self.state.humans:
                if npc.status in (EntityStatus.DEAD, EntityStatus.EXILED):
                    continue
                distance = get_distance(self.state.sectors, npc.sector_id, group.sector_id)
                if distance is None or distance > 3:
                    continue
                kb = self.state.knowledge_bases.setdefault(npc.id, KnowledgeBase())
                kb.add_manual(
                    npc.id, KnowledgeType.EVENT, subject_id=group.id,
                    payload={
                        "type": "distress",
                        "sector_id": group.sector_id,
                        "group_id": group.id,
                        "faction": faction,
                        "hour": hour,
                    },
                    hour=hour,
                )
            self.state.news_manager.create_event(
                hour=hour, minute=5, sector_id=group.sector_id,
                event_type="distress_signal",
                participants=[m.id for m in members], result="sent", importance=45,
                summary=f"Группа {group.id} подаёт сигнал бедствия",
                details={"group_id": group.id, "sector_id": group.sector_id},
            )

    def _active_distress_for(self, group: HumanGroup, hour: int) -> dict | None:
        """Самый свежий активный сигнал, известный группе."""
        humans = {npc.id: npc for npc in self.state.humans}
        best: dict | None = None
        for member_id in group.members:
            npc = humans.get(member_id)
            if npc is None:
                continue
            kb = self.state.knowledge_bases.get(npc.id)
            if kb is None:
                continue
            for fact in kb.get_facts(KnowledgeType.EVENT):
                payload = fact.payload
                if payload.get("type") != "distress":
                    continue
                if payload.get("group_id") == group.id:
                    continue
                if hour - payload.get("hour", -100) > 24:
                    continue
                if best is None or payload["hour"] > best["hour"]:
                    best = payload
        return best

    def _aid_distress_group(
        self, group: HumanGroup, members: list[HumanNPC], distress: dict, hour: int,
    ) -> None:
        """Помощь прибывшей группы: передать заряд аптечки самому раненому."""
        target_group = self.state.human_groups.get(distress["group_id"])
        if target_group is None:
            return
        victims = [m for m in active_members(self.state,  target_group) if m.health_share < 0.95]
        if not victims:
            return
        patient = min(victims, key=lambda npc: npc.health_share)
        medkits = [
            self.state.items[item_id]
            for npc in members for item_id in npc.inventory
            if item_id in self.state.items
            and self.state.items[item_id].type is ItemType.MEDICINE
            and self.state.items[item_id].properties.get("charges", 0) > 0
        ]
        if not medkits:
            return
        patient.health = min(
            patient.max_health,
            patient.health + medkits[0].properties.get("heal_amount", 30),
        )
        use_medkit_charge(self.state,  medkits[0], members)
        self.state.news_manager.create_event(
            hour=hour, minute=50, sector_id=group.sector_id,
            event_type="distress_aid",
            participants=[m.id for m in members] + [patient.id],
            result="aided", importance=30,
            summary=f"Группа {group.id} помогла группе {target_group.id}",
            details={"group_id": target_group.id, "patient_id": patient.id},
        )
        # сигнал считается отработанным
        for kb in self.state.knowledge_bases.values():
            kb.facts = [
                f for f in kb.facts
                if not (
                    f.fact_type == KnowledgeType.EVENT
                    and f.payload.get("type") == "distress"
                    and f.payload.get("group_id") == target_group.id
                )
            ]

    def _equip_guard(self, npc: HumanNPC) -> None:
        """Охранник базы получает лучшее оружие и броню из каталога,
        много патронов и аптечек — бесплатно, за счёт группировки."""
        for item_id in (npc.equipped_weapon_id, npc.equipped_armor_id):
            item = self.state.items.get(item_id)
            if item is not None and item_id in npc.inventory:
                npc.inventory.remove(item_id)
            self.state.items.pop(item_id, None)
        weapon_entry = max(
            (e for e in self.catalog.entries() if e["category"] == "weapon"),
            key=lambda e: (e["base_damage"], e["base_value"]),
        )
        armor_entry = max(
            (e for e in self.catalog.entries() if e["category"] == "body_armor"),
            key=lambda e: (e["armor_factor"], e["base_value"]),
        )
        weapon = self._spawn_catalog_item(weapon_entry["id"], npc.id)
        armor = self._spawn_catalog_item(armor_entry["id"], npc.id)
        npc.equipped_weapon_id = weapon.id
        npc.equipped_armor_id = armor.id
        if weapon_entry.get("ammo_type"):
            self._spawn_catalog_item(weapon_entry["ammo_type"], npc.id, quantity=60)
        for _ in range(3):
            self._spawn_catalog_item("gear.medkit.sanitar2", npc.id)
        sync_npc_from_items(self.state, npc)

    # --- Ротация охраны: раненый уходит лечиться, пост занимает резервист ---
    # Расхождение ТЗ/код: ТЗ указывает 2, в коде DEFAULT_GUARDS_PER_BASE = 4
    # (см. config.py). Инвариант #11 проверяет >= DEFAULT_GUARDS_PER_BASE.

    GUARD_ROTATION_HEALTH = 0.5    # ниже этого доли здоровья — смена
    GUARD_RECOVERY_PER_DAY = 0.5   # лазарет базы лечит 50% в сутки
    GUARDS_PER_BASE = DEFAULT_GUARDS_PER_BASE  # штат охраны базы

    def _process_guard_rotation(self, hour: int) -> None:
        """Раненый охранник лечится и заменяется резервистом; погибших
        группировка восполняет новобранцами.

        Гарантирует минимум GUARDS_PER_BASE активных охранников на базе
        (даже когда некоторые на лечении).
        """
        if hour % 24 != 0:
            return
        guards = [
            n for n in self.state.stationary_humans
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
                        guard.health + int(guard.max_health * self.GUARD_RECOVERY_PER_DAY),
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
                        self.state.news_manager.create_event(
                            hour=hour, minute=0, sector_id=sector_id,
                            event_type="guard_returned", participants=[guard.id],
                            result="returned", importance=25,
                            summary=f"Охранник {guard.id} вернулся на пост после лечения",
                            details={"guard_id": guard.id},
                        )
                elif (
                    guard.status == EntityStatus.ACTIVE
                    and guard.health_share <= self.GUARD_ROTATION_HEALTH
                    and not getattr(guard, "on_treatment", False)
                    and not any(
                        getattr(n, "reserve_for", None) == guard.id
                        and n.status not in (EntityStatus.DEAD, EntityStatus.EXILED)
                        for n in guards
                    )
                    # Не отправляем на лечение, если это приведёт к падению ниже
                    # минимума (с учётом одного охранника на лечении)
                    and (active_count - 1) >= self.GUARDS_PER_BASE - 1
                ):
                    guard.on_treatment = True
                    guard.status = EntityStatus.SLEEPING
                    reserve = self._spawn_guard(guard, name="Резервист", reserve_for=guard.id)
                    self.state.news_manager.create_event(
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
        for sector in self.state.sectors.values():
            if not sector.is_faction_start:
                continue
            roster = [
                n for n in self.state.stationary_humans
                if n.stationary_role == "guard"
                and n.sector_id == sector.id
                and n.status == EntityStatus.ACTIVE
                and getattr(n, "reserve_for", None) is None
            ]
            while len(roster) < self.GUARDS_PER_BASE:
                template = roster[0] if roster else next(
                    (n for n in self.state.stationary_humans
                     if n.stationary_role == "trader" and n.sector_id == sector.id),
                    None,
                )
                faction = template.faction if template else sector.controller_faction or "Бродяги"
                recruit = HumanNPC(
                    id=self.state.next_human_id,
                    faction=faction,
                    sector_id=sector.id,
                    name="Охранник-новобранец",
                    attack=55, defense=55, attentiveness=55, bravery=70,
                    is_stationary=True, stationary_role="guard",
                    money=0,
                )
                self.state.next_human_id += 1
                self.state.stationary_humans.append(recruit)
                self._equip_guard(recruit)
                roster.append(recruit)
                self.state.news_manager.create_event(
                    hour=hour, minute=0, sector_id=sector.id,
                    event_type="guard_recruited", participants=[recruit.id],
                    result="recruited", importance=25,
                    summary=f"Группировка «{faction}» пополнила охрану базы новобранцем {recruit.id}",
                    details={"guard_id": recruit.id, "faction": faction},
                )

    def _spawn_guard(self, wounded: HumanNPC, name: str, reserve_for: int | None) -> HumanNPC:
        guard = HumanNPC(
            id=self.state.next_human_id,
            faction=wounded.faction,
            sector_id=wounded.sector_id,
            name=name,
            attack=55, defense=55, attentiveness=55, bravery=70,
            is_stationary=True, stationary_role="guard",
            money=0,
        )
        self.state.next_human_id += 1
        guard.reserve_for = reserve_for
        self.state.stationary_humans.append(guard)
        self._equip_guard(guard)
        return guard

    def trade_price(self, item_ref: str, quantity: int = 1) -> float:
        """Цена покупки у торговца с учётом stock_multiplier (§16.3)."""
        entry = self.catalog.get(item_ref)
        base_price = entry["base_value"] * entry.get("quality", 1.0)
        
        # Находим торговца для этого предмета
        trader_id = self._find_trader_for_item(item_ref)
        if trader_id is None:
            # Фоллбэк: простая формула
            return round(base_price * self.TRADE_MARKUP * quantity, 1)
        
        # Получаем текущий запас
        stock = self.state.trader_stock.get(trader_id, {})
        current_stock = stock.get(item_ref, 0)
        target_stock = self.TRADER_START_QTY.get(entry["category"], 1)
        
        # Используем формулы ТЗ §16.3
        type_mult = get_type_multiplier(item_ref)
        sell_price = calculate_sell_price(base_price, current_stock, target_stock, type_mult)
        
        return round(sell_price * quantity, 1)

    def _find_trader_for_item(self, item_ref: str) -> int | None:
        """Находит ID торговца для данного предмета."""
        # Для MVP: используем первого активного торговца
        for npc in self.state.stationary_humans:
            if npc.stationary_role == "trader" and npc.status == EntityStatus.ACTIVE:
                return npc.id
        return None

    # Скупочная цена ценностей (доля базовой стоимости)
    SELL_PRICE_SHARE = 0.6
    # Обмен в час отдыха: пороги отношений фракций
    REST_EXCHANGE_RELATION = 20   # обмен информацией
    REST_TRADE_RELATION = 40      # меновая торговля ценностями
    REST_TRADE_PRICE_SHARE = 0.8  # цена меновой сделки от базовой стоимости
    # Семейства комплектов для проактивной закупки: (тип, самая дешёвая модель)
    PROACTIVE_KITS = (
        (ItemType.DETECTOR, "gear.detector.radar1"),
        (ItemType.CAPTURE_KIT, "capture.kit.predator"),
        (ItemType.DESTROY_KIT, "anomaly.kit.subtle"),
    )

    def _purchase_plan(
        self, group: HumanGroup, members: list[HumanNPC], stock: dict[str, int],
        leader_money: float = 0.0,
    ) -> list[tuple[str, int]]:
        """Приоритетный список покупок группы у торговца."""
        plan: list[tuple[str, int]] = []
        spent = 0.0
        has_medkit = any(
            self.state.items[item_id].type is ItemType.MEDICINE
            for npc in members for item_id in npc.inventory
            if item_id in self.state.items
        )
        if not has_medkit and stock.get("gear.medkit.sanitar2", 0) > 0:
            ref = "gear.medkit.sanitar2"
            price = self.trade_price(ref)
            if spent + price <= leader_money:
                spent += price
                plan.append((ref, 1))
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
                price = self.trade_price(kit_ref)
                if spent + price <= leader_money:
                    spent += price
                    plan.append((kit_ref, 1))
        target = capture_target(self.state, group)
        if target is not None:
            kit_ref = CAPTURE_KIT_REF.get(species_value(target))
            owned = any(
                item.properties.get("target_species") == species_value(target)
                for npc in members for item_id in npc.inventory
                if (item := self.state.items.get(item_id)) is not None
                and item.type is ItemType.CAPTURE_KIT and item.condition > 0
            )
            if kit_ref and not owned and stock.get(kit_ref, 0) > 0:
                price = self.trade_price(kit_ref)
                if spent + price <= leader_money:
                    spent += price
                    plan.append((kit_ref, 1))
        leader = group_leader(group, members)
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
                price = self.trade_price(ammo_ref, 12)
                if spent + price <= leader_money:
                    spent += price
                    plan.append((ammo_ref, 12))
        # проактивная закупка комплектов только если не купили essentials
        if not plan:
            for kit_type, default_ref in self.PROACTIVE_KITS:
                owned_any = any(
                    self.state.items[item_id].type is kit_type and self.state.items[item_id].condition > 0
                    for npc in members for item_id in npc.inventory
                    if item_id in self.state.items
                )
                if owned_any or stock.get(default_ref, 0) <= 0:
                    continue
                price = self.trade_price(default_ref)
                if spent + price <= leader_money:
                    spent += price
                    plan.append((default_ref, 1))
        return plan


    def _process_rest_trade(self, hour: int, resting_groups: list[HumanGroup]) -> None:
        """Торговля как час отдыха у торговца: сначала продажа, потом закупка. (§16)"""
        traders = [
            npc for npc in self.state.stationary_humans
            if npc.stationary_role == "trader" and npc.status == EntityStatus.ACTIVE
        ]
        for group in resting_groups:
            members = active_members(self.state,  group)
            if not members or any(npc.id in self._combat_human_ids for npc in members):
                continue
            rest_heal(self.state,  group, members)
            if not traders:
                continue
            trader = next(
                (t for t in traders if t.sector_id == group.sector_id), None,
            )
            if trader is None:
                continue
            leader = group_leader(group, members)
            stock = self.state.trader_stock.setdefault(trader.id, {})
            # сначала продажа добычи — освобождает деньги для закупки
            initial_money = leader.money
            sell_loot(self.state,  leader, trader)
            # buyer money = initial + proceeds from sell
            buyer_money = leader.money
            for item_ref, quantity in self._purchase_plan(group, members, stock, buyer_money):
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
                sync_npc_from_items(self.state, leader)

    def _process_rest_exchanges(self, hour: int, resting_groups: list[HumanGroup]) -> None:
        """Обмен информацией и ценностями между отдыхающими группами. (§14.3)"""
        by_sector: dict[int, list[HumanGroup]] = {}
        for group in resting_groups:
            by_sector.setdefault(group.sector_id, []).append(group)
        for sector_id, groups in by_sector.items():
            for index, first in enumerate(groups):
                for second in groups[index + 1:]:
                    first_faction = group_faction(first, self.state)
                    second_faction = group_faction(second, self.state)
                    if first_faction is None or second_faction is None:
                        continue
                    relation = self.state.faction_relations.get(first_faction, second_faction)
                    if relation >= self.REST_EXCHANGE_RELATION:
                        self._exchange_knowledge(first, second, hour)
                    if relation >= self.REST_TRADE_RELATION:
                        self._barter_groups(first, second, sector_id, hour)
                        # Улучшение отношений при торговле (§15.2, #17 инвариант)
                        delta = 3
                        evt = self.state.news_manager.create_event(
                            hour=hour, minute=55, sector_id=sector_id,
                            event_type="faction_cooperation",
                            participants=[],
                            result="trade",
                            importance=15,
                            summary=f"Торговля: {first_faction} ↔ {second_faction} +{delta}",
                            details={"delta": delta, "sector_id": sector_id},
                            notified_factions=[first_faction, second_faction],
                        )
                        self.state.faction_relations.change(first_faction, second_faction, delta)
                        log_relation_change(self.state, hour, first_faction, second_faction, delta, evt.id)

    def _exchange_knowledge(self, group_a: HumanGroup, group_b: HumanGroup, hour: int) -> None:
        """Обмен сведениями между лидерами отдыхающих групп. (§17)"""
        npcs = {npc.id: npc for npc in self.state.humans}
        leader_a = npcs.get(group_a.leader_id)
        leader_b = npcs.get(group_b.leader_id)
        if leader_a is None or leader_b is None:
            return
        kb_a = self.state.knowledge_bases.get(leader_a.id)
        kb_b = self.state.knowledge_bases.get(leader_b.id)
        if kb_a is None or kb_b is None:
            return
        for source, target, owner in ((kb_a, kb_b, leader_b), (kb_b, kb_a, leader_a)):
            existing = {(f.fact_type, f.subject_id) for f in target.facts}
            for fact in source.facts:
                if (fact.fact_type, fact.subject_id) in existing:
                    continue
                target.add_manual(
                    owner.id, fact.fact_type, fact.subject_id,
                    dict(fact.payload), hour, source="conversation",
                )

    def _barter_groups(
        self, group_a: HumanGroup, group_b: HumanGroup, sector_id: int, hour: int,
    ) -> None:
        """Меновая торговля ценностью между отдыхающими группами. (§14.3)"""
        npcs = {npc.id: npc for npc in self.state.humans}
        leader_a = npcs.get(group_a.leader_id)
        leader_b = npcs.get(group_b.leader_id)
        if leader_a is None or leader_b is None:
            return
        sellable = (
            ItemType.ARTIFACT, ItemType.MONSTER_PART,
            ItemType.ANOMALY_PART, ItemType.LIVE_MONSTER,
        )
        seller, buyer = (leader_a, leader_b) if leader_a.money <= leader_b.money else (leader_b, leader_a)
        goods = [
            self.state.items[item_id] for item_id in seller.inventory
            if item_id in self.state.items
            and self.state.items[item_id].type in sellable
        ]
        if not goods:
            return
        item = max(goods, key=lambda entry: entry.base_value)
        price = round(item.base_value * self.REST_TRADE_PRICE_SHARE, 1)
        if buyer.money < price:
            return
        seller.inventory.remove(item.id)
        give_item(item, buyer.id, buyer.inventory)
        seller.money += price
        buyer.money -= price
        self.state.news_manager.create_event(
            hour=hour, minute=50, sector_id=sector_id,
            event_type="rest_trade",
            participants=[seller.id, buyer.id],
            result="barter", importance=10,
            summary=f"NPC {buyer.id} купил «{item.name}» у NPC {seller.id} за {price}",
            details={"item_id": item.id, "price": price},
        )

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
        self._spawn_catalog_item("shelter.kit.basic", npc.id)  # нерасходный набор для убежища (§7.10)
        sync_npc_from_items(self.state, npc)

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

    # === Инвариант #17: журнал изменений отношений фракций ===

    def _save_relation_snapshot(self) -> None:
        """Сохраняет снимок текущих отношений перед шагом (§17 инвариант)."""
        fr = self.state.faction_relations
        snap: dict[tuple[str, str], int] = {}
        for (a, b), val in fr._relations.items():
            snap[(a, b)] = val
        self.state.prev_relation_snapshot = snap

    def simulate_hour(self) -> dict[str, Any]:
        """
        Выполняет один час симуляции. (§8 ТЗ)
        Возвращает сводку по событиям часа.
        """
        hour = self.state.time.hour
        day = self.state.time.day
        phase = self.state.time.current_phase
        is_night = self.state.time.is_night()

        # Контекст текущего часа
        self.context.hour = hour
        self.context.day = day
        self.context.phase = phase
        self.context.is_night = is_night
        self.context.events = []
        self.context.phase_results = {}

        events: list[dict] = []

        # Сохраняем снимок отношений перед шагом (для инварианта #17)
        self._save_relation_snapshot()
        # Очищаем intention_knowledge_used — данные не должны смешиваться между часами
        self.state.intention_knowledge_used = {}

        # Фаза 0: Проверка состояния
        run_phase0_check(self.context)

        # Фаза 1: Запланированные события
        run_phase1_scheduled(self.context)

        # Фаза 2: Окружающая среда и торговля
        run_phase2_environment(self.context)

        # Фаза 3: Обнаружение и распространение сведений
        run_phase3_knowledge(self.context)

        # Фаза 4: Выбор намерений
        run_phase4_intentions(self.context)

        # Фаза 5: Перемещение
        run_phase5_movement(self.context)

        # Фаза 6: Обнаружение и встречи
        run_phase6_detections(self.context)

        # Фаза 7: Основные действия
        run_phase7_actions(self.context)

        # Фаза 8: Воздействие окружающей среды
        run_phase8_environment(self.context)

        # Фаза 9: Последствия
        run_phase9_consequences(self.context)

        # Перед проверкой инвариантов — финальная согласованность укрытий (#23)
        free_emptied_shelters(self.state, hour)

        # Проверка инвариантов мира (§22 ТЗ) — ПОСЛЕ шага, на моменте часа
        errors = assert_world_invariants(self.state)
        if errors:
            raise InvariantViolation(
                f"Hour={hour}, Day={day}: " + "; ".join(errors[:10])
            )

        # Фаза 10: сначала фиксируется следующий час, затем выполняется автосохранение
        self.state.time.advance()
        run_phase10_report(self.context)

        # Заполнить events событиями часа из news_manager
        events = [
            e.to_dict()
            for e in self.state.news_manager.events
            if e.hour == hour
        ]

        return {
            "hour": hour,
            "day": day,
            "phase": phase.value,
            "is_night": is_night,
            "events": events,
        }

    def _phase4_monster_intentions(self, hour: int) -> None:
        entities = {
            entity.id: entity
            for entity in self.state.humans + self.state.stationary_humans + self.state.monsters
        }
        for group in self.state.monster_groups.values():
            members = monster_group_members(self.state, group)
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

    def _apply_human_move(
        self,
        group: HumanGroup,
        members: list[HumanNPC],
        path: list[int],
        npcs: dict[int, HumanNPC],
        hour: int,
    ) -> None:
        crossed = []
        prev = group.sector_id
        for sector_id in path:
            crossed.append(edge_key(prev, sector_id))
            prev = sector_id
        group.sector_id = path[-1]
        for npc in members:
            npc.sector_id = group.sector_id
            self._moved_human_ids.add(npc.id)
            update_stamina(
                npc, STAMINA_COST_MOVEMENT * len(path), "movement", self.state.time,
            )
            self.state.visit_memory.setdefault(npc.id, {})[group.sector_id] = hour
        for prisoner_id in group.prisoners:
            if prisoner_id in npcs:
                npcs[prisoner_id].sector_id = group.sector_id
        self._check_blocked_trails(group, members, crossed, hour, is_monster=False)

    def _check_blocked_trails(
        self,
        group,
        members: list,
        crossed: list[tuple[int, int]],
        hour: int,
        is_monster: bool,
    ) -> None:
        """Перекрытые тропы: одна проверка на группу при переходе. (§10.5)"""
        if not crossed:
            return
        blocked = blocked_trail_map(self.state)
        is_night = self.state.time.is_night()
        for edge in crossed:
            anomaly = blocked.get(edge)
            if anomaly is None:
                continue
            if not is_monster and group_has_passage(self.state, group, anomaly):
                continue  # держатели прохода пересекают без проверки
            attentiveness = max(member.attentiveness for member in members)
            if is_monster:
                bonus = (
                    0 if species_value(members[0]) == "large_migrator"
                    else MONSTER_NATIVE_ANOMALY_BONUS
                )
            else:
                bonus = group_detector_bonus(self.state).get(group.id, 0)
            contact = check_anomaly_contact(
                entity_sector=members[0].sector_id,
                anomaly=anomaly,
                rng_func=self.state.rng.random,
                attentiveness=attentiveness,
                known_bonus=bonus,
                is_night=is_night,
            )
            if contact["result"] != "hit":
                continue
            victim = self.state.rng.choice(members)
            is_monster = isinstance(victim, Monster)
            start = victim.health
            result = apply_anomaly_damage(
                victim.health, victim.max_health, anomaly, self.state.rng.random(),
            )
            victim.health = result["new_health"]
            if is_monster:
                if victim.health <= 0:
                    victim.status = EntityStatus.DEAD
                    from zonesim.combat.loot import create_corpse
                    create_corpse(self.state, victim, hour)
            elif victim.health <= 0:
                set_unconscious_or_dead(self.state,  victim, start, hour, cause="anomaly")
            self.state.news_manager.create_event(
                hour=hour, minute=10, sector_id=victim.sector_id,
                event_type="trail_block_hit",
                participants=[victim.id], result="hit", importance=20,
                summary=(
                    f"{'Монстр' if is_monster else 'NPC'} {victim.id} прошёл"
                    f" через блокированную тропу аномалии {anomaly.id}"
                ),
                details={"anomaly_id": anomaly.id, "edge": list(edge)},
            )

    def _move_monster_groups(self, hour: int) -> None:
        from zonesim.world.sector import get_distance

        self._moved_monster_ids = set()
        trails = trail_set(self.state)
        for group in self.state.monster_groups.values():
            all_members = monster_group_members(self.state, group, active_only=False)
            members = [monster for monster in all_members if monster.status == EntityStatus.ACTIVE]
            if not members or len(members) != len(all_members):
                continue
            if group.intention in ("feed", "hunt", "rest"):
                continue
            # пункты движения: хищник 2,0, остальные 1,0 (§10.4)
            points = 2.0 if group.species == "territorial_predator" else 1.0
            path: list[int] = []
            if group.intention == "stalk" and group.target_sector_id is not None:
                path = walk(
                    self.state, group.sector_id, {group.target_sector_id}, set(), points,
                )
            elif group.intention == "return_home" and group.home_sector_id is not None:
                path = walk(
                    self.state, group.sector_id, {group.home_sector_id}, set(), points,
                )
            elif group.intention == "roam":
                current = group.sector_id
                while points > 1e-9:
                    sector = self.state.sectors[current]
                    candidates = list(sector.neighbors)
                    if group.species == "scavenger_pack":
                        corpse_sectors = [
                            sid for sid in candidates
                            if any(
                                corpse.sector_id == sid and corpse.status == "available"
                                for corpse in self.state.corpses
                            )
                        ]
                        if corpse_sectors:
                            candidates = corpse_sectors
                    if group.species == "territorial_predator" and group.home_sector_id is not None:
                        nearby = []
                        for sid in candidates:
                            distance = get_distance(
                                self.state.sectors, sid, group.home_sector_id
                            )
                            if distance is not None and distance <= 2:
                                nearby.append(sid)
                        if nearby:
                            candidates = nearby
                    if not candidates or self.state.rng.random() >= 0.4:
                        break
                    destination = self.state.rng.choice(candidates)
                    cost = edge_cost(trails, current, destination)
                    if points + 1e-9 < cost:
                        break
                    points -= cost
                    current = destination
                    path.append(destination)
            if not path:
                continue
            crossed = []
            prev = group.sector_id
            for sector_id in path:
                crossed.append(edge_key(prev, sector_id))
                prev = sector_id
            group.sector_id = path[-1]
            for monster in members:
                monster.sector_id = group.sector_id
                monster.stamina = max(0, monster.stamina - 5 * len(path))
                self._moved_monster_ids.add(monster.id)
            self._check_blocked_trails(group, members, crossed, hour, is_monster=True)

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
            # Местные виды чувствуют аномалии; крупные мигранты — нет (§12.2)
            native_bonus = (
                0 if species_value(monster) == "large_migrator" else MONSTER_NATIVE_ANOMALY_BONUS
            )
            contact = check_anomaly_contact(
                entity_sector=monster.sector_id,
                anomaly=anomaly,
                rng_func=self.state.rng.random,
                attentiveness=max(1, monster.attentiveness - 2 * (group_size - 1)),
                known_bonus=native_bonus,
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
                from zonesim.combat.loot import create_corpse
                create_corpse(self.state, monster, hour)
            self.state.news_manager.create_event(
                hour=hour, minute=5, sector_id=monster.sector_id,
                event_type="anomaly_hit", participants=[monster.id],
                result="dead" if monster.status == EntityStatus.DEAD else "hit",
                importance=60 if monster.status == EntityStatus.DEAD else 30,
                summary=f"Монстр {monster.id} попал в аномалию {anomaly.id}",
                details={"damage": result["damage"], "anomaly_id": anomaly.id},
            )

    def _schedule_encounters(self, is_night: bool, hour: int) -> None:
        """Определяет боевые встречи; сами бои исполняются в фазе 7 (§8)."""
        self._pending_battles = []
        self._combat_human_ids = set()
        self._combat_monster_ids = set()
        self._feeding_claims = {}
        humans = {npc.id: npc for npc in self.state.humans}
        engaged_groups: set[int] = set()
        engaged_monsters: set[int] = set()

        def in_combat_cooldown(*groups) -> bool:
            return any(
                hour - getattr(group, "last_combat_hour", -100) < COMBAT_COOLDOWN_HOURS
                for group in groups
            )

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
                    monster for monster in monster_group_members(self.state, group)
                    if monster.id not in engaged_monsters
                ]
                if members:
                    monster_groups.append((group, members))

            for monster_group, monsters in monster_groups:
                if monster_group.intention in ("feed", "rest"):
                    continue
                if in_combat_cooldown(monster_group):
                    continue  # передышка после недавнего боя (§11.1)
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
                        guards = base_guards(self.state, sector_id, target_members[0].faction)
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
                    if in_combat_cooldown(first_group, second_group):
                        continue  # передышка после недавнего боя (§11.1)
                    first_faction = first_members[0].faction
                    second_faction = second_members[0].faction
                    relation = self.state.faction_relations.get(first_faction, second_faction)
                    if first_faction == second_faction or relation > -20:
                        continue
                    if self.state.rng.random() >= 0.25:
                        continue

                    attacker_group, attacker_members = first_group, first_members
                    defender_group, defender_members = second_group, second_members
                    if sector.controller_faction == first_faction != second_faction:
                        defender_group, defender_members = first_group, first_members
                        attacker_group, attacker_members = second_group, second_members
                    guards = base_guards(self.state, sector_id, defender_members[0].faction)
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
                    if in_combat_cooldown(attacker_group, defender_group):
                        continue  # передышка после недавнего боя (§11.1)
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

        self._resolve_feeding_competition(engaged_monsters, hour)

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

    def _resolve_feeding_competition(self, engaged_monsters: set[int], hour: int) -> None:
        claims: dict[int, list[tuple[MonsterGroup, list[Monster]]]] = {}
        for group in self.state.monster_groups.values():
            if group.intention != "feed":
                continue
            members = monster_group_members(self.state, group)
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
            competitors.sort(key=lambda item: monster_group_power(item[1]), reverse=True)
            strongest = competitors[0]
            if len(competitors) > 1:
                challenger = competitors[1]
                strong_power = monster_group_power(strongest[1])
                weak_power = monster_group_power(challenger[1])
                difference = abs(strong_power - weak_power) / max(strong_power, weak_power, 0.001)
                rested = all(
                    hour - getattr(group, "last_combat_hour", -100) >= COMBAT_COOLDOWN_HOURS
                    for group in (strongest[0], challenger[0])
                )
                if difference <= 0.15 and rested:
                    self._schedule_monster_attack(
                        strongest[0], strongest[1], challenger[1], None,
                        strongest[0].sector_id, True,
                        defender_monster_group_id=challenger[0].id,
                        feed_corpse_id=corpse_id,
                    )
                    continue
                challenger[0].intention = "roam"
            self._feeding_claims[strongest[0].id] = corpse_id

    def _monsters_attack(self, monsters: list[Monster], prey: list, is_night: bool) -> bool:
        predator = monsters[0]
        species = species_value(predator)
        health_share = sum(target.health_share for target in prey) / len(prey)
        predator_health = sum(monster.health_share for monster in monsters) / len(monsters)
        prey_is_monster = isinstance(prey[0], Monster)
        if predator_health <= 0.35:
            return False
        if species == "territorial_predator" and len(monsters) == 1 and health_share > 0.8:
            return False
        if species == "scavenger_pack" and health_share > 0.6 and len(monsters) <= len(prey):
            return False
        if not prey_is_monster and health_share > 0.6 and len(monsters) < len(prey):
            return False  # здоровая группа людей численно сильнее — не атаковать
        # решение по конечной силе отряда, а не только по здоровью и численности
        prey_power = squad_power(prey, self.state.items)
        if not prey_is_monster:
            sector = self.state.sectors.get(prey[0].sector_id)
            if sector is not None and sector.is_faction_start:
                prey_power *= 1.0 + BASE_FORTIFICATION_BONUS  # укрепление базы
        predator_power = squad_power(monsters, self.state.items)
        if predator_power <= 0:
            return False
        if prey_power > predator_power * MONSTER_ATTACK_POWER_LIMIT:
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

    # --- Вспомогательные методы намерений ---

    def _known_anomaly_sectors(self, npc: HumanNPC) -> set[int]:
        kb = self.state.knowledge_bases.get(npc.id)
        if not kb:
            return set()
        return known_anomaly_sectors(kb.get_facts(KnowledgeType.ANOMALY))

    def _sleep_tick(self, npc: HumanNPC) -> None:
        """Сон: восстановление выносливости по §14.1 (комфорт 4 ч / иначе 6 ч)."""
        group = HumanGroup(id=-(npc.id + 1), members=[npc.id], sector_id=npc.sector_id)
        human_sleep_recover(
            group,
            sector_humans(self.state.humans, self.state.stationary_humans, npc.sector_id),
            self.state.time,
            self.state.rng,
            stationary={n.id: n for n in self.state.stationary_humans},
            shelters=self.state.shelters,
            temp_shelters=self.state.temp_shelters,
            sectors=self.state.sectors,
            faction=npc.faction,
        )

    def _unconscious_tick(self, npc: HumanNPC, hour: int) -> None:
        """Бессознательные состояния (§11.10, §14.2)."""
        if getattr(npc, "unconscious_reason", "") == "health_zero":
            # Сначала группа тратит медикаменты на своего бойца (§11.10)
            group = self.state.human_groups.get(npc.group_id)
            member_ids = set(group.members) if group else {npc.id}
            medkit = None
            owner = None
            for other in self.state.humans:
                if other.id not in member_ids or other.id == npc.id:
                    continue
                for item_id in other.inventory:
                    item = self.state.items.get(item_id)
                    if (
                        item is not None
                        and item.type is ItemType.MEDICINE
                        and item.quantity > 0
                    ):
                        medkit, owner = item, other
                        break
                if medkit is not None:
                    break
            if medkit is not None:
                heal = medkit.properties.get("heal_amount", 30)
                # тяжёлое состояние ~15% + лечение, не выше 60% (§11.10)
                npc.health = min(
                    int(npc.max_health * 0.6),
                    int(npc.max_health * 0.15) + heal,
                )
                npc.status = EntityStatus.ACTIVE  # тяжёлое состояние, но в строю
                use_medkit_charge(self.state,  medkit, [owner] if owner else [])
                sync_npc_from_items(self.state, owner)
                return
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
            group, sector_humans(self.state.humans, self.state.stationary_humans, npc.sector_id), self.state.time, self.state.rng,
        )

    def _rest_tick(self, npc: HumanNPC) -> None:
        """Отдых: ½ темпа комфортного сна при комфорте; на базе своей
        группировки — платное лечение до полного здоровья за 2 часа. (§14.3)"""
        group = self.state.human_groups.get(npc.group_id)
        member_ids = set(group.members) if group else set()
        # Комфорт отдыха — посторонний активный NPC в секторе (персонал базы,
        # другая группа); собственное присутствие группы комфортом не считается.
        comfort = any(
            other.status == EntityStatus.ACTIVE
            and other.sector_id == npc.sector_id
            and other.id not in member_ids
            for other in self.state.humans + self.state.stationary_humans
        )
        if comfort:
            max_st = npc.max_stamina
            npc.stamina = min(max_st, npc.stamina + max_st * 0.5 / HUMAN_COMFORT_HOURS)
        self._base_heal_tick(npc)

    def _base_heal_tick(self, npc: HumanNPC) -> None:
        """Лечение на базе своей группировки: курс 2 часа до полного
        здоровья, оплата — половина цены аптечки за курс."""
        home = home_sector_id(self.state.sectors, npc.faction, self._home_cache)
        if home is None or npc.sector_id != home or npc.health >= npc.max_health:
            return
        hour = self.state.time.hour
        heal_until = getattr(npc, "base_heal_until", -100)
        if hour >= heal_until:
            course_cost = round(self.trade_price("gear.medkit.sanitar2") / 2, 1)
            if npc.money < course_cost:
                return  # не хватает денег — база не лечит
            npc.money -= course_cost
            npc.base_heal_until = hour + 2
        npc.health = min(npc.max_health, npc.health + npc.max_health / 2)

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
                "has_artifact": True,  # артефакт обнаружен при исследовании
            }, hour)
            # Сформировавшийся артефакт извлекается (§12.3)
            give_artifact(self.state, npc, target, hour)
        elif result == "safe_path_found":
            kb.add_manual(npc.id, KnowledgeType.SAFE_PATH, target.id, {
                "sector_id": npc.sector_id, "active": True,
            }, hour)
        elif result == "artifact_found":
            kb.add_manual(npc.id, KnowledgeType.ANOMALY, target.id, {
                "sector_id": npc.sector_id, "has_artifact": True,
            }, hour)
            give_artifact(self.state, npc, target, hour)
        elif result == "damage_taken":
            start = npc.health
            npc.health = max(0, npc.health - outcome.get("damage", 0))
            if npc.health <= 0:
                set_unconscious_or_dead(self.state,  npc, start, hour, cause="research")

        if result != "no_new_info":
            self.state.news_manager.create_event(
                hour=hour, minute=30, sector_id=npc.sector_id,
                event_type="research", participants=[npc.id], result=result,
                importance=25, summary=f"NPC {npc.id} исследует аномалию {target.id}: {result}",
                details={"anomaly_id": target.id, "outcome": result},
            )

    def _process_artifact_sales(self, hour: int) -> None:
        """Продажа артефактов торговцу по формулам §16.3.

        Если NPC находится в секторе стационарного торговца и имеет артефакты,
        артефакт автоматически предлагается на продажу по цене:
        SellPrice = BasePrice × StockMultiplier × TypeMultiplier.
        """
        for trader in self.state.stationary_humans:
            if trader.stationary_role != "trader" or trader.status != EntityStatus.ACTIVE:
                continue
            trader_sector = trader.sector_id
            # Ищем мобильных NPC в секторе торговца
            for npc in self.state.humans:
                if npc.status != EntityStatus.ACTIVE or npc.sector_id != trader_sector:
                    continue
                # NPC продает все артефакты
                for art_id in list(npc.artifacts):
                    art = next(
                        (a for a in self.state.artifacts.artifacts if a.id == art_id),
                        None,
                    )
                    if art is None:
                        continue
                    # Рассчитываем цену по формуле §16.3
                    base_price = 200.0  # базовая цена артефакта
                    type_multiplier = 3.0  # TYPE_MULTIPLIERS["artifact"]
                    current_stock = sum(
                        1 for a in self.state.artifacts.artifacts if a.discovered
                    )
                    target_stock = 5
                    stock_mult = calculate_stock_multiplier(current_stock, target_stock)
                    sell_price = round(
                        base_price * stock_mult * type_multiplier, 2
                    )
                    # Проверяем деньги у NPC
                    if npc.money < sell_price:
                        continue
                    # Транзакция
                    npc.money -= int(sell_price)
                    trader.money += int(sell_price)
                    npc.artifacts.remove(art_id)
                    # Удаляем предмет из инвентаря
                    for item_id in list(npc.inventory):
                        item = self.state.items.get(item_id)
                        if item and item.properties.get("artifact_id") == art_id:
                            npc.inventory.remove(item_id)
                            self.state.items.pop(item_id, None)
                            break
                    self.state.news_manager.create_event(
                        hour=hour,
                        minute=0,
                        sector_id=trader_sector,
                        event_type="artifact_sale",
                        participants=[npc.id, trader.id],
                        result="sold",
                        importance=25,
                        summary=f"NPC {npc.id} продал артефакт ({art.rarity}) торговцу {trader.id} за {int(sell_price)}",
                        details={
                            "artifact_id": art_id,
                            "rarity": art.rarity,
                            "price": sell_price,
                        },
                    )
                    # Лимит 1 артефакт в час на торговца- NPC
                    break

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

    def _execute_battles(self, hour: int) -> None:
        for battle in self._pending_battles:
            for entity in battle["attackers"] + battle["defenders"]:
                if isinstance(entity, HumanNPC):
                    sync_npc_from_items(self.state, entity)
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
            # Отступление не ведёт в сектора с активными аномалиями (§11.7);
            # если обхода нет — маршрут остаётся прежним.
            anomaly_sectors = {
                a.sector_id for a in self.state.anomalies.values()
                if a.status == AnomalyStatus.ACTIVE
            }
            combat_sectors = {
                sid: replace(
                    sector,
                    neighbors=[
                        n for n in sector.neighbors if n not in anomaly_sectors
                    ] or list(sector.neighbors),
                )
                for sid, sector in self.state.sectors.items()
            }
            combat = CombatSystem(
                attackers=attackers,
                defenders=defenders,
                sectors=combat_sectors,
                attacker_is_monster=battle["attacker_is_monster"],
                defender_is_monster=battle["defender_is_monster"],
                battle_sector_id=battle["sector_id"],
                relation=battle.get("relation", 0),
                attacker_ambush=battle.get("attacker_ambush", False),
                defender_ambush=battle.get("defender_ambush", False),
                # базы и стационарные укрытия — опорные пункты при обороне (§7.16)
                defender_has_shelter=(
                    not battle["defender_is_monster"]
                    and battle["sector_id"] in shelter_sector_ids(self.state)
                ),
                defender_bonus=(
                    BASE_FORTIFICATION_BONUS
                    if self.state.sectors[battle["sector_id"]].is_faction_start
                    else 0.1
                ),
                # Условие B: бой до исхода — люди не отступают/не сдаются
                force_no_retreat=battle.get("force_no_retreat", False),
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
                # Инвариант #5: пленные не выбирают действий
                if hasattr(entity, 'intention'):
                    entity.intention = "sleep"
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
                # Фикс: если во время выброса группа отступает НЕ shelter —
                # она получает урон выброса и записывается в emission_exposed (§12.7)
                if (
                    group.id in self.state.human_groups
                    and emission_active(self.state, hour)
                    and not is_group_emission_sheltered(self.state,  group)
                ):
                    mark_group_emission_exposed(self.state, group, hour)
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
                for member_id in monster_group.members:
                    if member_id in entities and entities[member_id].status != EntityStatus.DEAD:
                        entities[member_id].sector_id = retreat_sector

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
                from zonesim.combat.loot import create_corpse
                create_corpse(self.state, entities[combatant.id], hour)

        participants = [entity.id for entity in battle["attackers"] + battle["defenders"]]
        # Передышка после боя для участвовавших групп (§11.1)
        for group_key in (
            "attacker_group_id", "defender_group_id",
            "attacker_monster_group_id", "defender_monster_group_id",
        ):
            group_id = battle.get(group_key)
            if group_id is None:
                continue
            group = (
                self.state.human_groups.get(group_id)
                or self.state.monster_groups.get(group_id)
            )
            if group is not None:
                group.last_combat_hour = hour
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

        # Изменение отношений фракций после боя людей (§15.2, #17 инвариант)
        if (
            not battle["attacker_is_monster"]
            and not battle["defender_is_monster"]
        ):
            attacker_faction = battle["attackers"][0].faction if battle["attackers"] else ""
            defender_faction = battle["defenders"][0].faction if battle["defenders"] else ""
            if attacker_faction and defender_faction and attacker_faction != defender_faction:
                # Проигрышшая сторона получает штраф к отношениям
                outcome = result.outcome
                if "attacker_wins" in outcome:
                    # Атакующие победили — отношения улучшаются незначительно
                    delta = 5
                elif "defender_wins" in outcome:
                    # Защитники победили — атакующие получают штраф
                    delta = -10
                else:
                    # Ничья или отступление
                    delta = -5
                # Создаём событие в news_manager
                evt = self.state.news_manager.create_event(
                    hour=hour, minute=20, sector_id=battle["sector_id"],
                    event_type="faction_relation_change",
                    participants=participants,
                    result=attacker_faction if "ATTACKER" in outcome else defender_faction,
                    importance=30,
                    summary=f"Отношения {attacker_faction} ↔ {defender_faction}: {delta}",
                    details={"delta": delta, "outcome": outcome},
                    notified_factions=[attacker_faction, defender_faction],
                )
                self.state.faction_relations.change(attacker_faction, defender_faction, delta)
                log_relation_change(self.state, hour, attacker_faction, defender_faction, delta, evt.id)

        # Условие A: после зачистки убежища — все атакующие группы входят без лимита (§12.7)
        if battle.get("emission_shelter_assault") and (
            "attacker_wins" in result.outcome
            or "defender_retreated" in result.outcome
        ):
            shelter_id = battle.get("shelter_id")
            if shelter_id is not None:
                shelter = self.state.shelters.get(shelter_id)
                if shelter and shelter.is_occupied:
                    # Монстры побеждены/отступили — убежище свободно
                    shelter.occupied_by = None
                    shelter.occupied_until = 0
                    self.state.news_manager.create_event(
                        hour=hour, minute=0, sector_id=battle["sector_id"],
                        event_type="shelter", participants=[], result="cleared",
                        importance=35,
                        summary=f"Укрытие {shelter_id} зачищено людьми (монстры изгнаны)",
                        details={"shelter_id": shelter_id},
                    )
                    # Условие A: все атакующие группы входят (безлимитная вместимость)
                    for npc in battle["attackers"]:
                        if isinstance(npc, HumanNPC) and npc.status not in (
                            EntityStatus.DEAD, EntityStatus.EXILED
                        ):
                            npc.sector_id = battle["sector_id"]
                    # Обновляем группы
                    for group in self.state.human_groups.values():
                        if group.sector_id != battle["sector_id"]:
                            # Перемещаем к зачищенному убежищу
                            group.sector_id = battle["sector_id"]
                        # Условие #20: убираем из emission_exposed
                        self.state.emission_exposed.pop(group.id, None)
                    # Условие D: факт "занято монстрами" устаревает
                    stale_shelter_occupied_knowledge(self.state, shelter_id, hour)

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
            members = monster_group_members(self.state, group)
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
            # Регенерация здоровья: пассивная, усиленная в час отдыха (§14.3)
            for monster in monster_group_members(self.state, group, active_only=False):
                if monster.status in (EntityStatus.DEAD, EntityStatus.EXILED):
                    continue
                regen = MONSTER_HEALTH_REGEN_PASSIVE
                if group.intention == "rest":
                    regen += MONSTER_HEALTH_REGEN_REST
                monster.health = min(
                    monster.max_health,
                    monster.health + monster.max_health * regen,
                )
            if group.id in fed_groups:
                continue
            members = monster_group_members(self.state, group, active_only=False)
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
        members = active_members(self.state,  group)
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
        _, kit = group_kit(self.state, 
            members, ItemType.DESTROY_KIT,
            lambda item: item.properties.get("target_anomaly_type") == anomaly.anomaly_type.value,
        )
        if kit is None:
            return False
        leader = group_leader(group, members)
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
            consume_item(self.state, kit, members)
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
                set_unconscious_or_dead(self.state,  victim, start, hour, cause="anomaly")

        if result["destroyed"]:
            parts = get_anomaly_parts_after_destruction(anomaly)
            for _ in range(parts["quantity"]):
                create_item(self.state, 
                    ItemType.ANOMALY_PART, "Часть аномалии", 40.0, leader.id,
                    properties={
                        "anomaly_type": anomaly.anomaly_type.value,
                        "source_anomaly_id": anomaly.id,
                    },
                )
            # уже сформировавшийся артефакт может быть извлечён (§12.4)
            give_artifact(self.state, leader, anomaly, hour)
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
        members = active_members(self.state,  group)
        if not members or any(npc.id in self._combat_human_ids for npc in members):
            return False
        target = capture_target(self.state, group)
        if target is None:
            return False
        _, kit = group_kit(self.state, 
            members, ItemType.CAPTURE_KIT,
            lambda item: item.properties.get("target_species") == species_value(target),
        )
        if kit is None:
            return False
        leader = group_leader(group, members)
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
            create_item(self.state, 
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
                consume_item(self.state, kit, members)
            if self.state.rng.random() < 0.5:
                victim = self.state.rng.choice(members)
                start = victim.health
                victim.health = max(0, victim.health - max(5, round(target.attack * 0.5)))
                if victim.health <= 0:
                    set_unconscious_or_dead(self.state,  victim, start, hour, cause="capture")
                outcome = "counterattack"
            else:
                # монстр уходит: уходит вся его группа, чтобы не разделять состав
                monster_group = self.state.monster_groups.get(target.group_id)
                sector = self.state.sectors.get(target.sector_id)
                if sector and sector.neighbors:
                    flee_sector = self.state.rng.choice(list(sector.neighbors))
                    target.sector_id = flee_sector
                    if monster_group is not None:
                        monster_group.sector_id = flee_sector
                        for member in monster_group_members(self.state, monster_group, active_only=False):
                            member.sector_id = flee_sector
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

    def _process_artifact_formations(self, hour: int) -> None:
        """Формирование артефактов — Фаза 2: Окружающая среда. (§12.5)"""
        # Формирование артефактов; во время выброса — с ускорением (§12.7)
        acceleration = (
            EMISSION_ARTIFACT_ACCELERATION if emission_active(self.state, hour) else 1
        )
        for anomaly in self.state.anomalies.values():
            if anomaly.status == AnomalyStatus.ACTIVE:
                artifact_result = self.state.artifacts.check_artifact_formation(
                    anomaly, hour, rng=self.state.rng, acceleration=acceleration,
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

    def _process_daily_export(self, hour: int) -> None:
        """Ежедневный экспорт артефактов и ресурсов (§16.4).

        Подсчитывает артефакты, переносимые NPC, и начисляет ценность
        через ImportExportManager с учётом лимитов.
        """
        day = self.state.time.day
        total_artifacts = 0
        total_value = 0.0

        # Считаем артефакты у всех мобильных NPC
        for npc in self.state.humans:
            total_artifacts += len(npc.artifacts)

        # Лимит экспорта артефактов: 2 шт/день (§16.4)
        limit = 2
        actual = min(total_artifacts, limit)
        if actual > 0:
            # Средняя цена артефакта
            avg_value = 200.0  # базовая
            total_value = avg_value * actual
            # Записываем экспорт
            record = ExportRecord(
                day=day,
                category="artifacts",
                quantity=actual,
                total_value=total_value,
            )
            self.state.import_export.export_records.append(record)
            self.state.import_export.daily_export_totals["artifacts"] = (
                self.state.import_export.daily_export_totals.get("artifacts", 0) + actual
            )
            self.state.news_manager.create_event(
                hour=hour,
                minute=0,
                sector_id=0,
                event_type="daily_export",
                participants=[],
                result="artifacts_exported",
                importance=35,
                summary=f"Ежедневный экспорт: {actual} артефактов на {total_value}",
                details={
                    "day": day,
                    "artifacts_count": actual,
                    "total_value": total_value,
                },
            )

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
