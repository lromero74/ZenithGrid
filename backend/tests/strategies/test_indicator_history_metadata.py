"""Tests for indicator snapshot metadata when history is incomplete."""

from unittest.mock import MagicMock

from app.strategies.indicator_based_indicators import IndicatorCalculationMixin


class IndicatorHarness(IndicatorCalculationMixin):
    def __init__(self):
        self.base_order_conditions = []
        self.safety_order_conditions = []
        self.take_profit_conditions = []
        self.previous_indicators = {}
        self.phase_evaluator = MagicMock()
        self.indicator_calculator = MagicMock()


def test_traditional_indicators_report_missing_timeframe_history():
    harness = IndicatorHarness()
    harness.phase_evaluator.get_required_indicators_from_expression.side_effect = [
        {"ONE_DAY_rsi_14"},
        set(),
        set(),
    ]

    indicators = harness._calculate_traditional_indicators(
        candles_by_timeframe={"ONE_DAY": [{}] * 11},
        candles=[{}] * 30,
        min_candles_needed=30,
    )

    assert indicators == {"ONE_DAY_missing_reason": "not enough ONE_DAY candles: 11/30"}
    harness.indicator_calculator.calculate_all_indicators.assert_not_called()
