"""Система знаний NPC. Основано на §7.12 и §17 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class KnowledgeType(str, Enum):
    TRADER = "trader"  # торговец, расписание
    ANOMALY = "anomaly"  # аномалия, расположение
    SAFE_PATH = "safe_path"  # безопасная тропа
    STASH = "stash"  # тайник
    MONSTERS = "monsters"  # группы монстров
    CONTRACT = "contract"  # заказ
    ROUTE = "route"  # безопасный маршрут
    FACTION = "faction"  # состояние фракции
    EVENT = "event"  # важное событие
    SHELTER_OCCUPIED = "shelter_occupied"  # убежище занято монстрами (§12.7, условие D)


@dataclass
class KnowledgeFact:
    """Знание = снимок факта в конкретный час. (§7.12)"""
    id: int
    fact_type: KnowledgeType
    subject_id: int  # ID объекта (сектор, аномалия, торговец и т.д.)
    payload: dict[str, Any]  # снимок: sector, time, composition, schedule...
    observed_hour: int  # когда получено
    valid_until: int | None = None  # необязательный срок актуальности
    source: str = "observation"  # observation, conversation, purchase, report
    reliability: float = 1.0  # в MVP всегда 1.0

    @property
    def age(self) -> int:
        """Возраст знания в часах. (§17.3)"""
        # caller должен передать current_hour
        return 0  # placeholder, считается снаружи

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fact_type": self.fact_type.value,
            "subject_id": self.subject_id,
            "payload": self.payload,
            "observed_hour": self.observed_hour,
            "valid_until": self.valid_until,
            "source": self.source,
            "reliability": self.reliability,
        }


class KnowledgeBase:
    """Хранилище знаний NPC/фракции. (§7.12, §17)"""

    def __init__(self):
        self.facts: list[KnowledgeFact] = []
        self._next_id: int = 0

    def add_fact(self, fact: KnowledgeFact) -> None:
        """Добавляет факт. Если есть свежая версия — заменяет старую. (§7.12)"""
        # Удаляем устаревшую версию того же факта
        self.facts = [
            f for f in self.facts
            if not (f.fact_type == fact.fact_type and f.subject_id == fact.subject_id)
        ]
        self.facts.append(fact)

    def add_manual(self, npc_id: int, fact_type: KnowledgeType, subject_id: int,
                   payload: dict, hour: int, source: str = "observation") -> int:
        """Создаёт факт от имени NPC. Возвращает ID."""
        fact = KnowledgeFact(
            id=self._next_id,
            fact_type=fact_type,
            subject_id=subject_id,
            payload=payload,
            observed_hour=hour,
            source=source,
        )
        self._next_id += 1
        self.add_fact(fact)
        return fact.id

    def get_facts(self, fact_type: KnowledgeType | None = None,
                  subject_id: int | None = None) -> list[KnowledgeFact]:
        """Получает знания с фильтрацией."""
        result = self.facts
        if fact_type:
            result = [f for f in result if f.fact_type == fact_type]
        if subject_id is not None:
            result = [f for f in result if f.subject_id == subject_id]
        return result

    def get_staleness_score(self, current_hour: int) -> float:
        """
        Оценка «старости» знаний. (§17.3)
        Возвращает среднюю свежесть 0..1 (0 = совсем свежие, 1 = устарели).
        """
        if not self.facts:
            return 1.0

        total = 0.0
        for f in self.facts:
            age = current_hour - f.observed_hour
            total += min(age / 48.0, 1.0)  # 48 часов = максимальная старость

        return total / len(self.facts)

    def get_copy(self) -> KnowledgeBase:
        """Создаёт копию для продажи знания (§17.4). ID фактов уникальны."""
        new_kb = KnowledgeBase()
        for i, f in enumerate(self.facts):
            new_fact = KnowledgeFact(
                id=f.id + 10000 + i,  # Уникальный ID для копии
                fact_type=f.fact_type,
                subject_id=f.subject_id,
                payload=f.payload.copy(),
                observed_hour=f.observed_hour,
                valid_until=f.valid_until,
                source=f.source,
                reliability=f.reliability,
            )
            new_kb.facts.append(new_fact)
            new_kb._next_id += 1
        return new_kb

    def get_knowledge_age(self, current_hour: int) -> list[tuple[KnowledgeFact, int]]:
        """Возвращает все знания с их возрастом в часах."""
        return [(f, current_hour - f.observed_hour) for f in self.facts]
