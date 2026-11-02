"""Тесты Фазы 6: экономика (§16 ТЗ)."""

import pytest
from zonesim.economy.trader import Trader, TraderType, TraderStatus, TradeOffer
from zonesim.economy.pricing import (
    calculate_stock_multiplier,
    calculate_sell_price,
    calculate_buy_price,
    get_condition_multiplier,
    calculate_trade_margin,
    should_buy,
    should_sell,
)
from zonesim.economy.contracts import (
    ContractManager, ContractType, ContractStatus,
)
from zonesim.economy.trade import (
    ImportExportManager, CaptureManager, EXPORT_LIMITS,
)


# ==================== Trader Tests ====================

class TestTrader:
    """Тесты торговцев (§7.13)."""

    def test_create_persistent_trader(self):
        trader = Trader(
            id=1,
            trader_type=TraderType.HOUNDS_PERSISTENT,
            faction="Борзые",
            sector_id=5,
        )
        assert trader.is_persistent is True
        assert trader.is_conditional is False
        assert trader.is_available is True

    def test_create_conditional_trader(self):
        trader = Trader(
            id=2,
            trader_type=TraderType.GREY_LIGUE_CONDITIONAL,
            faction="Серая лига",
            sector_id=10,
        )
        assert trader.is_conditional is True
        assert trader.is_persistent is False

    def test_conditional_trader_schedule(self):
        trader = Trader(
            id=2,
            trader_type=TraderType.GREY_LIGUE_CONDITIONAL,
            faction="Серая лига",
            sector_id=10,
        )
        trader.set_schedule(hour=24, sector=10, duration=6)
        assert trader.appearance_hour == 24
        assert trader.known_appearance_sector == 10
        assert trader.known_appearance_duration == 6
        assert trader.departure_hour == 30

    def test_stock_operations(self):
        trader = Trader(1, TraderType.ROGUES_PERSISTENT, "Бродяги", 0)
        trader.add_to_stock("ammo", 50)
        assert trader.get_stock("ammo") == 50

        removed = trader.remove_from_stock("ammo", 20)
        assert removed == 20
        assert trader.get_stock("ammo") == 30

        removed = trader.remove_from_stock("ammo", 100)
        assert removed == 30  # не больше чем есть

    def test_to_dict(self):
        trader = Trader(1, TraderType.GREY_LIGUE_PERSISTENT, "Серая лига", 3)
        trader.add_to_stock("artifacts", 2)
        d = trader.to_dict()
        assert d["id"] == 1
        assert d["faction"] == "Серая лига"
        assert d["stock_levels"]["artifacts"] == 2
        assert d["is_conditional"] is False


# ==================== Pricing Tests ====================

class TestPricing:
    """Тесты ценообразования (§16.3)."""

    def test_stock_multiplier_full(self):
        """Q = T → multiplier = 1.0."""
        assert calculate_stock_multiplier(10, 10) == pytest.approx(1.0, abs=0.01)

    def test_stock_multiplier_low(self):
        """Q < T → multiplier > 1.0."""
        m = calculate_stock_multiplier(0, 10)
        # 1 + 0.60 * (10 - 0) / 10 = 1.6
        assert m == pytest.approx(1.6, abs=0.01)

    def test_stock_multiplier_high(self):
        """Q > T → multiplier < 1.0, min 0.65."""
        m = calculate_stock_multiplier(30, 10)
        # 1 + 0.60 * (10 - 30) / 10 = -0.2 → clamp to 0.65
        assert m == pytest.approx(0.65, abs=0.01)

    def test_stock_multiplier_max(self):
        """Extreme surplus → max 2.50."""
        m = calculate_stock_multiplier(0, 100)
        # 1 + 0.60 * 100 / 100 = 1.6
        assert m <= 2.50

    def test_sell_price_formula(self):
        """SellPrice = BasePrice × StockMultiplier × TypeMultiplier."""
        price = calculate_sell_price(base_price=100.0, current_stock=5, target_stock=10, type_multiplier=1.0)
        # SM = 1 + 0.6 * (10-5)/10 = 1.3
        # SP = 100 * 1.3 * 1.0 = 130
        assert price == pytest.approx(130.0, abs=0.1)

    def test_buy_price_formula(self):
        """BuyPrice = SellPrice × BuyRate × ConditionMultiplier."""
        sell = 100.0
        buy = calculate_buy_price(sell, buy_rate=0.55, condition=100)
        # 100 * 0.55 * 1.0 = 55.0
        assert buy == pytest.approx(55.0, abs=0.1)

    def test_buy_price_condition(self):
        """Сломанный товар дешевле."""
        full = calculate_buy_price(100.0, 0.55, 100)
        broken = calculate_buy_price(100.0, 0.55, 0)
        # 100 * 0.55 * 0.25 = 13.75
        assert broken == pytest.approx(13.75, abs=0.1)
        assert broken < full

    def test_condition_multiplier(self):
        assert get_condition_multiplier(100) == pytest.approx(1.0, abs=0.01)
        assert get_condition_multiplier(0) == pytest.approx(0.25, abs=0.01)
        assert get_condition_multiplier(50) == pytest.approx(0.625, abs=0.01)

    def test_trade_margin(self):
        buy, sell, margin = calculate_trade_margin(0, 5, 10, "ammo_standard")
        assert sell > buy
        assert margin > 0

    def test_should_buy(self):
        assert should_buy(10.0, 100.0) is True
        assert should_buy(100.0, 10.0) is False

    def test_should_sell(self):
        # sell_price > item_value * 0.3
        assert should_sell(50.0, 30.0, 100.0) is True
        assert should_sell(5.0, 0.1, 100.0) is False


