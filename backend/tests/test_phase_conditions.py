"""
Tests for backend/app/phase_conditions.py

Covers the PhaseConditionEvaluator class including:
- evaluate_expression (both grouped and legacy formats)
- _evaluate_grouped_expression
- _evaluate_group
- evaluate_phase_conditions (legacy flat list)
- _evaluate_single_condition (comparisons, crossing, increasing/decreasing)
- _get_indicator_value (all indicator types)
- _get_previous_indicator_value (all indicator types)
- get_required_indicators_from_expression
- get_required_indicators
- Bidirectional direction filtering
- Negate modifier
- capture_details mode
"""

import pytest

from app.phase_conditions import PhaseConditionEvaluator
from app.indicator_calculator import IndicatorCalculator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def calculator():
    """Real IndicatorCalculator (PhaseConditionEvaluator uses it as a dependency)."""
    return IndicatorCalculator()


@pytest.fixture
def evaluator(calculator):
    """PhaseConditionEvaluator with no position direction."""
    return PhaseConditionEvaluator(calculator)


@pytest.fixture
def long_evaluator(calculator):
    """PhaseConditionEvaluator for a long position."""
    return PhaseConditionEvaluator(calculator, position_direction="long")


@pytest.fixture
def short_evaluator(calculator):
    """PhaseConditionEvaluator for a short position."""
    return PhaseConditionEvaluator(calculator, position_direction="short")


# ---------------------------------------------------------------------------
# evaluate_expression — dispatch
# ---------------------------------------------------------------------------


class TestEvaluateExpression:
    """Tests for evaluate_expression() dispatch logic."""

    def test_empty_expression_returns_false(self, evaluator):
        """Edge case: None expression returns False."""
        assert evaluator.evaluate_expression(None, {}) is False

    def test_empty_expression_capture_details_returns_tuple(self, evaluator):
        """Edge case: None expression with capture_details returns (False, [])."""
        result = evaluator.evaluate_expression(None, {}, capture_details=True)
        assert result == (False, [])

    def test_empty_list_expression_returns_false(self, evaluator):
        """Edge case: empty list returns False."""
        assert evaluator.evaluate_expression([], {}) is False

    def test_empty_dict_expression_returns_false(self, evaluator):
        """Edge case: empty dict without 'groups' key returns False."""
        assert evaluator.evaluate_expression({}, {}) is False

    def test_unknown_format_returns_false(self, evaluator):
        """Failure: non-dict, non-list format returns False."""
        assert evaluator.evaluate_expression("invalid", {}) is False

    def test_unknown_format_capture_details(self, evaluator):
        """Failure: unknown format with capture_details returns (False, [])."""
        result = evaluator.evaluate_expression("invalid", {}, capture_details=True)
        assert result == (False, [])

    def test_dispatches_to_grouped_expression(self, evaluator):
        """Happy path: dict with 'groups' key dispatches to grouped evaluation."""
        expression = {
            "groups": [
                {
                    "id": "g1",
                    "conditions": [
                        {"type": "rsi", "operator": "greater_than", "value": 30, "timeframe": "FIVE_MINUTE"}
                    ],
                    "logic": "and"
                }
            ],
            "groupLogic": "and"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 45.0}
        assert evaluator.evaluate_expression(expression, indicators) is True

    def test_dispatches_to_legacy_format(self, evaluator):
        """Happy path: list dispatches to legacy evaluation."""
        conditions = [
            {"type": "rsi", "operator": "greater_than", "value": 30, "timeframe": "FIVE_MINUTE"}
        ]
        indicators = {"FIVE_MINUTE_rsi_14": 45.0}
        assert evaluator.evaluate_expression(conditions, indicators, legacy_logic="and") is True


# ---------------------------------------------------------------------------
# _evaluate_grouped_expression
# ---------------------------------------------------------------------------


class TestEvaluateGroupedExpression:
    """Tests for _evaluate_grouped_expression()."""

    def test_empty_groups_returns_false(self, evaluator):
        """Edge case: expression with empty groups list returns False."""
        expression = {"groups": [], "groupLogic": "and"}
        assert evaluator.evaluate_expression(expression, {}) is False

    def test_single_group_and_logic_true(self, evaluator):
        """Happy path: single group with one true condition."""
        expression = {
            "groups": [
                {
                    "id": "g1",
                    "conditions": [
                        {"type": "rsi", "operator": "less_than", "value": 50, "timeframe": "FIVE_MINUTE"}
                    ],
                    "logic": "and"
                }
            ],
            "groupLogic": "and"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0}
        assert evaluator.evaluate_expression(expression, indicators) is True

    def test_two_groups_and_logic_both_true(self, evaluator):
        """Happy path: AND of two groups, both true."""
        expression = {
            "groups": [
                {
                    "id": "g1",
                    "conditions": [
                        {"type": "rsi", "operator": "less_than", "value": 50, "timeframe": "FIVE_MINUTE"}
                    ],
                    "logic": "and"
                },
                {
                    "id": "g2",
                    "conditions": [
                        {"type": "volume", "operator": "greater_than", "value": 100, "timeframe": "FIVE_MINUTE"}
                    ],
                    "logic": "and"
                }
            ],
            "groupLogic": "and"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0, "FIVE_MINUTE_volume": 500.0}
        assert evaluator.evaluate_expression(expression, indicators) is True

    def test_two_groups_and_logic_one_false(self, evaluator):
        """Failure: AND of two groups, one false."""
        expression = {
            "groups": [
                {
                    "id": "g1",
                    "conditions": [
                        {"type": "rsi", "operator": "less_than", "value": 50, "timeframe": "FIVE_MINUTE"}
                    ],
                    "logic": "and"
                },
                {
                    "id": "g2",
                    "conditions": [
                        {"type": "volume", "operator": "greater_than", "value": 1000, "timeframe": "FIVE_MINUTE"}
                    ],
                    "logic": "and"
                }
            ],
            "groupLogic": "and"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0, "FIVE_MINUTE_volume": 500.0}
        assert evaluator.evaluate_expression(expression, indicators) is False

    def test_two_groups_or_logic_one_true(self, evaluator):
        """Happy path: OR of two groups, one true is sufficient."""
        expression = {
            "groups": [
                {
                    "id": "g1",
                    "conditions": [
                        {"type": "rsi", "operator": "less_than", "value": 20, "timeframe": "FIVE_MINUTE"}
                    ],
                    "logic": "and"
                },
                {
                    "id": "g2",
                    "conditions": [
                        {"type": "volume", "operator": "greater_than", "value": 100, "timeframe": "FIVE_MINUTE"}
                    ],
                    "logic": "and"
                }
            ],
            "groupLogic": "or"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0, "FIVE_MINUTE_volume": 500.0}
        assert evaluator.evaluate_expression(expression, indicators) is True

    def test_grouped_expression_capture_details(self, evaluator):
        """Happy path: capture_details returns (bool, list) tuple."""
        expression = {
            "groups": [
                {
                    "id": "g1",
                    "conditions": [
                        {"type": "rsi", "operator": "greater_than", "value": 30, "timeframe": "FIVE_MINUTE"}
                    ],
                    "logic": "and"
                }
            ],
            "groupLogic": "and"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 45.0}
        result, details = evaluator.evaluate_expression(expression, indicators, capture_details=True)
        assert result is True
        assert len(details) == 1
        assert details[0]["type"] == "rsi"
        assert details[0]["result"] is True


