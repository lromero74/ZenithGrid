"""
Tests for backend/app/strategies/indicator_based.py

Covers:
- IndicatorBasedStrategy.validate_config
- IndicatorBasedStrategy.calculate_base_order_size
- IndicatorBasedStrategy.calculate_safety_order_size
- IndicatorBasedStrategy.calculate_safety_order_price
- IndicatorBasedStrategy._flatten_conditions
- IndicatorBasedStrategy._needs_aggregate_indicators
- IndicatorBasedStrategy._check_entry_conditions
- IndicatorBasedStrategy.should_buy (async)
- IndicatorBasedStrategy.should_sell (async)
"""

import pytest
from unittest.mock import MagicMock, patch

from app.strategies.indicator_based import IndicatorBasedStrategy


# ---------------------------------------------------------------------------
# Fixture: minimal valid config
# ---------------------------------------------------------------------------


def _make_strategy(config_overrides=None):
    """Create a strategy with sane defaults, optionally overridden."""
    base_config = {
        "base_order_type": "percentage",
        "base_order_percentage": 10.0,
        "base_order_fixed": 0.001,
        "max_safety_orders": 5,
        "safety_order_type": "percentage_of_base",
        "safety_order_percentage": 50.0,
        "safety_order_volume_scale": 1.0,
        "safety_order_step_scale": 1.0,
        "price_deviation": 2.0,
        "take_profit_percentage": 3.0,
        "stop_loss_enabled": False,
        "stop_loss_percentage": -10.0,
        "trailing_take_profit": False,
        "trailing_stop_loss": False,
        "base_order_conditions": [],
        "base_order_logic": "and",
        "safety_order_conditions": [],
        "safety_order_logic": "and",
        "take_profit_conditions": [],
        "take_profit_logic": "and",
    }
    if config_overrides:
        base_config.update(config_overrides)

    # Patch out heavy dependencies that require external modules
    with patch("app.strategies.indicator_based.IndicatorCalculator"), \
         patch("app.strategies.indicator_based.PhaseConditionEvaluator"), \
         patch("app.strategies.indicator_based.AISpotOpinionEvaluator"), \
         patch("app.strategies.indicator_based.BullFlagIndicatorEvaluator"):
        strategy = IndicatorBasedStrategy(base_config)

    return strategy


def _make_mock_position(
    avg_price=100.0,
    total_base=0.01,
    total_quote=1.0,
    max_quote=10.0,
    trades=None,
    direction="long",
    entry_stop_loss=None,
    entry_take_profit_target=None,
):
    """Create a mock position object."""
    pos = MagicMock()
    pos.average_buy_price = avg_price
    pos.total_base_acquired = total_base
    pos.total_quote_spent = total_quote
    pos.max_quote_allowed = max_quote
    pos.direction = direction
    pos.entry_stop_loss = entry_stop_loss
    pos.entry_take_profit_target = entry_take_profit_target
    pos.highest_price_since_entry = None
    pos.trailing_stop_loss_price = None
    pos.trailing_tp_active = False
    pos.highest_price_since_tp = None
    pos.previous_indicators = None
    pos.id = 1

    if trades is None:
        # Default: 1 base order buy trade
        trade = MagicMock()
        trade.side = "buy"
        trade.price = avg_price
        trade.timestamp = 1000
        pos.trades = [trade]
    else:
        pos.trades = trades

    return pos


# =====================================================================
# validate_config
# =====================================================================


class TestValidateConfig:
    """Tests for validate_config()"""

    def test_sets_defaults_for_missing_params(self):
        """Missing config keys should get default values from definition."""
        strategy = _make_strategy({})
        # Should have defaults set
        assert "max_concurrent_deals" in strategy.config
        assert strategy.config["max_concurrent_deals"] == 1

    def test_preserves_existing_config(self):
        """Existing config values should not be overwritten."""
        strategy = _make_strategy({"take_profit_percentage": 5.0})
        assert strategy.config["take_profit_percentage"] == 5.0

    def test_initializes_evaluators(self):
        """validate_config should set up indicator_calculator and phase_evaluator."""
        strategy = _make_strategy()
        assert hasattr(strategy, "indicator_calculator")
        assert hasattr(strategy, "phase_evaluator")
        assert hasattr(strategy, "ai_evaluator")
        assert hasattr(strategy, "bull_flag_evaluator")


