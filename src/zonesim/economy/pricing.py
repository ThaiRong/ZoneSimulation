"""Ценообразование и закупка. Основано на §16.3 ТЗ."""

from __future__ import annotations


def calculate_stock_multiplier(
    current_stock: int,
    target_stock: int,
) -> float:
    """
    StockMultiplier = clamp(1 + 0.60 × (T - Q) / max(T; 1); 0.65; 2.50)
    (§16.3)
    """
    t = max(target_stock, 1)
    mult = 1.0 + 0.60 * (target_stock - current_stock) / t
    return max(0.65, min(mult, 2.50))


def calculate_sell_price(
    base_price: float,
    current_stock: int,
    target_stock: int,
    type_multiplier: float = 1.0,
) -> float:
    """
    SellPrice = BasePrice × StockMultiplier × TypeMultiplier
    (§16.3)
    """
    stock_mult = calculate_stock_multiplier(current_stock, target_stock)
    return round(base_price * stock_mult * type_multiplier, 2)


def calculate_buy_price(
    sell_price: float,
    buy_rate: float = 0.55,
    condition: int = 100,
) -> float:
    """
    BuyPrice = SellPrice × BuyRate × ConditionMultiplier
    (§16.3)
    ConditionMultiplier = 0.25 + 0.75 × Condition / 100
    """
    condition_mult = 0.25 + 0.75 * (condition / 100.0)
    return round(sell_price * buy_rate * condition_mult, 2)


def get_condition_multiplier(condition: int) -> float:
    """ConditionMultiplier = 0.25 + 0.75 × Condition / 100."""
    return 0.25 + 0.75 * (condition / 100.0)


# Типовые базовые цены
BASE_PRICES = {
    "ammo_standard": 5.0,
    "ammo_military": 12.0,
    "medkit_basic": 15.0,
    "medkit_advanced": 30.0,
    "armor_light": 40.0,
    "armor_heavy": 80.0,
    "weapon_standard": 50.0,
    "weapon_military": 120.0,
    "capture_kit": 60.0,
    "destroy_kit_subtle": 80.0,
    "destroy_kit_visible": 150.0,
    "destroy_kit_large": 200.0,
    "artifact": 200.0,
    "monster_parts_standard": 25.0,
    "monster_parts_rare": 100.0,
    "anomaly_parts": 50.0,
    "knowledge_basic": 10.0,
    "knowledge_valuable": 30.0,
    "knowledge_rare": 100.0,
}

# Типовые множители по категориям
TYPE_MULTIPLIERS = {
    "standard": 1.0,
    "military": 1.5,
    "contraband": 2.0,
    "artifact": 3.0,
    "rare_parts": 2.0,
    "anomaly_parts": 1.5,
    "knowledge_basic": 1.0,
    "knowledge_valuable": 2.0,
    "knowledge_rare": 5.0,
}

# Множители закупки
BUY_RATES = {
    "standard": 0.55,
    "valuable": 0.65,
    "rare": 0.75,
    "contraband": 0.80,
    "knowledge": 0.50,
}


def get_base_price(item_type: str) -> float:
    return BASE_PRICES.get(item_type, 10.0)


def get_type_multiplier(item_type: str) -> float:
    for key, mult in TYPE_MULTIPLIERS.items():
        if key in item_type:
            return mult
    return 1.0


def get_buy_rate(item_type: str) -> float:
    for key, rate in BUY_RATES.items():
        if key in item_type:
            return rate
    return 0.55


def calculate_trade_margin(
    base_price: float,
    current_stock: int,
    target_stock: int,
    item_type: str = "standard",
) -> tuple[float, float, float]:
    """
    Рассчитывает полную торговую цепочку.
    Возвращает (buy_price, sell_price, margin).
    """
    base = get_base_price(item_type) if base_price <= 0 else base_price
    mult = get_type_multiplier(item_type)
    sell = calculate_sell_price(base, current_stock, target_stock, mult)
    rate = get_buy_rate(item_type)
    buy = calculate_buy_price(sell, rate)
    margin = sell - buy
    return buy, sell, margin


def should_buy(sell_price: float, npc_money: float, urgency: float = 0.0) -> bool:
    """Решает, должен ли NPC купить товар."""
    return sell_price * (1.0 - urgency) <= npc_money * 0.5


def should_sell(npc_item_value: float, buy_price: float, npc_money: float) -> bool:
    """Решает, должен ли NPC продать товар торговцу."""
    return buy_price > npc_item_value * 0.3
