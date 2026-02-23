"""
Tests for backend/app/conditions.py

Covers the ConditionEvaluator, Condition, ConditionGroup models,
and the _get_indicator_value helper across all indicator types.
"""

import pytest
from unittest.mock import MagicMock

from app.conditions import (
    ComparisonOperator,
    Condition,
    ConditionGroup,
    ConditionEvaluator,
    IndicatorType,
    LogicOperator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def evaluator():
    """Create a ConditionEvaluator with a mock indicator calculator."""
    mock_calc = MagicMock()
    return ConditionEvaluator(mock_calc)


# ---------------------------------------------------------------------------
# _get_indicator_value
# ---------------------------------------------------------------------------


class TestGetIndicatorValue:
    """Tests for ConditionEvaluator._get_indicator_value()"""

    def test_price_returns_price_key(self, evaluator):
        """Happy path: PRICE indicator looks up 'price' key."""
        indicators = {"price": 50000.0}
        result = evaluator._get_indicator_value(IndicatorType.PRICE, {}, indicators)
        assert result == 50000.0

    def test_rsi_default_period(self, evaluator):
        """Happy path: RSI with no params uses default period 14."""
        indicators = {"rsi_14": 35.0}
        result = evaluator._get_indicator_value(IndicatorType.RSI, {}, indicators)
        assert result == 35.0

    def test_rsi_custom_period(self, evaluator):
        """Happy path: RSI with custom period."""
        indicators = {"rsi_7": 65.0}
        result = evaluator._get_indicator_value(IndicatorType.RSI, {"period": 7}, indicators)
        assert result == 65.0

    def test_macd_default_params(self, evaluator):
        """Happy path: MACD with default fast/slow/signal."""
        indicators = {"macd_12_26_9": 0.5}
        result = evaluator._get_indicator_value(IndicatorType.MACD, {}, indicators)
        assert result == 0.5

    def test_macd_signal_default_params(self, evaluator):
        indicators = {"macd_signal_12_26_9": 0.3}
        result = evaluator._get_indicator_value(IndicatorType.MACD_SIGNAL, {}, indicators)
        assert result == 0.3

    def test_macd_histogram_default_params(self, evaluator):
        indicators = {"macd_histogram_12_26_9": 0.2}
        result = evaluator._get_indicator_value(IndicatorType.MACD_HISTOGRAM, {}, indicators)
        assert result == 0.2

    def test_sma_default_period(self, evaluator):
        indicators = {"sma_20": 100.0}
        result = evaluator._get_indicator_value(IndicatorType.SMA, {}, indicators)
        assert result == 100.0

    def test_ema_custom_period(self, evaluator):
        indicators = {"ema_50": 99.0}
        result = evaluator._get_indicator_value(IndicatorType.EMA, {"period": 50}, indicators)
        assert result == 99.0

    def test_bollinger_upper(self, evaluator):
        indicators = {"bb_upper_20_2": 110.0}
        result = evaluator._get_indicator_value(IndicatorType.BOLLINGER_UPPER, {}, indicators)
        assert result == 110.0

    def test_bollinger_middle(self, evaluator):
        indicators = {"bb_middle_20_2": 100.0}
        result = evaluator._get_indicator_value(IndicatorType.BOLLINGER_MIDDLE, {}, indicators)
        assert result == 100.0

    def test_bollinger_lower(self, evaluator):
        indicators = {"bb_lower_20_2": 90.0}
        result = evaluator._get_indicator_value(IndicatorType.BOLLINGER_LOWER, {}, indicators)
        assert result == 90.0

    def test_stochastic_k(self, evaluator):
        indicators = {"stoch_k_14_3": 75.0}
        result = evaluator._get_indicator_value(IndicatorType.STOCHASTIC_K, {}, indicators)
        assert result == 75.0

    def test_stochastic_d(self, evaluator):
        indicators = {"stoch_d_14_3": 72.0}
        result = evaluator._get_indicator_value(IndicatorType.STOCHASTIC_D, {}, indicators)
        assert result == 72.0

    def test_volume(self, evaluator):
        indicators = {"volume": 1234.5}
        result = evaluator._get_indicator_value(IndicatorType.VOLUME, {}, indicators)
        assert result == 1234.5

    def test_volume_rsi(self, evaluator):
        indicators = {"volume_rsi_14": 55.0}
        result = evaluator._get_indicator_value(IndicatorType.VOLUME_RSI, {}, indicators)
        assert result == 55.0

    def test_ai_buy(self, evaluator):
        indicators = {"ai_buy": 1}
        result = evaluator._get_indicator_value(IndicatorType.AI_BUY, {}, indicators)
        assert result == 1

    def test_ai_sell(self, evaluator):
        indicators = {"ai_sell": 0}
        result = evaluator._get_indicator_value(IndicatorType.AI_SELL, {}, indicators)
        assert result == 0

    def test_bull_flag(self, evaluator):
        indicators = {"bull_flag": 1}
        result = evaluator._get_indicator_value(IndicatorType.BULL_FLAG, {}, indicators)
        assert result == 1

    def test_missing_indicator_returns_none(self, evaluator):
        """Edge case: indicator key not in dict returns None."""
        result = evaluator._get_indicator_value(IndicatorType.RSI, {}, {})
        assert result is None


# ---------------------------------------------------------------------------
# evaluate_condition — simple comparisons
# ---------------------------------------------------------------------------


class TestEvaluateConditionSimple:
    """Tests for simple comparison operators (>, <, >=, <=, ==)."""

    def test_greater_than_true(self, evaluator):
        """Happy path: RSI(14) > 30 when RSI is 45."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.GREATER_THAN,
            value_type="static",
            static_value=30.0,
        )
        indicators = {"rsi_14": 45.0}
        assert evaluator.evaluate_condition(cond, indicators) is True

    def test_greater_than_false(self, evaluator):
        """Failure case: RSI(14) > 30 when RSI is 25."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.GREATER_THAN,
            value_type="static",
            static_value=30.0,
        )
        indicators = {"rsi_14": 25.0}
        assert evaluator.evaluate_condition(cond, indicators) is False

    def test_less_than_true(self, evaluator):
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.LESS_THAN,
            value_type="static",
            static_value=30.0,
        )
        indicators = {"rsi_14": 25.0}
        assert evaluator.evaluate_condition(cond, indicators) is True

    def test_less_than_false(self, evaluator):
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.LESS_THAN,
            value_type="static",
            static_value=30.0,
        )
        indicators = {"rsi_14": 35.0}
        assert evaluator.evaluate_condition(cond, indicators) is False

    def test_greater_equal_boundary(self, evaluator):
        """Edge case: exact boundary value for >=."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.GREATER_EQUAL,
            value_type="static",
            static_value=30.0,
        )
        indicators = {"rsi_14": 30.0}
        assert evaluator.evaluate_condition(cond, indicators) is True

    def test_less_equal_boundary(self, evaluator):
        """Edge case: exact boundary value for <=."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.LESS_EQUAL,
            value_type="static",
            static_value=70.0,
        )
        indicators = {"rsi_14": 70.0}
        assert evaluator.evaluate_condition(cond, indicators) is True

    def test_equal_true(self, evaluator):
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.EQUAL,
            value_type="static",
            static_value=50.0,
        )
        indicators = {"rsi_14": 50.0}
        assert evaluator.evaluate_condition(cond, indicators) is True

    def test_equal_float_precision(self, evaluator):
        """Edge case: float equality uses epsilon comparison."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.EQUAL,
            value_type="static",
            static_value=50.0,
        )
        # Tiny difference should still be equal (within 1e-9)
        indicators = {"rsi_14": 50.0 + 1e-10}
        assert evaluator.evaluate_condition(cond, indicators) is True

    def test_equal_float_not_equal(self, evaluator):
        """Failure: values differ by more than epsilon."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.EQUAL,
            value_type="static",
            static_value=50.0,
        )
        indicators = {"rsi_14": 50.001}
        assert evaluator.evaluate_condition(cond, indicators) is False

    def test_missing_indicator_returns_false(self, evaluator):
        """Failure: indicator not present in dict => False."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.GREATER_THAN,
            value_type="static",
            static_value=30.0,
        )
        assert evaluator.evaluate_condition(cond, {}) is False

    def test_static_value_none_returns_false(self, evaluator):
        """Failure: static_value is None => compare_value is None => False."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.GREATER_THAN,
            value_type="static",
            static_value=None,
        )
        indicators = {"rsi_14": 45.0}
        assert evaluator.evaluate_condition(cond, indicators) is False


