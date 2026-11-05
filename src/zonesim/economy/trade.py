"""Импорт, экспорт и захват монстров. Основано на §16.4 и §16.8 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Лимиты экспорта по категориям
EXPORT_LIMITS = {
    "monster_parts": 3,
    "live_monsters": 1,
    "artifacts": 2,
    "anomaly_parts": 2,
    "knowledge_contracts": 1,
}

# Лимиты импорта
IMPORT_LIMITS = {
    "ammo_standard": 50,
    "ammo_military": 20,
    "medkits": 15,
    "armor": 10,
    "weapons": 8,
    "capture_kits": 5,
    "destroy_kits": 3,
}

# Стартовые цены импорта
IMPORT_PRICES = {
    "ammo_standard": 5.0,
    "ammo_military": 12.0,
    "medkits": 20.0,
    "armor": 50.0,
    "weapons": 70.0,
    "capture_kits": 60.0,
    "destroy_kits": 150.0,
}

# Стоимость экспорта
EXPORT_BUYBACK = {
    "monster_parts_standard": 20.0,
    "monster_parts_rare": 80.0,
    "live_monsters": 150.0,
    "artifacts": 200.0,
    "anomaly_parts": 40.0,
    "knowledge_contracts": 50.0,
}


@dataclass
class ExportRecord:
    """Запись об экспорте за сутки."""
    day: int
    category: str
    quantity: int
    total_value: float


@dataclass
class ImportRecord:
    """Запись об импорте за сутки."""
    day: int
    category: str
    quantity: int
    total_cost: float


class ImportExportManager:
    """Управление импортом/экспортом. (§16.4)"""

    def __init__(self):
        self.export_records: list[ExportRecord] = []
        self.import_records: list[ImportRecord] = []
        self.daily_export_totals: dict[str, int] = {}
        self.daily_import_totals: dict[str, int] = {}

    def process_daily_export(
        self,
        trader_id: int,
        day: int,
        export_items: dict[str, int],
    ) -> dict[str, Any]:
        """
        Обрабатывает суточный экспорт. (§16.4)
        export_items: {"category": quantity}
        """
        total_exported: dict[str, int] = {}
        total_value = 0.0

        for category, quantity in export_items.items():
            limit = EXPORT_LIMITS.get(category, 1)
            current_day_total = self.daily_export_totals.get(category, 0)

            if current_day_total + quantity <= limit:
                actual = quantity
            else:
                actual = max(0, limit - current_day_total)

            if actual > 0:
                buyback = EXPORT_BUYBACK.get(category, 10.0)
                value = buyback * actual
                total_value += value

                record = ExportRecord(
                    day=day,
                    category=category,
                    quantity=actual,
                    total_value=value,
                )
                self.export_records.append(record)
                total_exported[category] = actual

            self.daily_export_totals[category] = current_day_total + actual

        return {
            "exported": total_exported,
            "total_value": round(total_value, 2),
            "trader_id": trader_id,
        }

    def process_daily_import(
        self,
        trader_id: int,
        day: int,
        import_items: dict[str, int],
        budget: float,
    ) -> dict[str, Any]:
        """
        Обрабатывает суточный импорт. (§16.1, §16.4)
        import_items: {"category": quantity}
        """
        total_cost = 0.0
        purchased: dict[str, int] = {}

        for category, requested_qty in import_items.items():
            limit = IMPORT_LIMITS.get(category, 10)
            current_day_total = self.daily_import_totals.get(category, 0)
            available = limit - current_day_total

            if available <= 0:
                continue

            actual = min(requested_qty, available)

            price = IMPORT_PRICES.get(category, 10.0)
            cost = price * actual

            if cost <= budget:
                purchased[category] = actual
                total_cost += cost
                budget -= cost

                record = ImportRecord(
                    day=day,
                    category=category,
                    quantity=actual,
                    total_cost=cost,
                )
                self.import_records.append(record)

            self.daily_import_totals[category] = current_day_total + actual

        return {
            "purchased": purchased,
            "total_cost": round(total_cost, 2),
            "remaining_budget": round(budget, 2),
            "trader_id": trader_id,
        }

    def reset_daily_totals(self, day: int) -> None:
        """Сбрасывает дневные лимиты."""
        self.daily_export_totals = {}
        self.daily_import_totals = {}


class CaptureManager:
    """Захват живых монстров. (§16.8)"""

    @staticmethod
    def calculate_capture_chance(
        health_share: float,
        attacker_att: int,
        target_att: int,
        num_attackers: int = 1,
        kit_bonus: float = 0.0,
    ) -> float:
        """
        P_capture = clamp(25 + 35 × (1 - HealthShare)
                         + 0.25 × (Att - TargetAtt) + 10 × (N - 1) + BonusKit, 5; 85)
        (§16.8)
        """
        p = (
            25 +
            35 * (1.0 - health_share) +
            0.25 * (attacker_att - target_att) +
            10 * min(num_attackers - 1, 3) +
            kit_bonus
        )
        return max(5.0, min(p, 85.0))

    @staticmethod
    def resolve_capture(
        rng_value: float,
        capture_chance: float,
    ) -> bool:
        """Результат захвата."""
        return rng_value * 100 < capture_chance

    @staticmethod
    def check_prerequisites(
        has_capture_kit: bool,
        monster_health_share: float,
        max_health_share: float = 0.35,
        no_nearby_monsters: bool = True,
    ) -> tuple[bool, str]:
        """
        Проверяет условия для захвата (§16.8):
        - комплект захвата
        - здоровье цели <= 35%
        - нет активного сопротивления других монстров рядом
        """
        if not has_capture_kit:
            return False, "no_capture_kit"
        if monster_health_share > max_health_share:
            return False, "monster_too_healthy"
        if not no_nearby_monsters:
            return False, "nearby_monsters_present"
        return True, "ready"

    @staticmethod
    def get_kit_damage_on_failure() -> tuple[int, int]:
        """Урон комплекту при провале: 10-30."""
        return 10, 30
