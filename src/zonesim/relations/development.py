"""Развитие характеристик, выход из Зоны и смена фракции. Основано на §14.5-14.7 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from zonesim.world.entity import EntityStatus, HumanNPC


class StatType(str, Enum):
    ATTACK = "attack"
    DEFENSE = "defense"
    STAMINA = "stamina"
    ATTENTIVENESS = "attentiveness"
    BRAVERY = "bravery"


class FactionChangeReason(str, Enum):
    CONFLICT = "conflict"           # конфликт с текущей фракцией
    RESCUE = "rescue"               # спасение другой фракцией
    ISOLATION = "isolation"         # изоляция
    COOPERATION = "cooperation"     # выгодное сотрудничество


@dataclass
class PracticeProgress:
    """Прогресс практики для одной характеристики."""
    stat_type: StatType
    practice_points: float = 0.0
    last_growth_hour: int = 0

    def add_points(self, points: float) -> None:
        self.practice_points += points

    def try_grow(self, current_value: int, max_value: int = 100,
                 current_hour: int = 0, points_needed: float = 5.0) -> tuple[int, bool]:
        """
        Пробует увеличить характеристику.
        Возвращает (новое_значение, было_ли_увеличение).
        (§14.5)
        - Не более 1 повышения характеристики за 24 часа
        - Требуется несколько успешных событий
        - Лимит 100
        """
        if current_value >= max_value:
            return current_value, False

        if current_hour - self.last_growth_hour < 24:
            return current_value, False

        if self.practice_points >= points_needed:
            self.practice_points -= points_needed
            self.last_growth_hour = current_hour
            return min(current_value + 1, max_value), True

        return current_value, False


class DevelopmentManager:
    """Управление развитием характеристик. (§14.5)"""

    def __init__(self):
        # npc_id -> {stat_type: PracticeProgress}
        self.progress: dict[int, dict[StatType, PracticeProgress]] = {}

    def get_progress(self, npc_id: int, stat_type: StatType) -> PracticeProgress:
        if npc_id not in self.progress:
            self.progress[npc_id] = {}
        if stat_type not in self.progress[npc_id]:
            self.progress[npc_id][stat_type] = PracticeProgress(stat_type)
        return self.progress[npc_id][stat_type]

    def add_practice(self, npc_id: int, stat_type: StatType, points: float,
                     current_hour: int) -> None:
        """Добавляет очки практики."""
        prog = self.get_progress(npc_id, stat_type)
        prog.add_points(points)
        prog.last_growth_hour = current_hour  # сбрасываем для проверки cooldown

    def try_grow_stat(self, npc_id: int, stat_type: StatType,
                      current_value: int, current_hour: int,
                      max_value: int = 100) -> tuple[int, bool]:
        """
        Пытается увеличить характеристику.
        Возвращает (новое_значение, было_ли_увеличение).
        """
        prog = self.get_progress(npc_id, stat_type)
        new_value, grown = prog.try_grow(current_value, max_value, current_hour)
        return new_value, grown

    def grow_all_stats(self, npc: HumanNPC, current_hour: int) -> dict[str, tuple[int, bool]]:
        """
        Пробует увеличить все характеристики NPC.
        Возвращает dict: stat_type -> (new_value, grown).
        """
        results = {}

        stats_map = {
            StatType.ATTACK: ("attack", npc.attack),
            StatType.DEFENSE: ("defense", npc.defense),
            StatType.STAMINA: ("stamina", npc.stamina),
            StatType.ATTENTIVENESS: ("attentiveness", npc.attentiveness),
            StatType.BRAVERY: ("bravery", npc.bravery),
        }

        for stat_type, (field_name, current_value) in stats_map.items():
            if current_value >= 100:
                results[stat_type.value] = (current_value, False)
                continue

            new_value, grown = self.try_grow_stat(npc.id, stat_type, current_value, current_hour)
            results[stat_type.value] = (new_value, grown)

        return results

    def reset_progress(self, npc_id: int) -> None:
        """Сбрасывает прогресс (например, при смерти NPC)."""
        if npc_id in self.progress:
            del self.progress[npc_id]


# Факторы практики для различных действий (§14.5)
PRACTICE_FACTORS = {
    "combat_win": {
        StatType.ATTACK: 1.0,
        StatType.DEFENSE: 0.5,
        StatType.BRAVERY: 0.3,
    },
    "combat_survive": {
        StatType.DEFENSE: 0.8,
        StatType.STAMINA: 0.4,
        StatType.BRAVERY: 0.5,
    },
    "movement_long": {
        StatType.STAMINA: 0.3,
    },
    "research": {
        StatType.ATTENTIVENESS: 0.6,
    },
    "ambush": {
        StatType.ATTENTIVENESS: 0.8,
    },
    "stash_find": {
        StatType.ATTENTIVENESS: 0.5,
    },
    "danger_escape": {
        StatType.BRAVERY: 0.6,
        StatType.STAMINA: 0.3,
    },
}


def get_practice_rewards(action: str, is_successful: bool = True) -> dict[StatType, float]:
    """
    Возвращает факторы практики для действия.
    (§14.5)
    """
    if not is_successful:
        return {}

    return PRACTICE_FACTORS.get(action, {})


class ExileManager:
    """Управление выходом NPC из Зоны. (§14.6)"""

    def can_attempt_exile(self, npc: HumanNPC) -> tuple[bool, str]:
        """
        Проверяет, может ли NPC попытаться выйти из Зоны.
        Возвращает (allowed, reason).
        """
        if npc.status not in (EntityStatus.ACTIVE, EntityStatus.SLEEPING):
            return False, "not_active"

        # Тяжёлое состояние, травма, сломанное снаряжение, враждебное окружение
        if npc.health < 30:
            return True, "heavy_injury"

        return False, "condition_not_met"

    def process_exile_attempt(self, npc: HumanNPC, current_sector_id: int,
                              border_sectors: set[int], rng) -> tuple[bool, str]:
        """
        Обрабатывает попытку выхода.
        Возвращает (success, result).
        """
        allowed, reason = self.can_attempt_exile(npc)
        if not allowed:
            return False, reason

        # Проверка: NPC должен быть на границе
        if current_sector_id not in border_sectors:
            return False, "not_at_border"

        # Шанс успеха зависит от состояния
        success_chance = 0.7 if npc.health > 50 else 0.4

        if rng.random() < success_chance:
            npc.status = EntityStatus.EXILED
            return True, "exiled"
        else:
            return False, "failed_exit"


class FactionChangeManager:
    """Управление сменой фракции NPC. (§14.7)"""

    MIN_TIME_HOURS = 72  # минимальный срок между сменами

    def can_change_faction(self, npc: HumanNPC, new_faction: str,
                           current_hour: int,
                           current_faction_relations: dict) -> tuple[bool, str]:
        """
        Проверяет возможность смены фракции.
        Возвращает (allowed, reason).
        """
        # Проверка cooldown
        if hasattr(npc, "last_faction_change") and (current_hour - npc.last_faction_change < self.MIN_TIME_HOURS):
            return False, "cooldown"

        # Проверка: нет личной вражды с новой фракцией
        faction_relation = current_faction_relations.get(new_faction, 0)
        if faction_relation < -50:
            return False, "hostile_faction"

        # Проверка: безопасное присоединение
        if not hasattr(npc, "can_join"):
            return False, "cannot_join"

        return True, "allowed"

    def process_faction_change(self, npc: HumanNPC, new_faction: str,
                               current_hour: int) -> bool:
        """
        Выполняет смену фракции.
        Возвращает success.
        """
        npc.faction = new_faction
        npc.last_faction_change = current_hour
        return True
