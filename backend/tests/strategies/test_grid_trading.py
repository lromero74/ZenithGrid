"""Tests for app/strategies/grid_trading.py — pure calculation functions"""

import pytest
from app.strategies.grid_trading import (
    calculate_arithmetic_levels,
    calculate_geometric_levels,
    calculate_auto_range_from_volatility,
)


class TestCalculateArithmeticLevels:
    def test_basic_10_levels(self):
        levels = calculate_arithmetic_levels(45, 55, 10)
        assert len(levels) == 10
        assert pytest.approx(levels[0]) == 45.0
        assert pytest.approx(levels[-1]) == 55.0

    def test_equal_spacing(self):
        levels = calculate_arithmetic_levels(100, 200, 5)
        # Step = (200-100) / 4 = 25
        assert pytest.approx(levels[1] - levels[0]) == 25.0
        assert pytest.approx(levels[2] - levels[1]) == 25.0

    def test_two_levels(self):
        levels = calculate_arithmetic_levels(10, 20, 2)
        assert levels == [10.0, 20.0]

    def test_less_than_2_levels_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            calculate_arithmetic_levels(10, 20, 1)

    def test_upper_not_greater_raises(self):
        with pytest.raises(ValueError, match="upper must be greater"):
            calculate_arithmetic_levels(20, 10, 5)

    def test_equal_bounds_raises(self):
        with pytest.raises(ValueError, match="upper must be greater"):
            calculate_arithmetic_levels(10, 10, 5)

    def test_small_btc_range(self):
        """BTC-denominated pair with small range."""
        levels = calculate_arithmetic_levels(0.05, 0.06, 5)
        assert len(levels) == 5
        assert pytest.approx(levels[0]) == 0.05
        assert pytest.approx(levels[-1]) == 0.06


class TestCalculateGeometricLevels:
    def test_basic_10_levels(self):
        levels = calculate_geometric_levels(45, 55, 10)
        assert len(levels) == 10
        assert pytest.approx(levels[0]) == 45.0
        assert pytest.approx(levels[-1], abs=0.01) == 55.0

    def test_percentage_spacing_increases(self):
        """Geometric spacing should have increasing dollar gaps."""
        levels = calculate_geometric_levels(100, 200, 5)
        gap1 = levels[1] - levels[0]
        gap2 = levels[2] - levels[1]
        gap3 = levels[3] - levels[2]
        assert gap2 > gap1
        assert gap3 > gap2

    def test_two_levels(self):
        levels = calculate_geometric_levels(10, 20, 2)
        assert pytest.approx(levels[0]) == 10.0
        assert pytest.approx(levels[1]) == 20.0

    def test_less_than_2_levels_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            calculate_geometric_levels(10, 20, 1)

    def test_zero_lower_raises(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_geometric_levels(0, 20, 5)

    def test_negative_lower_raises(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_geometric_levels(-10, 20, 5)


class TestCalculateAutoRangeFromVolatility:
    def test_sufficient_candles(self):
        # 30 candles with prices around 100, std dev ~ 3
        candles = [{"close": 100 + (i % 7 - 3)} for i in range(30)]
        upper, lower = calculate_auto_range_from_volatility(candles, 100.0)
        assert upper > 100.0
        assert lower < 100.0
        assert lower > 0

    def test_insufficient_candles_fallback(self):
        """Less than 7 candles: fallback to ±10%."""
        candles = [{"close": 100}] * 3
        upper, lower = calculate_auto_range_from_volatility(candles, 100.0)
        assert pytest.approx(upper) == 110.0
        assert pytest.approx(lower) == 90.0

    def test_empty_candles_fallback(self):
        upper, lower = calculate_auto_range_from_volatility([], 50.0)
        assert pytest.approx(upper) == 55.0
        assert pytest.approx(lower) == 45.0

    def test_lower_bound_stays_positive(self):
        """Very volatile data should still have positive lower bound."""
        # Large variance should not make lower bound negative
        candles = [{"close": p} for p in [10, 100, 10, 100, 10, 100, 10, 100]]
        upper, lower = calculate_auto_range_from_volatility(candles, 50.0)
        assert lower > 0

    def test_custom_buffer(self):
        """Buffer percentage affects the range width."""
        candles = [{"close": 100 + (i % 5 - 2)} for i in range(30)]
        upper_5, lower_5 = calculate_auto_range_from_volatility(candles, 100.0, buffer_percent=5.0)
        upper_20, lower_20 = calculate_auto_range_from_volatility(candles, 100.0, buffer_percent=20.0)
        # Larger buffer = wider range
        assert (upper_20 - lower_20) > (upper_5 - lower_5)
