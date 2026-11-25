"""Фаза 4: Выбор намерений групп.

Этап 3, Промпт 3.5: тело перенесено из engine.py в standalone функцию.
Работает с SimulationContext, вспомогательные методы вызываются через ctx.engine_ref.
"""

from __future__ import annotations

from zonesim.ai import (
    ARTIFACT_SEARCH,
    RESEARCH,
    SHELTER,
    IntentionContext,
    choose_intention,
)
from zonesim.anomalies.core import AnomalyStatus
from zonesim.knowledge.fact import KnowledgeType
from zonesim.needs.comfort import has_strict_comfort
from zonesim.simulation.context import SimulationContext
from zonesim.world.entity import EntityStatus
from zonesim.world.faction import distance_to_border, home_sector_id


def run_phase4_intentions(ctx: SimulationContext) -> None:
    """Фаза 4: лидер выбирает одно намерение для всей группы (§7.5, §9.2)."""
    engine = ctx.engine_ref
    state = ctx.state
    hour = state.time.hour
    is_night = state.time.is_night()
    npcs = {npc.id: npc for npc in state.humans}

    engine._process_distress_signals(hour)
    emission_known = engine._emission_known(hour)

    # Снимок KB перед выбором намерений — для инварианта #25
    snap: dict[int, list[dict]] = {}
    for npc in state.humans:
        kb = state.knowledge_bases.get(npc.id)
        if kb:
            snap[npc.id] = [f.to_dict() for f in kb.facts]
    state.knowledge_snapshot_at_intention = snap

    # Предварительное вычисление расстояний до границы (BFS один раз, кэшируется в engine)
    if engine._border_dist is None:
        engine._border_dist = distance_to_border(state.sectors, None)

    for group in state.human_groups.values():
        group.select_leader(npcs)
        leader = npcs.get(group.leader_id) if group.leader_id is not None else None
        if leader is None or leader.status != EntityStatus.ACTIVE:
            continue

        members = [npcs[mid] for mid in group.members if mid in npcs]
        if not members:
            continue
        if emission_known or engine._emission_active(hour):
            group.intention = SHELTER
            for member in members:
                if member.status == EntityStatus.ACTIVE:
                    member.intention = SHELTER
            continue

        facts = []
        for member in members:
            kb = state.knowledge_bases.get(member.id)
            if kb:
                facts.extend(kb.get_facts(KnowledgeType.ANOMALY))

        here = [f for f in facts if f.payload.get("sector_id") == group.sector_id]
        researchable = [f for f in here if not f.payload.get("researched")]
        home = home_sector_id(state.sectors, leader.faction, engine._home_cache)
        all_npcs = {n.id: n for n in state.humans + state.stationary_humans}
        hours_awake = max(
            hour - getattr(member, "awake_since_hour", hour) for member in members
        )
        distress = engine._active_distress_for(group, hour)
        avg_health = sum(npc.health_share for npc in members) / len(members)
        can_help = False
        distress_distance = 6
        if distress is not None and avg_health >= 0.6:
            from zonesim.world.sector import get_distance
            distress_distance = get_distance(
                state.sectors, group.sector_id, distress["sector_id"],
            ) or 6
            can_help = state.faction_relations.get(
                leader.faction, distress.get("faction", ""),
            ) >= 20

        # Устанавливаем group.comfort для инварианта #13
        all_npcs = {n.id: n for n in state.humans}
        group.comfort = has_strict_comfort(
            group, all_npcs,
            {n.id: n for n in state.stationary_humans},
            state.shelters,
            state.temp_shelters,
            state.sectors,
            group.sector_id,
            leader.faction if leader else None,
        )

        ctx_int = IntentionContext(
            hour=hour,
            is_night=is_night,
            bravery=round(sum(npc.bravery for npc in members) / len(members)),
            faction=leader.faction,
            health_share=sum(npc.health_share for npc in members) / len(members),
            stamina_share=sum(npc.stamina_share for npc in members) / len(members),
            at_home=(home is not None and group.sector_id == home),
            home_sector_id=home,
            distance_to_border=engine._border_dist.get(group.sector_id) if engine._border_dist else None,
            has_known_anomaly=any(
                state.anomalies[f.subject_id].status == AnomalyStatus.ACTIVE
                for f in researchable if f.subject_id in state.anomalies
            ),
            known_anomaly_concealment=max(
                (f.payload.get("concealment", 50) for f in researchable), default=0
            ),
            known_has_artifact=any(f.payload.get("has_artifact") for f in researchable),
            can_destroy=engine._group_can_destroy(group, members),
            can_capture=engine._group_can_capture(group, members),
            can_rest=group.is_comfort_sleep_possible(
                all_npcs,
                {n.id: n for n in state.stationary_humans},
                state.shelters,
                state.temp_shelters,
                state.sectors,
                group.sector_id,
                leader.faction if leader else None,
            ),
            can_help=can_help,
            distress_distance=distress_distance,
            can_create_shelter=engine._group_can_create_shelter(group, members),
            can_search_artifact=any(
                f.subject_id in state.anomalies
                and state.anomalies[f.subject_id].status == AnomalyStatus.ACTIVE
                for f in researchable
            ) or bool(state.knowledge_bases.get(group.leader_id)),
            known_artifact_sectors={
                int(f.payload["sector_id"])
                for member in members
                for kb in (state.knowledge_bases.get(member.id),)
                if kb
                for f in kb.get_facts(KnowledgeType.ANOMALY)
                if f.payload.get("has_artifact") and f.payload.get("sector_id")
            },
        )
        # Фиксируем знания, использованные для выбора намерения (инвариант #25)
        snap = state.knowledge_snapshot_at_intention
        captured_facts = []
        for member in members:
            kb_facts = snap.get(member.id, [])
            for f in kb_facts:
                ft = f.get("fact_type")
                if ft in ("anomaly", "safe_path", "trader", "event"):
                    captured_facts.append(f)
        state.intention_knowledge_used[group.id] = captured_facts
        group.intention = choose_intention(ctx_int, state.rng)
        # Установить целевой сектор для RESEARCH / ARTIFACT_SEARCH
        if group.intention in (RESEARCH, ARTIFACT_SEARCH):
            if ctx_int.known_has_artifact:
                for f in researchable:
                    if f.payload.get("has_artifact"):
                        group.target_sector_id = f.payload.get("sector_id")
                        break
            elif group.intention == ARTIFACT_SEARCH and ctx_int.known_artifact_sectors:
                group.target_sector_id = next(iter(ctx_int.known_artifact_sectors))
        for member in members:
            if member.status == EntityStatus.ACTIVE:
                member.intention = group.intention

    engine._phase4_monster_intentions(hour)