# ==================== Contract Tests ====================

class TestContractManager:
    """Тесты внешних заказов (§16.7)."""

    def test_create_contract(self):
        cm = ContractManager()
        contract = cm.create_contract(
            trader_id=1,
            contract_type=ContractType.ARTIFACT,
            required_item_type="artifact",
            quantity=1,
            reward=200.0,
            deadline_hours=48,
        )
        assert contract.id == 0
        assert contract.status == ContractStatus.ACTIVE
        assert contract.reward == 200.0

    def test_accept_contract(self):
        cm = ContractManager()
        contract = cm.create_contract(1, ContractType.MONSTER_PARTS, "parts", 5, 100.0)
        result = cm.accept_contract(0, npc_id=10, sector_id=5, current_hour=10)
        assert result is True
        assert contract.accepted_by == 10
        assert contract.status == ContractStatus.ACCEPTED

    def test_accept_nonexistent_contract(self):
        cm = ContractManager()
        result = cm.accept_contract(999, npc_id=10, sector_id=5, current_hour=10)
        assert result is False

    def test_accept_already_accepted(self):
        cm = ContractManager()
        contract = cm.create_contract(1, ContractType.KNOWLEDGE, "knowledge", 1, 50.0)
        cm.accept_contract(0, npc_id=10, sector_id=5, current_hour=10)
        result = cm.accept_contract(0, npc_id=20, sector_id=5, current_hour=11)
        assert result is False  # уже принят

    def test_complete_contract(self):
        cm = ContractManager()
        contract = cm.create_contract(1, ContractType.ARTIFACT, "artifact", 1, 200.0, deadline_hours=100)
        cm.accept_contract(0, npc_id=10, sector_id=5, current_hour=10)
        success, reward, details = cm.complete_contract(0, current_hour=20)
        assert success is True
        assert reward == 200.0
        assert contract.status == ContractStatus.COMPLETED

    def test_fail_contract_expired(self):
        cm = ContractManager()
        contract = cm.create_contract(1, ContractType.MONSTER_PARTS, "parts", 3, 100.0, deadline_hours=10, current_hour=0)
        cm.accept_contract(0, npc_id=10, sector_id=5, current_hour=0)
        success, penalty, debt, reason = cm.fail_contract(0, current_hour=20)
        assert success is True
        assert reason == "expired"
        assert contract.status == ContractStatus.FAILED

    def test_fail_contract_no_penalty_for_zero(self):
        cm = ContractManager()
        contract = cm.create_contract(1, ContractType.ARTIFACT, "artifact", 1, 200.0, deadline_hours=10, penalty=0.0)
        cm.accept_contract(0, npc_id=10, sector_id=5, current_hour=0)
        success, penalty, debt, reason = cm.fail_contract(0, current_hour=20)
        assert success is True
        assert debt == 0.0

    def test_expire_inactive_contracts(self):
        cm = ContractManager()
        c1 = cm.create_contract(1, ContractType.KNOWLEDGE, "knowledge", 1, 10.0, deadline_hours=5, current_hour=0)
        c2 = cm.create_contract(1, ContractType.KNOWLEDGE, "knowledge", 1, 20.0, deadline_hours=100, current_hour=0)
        expired = cm.expire_inactive_contracts(10)
        assert 0 in expired
        assert 1 not in expired

    def test_active_contracts_limit(self):
        cm = ContractManager()
        for i in range(8):
            cm.create_contract(1, ContractType.KNOWLEDGE, "knowledge", 1, 10.0, deadline_hours=100)
        active = cm.get_active_contracts(1, current_hour=0)
        assert len(active) <= 5

    def test_accepted_contracts_for_npc(self):
        cm = ContractManager()
        c1 = cm.create_contract(1, ContractType.ARTIFACT, "artifact", 1, 200.0)
        c2 = cm.create_contract(2, ContractType.MONSTER_PARTS, "parts", 3, 100.0)
        cm.accept_contract(0, npc_id=10, sector_id=5, current_hour=0)
        cm.accept_contract(1, npc_id=10, sector_id=5, current_hour=0)

        npc_contracts = cm.get_accepted_contracts(10)
        assert len(npc_contracts) == 2