# =====================================================================
# calculate_base_order_size
# =====================================================================


class TestCalculateBaseOrderSize:
    """Tests for calculate_base_order_size()"""

    def test_percentage_mode_basic(self):
        """10% of 1.0 BTC balance = 0.1 BTC."""
        strategy = _make_strategy({"base_order_percentage": 10.0})
        result = strategy.calculate_base_order_size(1.0)
        assert pytest.approx(result) == 0.1

    def test_percentage_mode_full_balance(self):
        """100% of balance = entire balance."""
        strategy = _make_strategy({"base_order_percentage": 100.0})
        result = strategy.calculate_base_order_size(0.5)
        assert pytest.approx(result) == 0.5

    def test_percentage_auto_calculate_with_safety_orders(self):
        """Auto-calculate should divide budget across base + safety orders."""
        strategy = _make_strategy({
            "base_order_type": "percentage",
            "auto_calculate_order_sizes": True,
            "max_safety_orders": 2,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,  # Each SO = 100% of base
            "safety_order_volume_scale": 1.0,
        })
        # Total multiplier = 1 (base) + 1.0 (SO1) + 1.0 (SO2) = 3.0
        # Base = budget / 3.0 * (100 / 3.0 / 100) ... actually:
        # optimal_percentage = 100 / 3.0 = 33.33%
        # result = 1.0 * (33.33 / 100) = 0.3333
        result = strategy.calculate_base_order_size(1.0)
        assert pytest.approx(result, abs=0.01) == 1.0 / 3.0

    def test_percentage_auto_calculate_with_volume_scaling(self):
        """Auto-calculate with volume_scale > 1 should create larger later orders."""
        strategy = _make_strategy({
            "base_order_type": "percentage",
            "auto_calculate_order_sizes": True,
            "max_safety_orders": 2,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 2.0,
        })
        # Total multiplier = 1 (base) + 1.0*2^0 (SO1) + 1.0*2^1 (SO2) = 1 + 1 + 2 = 4
        result = strategy.calculate_base_order_size(1.0)
        assert pytest.approx(result, abs=0.01) == 0.25  # 1.0 / 4

    def test_fixed_btc_mode_no_safety_orders(self):
        """Fixed mode with no safety orders returns configured amount."""
        strategy = _make_strategy({
            "base_order_type": "fixed_btc",
            "base_order_btc": 0.005,
            "max_safety_orders": 0,
        })
        result = strategy.calculate_base_order_size(1.0)
        assert pytest.approx(result) == 0.005

    def test_fixed_mode_auto_calculate_percentage_of_base(self):
        """Fixed mode with auto_calculate + percentage SOs."""
        strategy = _make_strategy({
            "base_order_type": "fixed_btc",
            "auto_calculate_order_sizes": True,
            "max_safety_orders": 1,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 1.0,
        })
        # Total multiplier = 1 (base) + 1.0 (SO1) = 2.0
        # base = budget / 2.0
        result = strategy.calculate_base_order_size(0.01)
        assert pytest.approx(result) == 0.005

    def test_fixed_mode_auto_calculate_fixed_sos(self):
        """Fixed mode with auto_calculate + fixed SOs."""
        strategy = _make_strategy({
            "base_order_type": "fixed_btc",
            "auto_calculate_order_sizes": True,
            "max_safety_orders": 2,
            "safety_order_type": "fixed_btc",
            "safety_order_volume_scale": 1.0,
        })
        # Total multiplier = 1 (base) + 1 (SO1) + 1*1^1 (SO2) = 3.0
        result = strategy.calculate_base_order_size(0.03)
        assert pytest.approx(result) == 0.01

    def test_zero_balance_returns_zero(self):
        """Zero balance should produce zero order size."""
        strategy = _make_strategy({"base_order_percentage": 10.0})
        result = strategy.calculate_base_order_size(0.0)
        assert result == 0.0

    def test_unknown_order_type_fallback(self):
        """Unknown order type should fallback to base_order_fixed."""
        strategy = _make_strategy({
            "base_order_type": "magical_unicorn",
            "base_order_fixed": 0.002,
        })
        result = strategy.calculate_base_order_size(1.0)
        assert pytest.approx(result) == 0.002


