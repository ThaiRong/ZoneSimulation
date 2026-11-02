"""Главный движок симуляции. Связывает все модули в почасовой цикл (§8 ТЗ)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zonesim.core.time import GameTime, SeededRNG
from zonesim.world.sector import Sector
from zonesim.world.entity import HumanNPC, Monster, Anomaly, EntityStatus
from zonesim.combat.loot import Corpse

from zonesim.core.config import GameConfig
from zonesim.generation.worldgen import generate_world
from zonesim.generation.migration import MigrationState, process_migration

from zonesim.combat import CombatSystem
from zonesim.combat.base import Combatant

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
    next_group_id: int = 0
    next_anomaly_id: int = 0
    next_stash_id: int = 0

    config: dict = field(default_factory=dict)


class SimulationEngine:
    """Главный движок симуляции. Интегрирует все модули."""

    def __init__(self, seed: int = 42, config: dict | None = None):
        self.state = SimulationState(rng=SeededRNG(seed), config=config or {})
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
            if hasattr(entity, "status") and entity.status == EntityStatus.DEAD:
                continue
            if isinstance(entity, MonsterEntity):
                self.state.monsters.append(entity)
            elif isinstance(entity, HumanNPC):
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
        self.state.monsters.extend(new_monsters)

    def _phase2_environment(self, hour: int) -> None:
        """Фаза 2: Окружающая среда и торговля."""
        # Обработка контрактов
        expired = self.state.contracts.expire_inactive_contracts(hour)
        for cid in expired:
            pass  # просрочка контрактов

    def _phase3_knowledge(self, hour: int, is_night: bool) -> None:
        """Фаза 3: Обнаружение и распространение сведений."""
        # NPC получают знания о видимых объектах в секторе
        for npc in self.state.humans:
            if npc.status not in (EntityStatus.ACTIVE, EntityStatus.SLEEPING):
                continue
            if npc.id not in self.state.knowledge_bases:
                self.state.knowledge_bases[npc.id] = KnowledgeBase()

            # Простое распространение: если соседний сектор с аномалией
            sector = self.state.sectors.get(npc.sector_id)
            if sector:
                # Проверка известных аномалий в секторе
                for aid, anomaly in self.state.anomalies.items():
                    if anomaly.sector_id == npc.sector_id and anomaly.status == AnomalyStatus.ACTIVE:
                        kb = self.state.knowledge_bases[npc.id]
                        kb.add_manual(
                            npc_id=npc.id,
                            fact_type=KnowledgeType.ANOMALY,
                            subject_id=aid,
                            payload={
                                "sector_id": anomaly.sector_id,
                                "anomaly_type": anomaly.anomaly_type.value,
                            },
                            hour=hour,
                        )

    def _phase4_intentions(self, hour: int) -> None:
        """Фаза 4: Выбор намерений групп."""
        # Группы людей и монстров выбирают действия
        pass  # Упрощённо: выбираем случайные намерения для тестирования

    def _phase5_movement(self, hour: int, is_night: bool) -> None:
        """Фаза 5: Перемещение сущностей."""
        for npc in self.state.humans:
            if npc.status in (EntityStatus.SLEEPING, EntityStatus.UNCONSCIOUS, EntityStatus.DEAD):
                continue
            # Случайное перемещение для демонстрации
            if self.state.rng.random() < 0.3:
                sector = self.state.sectors.get(npc.sector_id)
                if sector and sector.neighbors:
                    new_sector = self.state.rng.choice(sector.neighbors)
                    npc.sector_id = new_sector

        for monster in self.state.monsters:
            if monster.status in (EntityStatus.SLEEPING, EntityStatus.UNCONSCIOUS, EntityStatus.DEAD):
                continue
            if self.state.rng.random() < 0.4:
                sector = self.state.sectors.get(monster.sector_id)
                if sector and sector.neighbors:
                    new_sector = self.state.rng.choice(sector.neighbors)
                    monster.sector_id = new_sector

    def _phase6_detections(self, hour: int) -> None:
        """Фаза 6: Обнаружение и встречи."""
        # Проверка контактов NPC с аномалиями
        for npc in self.state.humans:
            if npc.status not in (EntityStatus.ACTIVE, EntityStatus.SLEEPING):
                continue

            for anomaly in self.state.anomalies.values():
                if anomaly.sector_id == npc.sector_id and anomaly.status == AnomalyStatus.ACTIVE:
                    # Проверка контакта
                    rng_val = self.state.rng.random()
                    contact = check_anomaly_contact(
                        entity_sector=npc.sector_id,
                        anomaly=anomaly,
                        rng_func=lambda: rng_val,
                        is_night=self.state.time.is_night(),
                    )

                    if contact["result"] == "hit":
                        self.state.news_manager.create_event(
                            hour=hour,
                            minute=0,
                            sector_id=npc.sector_id,
                            event_type="anomaly_hit",
                            participants=[npc.id],
                            result="hit",
                            importance=30,
                            summary=f"NPC {npc.id} попал в аномалию",
                            details={"damage": contact.get("damage", 0)},
                        )

    def _phase7_actions(self, hour: int, is_night: bool) -> None:
        """Фаза 7: Основные действия."""
        for npc in self.state.humans:
            if npc.status not in (EntityStatus.ACTIVE, EntityStatus.SLEEPING):
                continue

            # Обработка сна
            if npc.status == EntityStatus.SLEEPING:
                if self.state.rng.random() < 0.2:
                    npc.status = EntityStatus.ACTIVE
                    npc.stamina = min(npc.stamina + 25, npc.max_stamina)
                    continue

            # Обработка бессознательного
            if npc.status == EntityStatus.UNCONSCIOUS:
                if self.state.rng.random() < 0.1:
                    npc.status = EntityStatus.SLEEPING
                    npc.stamina = min(npc.stamina + 10, npc.max_stamina * 0.3)

        # Обработка сна монстров
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
                rng_val = self.state.rng.random()
                artifact_result = self.state.artifacts.check_artifact_formation(
                    anomaly, hour, rng_value=rng_val,
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
        """Фаза 9: Последствия."""
        # Развитие характеристик
        for npc in self.state.humans:
            if npc.status == EntityStatus.ACTIVE:
                # Проверка возможности выхода
                border_ids = {s.id for s in self.state.sectors.values() if s.is_border}
                if npc.sector_id in border_ids:
                    success, result = self.state.exile_manager.process_exile_attempt(
                        npc, npc.sector_id, border_ids, self.state.rng,
                    )
                    if success:
                        self.state.news_manager.create_event(
                            hour=hour,
                            minute=0,
                            sector_id=npc.sector_id,
                            event_type="exile",
                            participants=[npc.id],
                            result="exiled",
                            importance=75,
                            summary=f"NPC {npc.id} покинул Зону",
                            details={"result": result},
                        )

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
