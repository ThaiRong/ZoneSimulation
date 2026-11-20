"""Инварианты #16, #25: знания.

§22 ТЗ:
16 Знание — неизменный снимок наблюдения, не обновляется само при изменении мира.
25 Знание, полученное любым членом группы, доступно всем её текущим членам
   для решений в этом же часу.

check_fn → _check_knowledge_immutability (#16) и _check_group_knowledge (#25).
"""

from __future__ import annotations

from zonesim.world.entity import EntityStatus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonesim.simulation.state import SimulationState


def _check_knowledge_immutability(state: "SimulationState") -> list[str]:
    """Инвариант #16: знание содержит неизменный снимок наблюдения.

    После создания KnowledgeFact.payload и observed_hour НЕ мутируют.
    В MVP: structural check — observed_hour не может быть из будущего.
    """
    errors: list[str] = []
    hour = state.time.hour

    for kb in state.knowledge_bases.values():
        for fact in kb.facts:
            # observed_hour не может быть больше текущего часа + 24
            if fact.observed_hour > hour + 24:
                errors.append(
                    f"Инвариант #16 (ч. {hour}): факт {fact.id} "
                    f"observed_hour={fact.observed_hour} > current {hour} + 24"
                )

    return errors


def _check_group_knowledge(state: "SimulationState") -> list[str]:
    """Инвариант #25: знания группы — общие.

    Проверяет: intention_knowledge_used для каждой группы должен содержать
    ОБЪЕДИНЕНИЕ фактов из knowledge_snapshot_at_intention всех членов группы.
    Если факт известен члену группы, но отсутствует в intention_knowledge_used — violation.
    """
    errors: list[str] = []
    hour = state.time.hour

    knowledge_snapshot = getattr(state, "knowledge_snapshot_at_intention", {})
    if not knowledge_snapshot:
        return errors

    human_groups = getattr(state, "human_groups", {})
    if not human_groups:
        return errors

    intention_knowledge = getattr(state, "intention_knowledge_used", {})
    if not intention_knowledge:
        return errors

    for gid, group in human_groups.items():
        if not group.members:
            continue

        leader = next(
            (n for n in state.humans if n.id == group.leader_id),
            None,
        )
        if leader is None or leader.status != EntityStatus.ACTIVE:
            continue

        if gid not in intention_knowledge:
            continue

        # Собираем ОБЪЕДИНЕНИЕ всех фактов из снимка KB по ключу (type, subject)
        union_facts_key: set[tuple[str, int]] = set()
        for mid in group.members:
            kb_facts = knowledge_snapshot.get(mid, [])
            for fact in kb_facts:
                ft = fact.get("fact_type")
                sid = fact.get("subject_id")
                if ft in ("anomaly", "safe_path", "trader", "event") and sid is not None:
                    union_facts_key.add((ft, sid))

        # Получаем знания, использованные для решений
        used_knowledge = intention_knowledge.get(gid, [])
        used_facts_key: set[tuple[str, int]] = {
            (fk.get("fact_type"), fk.get("subject_id"))
            for fk in used_knowledge
            if fk.get("fact_type") is not None and fk.get("subject_id") is not None
        }

        # Проверяем: все ключи из объединения должны быть в used_knowledge
        missing_keys = union_facts_key - used_facts_key
        if missing_keys:
            missing_types = sorted({kt[0] for kt in missing_keys})
            missing_subjects = sorted({kt[1] for kt in missing_keys})
            errors.append(
                f"Инвариант #25 (ч. {hour}): группа {gid} — "
                f"пропущены факты типов={missing_types} "
                f"subject_ids={missing_subjects} "
                f"при выборе намерения (известны членам группы)"
            )

    return errors