# ---------------------------------------------------------------------------
# _evaluate_group
# ---------------------------------------------------------------------------


class TestEvaluateGroup:
    """Tests for _evaluate_group()."""

    def test_empty_conditions_returns_false(self, evaluator):
        """Edge case: group with no conditions returns False."""
        group = {"id": "g1", "conditions": [], "logic": "and"}
        result = evaluator._evaluate_group(group, {}, None)
        assert result is False

    def test_and_logic_all_true(self, evaluator):
        """Happy path: AND logic, all conditions true."""
        group = {
            "conditions": [
                {"type": "rsi", "operator": "less_than", "value": 50, "timeframe": "FIVE_MINUTE"},
                {"type": "volume", "operator": "greater_than", "value": 10, "timeframe": "FIVE_MINUTE"},
            ],
            "logic": "and"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0, "FIVE_MINUTE_volume": 100.0}
        assert evaluator._evaluate_group(group, indicators, None) is True

    def test_and_logic_one_false(self, evaluator):
        """Failure: AND logic, one condition false."""
        group = {
            "conditions": [
                {"type": "rsi", "operator": "less_than", "value": 50, "timeframe": "FIVE_MINUTE"},
                {"type": "volume", "operator": "greater_than", "value": 1000, "timeframe": "FIVE_MINUTE"},
            ],
            "logic": "and"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0, "FIVE_MINUTE_volume": 100.0}
        assert evaluator._evaluate_group(group, indicators, None) is False

    def test_or_logic_one_true(self, evaluator):
        """Happy path: OR logic, one condition true is sufficient."""
        group = {
            "conditions": [
                {"type": "rsi", "operator": "less_than", "value": 20, "timeframe": "FIVE_MINUTE"},
                {"type": "volume", "operator": "greater_than", "value": 10, "timeframe": "FIVE_MINUTE"},
            ],
            "logic": "or"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0, "FIVE_MINUTE_volume": 100.0}
        assert evaluator._evaluate_group(group, indicators, None) is True

    def test_negate_modifier_inverts_result(self, evaluator):
        """Happy path: negate modifier inverts a true result to false."""
        group = {
            "conditions": [
                {
                    "type": "rsi", "operator": "less_than", "value": 50,
                    "timeframe": "FIVE_MINUTE", "negate": True
                }
            ],
            "logic": "and"
        }
        # RSI 30 < 50 is true, negated -> false
        indicators = {"FIVE_MINUTE_rsi_14": 30.0}
        assert evaluator._evaluate_group(group, indicators, None) is False

    def test_negate_modifier_with_capture_details(self, evaluator):
        """Edge case: negate modifier sets negated flag in details."""
        group = {
            "conditions": [
                {
                    "type": "rsi", "operator": "less_than", "value": 50,
                    "timeframe": "FIVE_MINUTE", "negate": True
                }
            ],
            "logic": "and"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0}
        result, details = evaluator._evaluate_group(group, indicators, None, capture_details=True)
        assert result is False
        assert details[0]["negated"] is True
        assert details[0]["result"] is False


# ---------------------------------------------------------------------------
# evaluate_phase_conditions (legacy flat list)
# ---------------------------------------------------------------------------


class TestEvaluatePhaseConditions:
    """Tests for evaluate_phase_conditions() legacy format."""

    def test_empty_conditions_returns_false(self, evaluator):
        """Edge case: empty list returns False."""
        assert evaluator.evaluate_phase_conditions([], "and", {}) is False

    def test_and_logic_happy_path(self, evaluator):
        """Happy path: AND logic with all conditions met."""
        conditions = [
            {"type": "rsi", "operator": "less_than", "value": 50, "timeframe": "FIVE_MINUTE"},
            {"type": "volume", "operator": "greater_than", "value": 10, "timeframe": "FIVE_MINUTE"},
        ]
        indicators = {"FIVE_MINUTE_rsi_14": 30.0, "FIVE_MINUTE_volume": 100.0}
        assert evaluator.evaluate_phase_conditions(conditions, "and", indicators) is True

    def test_or_logic_happy_path(self, evaluator):
        """Happy path: OR logic with one condition met."""
        conditions = [
            {"type": "rsi", "operator": "less_than", "value": 20, "timeframe": "FIVE_MINUTE"},
            {"type": "volume", "operator": "greater_than", "value": 10, "timeframe": "FIVE_MINUTE"},
        ]
        indicators = {"FIVE_MINUTE_rsi_14": 30.0, "FIVE_MINUTE_volume": 100.0}
        assert evaluator.evaluate_phase_conditions(conditions, "or", indicators) is True

    def test_capture_details_returns_tuple(self, evaluator):
        """Happy path: capture_details returns (bool, list)."""
        conditions = [
            {"type": "rsi", "operator": "greater_than", "value": 30, "timeframe": "FIVE_MINUTE"},
        ]
        indicators = {"FIVE_MINUTE_rsi_14": 45.0}
        result, details = evaluator.evaluate_phase_conditions(
            conditions, "and", indicators, capture_details=True
        )
        assert result is True
        assert len(details) == 1
        assert details[0]["actual_value"] == 45.0

    def test_negate_in_legacy_format(self, evaluator):
        """Edge case: negate works in legacy format too."""
        conditions = [
            {"type": "rsi", "operator": "less_than", "value": 50, "timeframe": "FIVE_MINUTE", "negate": True},
        ]
        indicators = {"FIVE_MINUTE_rsi_14": 30.0}
        # 30 < 50 is true, negated -> false
        assert evaluator.evaluate_phase_conditions(conditions, "and", indicators) is False


