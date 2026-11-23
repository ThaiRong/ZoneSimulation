"""Фаза 6: Обнаружение.

Этап 3, Промпт 3.6: тело перенесено из engine.py в standalone функцию.
Работает с SimulationContext, вспомогательные методы вызываются через ctx.engine_ref.
"""

from __future__ import annotations

from zonesim.anomalies.core import AnomalyStatus
from zonesim.anomalies.damage import apply_anomaly_damage, check_anomaly_contact
from zonesim.knowledge.fact import KnowledgeType
from zonesim.simulation.context import SimulationContext
from zonesim.world.entity import EntityStatus


def run_phase6_detections(ctx: SimulationContext) -> None:
    """Фаза 6: Обнаружение (монстры, аномалии, планирование боёв)."""
    engine = ctx.engine_ref
    state = ctx.state
    hour = ctx.hour

    is_night = ctx.is_night
    detector_bonus = engine._group_detector_bonus()

    for npc in state.humans:
        # Контакт проверяется при прохождении через сектор (§8, фаза 8)
        if npc.id not in engine._moved_human_ids:
            continue
        if npc.status not in (EntityStatus.ACTIVE, EntityStatus.SLEEPING):
            continue

        co_located = [
            a for a in state.anomalies.values()
            if a.sector_id == npc.sector_id and a.status == AnomalyStatus.ACTIVE
        ]
        if not co_located:
            continue

        # Одна проверка на вход в сектор — по одной (случайной) аномалии
        anomaly = state.rng.choice(co_located)
        kb = state.knowledge_bases.get(npc.id)
        known = bool(kb and kb.get_facts(KnowledgeType.ANOMALY, subject_id=anomaly.id))
        contact = check_anomaly_contact(
            entity_sector=npc.sector_id,
            anomaly=anomaly,
            rng_func=state.rng.random,
            attentiveness=npc.attentiveness,
            known_bonus=(
                (20 if known else 0)
                + detector_bonus.get(npc.group_id, 0)  # детектор группы
            ),
            is_night=is_night,
        )
        if contact["result"] != "hit":
            continue

        start_health = npc.health
        result = apply_anomaly_damage(
            npc.health, npc.max_health, anomaly, state.rng.random(),
        )
        npc.health = result["new_health"]

        outcome = "hit"
        if npc.health <= 0:
            outcome = engine._resolve_zero_health(npc, start_health)

        state.news_manager.create_event(
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

    engine._check_monster_anomaly_contacts(hour, is_night)
    engine._schedule_encounters(is_night, hour)
    # Штурм убежищ людьми в выброс (§12.7, условие B)
    engine._process_emission_shelter_assault(hour)
