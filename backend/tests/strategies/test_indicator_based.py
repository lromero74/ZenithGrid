"""
Tests for backend/app/strategies/indicator_based.py

Covers:
- IndicatorBasedStrategy.validate_config
- IndicatorBasedStrategy.calculate_base_order_size
- IndicatorBasedStrategy.calculate_safety_order_size
- IndicatorBasedStrategy.calculate_safety_order_price
- indicator_based_helpers.flatten_conditions
- indicator_based_helpers.needs_aggregate_indicators
- indicator_based_helpers.build_ai_params
- indicator_based_helpers.build_bull_flag_params
- IndicatorBasedStrategy._check_entry_conditions
- IndicatorBasedStrategy.should_buy (async)
- IndicatorBasedStrategy.should_sell (async)
"""

import pytest
from app.utils.timeutil import utcnow
from unittest.mock import MagicMock, patch

from app.strategies.indicator_based import IndicatorBasedStrategy
from app.strategies.indicator_based_helpers import (
    build_ai_params,
    build_bull_flag_params,
    flatten_conditions,
    needs_aggregate_indicators,
)


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
        "take_profit_mode": "fixed",
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
    entry_fees_quote=0.0,
    short_total_sold_quote=0.0,
    short_total_sold_base=0.0,
):
    """Create a mock position object."""
    pos = MagicMock()
    pos.average_buy_price = avg_price
    pos.total_base_acquired = total_base
    pos.total_quote_spent = total_quote
    # Short positions carry their cost basis in the short_* fields (long fields are 0).
    pos.short_total_sold_quote = short_total_sold_quote
    pos.short_total_sold_base = short_total_sold_base
    # Real numeric value so the fee-aware TP floor calibrates deterministically
    # (a bare MagicMock attr would float() to 1.0 → bogus fee rate). 0.0 makes
    # position_exit_fee_rate fall back to the default 0.6% taker rate.
    pos.entry_fees_quote = entry_fees_quote
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
        conditions = [{"type": "rsi"}, {"type": "macd"}]
        result = flatten_conditions(conditions)
        assert len(result) == 2

    def test_grouped_format(self):
        """New grouped format should be flattened into a single list."""
        expression = {
            "groups": [
                {"conditions": [{"type": "rsi"}]},
                {"conditions": [{"type": "macd"}, {"type": "bb_percent"}]},
            ],
            "groupLogic": "and",
        }
        result = flatten_conditions(expression)
        assert len(result) == 3

    def test_empty_expression(self):
        assert flatten_conditions(None) == []
        assert flatten_conditions([]) == []
        assert flatten_conditions({}) == []

    def test_invalid_format(self):
        """Non-list, non-dict with 'groups' => empty list."""
        assert flatten_conditions("not_valid") == []


# =====================================================================
# _needs_aggregate_indicators
# =====================================================================