# ---------------------------------------------------------------------------
# _evaluate_single_condition — simple comparisons
# ---------------------------------------------------------------------------


class TestEvaluateSingleConditionComparisons:
    """Tests for simple comparison operators in _evaluate_single_condition()."""

    def test_greater_than_true(self, evaluator):
        """Happy path: value > threshold."""
        condition = {"type": "rsi", "operator": "greater_than", "value": 30, "timeframe": "FIVE_MINUTE"}
        assert evaluator._evaluate_single_condition(condition, {"FIVE_MINUTE_rsi_14": 45.0}, None) is True

    def test_greater_than_false(self, evaluator):
        """Failure: value not > threshold."""
        condition = {"type": "rsi", "operator": "greater_than", "value": 50, "timeframe": "FIVE_MINUTE"}
        assert evaluator._evaluate_single_condition(condition, {"FIVE_MINUTE_rsi_14": 45.0}, None) is False

    def test_less_than_true(self, evaluator):
        condition = {"type": "rsi", "operator": "less_than", "value": 50, "timeframe": "FIVE_MINUTE"}
        assert evaluator._evaluate_single_condition(condition, {"FIVE_MINUTE_rsi_14": 30.0}, None) is True

    def test_less_than_false(self, evaluator):
        condition = {"type": "rsi", "operator": "less_than", "value": 20, "timeframe": "FIVE_MINUTE"}
        assert evaluator._evaluate_single_condition(condition, {"FIVE_MINUTE_rsi_14": 30.0}, None) is False

    def test_greater_equal_boundary(self, evaluator):
        """Edge case: exact boundary for >=."""
        condition = {"type": "rsi", "operator": "greater_equal", "value": 30, "timeframe": "FIVE_MINUTE"}
        assert evaluator._evaluate_single_condition(condition, {"FIVE_MINUTE_rsi_14": 30.0}, None) is True

    def test_less_equal_boundary(self, evaluator):
        """Edge case: exact boundary for <=."""
        condition = {"type": "rsi", "operator": "less_equal", "value": 30, "timeframe": "FIVE_MINUTE"}
        assert evaluator._evaluate_single_condition(condition, {"FIVE_MINUTE_rsi_14": 30.0}, None) is True

    def test_equal_true(self, evaluator):
        condition = {"type": "rsi", "operator": "equal", "value": 50, "timeframe": "FIVE_MINUTE"}
        assert evaluator._evaluate_single_condition(condition, {"FIVE_MINUTE_rsi_14": 50.0}, None) is True

    def test_not_equal_true(self, evaluator):
        condition = {"type": "rsi", "operator": "not_equal", "value": 50, "timeframe": "FIVE_MINUTE"}
        assert evaluator._evaluate_single_condition(condition, {"FIVE_MINUTE_rsi_14": 45.0}, None) is True

    def test_indicator_value_none_returns_false(self, evaluator):
        """Failure: indicator value is None (missing from dict)."""
        condition = {"type": "rsi", "operator": "greater_than", "value": 30, "timeframe": "FIVE_MINUTE"}
        assert evaluator._evaluate_single_condition(condition, {}, None) is False

    def test_indicator_value_none_with_capture_details(self, evaluator):
        """Failure: capture_details reports error for missing indicator."""
        condition = {"type": "rsi", "operator": "greater_than", "value": 30, "timeframe": "FIVE_MINUTE"}
        result, detail = evaluator._evaluate_single_condition(condition, {}, None, capture_details=True)
        assert result is False
        assert "error" in detail
        assert "None" in detail["error"]


# ---------------------------------------------------------------------------
# _evaluate_single_condition — crossing operators
# ---------------------------------------------------------------------------