# ---------------------------------------------------------------------------
# evaluate_condition — indicator vs indicator
# ---------------------------------------------------------------------------


class TestEvaluateConditionIndicatorComparison:
    """Tests for indicator vs indicator comparisons."""

    def test_macd_greater_than_signal(self, evaluator):
        """Happy path: MACD > MACD_SIGNAL."""
        cond = Condition(
            indicator=IndicatorType.MACD,
            operator=ComparisonOperator.GREATER_THAN,
            value_type="indicator",
            compare_indicator=IndicatorType.MACD_SIGNAL,
        )
        indicators = {"macd_12_26_9": 0.5, "macd_signal_12_26_9": 0.3}
        assert evaluator.evaluate_condition(cond, indicators) is True

    def test_price_less_than_bollinger_lower(self, evaluator):
        """Happy path: Price < Bollinger Lower."""
        cond = Condition(
            indicator=IndicatorType.PRICE,
            operator=ComparisonOperator.LESS_THAN,
            value_type="indicator",
            compare_indicator=IndicatorType.BOLLINGER_LOWER,
        )
        indicators = {"price": 89.0, "bb_lower_20_2": 90.0}
        assert evaluator.evaluate_condition(cond, indicators) is True

    def test_compare_indicator_missing_returns_false(self, evaluator):
        """Failure: compare indicator not in dict => False."""
        cond = Condition(
            indicator=IndicatorType.MACD,
            operator=ComparisonOperator.GREATER_THAN,
            value_type="indicator",
            compare_indicator=IndicatorType.MACD_SIGNAL,
        )
        indicators = {"macd_12_26_9": 0.5}  # signal missing
        assert evaluator.evaluate_condition(cond, indicators) is False