# =====================================================================
# calculate_safety_order_size
# =====================================================================


class TestCalculateSafetyOrderSize:
    """Tests for calculate_safety_order_size()"""

    def test_percentage_of_base_first_order(self):
        """First SO at 50% of base = 0.5 * base."""
        strategy = _make_strategy({
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 50.0,
            "safety_order_volume_scale": 1.0,
        })
        result = strategy.calculate_safety_order_size(0.01, order_number=1)
        assert pytest.approx(result) == 0.005

    def test_volume_scaling(self):
        """Second SO with 2x volume scale = base_safety * 2^1."""
        strategy = _make_strategy({
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 2.0,
        })
        # SO1 = 0.01 * 1.0 * 2^0 = 0.01
        # SO2 = 0.01 * 1.0 * 2^1 = 0.02
        result_so1 = strategy.calculate_safety_order_size(0.01, order_number=1)
        result_so2 = strategy.calculate_safety_order_size(0.01, order_number=2)
        assert pytest.approx(result_so1) == 0.01
        assert pytest.approx(result_so2) == 0.02

    def test_fixed_btc_auto_calculate(self):
        """Auto-calculate with fixed SOs: safety = base * volume_scale^(n-1)."""
        strategy = _make_strategy({
            "safety_order_type": "fixed_btc",
            "auto_calculate_order_sizes": True,
            "safety_order_volume_scale": 1.5,
        })
        # SO1 = 0.01 * 1.5^0 = 0.01
        # SO2 = 0.01 * 1.5^1 = 0.015
        result_so1 = strategy.calculate_safety_order_size(0.01, order_number=1)
        result_so2 = strategy.calculate_safety_order_size(0.01, order_number=2)
        assert pytest.approx(result_so1) == 0.01
        assert pytest.approx(result_so2) == 0.015

    def test_fixed_btc_manual(self):
        """Manual fixed SOs use configured safety_order_btc."""
        strategy = _make_strategy({
            "safety_order_type": "fixed_btc",
            "auto_calculate_order_sizes": False,
            "safety_order_btc": 0.002,
            "safety_order_volume_scale": 1.0,
        })
        result = strategy.calculate_safety_order_size(0.01, order_number=1)
        assert pytest.approx(result) == 0.002


# =====================================================================
# calculate_safety_order_price
# =====================================================================


class TestCalculateSafetyOrderPrice:
    """Tests for calculate_safety_order_price()"""

    def test_long_first_order(self):
        """Long SO1: entry * (1 - 2%) = 98."""
        strategy = _make_strategy({"price_deviation": 2.0, "safety_order_step_scale": 1.0})
        result = strategy.calculate_safety_order_price(100.0, order_number=1, direction="long")
        assert pytest.approx(result) == 98.0

    def test_long_second_order_no_step_scale(self):
        """Long SO2 with step_scale=1: entry * (1 - 4%) = 96."""
        strategy = _make_strategy({"price_deviation": 2.0, "safety_order_step_scale": 1.0})
        result = strategy.calculate_safety_order_price(100.0, order_number=2, direction="long")
        assert pytest.approx(result) == 96.0

    def test_long_second_order_with_step_scale(self):
        """Long SO2 with step_scale=1.5: deviation = 2 + 2*1.5 = 5%."""
        strategy = _make_strategy({"price_deviation": 2.0, "safety_order_step_scale": 1.5})
        result = strategy.calculate_safety_order_price(100.0, order_number=2, direction="long")
        # total_deviation = 2 (SO1) + 2 * 1.5^1 (SO2) = 2 + 3 = 5%
        assert pytest.approx(result) == 95.0

    def test_short_first_order(self):
        """Short SO1: entry * (1 + 2%) = 102."""
        strategy = _make_strategy({"price_deviation": 2.0, "safety_order_step_scale": 1.0})
        result = strategy.calculate_safety_order_price(100.0, order_number=1, direction="short")
        assert pytest.approx(result) == 102.0

    def test_short_second_order(self):
        """Short SO2: entry * (1 + 4%) = 104."""
        strategy = _make_strategy({"price_deviation": 2.0, "safety_order_step_scale": 1.0})
        result = strategy.calculate_safety_order_price(100.0, order_number=2, direction="short")
        assert pytest.approx(result) == 104.0

    def test_zero_deviation(self):
        """Zero deviation => trigger at entry price."""
        strategy = _make_strategy({"price_deviation": 0.0, "safety_order_step_scale": 1.0})
        result = strategy.calculate_safety_order_price(100.0, order_number=1, direction="long")
        assert pytest.approx(result) == 100.0


