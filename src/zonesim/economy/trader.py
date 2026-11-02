"""Торговцы и типы торговцев. Основано на §7.13 и §16 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TraderType(str, Enum):
    """Типы торговцев (§7.13)."""
    ROGUES_PERSISTENT = "rogues_persistent"       # постоянный торговец «Бродяг»
    HOUNDS_PERSISTENT = "hounds_persistent"        # постоянный торговец «Борзых»
    GREY_LIGUE_PERSISTENT = "grey_ligue_persistent"  # постоянный торговец «Серой лиги»
    GREY_LIGUE_CONDITIONAL = "grey_ligue_conditional"  # ситуативный «Серая лига»


class TraderStatus(str, Enum):
    ACTIVE = "active"
    DEPARTED = "departed"
    NONE = "none"


@dataclass
class TradeOffer:
    """Торговое предложение."""
    item_type: str
    quantity: int
    price_per_unit: float
    is_buy_offer: bool  # продаёт ли торговец или покупает у NPC


@dataclass
class ItemSnapshot:
    """Снимок предмета в запасе торговца."""
    item_id: int
    name: str
    item_type: str
    condition: int
    value: float
    quantity: int = 1


@dataclass
class Trader:
    """Торговец. (§7.13)"""
    id: int
    trader_type: TraderType
    faction: str  # «Бродяги», «Борзые», «Серая лига»
    sector_id: int
    status: TraderStatus = TraderStatus.ACTIVE
    money: float = 500.0  # стартовые деньги
    target_money: float = 1000.0

    # Товарный запас: item_type -> ItemSnapshot
    inventory: dict[str, ItemSnapshot] = field(default_factory=dict)
    # Целевые запасы по категориям
    target_inventory: dict[str, int] = field(default_factory=dict)

    # Для ситуативного торговца
    appearance_hour: int = 0
    departure_hour: int = 0
    known_appearance_sector: int = -1
    known_appearance_duration: int = 3

    # Активные заказы (ссылки по ID)
    active_contract_ids: list[int] = field(default_factory=list)

    # Текущие запасы по категориям
    stock_levels: dict[str, int] = field(default_factory=dict)

    @property
    def is_conditional(self) -> bool:
        return self.trader_type == TraderType.GREY_LIGUE_CONDITIONAL

    @property
    def is_persistent(self) -> bool:
        return self.trader_type != TraderType.GREY_LIGUE_CONDITIONAL

    @property
    def is_available(self) -> bool:
        if not self.is_conditional:
            return self.status == TraderStatus.ACTIVE

        from zonesim.core.time import GameTime
        return (self.status == TraderStatus.ACTIVE and
                self.known_appearance_sector >= 0 and
                0 <= self._current_hour - self.appearance_hour < self.known_appearance_duration)

    def set_schedule(self, hour: int, sector: int, duration: int = 6) -> None:
        """Задаёт расписание для ситуативного торговца (§16.6)."""
        self.appearance_hour = hour
        self.known_appearance_sector = sector
        self.known_appearance_duration = duration
        self.departure_hour = hour + duration
        self.status = TraderStatus.ACTIVE

    def add_to_stock(self, item_type: str, amount: int) -> None:
        """Добавляет предмет в запас."""
        if item_type not in self.stock_levels:
            self.stock_levels[item_type] = 0
        self.stock_levels[item_type] += amount

    def remove_from_stock(self, item_type: str, amount: int) -> int:
        """Удаляет из запаса. Возвращает фактическое количество."""
        current = self.stock_levels.get(item_type, 0)
        removed = min(amount, current)
        self.stock_levels[item_type] = current - removed
        return removed

    def get_stock(self, item_type: str) -> int:
        return self.stock_levels.get(item_type, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "trader_type": self.trader_type.value,
            "faction": self.faction,
            "sector_id": self.sector_id,
            "status": self.status.value,
            "money": self.money,
            "stock_levels": self.stock_levels.copy(),
            "is_conditional": self.is_conditional,
        }