# ---------------------------------------------------------------------------
# evaluate_condition — crossing operators
# ---------------------------------------------------------------------------


class TestEvaluateConditionCrossing:
    """Tests for crossing_above and crossing_below operators."""

    def test_crossing_above_static(self, evaluator):
        """Happy path: RSI crosses above 30 (was 28, now 32)."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.CROSSING_ABOVE,
            value_type="static",
            static_value=30.0,
        )
        current = {"rsi_14": 32.0}
        previous = {"rsi_14": 28.0}
        assert evaluator.evaluate_condition(cond, current, previous) is True

    def test_crossing_above_not_crossed(self, evaluator):
        """Failure: was already above, still above => no crossing."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.CROSSING_ABOVE,
            value_type="static",
            static_value=30.0,
        )
        current = {"rsi_14": 35.0}
        previous = {"rsi_14": 32.0}
        assert evaluator.evaluate_condition(cond, current, previous) is False

    def test_crossing_below_static(self, evaluator):
        """Happy path: RSI crosses below 70 (was 72, now 68)."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.CROSSING_BELOW,
            value_type="static",
            static_value=70.0,
        )
        current = {"rsi_14": 68.0}
        previous = {"rsi_14": 72.0}
        assert evaluator.evaluate_condition(cond, current, previous) is True

    def test_crossing_below_not_crossed(self, evaluator):
        """Failure: was already below, still below => no crossing."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.CROSSING_BELOW,
            value_type="static",
            static_value=70.0,
        )
        current = {"rsi_14": 65.0}
        previous = {"rsi_14": 68.0}
        assert evaluator.evaluate_condition(cond, current, previous) is False

    def test_crossing_above_indicator_vs_indicator(self, evaluator):
        """Happy path: MACD crossing above signal line."""
        cond = Condition(
            indicator=IndicatorType.MACD,
            operator=ComparisonOperator.CROSSING_ABOVE,
            value_type="indicator",
            compare_indicator=IndicatorType.MACD_SIGNAL,
        )
        current = {"macd_12_26_9": 0.5, "macd_signal_12_26_9": 0.3}
        previous = {"macd_12_26_9": 0.2, "macd_signal_12_26_9": 0.3}
        assert evaluator.evaluate_condition(cond, current, previous) is True

    def test_crossing_no_previous_indicators_returns_false(self, evaluator):
        """Failure: crossing requires previous indicators."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.CROSSING_ABOVE,
            value_type="static",
            static_value=30.0,
        )
        current = {"rsi_14": 32.0}
        assert evaluator.evaluate_condition(cond, current, None) is False

    def test_crossing_noise_filtered(self, evaluator):
        """Edge case: both values within noise epsilon => no crossing detected."""
        cond = Condition(
            indicator=IndicatorType.MACD_HISTOGRAM,
            operator=ComparisonOperator.CROSSING_ABOVE,
            value_type="static",
            static_value=0.0,
        )
        # Both values are within 1e-7 of the threshold
        current = {"macd_histogram_12_26_9": 1e-8}
        previous = {"macd_histogram_12_26_9": -1e-8}
        assert evaluator.evaluate_condition(cond, current, previous) is False

    def test_crossing_above_meaningful_values(self, evaluator):
        """Happy path: crossing detected when at least one side is meaningful."""
        cond = Condition(
            indicator=IndicatorType.MACD_HISTOGRAM,
            operator=ComparisonOperator.CROSSING_ABOVE,
            value_type="static",
            static_value=0.0,
        )
        current = {"macd_histogram_12_26_9": 0.5}
        previous = {"macd_histogram_12_26_9": -0.3}
        assert evaluator.evaluate_condition(cond, current, previous) is True

    def test_crossing_previous_value_missing_returns_false(self, evaluator):
        """Failure: previous indicator value is None."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.CROSSING_ABOVE,
            value_type="static",
            static_value=30.0,
        )
        current = {"rsi_14": 32.0}
        previous = {}  # RSI not in previous
        assert evaluator.evaluate_condition(cond, current, previous) is False