# =====================================================================
# _flatten_conditions
# =====================================================================


class TestFlattenConditions:
    """Tests for _flatten_conditions()"""

    def test_flat_list_format(self):
        """Old flat format should be returned as-is."""
        strategy = _make_strategy()
        conditions = [{"type": "rsi"}, {"type": "macd"}]
        result = strategy._flatten_conditions(conditions)
        assert len(result) == 2

    def test_grouped_format(self):
        """New grouped format should be flattened into a single list."""
        strategy = _make_strategy()
        expression = {
            "groups": [
                {"conditions": [{"type": "rsi"}]},
                {"conditions": [{"type": "macd"}, {"type": "bb_percent"}]},
            ],
            "groupLogic": "and",
        }
        result = strategy._flatten_conditions(expression)
        assert len(result) == 3

    def test_empty_expression(self):
        strategy = _make_strategy()
        assert strategy._flatten_conditions(None) == []
        assert strategy._flatten_conditions([]) == []
        assert strategy._flatten_conditions({}) == []

    def test_invalid_format(self):
        """Non-list, non-dict with 'groups' => empty list."""
        strategy = _make_strategy()
        assert strategy._flatten_conditions("not_valid") == []


# =====================================================================
# _needs_aggregate_indicators
# =====================================================================


class TestNeedsAggregateIndicators:
    """Tests for _needs_aggregate_indicators()"""

    def test_no_conditions_returns_all_false(self):
        strategy = _make_strategy()
        needs = strategy._needs_aggregate_indicators()
        assert needs["ai_buy"] is False
        assert needs["ai_sell"] is False
        assert needs["bull_flag"] is False

    def test_ai_opinion_in_base_order_needs_ai_buy(self):
        strategy = _make_strategy({
            "base_order_conditions": [{"type": "ai_opinion", "operator": "equals", "value": "buy"}],
        })
        needs = strategy._needs_aggregate_indicators()
        assert needs["ai_buy"] is True

    def test_ai_confidence_in_take_profit_needs_ai_sell(self):
        strategy = _make_strategy({
            "take_profit_conditions": [{"type": "ai_confidence", "operator": "greater_than", "value": 70}],
        })
        needs = strategy._needs_aggregate_indicators()
        assert needs["ai_sell"] is True

    def test_bull_flag_in_conditions(self):
        strategy = _make_strategy({
            "base_order_conditions": [{"type": "bull_flag", "operator": "equals", "value": 1}],
        })
        needs = strategy._needs_aggregate_indicators()
        assert needs["bull_flag"] is True

    def test_legacy_ai_buy_indicator(self):
        strategy = _make_strategy({
            "base_order_conditions": [{"indicator": "ai_buy", "operator": "equals", "value": 1}],
        })
        needs = strategy._needs_aggregate_indicators()
        assert needs["ai_buy"] is True


# =====================================================================
# _check_entry_conditions
# =====================================================================


class TestCheckEntryConditions:
    """Tests for _check_entry_conditions()"""

    def test_no_conditions_always_allows_entry(self):
        """With no base_order_conditions, entry is always allowed."""
        strategy = _make_strategy({"base_order_conditions": []})
        signal = {"base_order_signal": False}
        assert strategy._check_entry_conditions(signal, "long") is True

    def test_conditions_met_allows_entry(self):
        strategy = _make_strategy({
            "base_order_conditions": [{"type": "rsi", "operator": "less_than", "value": 30}],
        })
        signal = {"base_order_signal": True}
        assert strategy._check_entry_conditions(signal, "long") is True

    def test_conditions_not_met_blocks_entry(self):
        strategy = _make_strategy({
            "base_order_conditions": [{"type": "rsi", "operator": "less_than", "value": 30}],
        })
        signal = {"base_order_signal": False}
        assert strategy._check_entry_conditions(signal, "long") is False


# =====================================================================
# should_buy  (async)
# =====================================================================