class TestEvaluateSingleConditionCrossing:
    """Tests for crossing_above and crossing_below operators."""

    def test_crossing_above_using_prev_keys(self, evaluator):
        """Happy path: crossing above using prev_ prefix keys in current_indicators."""
        condition = {"type": "rsi", "operator": "crossing_above", "value": 30, "timeframe": "FIVE_MINUTE"}
        indicators = {
            "FIVE_MINUTE_rsi_14": 35.0,
            "prev_FIVE_MINUTE_rsi_14": 25.0,
        }
        assert evaluator._evaluate_single_condition(condition, indicators, None) is True

    def test_crossing_above_no_crossing(self, evaluator):
        """Failure: was already above, no crossing."""
        condition = {"type": "rsi", "operator": "crossing_above", "value": 30, "timeframe": "FIVE_MINUTE"}
        indicators = {
            "FIVE_MINUTE_rsi_14": 35.0,
            "prev_FIVE_MINUTE_rsi_14": 32.0,
        }
        assert evaluator._evaluate_single_condition(condition, indicators, None) is False

    def test_crossing_below_happy_path(self, evaluator):
        """Happy path: crossing below threshold."""
        condition = {"type": "rsi", "operator": "crossing_below", "value": 70, "timeframe": "FIVE_MINUTE"}
        indicators = {
            "FIVE_MINUTE_rsi_14": 65.0,
            "prev_FIVE_MINUTE_rsi_14": 75.0,
        }
        assert evaluator._evaluate_single_condition(condition, indicators, None) is True

    def test_crossing_below_no_crossing(self, evaluator):
        """Failure: was already below, no crossing."""
        condition = {"type": "rsi", "operator": "crossing_below", "value": 70, "timeframe": "FIVE_MINUTE"}
        indicators = {
            "FIVE_MINUTE_rsi_14": 65.0,
            "prev_FIVE_MINUTE_rsi_14": 68.0,
        }
        assert evaluator._evaluate_single_condition(condition, indicators, None) is False

    def test_crossing_fallback_to_previous_indicators(self, evaluator):
        """Happy path: falls back to previous_indicators dict when no prev_ keys."""
        condition = {"type": "rsi", "operator": "crossing_above", "value": 30, "timeframe": "FIVE_MINUTE"}
        current = {"FIVE_MINUTE_rsi_14": 35.0}
        previous = {"FIVE_MINUTE_rsi_14": 25.0}
        assert evaluator._evaluate_single_condition(condition, current, previous) is True

    def test_crossing_no_previous_returns_false(self, evaluator):
        """Failure: no previous value at all."""
        condition = {"type": "rsi", "operator": "crossing_above", "value": 30, "timeframe": "FIVE_MINUTE"}
        current = {"FIVE_MINUTE_rsi_14": 35.0}
        assert evaluator._evaluate_single_condition(condition, current, None) is False

    def test_crossing_noise_filtered(self, evaluator):
        """Edge case: both values within noise epsilon - crossing filtered out."""
        condition = {"type": "macd", "operator": "crossing_above", "value": 0,
                     "timeframe": "FIVE_MINUTE", "fast_period": 12, "slow_period": 26, "signal_period": 9}
        indicators = {
            "FIVE_MINUTE_macd_histogram_12_26_9": 1e-8,
            "prev_FIVE_MINUTE_macd_histogram_12_26_9": -1e-8,
        }
        assert evaluator._evaluate_single_condition(condition, indicators, None) is False

    def test_crossing_meaningful_magnitude(self, evaluator):
        """Happy path: crossing detected when at least one side is meaningful."""
        condition = {"type": "rsi", "operator": "crossing_above", "value": 30, "timeframe": "FIVE_MINUTE"}
        indicators = {
            "FIVE_MINUTE_rsi_14": 35.0,
            "prev_FIVE_MINUTE_rsi_14": 25.0,
        }
        assert evaluator._evaluate_single_condition(condition, indicators, None) is True

    def test_crossing_with_capture_details(self, evaluator):
        """Happy path: capture_details includes previous_value."""
        condition = {"type": "rsi", "operator": "crossing_above", "value": 30, "timeframe": "FIVE_MINUTE"}
        indicators = {
            "FIVE_MINUTE_rsi_14": 35.0,
            "prev_FIVE_MINUTE_rsi_14": 25.0,
        }
        result, detail = evaluator._evaluate_single_condition(
            condition, indicators, None, capture_details=True
        )
        assert result is True
        assert detail["previous_value"] == 25.0
        assert detail["actual_value"] == 35.0

    def test_crossing_below_cycle_based_detection(self, evaluator):
        """
        Cycle-based crossing detection: candle-based prev already dropped below threshold
        but check-cycle prev was still above — crossing should be detected.

        This matches the real-world scenario where BB% drops from 90.08 to 80.84 in
        two candle periods. The candle-based prev shows 83.83 (< 90) so candle-based
        misses the crossing, but the cycle-based prev was 90.08 (>= 90) from the
        last bot check.
        """
        condition = {"type": "rsi", "operator": "crossing_below", "value": 90, "timeframe": "FIVE_MINUTE"}
        # Candle-based: both current and prev are already below 90
        current = {
            "FIVE_MINUTE_rsi_14": 80.84,
            "prev_FIVE_MINUTE_rsi_14": 83.83,
        }
        # Cycle-based: previous check saw value above 90
        previous = {"FIVE_MINUTE_rsi_14": 90.08}
        assert evaluator._evaluate_single_condition(condition, current, previous) is True

    def test_crossing_above_cycle_based_detection(self, evaluator):
        """
        Cycle-based crossing detection for crossing_above: candle-based prev already
        rose above threshold but check-cycle prev was still below.
        """
        condition = {"type": "rsi", "operator": "crossing_above", "value": 30, "timeframe": "FIVE_MINUTE"}
        # Candle-based: both current and prev are already above 30
        current = {
            "FIVE_MINUTE_rsi_14": 40.0,
            "prev_FIVE_MINUTE_rsi_14": 35.0,
        }
        # Cycle-based: previous check saw value below 30
        previous = {"FIVE_MINUTE_rsi_14": 28.0}
        assert evaluator._evaluate_single_condition(condition, current, previous) is True

    def test_crossing_below_candle_based_still_works(self, evaluator):
        """Candle-based crossing still works when cycle-based would also trigger."""
        condition = {"type": "rsi", "operator": "crossing_below", "value": 70, "timeframe": "FIVE_MINUTE"}
        current = {
            "FIVE_MINUTE_rsi_14": 65.0,
            "prev_FIVE_MINUTE_rsi_14": 75.0,
        }
        previous = {"FIVE_MINUTE_rsi_14": 72.0}
        assert evaluator._evaluate_single_condition(condition, current, previous) is True

    def test_crossing_below_neither_source_triggers(self, evaluator):
        """Neither candle-based nor cycle-based prev indicates a crossing."""
        condition = {"type": "rsi", "operator": "crossing_below", "value": 90, "timeframe": "FIVE_MINUTE"}
        # Both candle-based values below 90
        current = {
            "FIVE_MINUTE_rsi_14": 80.0,
            "prev_FIVE_MINUTE_rsi_14": 85.0,
        }
        # Cycle-based also below 90
        previous = {"FIVE_MINUTE_rsi_14": 88.0}
        assert evaluator._evaluate_single_condition(condition, current, previous) is False

    def test_crossing_cycle_based_with_capture_details(self, evaluator):
        """Cycle-based crossing includes source in details."""
        condition = {"type": "rsi", "operator": "crossing_below", "value": 90, "timeframe": "FIVE_MINUTE"}
        current = {
            "FIVE_MINUTE_rsi_14": 80.0,
            "prev_FIVE_MINUTE_rsi_14": 83.0,
        }
        previous = {"FIVE_MINUTE_rsi_14": 95.0}
        result, detail = evaluator._evaluate_single_condition(
            condition, current, previous, capture_details=True
        )
        assert result is True
        assert detail["crossing_source"] == "cycle"

    def test_crossing_bb_percent_cycle_based(self, evaluator):
        """BB% crossing_below using cycle-based detection — the exact real-world scenario."""
        condition = {
            "type": "bb_percent", "operator": "crossing_below", "value": 90,
            "timeframe": "THREE_MINUTE", "period": 20, "std_dev": 2,
        }
        # Candle-based: both below 90 (candle-based prev_ values)
        current = {
            "THREE_MINUTE_price": 1.975e-05,
            "THREE_MINUTE_bb_upper_20_2": 1.9812e-05,
            "THREE_MINUTE_bb_lower_20_2": 1.9489e-05,
            "prev_THREE_MINUTE_price": 1.975e-05,
            "prev_THREE_MINUTE_bb_upper_20_2": 1.9803e-05,
            "prev_THREE_MINUTE_bb_lower_20_2": 1.9475e-05,
        }
        # Cycle-based: previous check had BB% above 90
        # BB% = (1.973 - 1.9455) / (1.976 - 1.9455) * 100 = 90.16
        previous = {
            "THREE_MINUTE_price": 1.973e-05,
            "THREE_MINUTE_bb_upper_20_2": 1.976e-05,
            "THREE_MINUTE_bb_lower_20_2": 1.9455e-05,
        }
        assert evaluator._evaluate_single_condition(condition, current, previous) is True