# ---------------------------------------------------------------------------
# evaluate_condition — increasing / decreasing operators
# ---------------------------------------------------------------------------


class TestEvaluateConditionIncreasingDecreasing:
    """Tests for INCREASING and DECREASING operators."""

    def test_increasing_simple(self, evaluator):
        """Happy path: RSI increasing (no min % threshold)."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.INCREASING,
            value_type="static",
            static_value=0,  # no minimum %
        )
        current = {"rsi_14": 45.0}
        previous = {"rsi_14": 40.0}
        assert evaluator.evaluate_condition(cond, current, previous) is True

    def test_increasing_fails_when_decreasing(self, evaluator):
        """Failure: value decreased, not increasing."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.INCREASING,
            value_type="static",
            static_value=0,
        )
        current = {"rsi_14": 35.0}
        previous = {"rsi_14": 40.0}
        assert evaluator.evaluate_condition(cond, current, previous) is False

    def test_decreasing_simple(self, evaluator):
        """Happy path: RSI decreasing."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.DECREASING,
            value_type="static",
            static_value=0,
        )
        current = {"rsi_14": 35.0}
        previous = {"rsi_14": 40.0}
        assert evaluator.evaluate_condition(cond, current, previous) is True

    def test_increasing_with_min_pct_threshold_met(self, evaluator):
        """Happy path: increasing by at least 10%."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.INCREASING,
            value_type="static",
            static_value=10.0,  # minimum 10% increase
        )
        current = {"rsi_14": 55.0}
        previous = {"rsi_14": 50.0}
        # pct_change = (55-50)/50 * 100 = 10%
        assert evaluator.evaluate_condition(cond, current, previous) is True

    def test_increasing_with_min_pct_threshold_not_met(self, evaluator):
        """Failure: increase is less than minimum threshold."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.INCREASING,
            value_type="static",
            static_value=20.0,  # minimum 20% increase
        )
        current = {"rsi_14": 52.0}
        previous = {"rsi_14": 50.0}
        # pct_change = (52-50)/50 * 100 = 4%
        assert evaluator.evaluate_condition(cond, current, previous) is False

    def test_decreasing_with_min_pct_threshold_met(self, evaluator):
        """Happy path: decreasing by at least 10%."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.DECREASING,
            value_type="static",
            static_value=10.0,
        )
        current = {"rsi_14": 45.0}
        previous = {"rsi_14": 50.0}
        # pct_change = (45-50)/50 * 100 = -10%
        assert evaluator.evaluate_condition(cond, current, previous) is True

    def test_increasing_no_previous_returns_false(self, evaluator):
        """Failure: no previous indicators for direction check."""
        cond = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.INCREASING,
            value_type="static",
            static_value=0,
        )
        current = {"rsi_14": 45.0}
        assert evaluator.evaluate_condition(cond, current, None) is False

    def test_increasing_previous_value_zero(self, evaluator):
        """Edge case: previous value is 0, avoid division by zero."""
        cond = Condition(
            indicator=IndicatorType.MACD_HISTOGRAM,
            operator=ComparisonOperator.INCREASING,
            value_type="static",
            static_value=0,
        )
        current = {"macd_histogram_12_26_9": 0.5}
        previous = {"macd_histogram_12_26_9": 0.0}
        # When previous is 0 and increasing, returns current_value > 0
        assert evaluator.evaluate_condition(cond, current, previous) is True

    def test_decreasing_previous_value_zero(self, evaluator):
        """Edge case: previous value is 0, decreasing checks current < 0."""
        cond = Condition(
            indicator=IndicatorType.MACD_HISTOGRAM,
            operator=ComparisonOperator.DECREASING,
            value_type="static",
            static_value=0,
        )
        current = {"macd_histogram_12_26_9": -0.5}
        previous = {"macd_histogram_12_26_9": 0.0}
        assert evaluator.evaluate_condition(cond, current, previous) is True