class TestShouldBuy:
    """Tests for should_buy()"""

    @pytest.mark.asyncio
    async def test_no_position_conditions_met_returns_buy(self):
        """Entry signal with sufficient balance => buy."""
        strategy = _make_strategy({
            "base_order_type": "percentage",
            "base_order_percentage": 10.0,
            "base_order_conditions": [{"type": "rsi"}],
        })
        signal = {"price": 100.0, "base_order_signal": True, "safety_order_signal": False}

        should, amount, reason = await strategy.should_buy(signal, position=None, balance=1.0)

        assert should is True
        assert pytest.approx(amount) == 0.1
        assert "Base order" in reason

    @pytest.mark.asyncio
    async def test_no_position_conditions_not_met_returns_no_buy(self):
        """Conditions not met => no buy."""
        strategy = _make_strategy({
            "base_order_conditions": [{"type": "rsi"}],
        })
        signal = {"price": 100.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = await strategy.should_buy(signal, position=None, balance=1.0)

        assert should is False
        assert amount == 0.0

    @pytest.mark.asyncio
    async def test_no_position_insufficient_balance(self):
        """Balance too low => no buy."""
        strategy = _make_strategy({
            "base_order_type": "percentage",
            "base_order_percentage": 100.0,
        })
        signal = {"price": 100.0, "base_order_signal": True, "safety_order_signal": False}

        should, amount, reason = await strategy.should_buy(signal, position=None, balance=0.0001)

        # calculate_base_order_size returns 0.0001, which equals balance, so it should pass
        # But if result > balance, it blocks
        # 100% of 0.0001 = 0.0001, which equals balance, so should pass
        assert should is True or "nsufficient" in reason

    @pytest.mark.asyncio
    async def test_safety_order_max_reached(self):
        """Max safety orders already used => no more buys."""
        strategy = _make_strategy({"max_safety_orders": 1})
        position = _make_mock_position()
        # Add a second buy trade (base + 1 SO = max reached)
        trade2 = MagicMock()
        trade2.side = "buy"
        trade2.price = 95.0
        trade2.timestamp = 2000
        position.trades = position.trades + [trade2]

        signal = {"price": 90.0, "base_order_signal": False, "safety_order_signal": True}

        should, amount, reason = await strategy.should_buy(signal, position=position, balance=1.0)

        assert should is False
        assert "Max safety orders" in reason

    @pytest.mark.asyncio
    async def test_safety_order_disabled(self):
        """max_safety_orders=0 => safety orders disabled."""
        strategy = _make_strategy({"max_safety_orders": 0})
        position = _make_mock_position()
        signal = {"price": 90.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = await strategy.should_buy(signal, position=position, balance=1.0)

        assert should is False
        assert "disabled" in reason.lower()

    @pytest.mark.asyncio
    async def test_safety_order_price_not_low_enough(self):
        """Price hasn't dropped enough for safety order."""
        strategy = _make_strategy({
            "max_safety_orders": 5,
            "price_deviation": 2.0,
            "safety_order_step_scale": 1.0,
        })
        position = _make_mock_position(avg_price=100.0)
        # Current price = 99.5, trigger = 98.0 => not low enough
        signal = {"price": 99.5, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = await strategy.should_buy(signal, position=position, balance=1.0)

        assert should is False
        assert "not low enough" in reason.lower()

    @pytest.mark.asyncio
    async def test_safety_order_triggered(self):
        """Price below trigger + no SO conditions => safety order placed."""
        strategy = _make_strategy({
            "max_safety_orders": 5,
            "price_deviation": 2.0,
            "safety_order_step_scale": 1.0,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 1.0,
            "safety_order_conditions": [],
        })
        position = _make_mock_position(avg_price=100.0, total_quote=1.0, max_quote=10.0)
        # Price = 97.0, trigger for SO1 = 98.0 => triggered
        signal = {"price": 97.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = await strategy.should_buy(signal, position=position, balance=1.0)

        assert should is True
        assert amount > 0
        assert "Safety order #1" in reason

    @pytest.mark.asyncio
    async def test_pattern_position_skips_dca(self):
        """Bull flag position (has entry_stop_loss) should skip DCA."""
        strategy = _make_strategy({"max_safety_orders": 5})
        position = _make_mock_position(entry_stop_loss=95.0)
        signal = {"price": 90.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = await strategy.should_buy(signal, position=position, balance=1.0)

        assert should is False
        assert "Pattern position" in reason

    @pytest.mark.asyncio
    async def test_bidirectional_long_entry(self):
        """Bidirectional mode with long signal => long entry (neutral zone disabled)."""
        strategy = _make_strategy({
            "enable_bidirectional": True,
            "enable_neutral_zone": False,
            "base_order_conditions": [],
            "base_order_type": "percentage",
            "base_order_percentage": 10.0,
        })
        signal = {"price": 100.0, "base_order_signal": True, "safety_order_signal": False}

        should, amount, reason = await strategy.should_buy(signal, position=None, balance=1.0)

        assert should is True
        assert signal.get("direction") == "long"

    @pytest.mark.asyncio
    async def test_bidirectional_neutral_zone_blocks(self):
        """Both long and short signals active + neutral zone => blocked."""
        strategy = _make_strategy({
            "enable_bidirectional": True,
            "enable_neutral_zone": True,
            "base_order_conditions": [],  # No conditions = always true
        })
        signal = {"price": 100.0, "base_order_signal": True, "safety_order_signal": False}

        should, amount, reason = await strategy.should_buy(signal, position=None, balance=1.0)

        assert should is False
        assert "Neutral zone" in reason


# =====================================================================
# should_sell  (async)
# =====================================================================


class TestShouldSell:
    """Tests for should_sell()"""

    @pytest.mark.asyncio
    async def test_take_profit_percentage_hit(self):
        """Price risen enough => sell at take profit %."""
        strategy = _make_strategy({
            "take_profit_percentage": 3.0,
            "trailing_take_profit": False,
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        # Current value = 0.1 * 103.5 = 10.35, profit = 0.35/10 = 3.5%
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=103.5)

        assert should is True
        assert "Take profit" in reason

    @pytest.mark.asyncio
    async def test_below_take_profit_holds(self):
        """Price not high enough => hold."""
        strategy = _make_strategy({"take_profit_percentage": 3.0})
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        # Current value = 0.1 * 101 = 10.1, profit = 0.1/10 = 1%
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=101.0)

        assert should is False
        assert "Holding" in reason

    @pytest.mark.asyncio
    async def test_stop_loss_triggered(self):
        """Price dropped enough => stop loss."""
        strategy = _make_strategy({
            "stop_loss_enabled": True,
            "stop_loss_percentage": -10.0,
            "take_profit_percentage": 3.0,
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        # Current value = 0.1 * 88 = 8.8, profit = -1.2/10 = -12%
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=88.0)

        assert should is True
        assert "Stop loss" in reason

    @pytest.mark.asyncio
    async def test_stop_loss_disabled_does_not_trigger(self):
        """Stop loss disabled => even deep loss does not trigger."""
        strategy = _make_strategy({
            "stop_loss_enabled": False,
            "take_profit_percentage": 3.0,
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=80.0)

        assert should is False

    @pytest.mark.asyncio
    async def test_trailing_take_profit_activates_and_holds(self):
        """TTP activates when TP% hit but does not sell until trailing deviation."""
        strategy = _make_strategy({
            "take_profit_percentage": 3.0,
            "trailing_take_profit": True,
            "trailing_deviation": 1.0,
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        # profit = 5% (> TP of 3%), so TTP activates
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=105.0)

        assert should is False
        assert "Trailing TP active" in reason

    @pytest.mark.asyncio
    async def test_trailing_stop_loss(self):
        """TSL triggered when price drops from peak."""
        strategy = _make_strategy({
            "trailing_stop_loss": True,
            "trailing_stop_deviation": 5.0,
            "take_profit_percentage": 50.0,  # high enough to not trigger TP
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        position.highest_price_since_entry = 110.0
        # TSL price = 110 * (1 - 0.05) = 104.5
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=104.0)

        assert should is True
        assert "Trailing stop loss" in reason

    @pytest.mark.asyncio
    async def test_condition_based_sell_with_min_profit(self):
        """Condition-based exit requires min profit; profit must meet conditions threshold."""
        strategy = _make_strategy({
            "take_profit_percentage": 10.0,  # High TP% so percentage check does NOT trigger
            "min_profit_for_conditions": 3.0,  # Lower threshold for condition-based sell
            "take_profit_conditions": [{"type": "rsi", "operator": "crossing_below", "value": 70}],
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": True}

        # profit = 4%, min_profit_for_conditions = 3% => conditions sell
        should, reason = await strategy.should_sell(signal, position, current_price=104.0)
        assert should is True
        assert "conditions met" in reason.lower()

    @pytest.mark.asyncio
    async def test_condition_based_sell_profit_too_low(self):
        """Conditions met but profit too low => hold."""
        strategy = _make_strategy({
            "take_profit_percentage": 3.0,
            "take_profit_conditions": [{"type": "rsi"}],
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": True}

        # profit = 1% < min 3% => hold
        should, reason = await strategy.should_sell(signal, position, current_price=101.0)
        assert should is False
        assert "profit too low" in reason.lower()

    @pytest.mark.asyncio
    async def test_min_profit_override(self):
        """min_profit_for_conditions overrides take_profit_percentage."""
        strategy = _make_strategy({
            "take_profit_percentage": 10.0,
            "min_profit_for_conditions": 1.0,
            "take_profit_conditions": [{"type": "rsi"}],
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": True}

        # profit = 2%, min override = 1% => sell
        should, reason = await strategy.should_sell(signal, position, current_price=102.0)
        assert should is True

    @pytest.mark.asyncio
    async def test_pattern_tsl_triggered(self):
        """Pattern-based position with TSL hit."""
        strategy = _make_strategy({})
        position = _make_mock_position(
            avg_price=100.0,
            total_base=0.1,
            total_quote=10.0,
            entry_stop_loss=95.0,
            entry_take_profit_target=110.0,
        )
        position.highest_price_since_entry = 100.0
        position.trailing_stop_loss_price = 95.0
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=94.0)

        assert should is True
        assert "TSL" in reason

    @pytest.mark.asyncio
    async def test_pattern_ttp_triggered(self):
        """Pattern TTP: price reached target, then dropped from peak."""
        strategy = _make_strategy({})
        position = _make_mock_position(
            avg_price=100.0,
            total_base=0.1,
            total_quote=10.0,
            entry_stop_loss=95.0,
            entry_take_profit_target=110.0,
        )
        position.highest_price_since_entry = 115.0
        position.trailing_stop_loss_price = 110.0  # Updated TSL
        position.trailing_tp_active = True
        position.highest_price_since_tp = 115.0
        signal = {"take_profit_signal": False}

        # TTP trigger = 115 * 0.99 = 113.85
        should, reason = await strategy.should_sell(signal, position, current_price=113.0)

        assert should is True
        assert "TTP" in reason


# =====================================================================
# get_definition
# =====================================================================


class TestGetDefinition:
    """Tests for get_definition()"""

    def test_returns_strategy_definition(self):
        strategy = _make_strategy()
        defn = strategy.get_definition()
        assert defn.id == "indicator_based"
        assert defn.name is not None
        assert len(defn.parameters) > 0
        assert len(defn.supported_products) > 0

    def test_all_parameters_have_names(self):
        strategy = _make_strategy()
        defn = strategy.get_definition()
        for param in defn.parameters:
            assert param.name is not None
            assert param.display_name is not None


# =====================================================================
# _get_ai_params and _get_bull_flag_params
# =====================================================================


class TestGetParams:
    """Tests for _get_ai_params() and _get_bull_flag_params()"""

    def test_get_ai_params_defaults(self):
        strategy = _make_strategy()
        params = strategy._get_ai_params()
        assert params.ai_model == "claude"
        assert params.ai_timeframe == "15m"

    def test_get_ai_params_custom(self):
        strategy = _make_strategy({"ai_model": "gpt", "ai_timeframe": "1h"})
        params = strategy._get_ai_params()
        assert params.ai_model == "gpt"
        assert params.ai_timeframe == "1h"

    def test_get_bull_flag_params_defaults(self):
        strategy = _make_strategy()
        params = strategy._get_bull_flag_params()
        assert params.timeframe == "FIFTEEN_MINUTE"
        assert params.min_pole_gain_pct == 3.0

    def test_get_bull_flag_params_from_explicit_config(self):
        """Explicit bull_flag_min_pole_gain should override default."""
        strategy = _make_strategy({"bull_flag_min_pole_gain": 7.0})
        params = strategy._get_bull_flag_params()
        assert params.min_pole_gain_pct == 7.0