# ---------------------------------------------------------------------------
# _evaluate_single_condition — increasing/decreasing operators
# ---------------------------------------------------------------------------


class TestEvaluateSingleConditionDirection:
    """Tests for increasing and decreasing operators."""

    def test_increasing_simple(self, evaluator):
        """Happy path: value increased (no min % threshold)."""
        condition = {"type": "rsi", "operator": "increasing", "value": 0, "timeframe": "FIVE_MINUTE"}
        current = {"FIVE_MINUTE_rsi_14": 45.0}
        previous = {"FIVE_MINUTE_rsi_14": 40.0}
        assert evaluator._evaluate_single_condition(condition, current, previous) is True

    def test_increasing_when_decreasing(self, evaluator):
        """Failure: value actually decreased."""
        condition = {"type": "rsi", "operator": "increasing", "value": 0, "timeframe": "FIVE_MINUTE"}
        current = {"FIVE_MINUTE_rsi_14": 35.0}
        previous = {"FIVE_MINUTE_rsi_14": 40.0}
        assert evaluator._evaluate_single_condition(condition, current, previous) is False

    def test_decreasing_simple(self, evaluator):
        """Happy path: value decreased."""
        condition = {"type": "rsi", "operator": "decreasing", "value": 0, "timeframe": "FIVE_MINUTE"}
        current = {"FIVE_MINUTE_rsi_14": 35.0}
        previous = {"FIVE_MINUTE_rsi_14": 40.0}
        assert evaluator._evaluate_single_condition(condition, current, previous) is True

    def test_increasing_with_min_pct_met(self, evaluator):
        """Happy path: minimum percent increase threshold met."""
        condition = {"type": "rsi", "operator": "increasing", "value": 10, "timeframe": "FIVE_MINUTE"}
        current = {"FIVE_MINUTE_rsi_14": 55.0}
        previous = {"FIVE_MINUTE_rsi_14": 50.0}
        # (55-50)/50 * 100 = 10%
        assert evaluator._evaluate_single_condition(condition, current, previous) is True

    def test_increasing_with_min_pct_not_met(self, evaluator):
        """Failure: increase is less than minimum threshold."""
        condition = {"type": "rsi", "operator": "increasing", "value": 20, "timeframe": "FIVE_MINUTE"}
        current = {"FIVE_MINUTE_rsi_14": 52.0}
        previous = {"FIVE_MINUTE_rsi_14": 50.0}
        # (52-50)/50 * 100 = 4%
        assert evaluator._evaluate_single_condition(condition, current, previous) is False

    def test_decreasing_with_min_pct_met(self, evaluator):
        """Happy path: minimum percent decrease threshold met."""
        condition = {"type": "rsi", "operator": "decreasing", "value": 10, "timeframe": "FIVE_MINUTE"}
        current = {"FIVE_MINUTE_rsi_14": 45.0}
        previous = {"FIVE_MINUTE_rsi_14": 50.0}
        # (45-50)/50 * 100 = -10%
        assert evaluator._evaluate_single_condition(condition, current, previous) is True

    def test_increasing_previous_zero(self, evaluator):
        """Edge case: previous value is 0, checks current > 0."""
        condition = {"type": "rsi", "operator": "increasing", "value": 0, "timeframe": "FIVE_MINUTE"}
        current = {"FIVE_MINUTE_rsi_14": 5.0}
        previous = {"FIVE_MINUTE_rsi_14": 0.0}
        assert evaluator._evaluate_single_condition(condition, current, previous) is True

    def test_decreasing_previous_zero(self, evaluator):
        """Edge case: previous value is 0, decreasing checks current < 0."""
        condition = {"type": "rsi", "operator": "decreasing", "value": 0, "timeframe": "FIVE_MINUTE"}
        current = {"FIVE_MINUTE_rsi_14": -5.0}
        previous = {"FIVE_MINUTE_rsi_14": 0.0}
        assert evaluator._evaluate_single_condition(condition, current, previous) is True

    def test_increasing_no_previous_returns_false(self, evaluator):
        """Failure: no previous data for direction check."""
        condition = {"type": "rsi", "operator": "increasing", "value": 0, "timeframe": "FIVE_MINUTE"}
        current = {"FIVE_MINUTE_rsi_14": 45.0}
        assert evaluator._evaluate_single_condition(condition, current, None) is False

    def test_increasing_uses_prev_keys_as_fallback(self, evaluator):
        """Happy path: falls back to prev_ keys when previous_indicators is None."""
        condition = {"type": "rsi", "operator": "increasing", "value": 0, "timeframe": "FIVE_MINUTE"}
        indicators = {
            "FIVE_MINUTE_rsi_14": 45.0,
            "prev_FIVE_MINUTE_rsi_14": 40.0,
        }
        assert evaluator._evaluate_single_condition(condition, indicators, None) is True