# ---------------------------------------------------------------------------
# evaluate_group
# ---------------------------------------------------------------------------


class TestEvaluateGroup:
    """Tests for ConditionEvaluator.evaluate_group()"""

    def test_and_all_true(self, evaluator):
        """Happy path: AND group with all conditions true."""
        cond1 = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.LESS_THAN,
            value_type="static",
            static_value=30.0,
        )
        cond2 = Condition(
            indicator=IndicatorType.PRICE,
            operator=ComparisonOperator.GREATER_THAN,
            value_type="static",
            static_value=100.0,
        )
        group = ConditionGroup(logic=LogicOperator.AND, conditions=[cond1, cond2])
        indicators = {"rsi_14": 25.0, "price": 150.0}
        assert evaluator.evaluate_group(group, indicators) is True

    def test_and_one_false(self, evaluator):
        """Failure: AND group fails if any condition is false."""
        cond1 = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.LESS_THAN,
            value_type="static",
            static_value=30.0,
        )
        cond2 = Condition(
            indicator=IndicatorType.PRICE,
            operator=ComparisonOperator.GREATER_THAN,
            value_type="static",
            static_value=200.0,
        )
        group = ConditionGroup(logic=LogicOperator.AND, conditions=[cond1, cond2])
        indicators = {"rsi_14": 25.0, "price": 150.0}
        assert evaluator.evaluate_group(group, indicators) is False

    def test_or_one_true(self, evaluator):
        """Happy path: OR group passes if any condition is true."""
        cond1 = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.LESS_THAN,
            value_type="static",
            static_value=30.0,
        )
        cond2 = Condition(
            indicator=IndicatorType.PRICE,
            operator=ComparisonOperator.GREATER_THAN,
            value_type="static",
            static_value=200.0,
        )
        group = ConditionGroup(logic=LogicOperator.OR, conditions=[cond1, cond2])
        indicators = {"rsi_14": 25.0, "price": 150.0}
        assert evaluator.evaluate_group(group, indicators) is True

    def test_or_all_false(self, evaluator):
        """Failure: OR group fails if all conditions are false."""
        cond1 = Condition(
            indicator=IndicatorType.RSI,
            operator=ComparisonOperator.LESS_THAN,
            value_type="static",
            static_value=20.0,
        )
        cond2 = Condition(
            indicator=IndicatorType.PRICE,
            operator=ComparisonOperator.GREATER_THAN,
            value_type="static",
            static_value=200.0,
        )
        group = ConditionGroup(logic=LogicOperator.OR, conditions=[cond1, cond2])
        indicators = {"rsi_14": 25.0, "price": 150.0}
        assert evaluator.evaluate_group(group, indicators) is False

    def test_empty_group_returns_false(self, evaluator):
        """Edge case: empty group returns False."""
        group = ConditionGroup(logic=LogicOperator.AND, conditions=[], sub_groups=[])
        assert evaluator.evaluate_group(group, {}) is False

    def test_nested_sub_groups(self, evaluator):
        """Happy path: nested sub-groups with mixed logic."""
        # Inner group: RSI < 30 AND Price > 100 (both true)
        inner = ConditionGroup(
            logic=LogicOperator.AND,
            conditions=[
                Condition(
                    indicator=IndicatorType.RSI,
                    operator=ComparisonOperator.LESS_THAN,
                    value_type="static",
                    static_value=30.0,
                ),
                Condition(
                    indicator=IndicatorType.PRICE,
                    operator=ComparisonOperator.GREATER_THAN,
                    value_type="static",
                    static_value=100.0,
                ),
            ],
        )
        # Outer group: (inner) OR (volume > 9999) -- inner is true
        outer = ConditionGroup(
            logic=LogicOperator.OR,
            conditions=[
                Condition(
                    indicator=IndicatorType.VOLUME,
                    operator=ComparisonOperator.GREATER_THAN,
                    value_type="static",
                    static_value=9999.0,
                ),
            ],
            sub_groups=[inner],
        )
        indicators = {"rsi_14": 25.0, "price": 150.0, "volume": 500.0}
        assert evaluator.evaluate_group(outer, indicators) is True
