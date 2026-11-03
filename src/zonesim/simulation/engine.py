"""Главный движок симуляции. Связывает все модули в почасовой цикл (§8 ТЗ)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zonesim.core.time import GameTime, SeededRNG
from zonesim.world.sector import Sector
from zonesim.world.entity import HumanNPC, Monster, EntityStatus
from zonesim.combat.loot import Corpse

from zonesim.core.config import GameConfig
from zonesim.generation.worldgen import generate_world
from zonesim.generation.migration import MigrationState, process_migration

from zonesim.combat import CombatSystem
from zonesim.combat.base import Combatant
from zonesim.combat.unconscious import calculate_unconscious_chance, resolve_unconscious_check

from zonesim.actions.detection import check_anomaly_detection

from zonesim.ai import (
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

from zonesim.world.group import HumanGroup

from zonesim.economy.contracts import ContractManager
from zonesim.economy.trade import ImportExportManager

from zonesim.anomalies.core import Anomaly as AnomalyEntity, AnomalyType, AnomalyStatus
from zonesim.anomalies.damage import apply_anomaly_damage, check_anomaly_contact
from zonesim.anomalies.artifact import ArtifactManager
from zonesim.anomalies.migration import check_anomaly_migration

from zonesim.monsters.behavior import Monster as MonsterEntity, MonsterSpecies
from zonesim.monsters.migration import MonsterMigrationManager

from zonesim.relations.personal import PersonalRelations
from zonesim.relations.factions import FactionRelations
from zonesim.relations.development import DevelopmentManager, ExileManager, FactionChangeManager
from zonesim.relations.news import NewsManager

from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType


@dataclass
class SimulationState:
    """Состояние симуляции."""
    time: GameTime = field(default_factory=GameTime)
    rng: SeededRNG = field(default_factory=lambda: SeededRNG(42))
    sectors: dict[int, Sector] = field(default_factory=dict)
    humans: list[HumanNPC] = field(default_factory=list)
    human_groups: dict[int, HumanGroup] = field(default_factory=dict)
    monsters: list[MonsterEntity] = field(default_factory=list)
    monster_groups: dict[int, MonsterGroup] = field(default_factory=dict)
    anomalies: dict[int, AnomalyEntity] = field(default_factory=dict)
    artifacts: ArtifactManager = field(default_factory=ArtifactManager)

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

    migration_state: MigrationState = field(default_factory=MigrationState)
    monster_migration: MonsterMigrationManager = field(default_factory=MonsterMigrationManager)

    next_human_id: int = 0
    next_monster_id: int = 0
    next_group_id: int = 0
    next_anomaly_id: int = 0
    next_stash_id: int = 0

    visit_memory: dict[int, dict[int, int]] = field(default_factory=dict)  # npc_id -> sector -> hour

    config: dict = field(default_factory=dict)


class SimulationEngine:
    """Главный движок симуляции. Интегрирует все модули."""

    def __init__(self, seed: int = 42, config: dict | None = None):
        self.state = SimulationState(rng=SeededRNG(seed), config=config or {})
        self._home_cache: dict[str, int | None] = {}
        self._border_dist: dict[int, int] | None = None
        self._generate_world()

    def _generate_world(self) -> None:
        """Генерирует мир по seed и config."""
        cfg = self.state.config
        result = generate_world(
            seed=self.state.rng.randint(1, 999999),
            config=cfg if cfg else None,
        )

        self.state.sectors = result["sectors"]
        self.state.humans = result["humans"]
        self.state.monsters = result["monsters"]
        self.state.anomalies = {a.id: a for a in result["anomalies"]}

        # Инициализация ID
        self.state.next_human_id = max((h.id for h in self.state.humans), default=0) + 1
        self.state.next_monster_id = max((m.id for m in self.state.monsters), default=0) + 1
        self.state.next_anomaly_id = max((a.id for a in self.state.anomalies.values()), default=0) + 1

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

        # Фаза 10: Отчёт и автосохранение
        self._phase10_report(hour)

        self.state.time.advance()

        return {
            "hour": hour,
            "day": day,
            "phase": phase.value,
            "is_night": is_night,
            "events": events,
        }

    def _phase0_check(self, hour: int) -> None:
        """Фаза 0: Проверка состояния мира."""
        # Удаление погибших из активных групп
        for npc in self.state.humans:
            if npc.status == EntityStatus.DEAD:
                npc.group_id = None

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
            if isinstance(entity, (MonsterEntity, Monster)):
                entity.id = self.state.next_monster_id
                self.state.next_monster_id += 1
                self.state.monsters.append(entity)
            elif isinstance(entity, HumanNPC):
                entity.id = self.state.next_human_id
                self.state.next_human_id += 1
                self.state.humans.append(entity)

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

    def _phase2_environment(self, hour: int) -> None:
        """Фаза 2: Окружающая среда и торговля."""
        # Обработка контрактов
        expired = self.state.contracts.expire_inactive_contracts(hour)
        for cid in expired:
            pass  # просрочка контрактов

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
        """Фаза 4: Выбор намерений по оценке полезности (§9.2).

        Спящие, бессознательные и пленные не выбирают (§8, фаза 4).
        """
        is_night = self.state.time.is_night()

        for npc in self.state.humans:
            if npc.status != EntityStatus.ACTIVE:
                continue

            kb = self.state.knowledge_bases.get(npc.id)
            facts = kb.get_facts(KnowledgeType.ANOMALY) if kb else []
            here = [f for f in facts if f.payload.get("sector_id") == npc.sector_id]
            researchable = [f for f in here if not f.payload.get("researched")]
            home = self._home_sector_id(npc.faction)

            ctx = IntentionContext(
                hour=hour,
                is_night=is_night,
                bravery=npc.bravery,
                faction=npc.faction,
                health_share=npc.health_share,
                stamina_share=npc.stamina_share,
                at_home=(home is not None and npc.sector_id == home),
                home_sector_id=home,
                distance_to_border=self._distance_to_border(npc.sector_id),
                has_known_anomaly=any(
                    self.state.anomalies[f.subject_id].status == AnomalyStatus.ACTIVE
                    for f in researchable if f.subject_id in self.state.anomalies
                ),
                known_anomaly_concealment=max(
                    (f.payload.get("concealment", 50) for f in researchable), default=0
                ),
                known_has_artifact=any(f.payload.get("has_artifact") for f in researchable),
            )
            npc.intention = choose_intention(ctx, self.state.rng)

    def _phase5_movement(self, hour: int, is_night: bool) -> None:
        """Фаза 5: Перемещение по намерениям (1 ребро в час, §6.2)."""
        self._moved_human_ids: set[int] = set()
        border_ids = {s.id for s in self.state.sectors.values() if s.is_border}

        for npc in self.state.humans:
            if npc.status != EntityStatus.ACTIVE:
                continue

            destination: int | None = None
            if npc.intention == EXPLORE:
                memory = self.state.visit_memory.setdefault(npc.id, {})
                destination = choose_explore_target(
                    self.state.sectors, npc.sector_id, memory, hour,
                    self._known_anomaly_sectors(npc), self.state.rng,
                )
            elif npc.intention == EXIT:
                destination = next_step_towards(
                    self.state.sectors, npc.sector_id, border_ids,
                    avoid_ids=self._known_anomaly_sectors(npc),
                )
            elif npc.intention == REST:
                home = self._home_sector_id(npc.faction)
                if home is not None and npc.sector_id != home:
                    destination = next_step_towards(
                        self.state.sectors, npc.sector_id, {home},
                        avoid_ids=self._known_anomaly_sectors(npc),
                    )

            if destination is not None and destination != npc.sector_id:
                npc.sector_id = destination
                self._moved_human_ids.add(npc.id)
                update_stamina(npc, STAMINA_COST_MOVEMENT, "movement", self.state.time)
                self.state.visit_memory.setdefault(npc.id, {})[destination] = hour

        for monster in self.state.monsters:
            if monster.status in (EntityStatus.SLEEPING, EntityStatus.UNCONSCIOUS, EntityStatus.DEAD):
                continue
            if self.state.rng.random() < 0.4:
                sector = self.state.sectors.get(monster.sector_id)
                if sector and sector.neighbors:
                    new_sector = self.state.rng.choice(sector.neighbors)
                    monster.sector_id = new_sector

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

    def _sleep_tick(self, npc: HumanNPC) -> None:
        """Сон: восстановление выносливости по §14.1 (комфорт 4 ч / иначе 6 ч)."""
        group = HumanGroup(id=-(npc.id + 1), members=[npc.id], sector_id=npc.sector_id)
        human_sleep_recover(group, {npc.id: npc}, self.state.time, self.state.rng)

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
        human_sleep_recover(group, {npc.id: npc}, self.state.time, self.state.rng)

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

    def _phase7_actions(self, hour: int, is_night: bool) -> None:
        """Фаза 7: Основные действия — исполнение намерений (§9.1) и сон."""
        for npc in self.state.humans:
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

        # Монстры: временное простое поведение (видовое поведение — отдельный этап)
        for monster in self.state.monsters:
            if monster.status == EntityStatus.ACTIVE and is_night and self.state.rng.random() < 0.3:
                monster.status = EntityStatus.SLEEPING
                monster.stamina = min(monster.stamina + 50, monster.max_stamina)
            elif monster.status == EntityStatus.SLEEPING:
                if self.state.rng.random() < 0.5:
                    monster.status = EntityStatus.ACTIVE
                    monster.stamina = min(monster.stamina + 50, monster.max_stamina)

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
        """Фаза 9: Последствия (добыча, плен, отношения — по мере готовности систем)."""
        pass

    def _phase10_report(self, hour: int) -> None:
        """Фаза 10: Отчёт."""
        pass

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
            "active_monsters": active_monsters,
            "active_anomalies": active_anomalies,
            "total_events": self.state.news_manager.get_total_count(),
        }