# ---------------------------------------------------------------------------
# Bidirectional direction filtering
# ---------------------------------------------------------------------------


class TestBidirectionalFiltering:
    """Tests for direction-based condition filtering."""

    def test_long_condition_matches_long_position(self, long_evaluator):
        """Happy path: long condition evaluated for long position."""
        condition = {
            "type": "rsi", "operator": "less_than", "value": 50,
            "timeframe": "FIVE_MINUTE", "direction": "long"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0}
        assert long_evaluator._evaluate_single_condition(condition, indicators, None) is True

    def test_short_condition_skipped_for_long_position(self, long_evaluator):
        """Failure: short condition returns False for long position."""
        condition = {
            "type": "rsi", "operator": "less_than", "value": 50,
            "timeframe": "FIVE_MINUTE", "direction": "short"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0}
        assert long_evaluator._evaluate_single_condition(condition, indicators, None) is False

    def test_no_direction_always_evaluated(self, long_evaluator):
        """Happy path: condition without direction is always evaluated."""
        condition = {
            "type": "rsi", "operator": "less_than", "value": 50,
            "timeframe": "FIVE_MINUTE"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0}
        assert long_evaluator._evaluate_single_condition(condition, indicators, None) is True

    def test_direction_mismatch_capture_details(self, long_evaluator):
        """Edge case: direction mismatch includes error in details."""
        condition = {
            "type": "rsi", "operator": "less_than", "value": 50,
            "timeframe": "FIVE_MINUTE", "direction": "short"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0}
        result, detail = long_evaluator._evaluate_single_condition(
            condition, indicators, None, capture_details=True
        )
        assert result is False
        assert "Direction mismatch" in detail["error"]

    def test_no_position_direction_evaluates_all(self, evaluator):
        """Happy path: evaluator with no position_direction evaluates all conditions."""
        condition = {
            "type": "rsi", "operator": "less_than", "value": 50,
            "timeframe": "FIVE_MINUTE", "direction": "short"
        }
        indicators = {"FIVE_MINUTE_rsi_14": 30.0}
        # No position_direction set, so direction filtering is skipped
        assert evaluator._evaluate_single_condition(condition, indicators, None) is True


# ---------------------------------------------------------------------------
# _get_indicator_value
# ---------------------------------------------------------------------------