class TestNeedsAggregateIndicators:
    """Tests for _needs_aggregate_indicators()"""

    def test_no_conditions_returns_all_false(self):
        strategy = _make_strategy()
        needs = needs_aggregate_indicators(
            strategy.base_order_conditions,
            strategy.safety_order_conditions,
            strategy.take_profit_conditions,
        )
        assert needs["ai_buy"] is False
        assert needs["ai_sell"] is False
        assert needs["bull_flag"] is False

    def test_ai_opinion_in_base_order_needs_ai_buy(self):
        strategy = _make_strategy({
            "base_order_conditions": [{"type": "ai_opinion", "operator": "equals", "value": "buy"}],
        })
        needs = needs_aggregate_indicators(
            strategy.base_order_conditions,
            strategy.safety_order_conditions,
            strategy.take_profit_conditions,
        )
        assert needs["ai_buy"] is True

    def test_ai_confidence_in_take_profit_needs_ai_sell(self):
        strategy = _make_strategy({
            "take_profit_conditions": [{"type": "ai_confidence", "operator": "greater_than", "value": 70}],
        })
        needs = needs_aggregate_indicators(
            strategy.base_order_conditions,
            strategy.safety_order_conditions,
            strategy.take_profit_conditions,
        )
        assert needs["ai_sell"] is True

    def test_bull_flag_in_conditions(self):
        strategy = _make_strategy({
            "base_order_conditions": [{"type": "bull_flag", "operator": "equals", "value": 1}],
        })
        needs = needs_aggregate_indicators(
            strategy.base_order_conditions,
            strategy.safety_order_conditions,
            strategy.take_profit_conditions,
        )
        assert needs["bull_flag"] is True

    def test_legacy_ai_buy_indicator(self):
        strategy = _make_strategy({
            "base_order_conditions": [{"indicator": "ai_buy", "operator": "equals", "value": 1}],
        })
        needs = needs_aggregate_indicators(
            strategy.base_order_conditions,
            strategy.safety_order_conditions,
            strategy.take_profit_conditions,
        )
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
    async def test_grace_allows_safety_order_beyond_configured(self):
        """With grace, an SO fires past the configured max (like a manual bump)."""
        strategy = _make_strategy({
            "max_safety_orders": 1,
            "grace_safety_orders": 2,  # effective ceiling = 3
            "price_deviation": 2.0,
            "safety_order_step_scale": 1.0,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 1.0,
            "safety_order_conditions": [],
        })
        # base + 1 configured SO already deployed (configured max reached)
        position = _make_mock_position(avg_price=100.0, total_quote=1.0, max_quote=10.0)
        trade2 = MagicMock(side="buy", price=98.0, timestamp=2000, dca_levels=1)
        position.trades = position.trades + [trade2]
        # SO#2 trigger from avg 100 @ 2% deviation = 98.0; price below it
        signal = {"price": 95.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = await strategy.should_buy(signal, position=position, balance=1.0)

        assert should is True
        assert amount > 0
        assert "Safety order #2" in reason

    @pytest.mark.asyncio
    async def test_grace_ceiling_blocks_beyond_configured_plus_grace(self):
        """Once configured + grace SOs are all deployed, no more fire."""
        strategy = _make_strategy({
            "max_safety_orders": 1,
            "grace_safety_orders": 2,  # effective ceiling = 3
            "price_deviation": 2.0,
            "safety_order_step_scale": 1.0,
        })
        position = _make_mock_position()
        # base + 3 SOs deployed = effective max (1 + 2) reached
        for i, price in enumerate((98.0, 96.0, 94.0)):
            position.trades = position.trades + [
                MagicMock(side="buy", price=price, timestamp=2000 + i, dca_levels=1)
            ]
        signal = {"price": 80.0, "base_order_signal": False, "safety_order_signal": True}

        should, amount, reason = await strategy.should_buy(signal, position=position, balance=1.0)

        assert should is False
        assert "Max safety orders reached (3/3)" in reason

    @pytest.mark.asyncio
    async def test_grace_zero_identical_to_today(self):
        """grace=0 must behave exactly like no grace key — gate blocks at configured max."""
        strategy = _make_strategy({"max_safety_orders": 1, "grace_safety_orders": 0})
        position = _make_mock_position()
        position.trades = position.trades + [
            MagicMock(side="buy", price=95.0, timestamp=2000, dca_levels=1)
        ]
        signal = {"price": 90.0, "base_order_signal": False, "safety_order_signal": True}

        should, amount, reason = await strategy.should_buy(signal, position=position, balance=1.0)

        assert should is False
        assert "Max safety orders reached (1/1)" in reason

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
    async def test_final_safety_order_uses_remaining_budget_when_shortfall_is_rounding_drift(self):
        """Whole-base fills may leave the final SO a few cents short of its ideal geometric size."""
        strategy = _make_strategy({
            "base_order_type": "fixed",
            "auto_calculate_order_sizes": True,
            "max_safety_orders": 3,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 1.62,
            "price_deviation": 2.0,
            "safety_order_step_scale": 1.0,
        })
        trades = []
        for price in (0.146384, 0.142502, 0.131376):
            trade = MagicMock(side="buy", price=price, timestamp=len(trades), dca_levels=1)
            trades.append(trade)
        # Safety orders size off the recorded base order (earliest entry trade). For a
        # normally-allocated auto-calc deal that equals the budget-derived base, so set
        # the base trade's quote accordingly (a MagicMock's auto quote_amount floats to 1.0).
        trades[0].quote_amount = strategy.calculate_base_order_size(6.3985617472)
        position = _make_mock_position(
            avg_price=0.139,
            total_base=27.0,
            total_quote=3.730089,
            max_quote=6.3985617472,
            trades=trades,
        )
        signal = {"price": 0.108979, "base_order_signal": False, "safety_order_signal": True}

        should, amount, reason = await strategy.should_buy(
            signal,
            position=position,
            balance=2.6684727472,
            dca_rounding_tolerance=0.108979,
            quote_increment=0.01,
        )

        assert should is True
        assert amount == pytest.approx(2.66)
        assert amount <= 2.6684727472
        assert "rounding-adjusted" in reason
        assert signal["dca_levels"] == 1

    def test_grace_safety_order_sizes_off_actual_base_not_inflated_budget(self):
        """Auto-calc: a grace SO must size off the deal's ACTUAL base order, not a base
        re-derived from max_quote_allowed. When max_quote_allowed is larger than the
        placed base ladder (the #651 case), re-deriving inflated the base so the grace SO
        overshot the budget and got blocked. Sizing off the recorded base fits."""
        strategy = _make_strategy({
            "base_order_type": "fixed",
            "auto_calculate_order_sizes": True,
            "max_safety_orders": 2,
            "grace_safety_orders": 2,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 1.62,
            "price_deviation": 2.5,
            "safety_order_step_scale": 1.62,
        })
        base_quote = 540.0
        base_trade = MagicMock(side="buy", quote_amount=base_quote, timestamp=0, dca_levels=1)
        # max_quote_allowed inflated relative to the actual base ladder (the #651 case).
        position = _make_mock_position(avg_price=0.07, max_quote=5673.0, trades=[base_trade])

        # SO #3 is the first GRACE order (configured max is 2); 2 already deployed.
        so3 = strategy._calculate_safety_order_amount(position, safety_orders_count=2, next_order_number=3)

        # Sized off the ACTUAL base (540), NOT the budget-re-derived (inflated) base.
        assert so3 == pytest.approx(strategy.calculate_safety_order_size(base_quote, 3))
        inflated = strategy.calculate_safety_order_size(strategy.calculate_base_order_size(5673.0), 3)
        assert so3 < inflated
        # And the grace SO fits within the deal's allocated budget (the bug was it didn't).
        assert so3 < 5673.0

    @pytest.mark.asyncio
    async def test_safety_order_still_blocks_when_shortfall_exceeds_rounding_tolerance(self):
        """A precision allowance must not turn a materially underfunded SO into a partial order."""
        strategy = _make_strategy({
            "base_order_type": "fixed",
            "auto_calculate_order_sizes": True,
            "max_safety_orders": 3,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 1.62,
            "price_deviation": 2.0,
            "safety_order_step_scale": 1.0,
        })
        trades = [
            MagicMock(side="buy", price=price, timestamp=index, dca_levels=1)
            for index, price in enumerate((0.146384, 0.142502, 0.131376))
        ]
        position = _make_mock_position(
            avg_price=0.139,
            total_quote=4.3985617472,
            max_quote=6.3985617472,
            trades=trades,
        )
        signal = {"price": 0.108979, "base_order_signal": False, "safety_order_signal": True}

        should, amount, reason = await strategy.should_buy(
            signal,
            position=position,
            balance=2.0,
            dca_rounding_tolerance=0.108979,
            quote_increment=0.01,
        )

        assert should is False
        assert amount == 0.0
        assert "Insufficient balance" in reason

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
        """Sell only when profit clears the target NET of round-trip fees."""
        strategy = _make_strategy({
            "take_profit_percentage": 3.0,
            "trailing_take_profit": False,
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": False}

        # 3.5% gross is above the 3% target but does NOT clear it net of fees
        # (floor ~4.24% at the 0.6% fallback rate) → hold.
        should, _ = await strategy.should_sell(signal, position, current_price=103.5)
        assert should is False

        # 5% gross clears the fee-adjusted floor → sell.
        should, reason = await strategy.should_sell(signal, position, current_price=105.0)
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
            "take_profit_mode": "trailing",
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
        """Condition-based exit requires min profit; profit must meet threshold."""
        strategy = _make_strategy({
            "take_profit_percentage": 3.0,
            "take_profit_mode": "minimum",
            "take_profit_conditions": [{"type": "rsi", "operator": "crossing_below", "value": 70}],
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": True}

        # 5% gross clears the 3% target net of fees (floor ~4.24%) => conditions sell
        should, reason = await strategy.should_sell(signal, position, current_price=105.0)
        assert should is True
        assert "conditions met" in reason.lower()

    @pytest.mark.asyncio
    async def test_condition_based_sell_profit_too_low(self):
        """Conditions met but profit too low => hold."""
        strategy = _make_strategy({
            "take_profit_percentage": 3.0,
            "take_profit_mode": "minimum",
            "take_profit_conditions": [{"type": "rsi"}],
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": True}

        # profit = 1% < min 3% => hold
        should, reason = await strategy.should_sell(signal, position, current_price=101.0)
        assert should is False
        assert "profit too low" in reason.lower()

    @pytest.mark.asyncio
    async def test_minimum_mode_low_tp_threshold(self):
        """Minimum mode: low TP% floor allows sell at small profit."""
        strategy = _make_strategy({
            "take_profit_percentage": 1.0,
            "take_profit_mode": "minimum",
            "take_profit_conditions": [{"type": "rsi"}],
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": True}

        # 3% gross clears the 1% target net of fees (floor ~2.22%) => sell
        should, reason = await strategy.should_sell(signal, position, current_price=103.0)
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
# take_profit_mode — new mode-aware sell logic
# =====================================================================


class TestTakeProfitModes:
    """Tests for the take_profit_mode system (fixed/trailing/minimum)."""

    @pytest.mark.asyncio
    async def test_fixed_mode_sells_at_tp_percentage(self):
        """Fixed mode: sell when profit >= TP%."""
        strategy = _make_strategy({
            "take_profit_percentage": 3.0,
            "take_profit_mode": "fixed",
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": False}

        # 3.5% gross sits above the 3% target but below it net of fees (floor ~4.24%) → hold
        should, _ = await strategy.should_sell(signal, position, current_price=103.5)
        assert should is False

        # 5% gross clears the fee-adjusted floor → sell
        should, reason = await strategy.should_sell(signal, position, current_price=105.0)
        assert should is True
        assert "Take profit target" in reason

    @pytest.mark.asyncio
    async def test_fixed_mode_holds_below_tp(self):
        """Fixed mode: hold when profit < TP%."""
        strategy = _make_strategy({
            "take_profit_percentage": 3.0,
            "take_profit_mode": "fixed",
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": False}

        # profit = 2%
        should, reason = await strategy.should_sell(signal, position, current_price=102.0)
        assert should is False

    @pytest.mark.asyncio
    async def test_trailing_mode_activates_on_target(self):
        """Trailing mode: activates trailing when TP% hit but holds for deviation."""
        strategy = _make_strategy({
            "take_profit_percentage": 3.0,
            "take_profit_mode": "trailing",
            "trailing_deviation": 1.0,
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": False}

        # profit = 5% > TP 3%, trailing activates but deviation not hit
        should, reason = await strategy.should_sell(signal, position, current_price=105.0)
        assert should is False
        assert "Trailing TP active" in reason

    @pytest.mark.asyncio
    async def test_trailing_mode_triggers_on_deviation(self):
        """Trailing mode: sells when price drops from peak by deviation %."""
        strategy = _make_strategy({
            "take_profit_percentage": 3.0,
            "take_profit_mode": "trailing",
            "trailing_deviation": 1.0,
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        position.trailing_tp_active = True
        position.highest_price_since_tp = 110.0  # peak at 110
        signal = {"take_profit_signal": False}

        # trigger = 110 * (1 - 0.01) = 108.9; price = 108 < 108.9
        should, reason = await strategy.should_sell(signal, position, current_price=108.0)
        assert should is True
        assert "Trailing TP triggered" in reason

    @pytest.mark.asyncio
    async def test_trailing_mode_holds_below_tp(self):
        """Trailing mode: does not activate when profit < TP%."""
        strategy = _make_strategy({
            "take_profit_percentage": 5.0,
            "take_profit_mode": "trailing",
            "trailing_deviation": 1.0,
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": False}

        # profit = 2% < TP 5%
        should, reason = await strategy.should_sell(signal, position, current_price=102.0)
        assert should is False
        assert "Holding" in reason

    @pytest.mark.asyncio
    async def test_minimum_mode_conditions_met_above_floor(self):
        """Minimum mode: sell when conditions fire AND profit >= TP%."""
        strategy = _make_strategy({
            "take_profit_percentage": 2.0,
            "take_profit_mode": "minimum",
            "take_profit_conditions": [{"type": "rsi", "operator": "crossing_below", "value": 70}],
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": True}

        # profit = 4% >= min 2%
        should, reason = await strategy.should_sell(signal, position, current_price=104.0)
        assert should is True
        assert "conditions met" in reason.lower()

    @pytest.mark.asyncio
    async def test_minimum_mode_conditions_met_profit_too_low(self):
        """Minimum mode: hold when conditions fire but profit < TP%."""
        strategy = _make_strategy({
            "take_profit_percentage": 5.0,
            "take_profit_mode": "minimum",
            "take_profit_conditions": [{"type": "rsi", "operator": "crossing_below", "value": 70}],
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": True}

        # profit = 2% < min 5%
        should, reason = await strategy.should_sell(signal, position, current_price=102.0)
        assert should is False
        assert "profit too low" in reason.lower()

    @pytest.mark.asyncio
    async def test_minimum_mode_no_signal_holds(self):
        """Minimum mode: hold when conditions haven't fired even if profit is high."""
        strategy = _make_strategy({
            "take_profit_percentage": 2.0,
            "take_profit_mode": "minimum",
            "take_profit_conditions": [{"type": "rsi", "operator": "crossing_below", "value": 70}],
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": False}

        # profit = 10% but conditions haven't fired
        should, reason = await strategy.should_sell(signal, position, current_price=110.0)
        assert should is False
        assert "Holding" in reason

    @pytest.mark.asyncio
    async def test_minimum_mode_no_conditions_configured_holds(self):
        """Minimum mode with no conditions: holds (warns, never sells via TP)."""
        strategy = _make_strategy({
            "take_profit_percentage": 2.0,
            "take_profit_mode": "minimum",
            "take_profit_conditions": [],
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=110.0)
        assert should is False

    @pytest.mark.asyncio
    async def test_legacy_trailing_take_profit_inferred_as_trailing(self):
        """Legacy: trailing_take_profit=True infers trailing mode."""
        strategy = _make_strategy({
            "take_profit_percentage": 3.0,
            "trailing_take_profit": True,
            "trailing_deviation": 1.0,
            # No take_profit_mode set — legacy field
        })
        # Remove the mode so legacy inference kicks in
        del strategy.config["take_profit_mode"]
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": False}

        # profit = 5% > TP 3%, should activate trailing
        should, reason = await strategy.should_sell(signal, position, current_price=105.0)
        assert should is False
        assert "Trailing TP active" in reason

    @pytest.mark.asyncio
    async def test_legacy_min_profit_for_conditions_inferred_as_minimum(self):
        """Legacy: min_profit_for_conditions set infers minimum mode."""
        strategy = _make_strategy({
            "take_profit_percentage": 10.0,
            "min_profit_for_conditions": 3.0,
            "take_profit_conditions": [{"type": "rsi"}],
        })
        del strategy.config["take_profit_mode"]
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        signal = {"take_profit_signal": True}

        # profit = 4%, min_profit = TP% = 10% (minimum mode uses take_profit_percentage)
        # But legacy min_profit_for_conditions is 3.0, and mode is inferred...
        # In the new code, minimum mode uses tp_pct directly (take_profit_percentage)
        # profit = 4% < 10% => should NOT sell
        should, reason = await strategy.should_sell(signal, position, current_price=104.0)
        assert should is False
        assert "profit too low" in reason.lower()


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
        params = build_ai_params(strategy.config)
        assert params.ai_model == "claude"
        assert params.ai_timeframe == "15m"

    def test_get_ai_params_custom(self):
        strategy = _make_strategy({"ai_model": "gpt", "ai_timeframe": "1h"})
        params = build_ai_params(strategy.config)
        assert params.ai_model == "gpt"
        assert params.ai_timeframe == "1h"

    def test_get_bull_flag_params_defaults(self):
        strategy = _make_strategy()
        params = build_bull_flag_params(strategy.config)
        assert params.timeframe == "FIFTEEN_MINUTE"
        assert params.min_pole_gain_pct == 3.0

    def test_get_bull_flag_params_from_explicit_config(self):
        """Explicit bull_flag_min_pole_gain should override default."""
        strategy = _make_strategy({"bull_flag_min_pole_gain": 7.0})
        params = build_bull_flag_params(strategy.config)
        assert params.min_pole_gain_pct == 7.0


# =====================================================================
# Speculative max-hold time-based exit
# =====================================================================
# See PRPs/high-risk-doubling-preset.md §Recommended Design §5.


class TestSpeculativeMaxHoldExit:
    """should_sell forces a close when a speculative position is older than
    speculative_max_hold_hours — runs BEFORE TP/SL checks so we always
    escape the bucket slot on schedule."""

    @pytest.mark.asyncio
    async def test_exits_when_past_max_hold(self):
        from datetime import timedelta
        strategy = _make_strategy({
            "speculative_max_hold_hours": 24,
            "take_profit_percentage": 999.0,  # not reachable
            "stop_loss_enabled": False,
        })
        position = _make_mock_position()
        position.opened_at = utcnow() - timedelta(hours=25)
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=101.0)

        assert should is True
        assert "Speculative max hold" in reason
        assert "24h" in reason

    @pytest.mark.asyncio
    async def test_does_not_exit_before_max_hold(self):
        from datetime import timedelta
        strategy = _make_strategy({
            "speculative_max_hold_hours": 24,
            "take_profit_percentage": 999.0,
            "stop_loss_enabled": False,
        })
        position = _make_mock_position()
        position.opened_at = utcnow() - timedelta(hours=23)
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=101.0)

        assert should is False
        assert "Speculative max hold" not in reason

    @pytest.mark.asyncio
    async def test_not_active_when_config_missing(self):
        """Regression guard: non-speculative bots (no speculative_max_hold_hours
        key) behave exactly like before — no time-based forced exit."""
        from datetime import timedelta
        strategy = _make_strategy({
            # No speculative_max_hold_hours at all
            "take_profit_percentage": 999.0,
            "stop_loss_enabled": False,
        })
        position = _make_mock_position()
        position.opened_at = utcnow() - timedelta(days=365)  # 1 year old
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=101.0)

        assert should is False
        assert "Speculative max hold" not in reason

    @pytest.mark.asyncio
    async def test_fires_before_tp(self):
        """If both TP and max-hold would trigger simultaneously, max-hold wins —
        it runs first so the bucket slot is always released on schedule."""
        from datetime import timedelta
        strategy = _make_strategy({
            "speculative_max_hold_hours": 24,
            "take_profit_percentage": 3.0,  # easily reachable
            "trailing_take_profit": False,
        })
        position = _make_mock_position(avg_price=100.0, total_base=0.1, total_quote=10.0)
        position.opened_at = utcnow() - timedelta(hours=25)
        signal = {"take_profit_signal": False}

        should, reason = await strategy.should_sell(signal, position, current_price=105.0)

        assert should is True
        assert "Speculative max hold" in reason
        # Confirm TP reason is NOT what triggered
        assert "Take profit" not in reason


# =====================================================================
# _calculate_bidirectional_order_amount — soft-ceiling-aware sizing
# =====================================================================


class TestBidirectionalSoftCeilingSizing:
    """Bidirectional base-order sizing must split the budget by the SAME
    effective deal count the engine uses to gate new deals (the soft ceiling),
    not the raw configured max_concurrent_deals. Otherwise a soft-ceiling bot
    under-sizes its base order (budget/20 instead of budget/effective)."""

    def _bidir_strategy(self, soft_ceiling: bool):
        # base_order_percentage=100 + no auto-calc → base order == per-position budget,
        # so the test asserts the divisor directly.
        return _make_strategy({
            "budget_percentage": 20.0,
            "long_budget_percentage": 50.0,
            "short_budget_percentage": 50.0,
            "max_concurrent_deals": 20,
            "base_order_type": "percentage",
            "base_order_percentage": 100.0,
            "auto_calculate_order_sizes": False,
            "enable_soft_ceiling": soft_ceiling,
        })

    def test_uses_effective_soft_ceiling_as_divisor(self):
        """Happy path: with soft ceiling on, divide by the effective ceiling (2),
        not the configured max (20). budget=1000×20%=200; long 50%=100; /2 = 50."""
        strategy = self._bidir_strategy(soft_ceiling=True)
        amount = strategy._calculate_bidirectional_order_amount(
            "long", 0.0, aggregate_usd_value=1000.0, effective_max_deals=2
        )
        assert pytest.approx(amount) == 50.0

    def test_effective_ceiling_of_one_uses_full_direction_budget(self):
        """Edge: effective ceiling 1 → no division → full direction budget (100)."""
        strategy = self._bidir_strategy(soft_ceiling=True)
        amount = strategy._calculate_bidirectional_order_amount(
            "long", 0.0, aggregate_usd_value=1000.0, effective_max_deals=1
        )
        assert pytest.approx(amount) == 100.0

    def test_falls_back_to_configured_max_when_soft_ceiling_disabled(self):
        """Failure/fallback: soft ceiling off → divide by configured max (20):
        200 × 50% / 20 = 5. (effective_max_deals is ignored when SC is off.)"""
        strategy = self._bidir_strategy(soft_ceiling=False)
        amount = strategy._calculate_bidirectional_order_amount(
            "long", 0.0, aggregate_usd_value=1000.0, effective_max_deals=2
        )
        assert pytest.approx(amount) == 5.0

    def test_falls_back_to_configured_max_when_no_effective_provided(self):
        """Fallback: SC on but no effective value passed → configured max (20) → 5."""
        strategy = self._bidir_strategy(soft_ceiling=True)
        amount = strategy._calculate_bidirectional_order_amount(
            "long", 0.0, aggregate_usd_value=1000.0
        )
        assert pytest.approx(amount) == 5.0


# =====================================================================
# should_sell — SHORT positions (direction-aware P&L / trailing)
# =====================================================================


class TestShouldSellShort:
    """Shorts profit by buying back cheaper; should_sell must use the short_* fields
    (the long fields are 0 for shorts → previously a constant 0% and ZeroDivisionError)."""

    def _short(self, sold_quote=100.0, sold_base=1.0, **o):
        # A short that sold `sold_base` for `sold_quote` (avg sell price = quote/base).
        return _make_mock_position(
            direction="short", avg_price=0.0, total_base=0.0, total_quote=0.0,
            short_total_sold_quote=sold_quote, short_total_sold_base=sold_base, **o
        )

    @pytest.mark.asyncio
    async def test_short_profit_when_price_falls_hits_fixed_tp(self):
        """Sold 1 @ 100; price now 95 → +5% → fixed TP (3%) sells."""
        strategy = _make_strategy({"take_profit_mode": "fixed", "take_profit_percentage": 3.0})
        pos = self._short(sold_quote=100.0, sold_base=1.0)
        should, reason = await strategy.should_sell({}, pos, current_price=95.0)
        assert should is True
        assert "Take profit" in reason

    @pytest.mark.asyncio
    async def test_short_loss_when_price_rises_no_tp(self):
        """Price rose to 104 → short is down ~4% → no take-profit."""
        strategy = _make_strategy({"take_profit_mode": "fixed", "take_profit_percentage": 3.0})
        pos = self._short(sold_quote=100.0, sold_base=1.0)
        should, reason = await strategy.should_sell({}, pos, current_price=104.0)
        assert should is False

    @pytest.mark.asyncio
    async def test_short_stop_loss_triggers_when_price_rises(self):
        """Short loss past the stop-loss % closes the position (no long-field crash)."""
        strategy = _make_strategy({
            "take_profit_mode": "fixed", "take_profit_percentage": 3.0,
            "stop_loss_enabled": True, "stop_loss_percentage": -10.0,
        })
        pos = self._short(sold_quote=100.0, sold_base=1.0)
        should, reason = await strategy.should_sell({}, pos, current_price=115.0)  # -15%
        assert should is True
        assert "Stop loss" in reason

    @pytest.mark.asyncio
    async def test_short_zero_cost_basis_does_not_crash(self):
        """Degenerate short (no sold quote) must not ZeroDivisionError."""
        strategy = _make_strategy()
        pos = self._short(sold_quote=0.0, sold_base=0.0)
        should, reason = await strategy.should_sell({}, pos, current_price=50.0)
        assert should is False  # 0% profit, no TP

    @pytest.mark.asyncio
    async def test_short_trailing_tp_triggers_on_rise_from_trough(self):
        """Trailing TP for a short: arms in profit, trails the low, exits when price rises back."""
        strategy = _make_strategy({
            "take_profit_mode": "trailing", "take_profit_percentage": 3.0,
            "trailing_deviation": 1.0,
        })
        pos = self._short(sold_quote=100.0, sold_base=1.0)
        # Price 90 → +10% arms trailing, trough tracked at 90 (90 < 90*1.01 → hold)
        should, _ = await strategy.should_sell({}, pos, current_price=90.0)
        assert should is False
        # Price rises to 91.5 (> 90*1.01 = 90.9) while still +8.5% (above fee floor)
        # → adverse reversal past the deviation → trailing TP triggers.
        should, reason = await strategy.should_sell({}, pos, current_price=91.5)
        assert should is True
        assert "Trailing TP" in reason


class TestGetDcaReferencePrice:
    """E (sweep #4): a short's DCA reference price must fall back to the first short
    entry price, NEVER average_buy_price (which is 0 for shorts and would collapse
    every safety-order trigger to 0 → DCA firing at any price)."""

    @staticmethod
    def _entries(*prices):
        out = []
        for i, p in enumerate(prices):
            t = MagicMock()
            t.price = p
            t.timestamp = 1000 + i
            out.append(t)
        return out

    def test_long_uses_average_buy_price(self):
        """Happy path (long): reference is average_buy_price."""
        strategy = _make_strategy({"dca_target_reference": "average_price"})
        pos = _make_mock_position(avg_price=100.0, direction="long")
        assert strategy._get_dca_reference_price(pos, self._entries(100.0)) == 100.0

    def test_short_uses_short_average_sell_price(self):
        """Happy path (short): reference is short_average_sell_price when present."""
        strategy = _make_strategy({"dca_target_reference": "average_price"})
        pos = _make_mock_position(direction="short", avg_price=0.0)
        pos.short_average_sell_price = 200.0
        assert strategy._get_dca_reference_price(pos, self._entries(195.0)) == 200.0

    def test_short_falls_back_to_first_entry_not_zero(self):
        """Edge: short_average_sell_price falsy → first short entry price, not 0."""
        strategy = _make_strategy({"dca_target_reference": "average_price"})
        pos = _make_mock_position(direction="short", avg_price=0.0)
        pos.short_average_sell_price = None
        assert strategy._get_dca_reference_price(pos, self._entries(195.0, 198.0)) == 195.0

    def test_short_no_entries_no_avg_returns_zero(self):
        """Failure: no entries and no short avg → 0.0 (guarded downstream)."""
        strategy = _make_strategy({"dca_target_reference": "average_price"})
        pos = _make_mock_position(direction="short", avg_price=0.0)
        pos.short_average_sell_price = None
        assert strategy._get_dca_reference_price(pos, []) == 0.0