# ==================== ImportExport Tests ====================

class TestImportExportManager:
    """Тесты импорта/экспорта (§16.4)."""

    def test_export_basic(self):
        iem = ImportExportManager()
        result = iem.process_daily_export(
            trader_id=1,
            day=1,
            export_items={"monster_parts": 2},
        )
        assert result["exported"]["monster_parts"] == 2
        assert result["total_value"] > 0

    def test_export_daily_limit(self):
        iem = ImportExportManager()
        # Первый экспорт
        iem.process_daily_export(1, 1, {"monster_parts": 2})
        # Второй — превысит лимит (3/сутки)
        result = iem.process_daily_export(1, 1, {"monster_parts": 3})
        # Итого должно быть 3 (лимит)
        assert result["exported"].get("monster_parts", 0) <= 1

    def test_export_no_limit_exceeded(self):
        iem = ImportExportManager()
        result = iem.process_daily_export(1, 1, {"artifacts": 5})
        # Лимит для артефактов — 2
        assert result["exported"].get("artifacts", 0) <= 2

    def test_import_basic(self):
        iem = ImportExportManager()
        result = iem.process_daily_import(
            trader_id=1,
            day=1,
            import_items={"ammo_standard": 30},
            budget=500.0,
        )
        assert result["purchased"]["ammo_standard"] > 0
        assert result["remaining_budget"] < 500.0

    def test_import_budget_limit(self):
        iem = ImportExportManager()
        result = iem.process_daily_import(
            trader_id=1,
            day=1,
            import_items={"weapons": 10},
            budget=10.0,
        )
        # weapons ~70 each, budget 10 → 0 purchased
        assert result["purchased"].get("weapons", 0) == 0 or result["purchased"].get("weapons", 0) <= 1

    def test_reset_daily_totals(self):
        iem = ImportExportManager()
        iem.process_daily_export(1, 1, {"monster_parts": 3})
        assert iem.daily_export_totals["monster_parts"] == 3

        iem.reset_daily_totals(2)
        assert "monster_parts" not in iem.daily_export_totals


# ==================== Capture Tests ====================

class TestCaptureManager:
    """Тесты захвата монстров (§16.8)."""

    def test_capture_chance_full_health(self):
        """Здоровый монстр — низкий шанс."""
        chance = CaptureManager.calculate_capture_chance(
            health_share=1.0,
            attacker_att=50,
            target_att=50,
            num_attackers=1,
        )
        # 25 + 0 + 0 + 0 = 25
        assert chance == pytest.approx(25.0, abs=0.1)

    def test_capture_chance_weakened(self):
        """Ослабленный — высокий шанс."""
        chance = CaptureManager.calculate_capture_chance(
            health_share=0.3,
            attacker_att=60,
            target_att=40,
            num_attackers=3,
        )
        # 25 + 35*0.7 + 0.25*20 + 10*2 = 25 + 24.5 + 5 + 20 = 74.5
        assert chance == pytest.approx(74.5, abs=0.5)

    def test_capture_chance_clamped(self):
        """Шанс в диапазоне [5, 85]."""
        high = CaptureManager.calculate_capture_chance(0.0, 100, 1, 4)
        assert 5 <= high <= 85

        low = CaptureManager.calculate_capture_chance(1.0, 1, 100, 1)
        assert 5 <= low <= 85

    def test_capture_resolve_success(self):
        assert CaptureManager.resolve_capture(0.3, 80) is True
        assert CaptureManager.resolve_capture(0.9, 80) is False

    def test_prerequisites_no_kit(self):
        ok, reason = CaptureManager.check_prerequisites(
            has_capture_kit=False,
            monster_health_share=0.2,
        )
        assert ok is False
        assert reason == "no_capture_kit"

    def test_prerequisites_too_healthy(self):
        ok, reason = CaptureManager.check_prerequisites(
            has_capture_kit=True,
            monster_health_share=0.5,
        )
        assert ok is False
        assert reason == "monster_too_healthy"

    def test_prerequisites_ready(self):
        ok, reason = CaptureManager.check_prerequisites(
            has_capture_kit=True,
            monster_health_share=0.3,
            no_nearby_monsters=True,
        )
        assert ok is True
        assert reason == "ready"