class TestGetIndicatorValue:
    """Tests for _get_indicator_value() across all indicator types."""

    def test_rsi_default_period(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE"}
        indicators = {"FIVE_MINUTE_rsi_14": 45.0}
        assert evaluator._get_indicator_value("rsi", condition, indicators) == 45.0

    def test_rsi_custom_period(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "period": 7}
        indicators = {"FIVE_MINUTE_rsi_7": 55.0}
        assert evaluator._get_indicator_value("rsi", condition, indicators) == 55.0

    def test_macd_default_params(self, evaluator):
        condition = {"timeframe": "ONE_HOUR"}
        indicators = {"ONE_HOUR_macd_histogram_12_26_9": 0.5}
        assert evaluator._get_indicator_value("macd", condition, indicators) == 0.5

    def test_macd_custom_params(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "fast_period": 8, "slow_period": 21, "signal_period": 5}
        indicators = {"FIVE_MINUTE_macd_histogram_8_21_5": -0.3}
        assert evaluator._get_indicator_value("macd", condition, indicators) == -0.3

    def test_bb_percent(self, evaluator):
        """Happy path: BB% calculated from price and bands."""
        condition = {"timeframe": "FIVE_MINUTE", "period": 20, "std_dev": 2}
        indicators = {
            "FIVE_MINUTE_price": 105.0,
            "FIVE_MINUTE_bb_upper_20_2": 110.0,
            "FIVE_MINUTE_bb_lower_20_2": 90.0,
        }
        # (105 - 90) / (110 - 90) * 100 = 75.0
        result = evaluator._get_indicator_value("bb_percent", condition, indicators)
        assert result == pytest.approx(75.0)

    def test_bb_percent_equal_bands(self, evaluator):
        """Edge case: upper == lower returns 50.0."""
        condition = {"timeframe": "FIVE_MINUTE", "period": 20, "std_dev": 2}
        indicators = {
            "FIVE_MINUTE_price": 100.0,
            "FIVE_MINUTE_bb_upper_20_2": 100.0,
            "FIVE_MINUTE_bb_lower_20_2": 100.0,
        }
        assert evaluator._get_indicator_value("bb_percent", condition, indicators) == 50.0

    def test_bb_percent_missing_bands(self, evaluator):
        """Failure: missing band data returns None."""
        condition = {"timeframe": "FIVE_MINUTE", "period": 20, "std_dev": 2}
        indicators = {"FIVE_MINUTE_price": 100.0}
        assert evaluator._get_indicator_value("bb_percent", condition, indicators) is None

    def test_ema_cross(self, evaluator):
        """Happy path: ema_cross returns price - EMA."""
        condition = {"timeframe": "FIVE_MINUTE", "period": 50}
        indicators = {"FIVE_MINUTE_price": 105.0, "FIVE_MINUTE_ema_50": 100.0}
        assert evaluator._get_indicator_value("ema_cross", condition, indicators) == pytest.approx(5.0)

    def test_ema_cross_missing_data(self, evaluator):
        """Failure: missing price or EMA returns None."""
        condition = {"timeframe": "FIVE_MINUTE", "period": 50}
        indicators = {"FIVE_MINUTE_price": 105.0}
        assert evaluator._get_indicator_value("ema_cross", condition, indicators) is None

    def test_sma_cross(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "period": 20}
        indicators = {"FIVE_MINUTE_price": 95.0, "FIVE_MINUTE_sma_20": 100.0}
        assert evaluator._get_indicator_value("sma_cross", condition, indicators) == pytest.approx(-5.0)

    def test_stochastic(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "period": 14}
        indicators = {"FIVE_MINUTE_stoch_k_14_3": 75.0}
        assert evaluator._get_indicator_value("stochastic", condition, indicators) == 75.0

    def test_volume(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE"}
        indicators = {"FIVE_MINUTE_volume": 1234.5}
        assert evaluator._get_indicator_value("volume", condition, indicators) == 1234.5

    def test_volume_rsi(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "period": 14}
        indicators = {"FIVE_MINUTE_volume_rsi_14": 60.0}
        assert evaluator._get_indicator_value("volume_rsi", condition, indicators) == 60.0

    def test_gap_fill_pct(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE"}
        indicators = {"FIVE_MINUTE_gap_fill_pct": 15.0}
        assert evaluator._get_indicator_value("gap_fill_pct", condition, indicators) == 15.0

    def test_ai_buy_no_timeframe_prefix(self, evaluator):
        """Happy path: ai_buy uses key directly without timeframe prefix."""
        condition = {"timeframe": "FIVE_MINUTE"}
        indicators = {"ai_buy": 1}
        assert evaluator._get_indicator_value("ai_buy", condition, indicators) == 1

    def test_ai_sell(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE"}
        indicators = {"ai_sell": 0}
        assert evaluator._get_indicator_value("ai_sell", condition, indicators) == 0

    def test_bull_flag(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE"}
        indicators = {"bull_flag": 1}
        assert evaluator._get_indicator_value("bull_flag", condition, indicators) == 1

    def test_price_change_returns_none(self, evaluator):
        """Edge case: price_change type always returns None (not implemented)."""
        condition = {"timeframe": "FIVE_MINUTE"}
        assert evaluator._get_indicator_value("price_change", condition, {}) is None

    def test_unknown_type_returns_none(self, evaluator):
        """Failure: unknown indicator type returns None."""
        condition = {"timeframe": "FIVE_MINUTE"}
        assert evaluator._get_indicator_value("unknown_indicator", condition, {}) is None


# ---------------------------------------------------------------------------
# _get_previous_indicator_value
# ---------------------------------------------------------------------------


class TestGetPreviousIndicatorValue:
    """Tests for _get_previous_indicator_value()."""

    def test_previous_rsi(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "period": 14}
        indicators = {"prev_FIVE_MINUTE_rsi_14": 40.0}
        assert evaluator._get_previous_indicator_value("rsi", condition, indicators) == 40.0

    def test_previous_macd(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "fast_period": 12, "slow_period": 26, "signal_period": 9}
        indicators = {"prev_FIVE_MINUTE_macd_histogram_12_26_9": -0.1}
        assert evaluator._get_previous_indicator_value("macd", condition, indicators) == -0.1

    def test_previous_bb_percent(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "period": 20, "std_dev": 2}
        indicators = {
            "prev_FIVE_MINUTE_price": 95.0,
            "prev_FIVE_MINUTE_bb_upper_20_2": 110.0,
            "prev_FIVE_MINUTE_bb_lower_20_2": 90.0,
        }
        # (95 - 90) / (110 - 90) * 100 = 25.0
        assert evaluator._get_previous_indicator_value("bb_percent", condition, indicators) == pytest.approx(25.0)

    def test_previous_bb_percent_equal_bands(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "period": 20, "std_dev": 2}
        indicators = {
            "prev_FIVE_MINUTE_price": 100.0,
            "prev_FIVE_MINUTE_bb_upper_20_2": 100.0,
            "prev_FIVE_MINUTE_bb_lower_20_2": 100.0,
        }
        assert evaluator._get_previous_indicator_value("bb_percent", condition, indicators) == 50.0

    def test_previous_ema_cross(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "period": 50}
        indicators = {"prev_FIVE_MINUTE_price": 98.0, "prev_FIVE_MINUTE_ema_50": 100.0}
        assert evaluator._get_previous_indicator_value("ema_cross", condition, indicators) == pytest.approx(-2.0)

    def test_previous_sma_cross(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "period": 20}
        indicators = {"prev_FIVE_MINUTE_price": 102.0, "prev_FIVE_MINUTE_sma_20": 100.0}
        assert evaluator._get_previous_indicator_value("sma_cross", condition, indicators) == pytest.approx(2.0)

    def test_previous_stochastic(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "period": 14}
        indicators = {"prev_FIVE_MINUTE_stoch_k_14_3": 80.0}
        assert evaluator._get_previous_indicator_value("stochastic", condition, indicators) == 80.0

    def test_previous_volume(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE"}
        indicators = {"prev_FIVE_MINUTE_volume": 500.0}
        assert evaluator._get_previous_indicator_value("volume", condition, indicators) == 500.0

    def test_previous_volume_rsi(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE", "period": 14}
        indicators = {"prev_FIVE_MINUTE_volume_rsi_14": 55.0}
        assert evaluator._get_previous_indicator_value("volume_rsi", condition, indicators) == 55.0

    def test_previous_gap_fill_pct(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE"}
        indicators = {"prev_FIVE_MINUTE_gap_fill_pct": 10.0}
        assert evaluator._get_previous_indicator_value("gap_fill_pct", condition, indicators) == 10.0

    def test_previous_ai_buy(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE"}
        indicators = {"prev_ai_buy": 1}
        assert evaluator._get_previous_indicator_value("ai_buy", condition, indicators) == 1

    def test_previous_missing_returns_none(self, evaluator):
        """Failure: missing previous value returns None."""
        condition = {"timeframe": "FIVE_MINUTE"}
        assert evaluator._get_previous_indicator_value("rsi", condition, {}) is None

    def test_previous_unknown_type_returns_none(self, evaluator):
        condition = {"timeframe": "FIVE_MINUTE"}
        assert evaluator._get_previous_indicator_value("unknown", condition, {}) is None


# ---------------------------------------------------------------------------
# get_required_indicators_from_expression
# ---------------------------------------------------------------------------


class TestGetRequiredIndicatorsFromExpression:
    """Tests for get_required_indicators_from_expression()."""

    def test_empty_expression_returns_empty_set(self, evaluator):
        assert evaluator.get_required_indicators_from_expression(None) == set()
        assert evaluator.get_required_indicators_from_expression([]) == set()
        assert evaluator.get_required_indicators_from_expression({}) == set()

    def test_grouped_format(self, evaluator):
        """Happy path: extracts indicators from grouped format."""
        expression = {
            "groups": [
                {
                    "conditions": [
                        {"type": "rsi", "timeframe": "FIVE_MINUTE", "period": 14},
                        {"type": "macd", "timeframe": "ONE_HOUR",
                         "fast_period": 12, "slow_period": 26, "signal_period": 9},
                    ]
                }
            ]
        }
        result = evaluator.get_required_indicators_from_expression(expression)
        assert "FIVE_MINUTE_rsi_14" in result
        assert "ONE_HOUR_macd_12_26_9" in result

    def test_legacy_list_format(self, evaluator):
        """Happy path: extracts indicators from legacy list format."""
        conditions = [
            {"type": "rsi", "timeframe": "FIVE_MINUTE", "period": 14},
            {"type": "volume", "timeframe": "FIVE_MINUTE"},
        ]
        result = evaluator.get_required_indicators_from_expression(conditions)
        assert "FIVE_MINUTE_rsi_14" in result
        assert "FIVE_MINUTE_volume" in result

    def test_unknown_format_returns_empty_set(self, evaluator):
        """Failure: non-dict, non-list returns empty set."""
        assert evaluator.get_required_indicators_from_expression("invalid") == set()


# ---------------------------------------------------------------------------
# get_required_indicators
# ---------------------------------------------------------------------------


class TestGetRequiredIndicators:
    """Tests for get_required_indicators()."""

    def test_rsi(self, evaluator):
        conditions = [{"type": "rsi", "timeframe": "FIVE_MINUTE", "period": 14}]
        assert "FIVE_MINUTE_rsi_14" in evaluator.get_required_indicators(conditions)

    def test_macd(self, evaluator):
        conditions = [{"type": "macd", "timeframe": "FIVE_MINUTE"}]
        assert "FIVE_MINUTE_macd_12_26_9" in evaluator.get_required_indicators(conditions)

    def test_bb_percent_returns_all_band_keys(self, evaluator):
        """Happy path: bb_percent requires upper, lower, and price."""
        conditions = [{"type": "bb_percent", "timeframe": "FIVE_MINUTE", "period": 20, "std_dev": 2}]
        result = evaluator.get_required_indicators(conditions)
        assert "FIVE_MINUTE_bb_upper_20_2" in result
        assert "FIVE_MINUTE_bb_lower_20_2" in result
        assert "FIVE_MINUTE_price" in result

    def test_ema_cross_requires_ema_and_price(self, evaluator):
        conditions = [{"type": "ema_cross", "timeframe": "FIVE_MINUTE", "period": 50}]
        result = evaluator.get_required_indicators(conditions)
        assert "FIVE_MINUTE_ema_50" in result
        assert "FIVE_MINUTE_price" in result

    def test_sma_cross_requires_sma_and_price(self, evaluator):
        conditions = [{"type": "sma_cross", "timeframe": "FIVE_MINUTE", "period": 20}]
        result = evaluator.get_required_indicators(conditions)
        assert "FIVE_MINUTE_sma_20" in result
        assert "FIVE_MINUTE_price" in result

    def test_stochastic(self, evaluator):
        conditions = [{"type": "stochastic", "timeframe": "FIVE_MINUTE", "period": 14}]
        assert "FIVE_MINUTE_stoch_k_14_3" in evaluator.get_required_indicators(conditions)

    def test_volume(self, evaluator):
        conditions = [{"type": "volume", "timeframe": "FIVE_MINUTE"}]
        assert "FIVE_MINUTE_volume" in evaluator.get_required_indicators(conditions)

    def test_volume_rsi(self, evaluator):
        conditions = [{"type": "volume_rsi", "timeframe": "ONE_HOUR", "period": 14}]
        assert "ONE_HOUR_volume_rsi_14" in evaluator.get_required_indicators(conditions)

    def test_gap_fill_pct(self, evaluator):
        conditions = [{"type": "gap_fill_pct", "timeframe": "FIVE_MINUTE"}]
        assert "FIVE_MINUTE_gap_fill_pct" in evaluator.get_required_indicators(conditions)

    def test_uses_indicator_key_fallback(self, evaluator):
        """Edge case: condition with 'indicator' key instead of 'type'."""
        conditions = [{"indicator": "rsi", "timeframe": "FIVE_MINUTE", "period": 7}]
        assert "FIVE_MINUTE_rsi_7" in evaluator.get_required_indicators(conditions)

    def test_empty_conditions(self, evaluator):
        assert evaluator.get_required_indicators([]) == set()
