"""
Unit tests for grid trading calculations

Tests the core mathematical functions used by grid trading strategy:
- Arithmetic (linear) grid level spacing
- Geometric (exponential) grid level spacing
- Auto-range calculation from volatility
"""

import math
import pytest
from app.strategies.grid_trading import (
    calculate_arithmetic_levels,
    calculate_geometric_levels,
    calculate_auto_range_from_volatility,
)


class TestArithmeticGrid:
    """Test arithmetic (linear) grid level calculations"""

    def test_basic_arithmetic_grid(self):
        """Test simple 10-level arithmetic grid"""
        levels = calculate_arithmetic_levels(lower=45.0, upper=55.0, num_levels=10)

        assert len(levels) == 10
        assert levels[0] == pytest.approx(45.0)
        assert levels[-1] == pytest.approx(55.0)

        # Check a level near the middle (index 5 is middle of 0-9)
        step_size = (55.0 - 45.0) / 9
        expected_level_5 = 45.0 + (5 * step_size)
        assert levels[5] == pytest.approx(expected_level_5, abs=0.01)

        # Check equal spacing
        step_size = (55.0 - 45.0) / 9
        for i in range(1, 10):
            expected = 45.0 + (i * step_size)
            assert levels[i] == pytest.approx(expected)

    def test_arithmetic_grid_two_levels(self):
        """Test minimum 2-level grid"""
        levels = calculate_arithmetic_levels(lower=100.0, upper=200.0, num_levels=2)

        assert len(levels) == 2
        assert levels[0] == 100.0
        assert levels[1] == 200.0

    def test_arithmetic_grid_btc_range(self):
        """Test realistic BTC price range"""
        levels = calculate_arithmetic_levels(lower=0.030, upper=0.040, num_levels=20)

        assert len(levels) == 20
        assert levels[0] == pytest.approx(0.030)
        assert levels[-1] == pytest.approx(0.040)

        # Verify ascending order
        for i in range(1, 20):
            assert levels[i] > levels[i - 1]

    def test_arithmetic_grid_validates_inputs(self):
        """Test input validation"""
        # Upper must be greater than lower
        with pytest.raises(ValueError, match="upper must be greater than lower"):
            calculate_arithmetic_levels(lower=100, upper=50, num_levels=10)

        # Need at least 2 levels
        with pytest.raises(ValueError, match="num_levels must be at least 2"):
            calculate_arithmetic_levels(lower=45, upper=55, num_levels=1)


class TestGeometricGrid:
    """Test geometric (exponential) grid level calculations"""

    def test_basic_geometric_grid(self):
        """Test simple 10-level geometric grid"""
        levels = calculate_geometric_levels(lower=45.0, upper=55.0, num_levels=10)

        assert len(levels) == 10
        assert levels[0] == pytest.approx(45.0)
        assert levels[-1] == pytest.approx(55.0)

        # Verify geometric progression (each level = previous * ratio)
        ratio = (55.0 / 45.0) ** (1 / 9)
        for i in range(1, 10):
            expected = 45.0 * (ratio ** i)
            assert levels[i] == pytest.approx(expected)

    def test_geometric_spacing_pattern(self):
        """Verify geometric spacing: tighter near bottom, wider near top"""
        levels = calculate_geometric_levels(lower=45.0, upper=55.0, num_levels=10)

        # Distance between first two levels should be smaller than
        # distance between last two levels
        first_gap = levels[1] - levels[0]
        last_gap = levels[-1] - levels[-2]

        assert first_gap < last_gap

        # Middle gaps should be between first and last
        middle_gap = levels[5] - levels[4]
        assert first_gap < middle_gap < last_gap

    def test_geometric_grid_btc_range(self):
        """Test geometric grid on realistic BTC price range"""
        levels = calculate_geometric_levels(lower=0.030, upper=0.040, num_levels=15)

        assert len(levels) == 15
        assert levels[0] == pytest.approx(0.030)
        assert levels[-1] == pytest.approx(0.040)

        # Verify exponential growth pattern
        for i in range(1, 15):
            assert levels[i] > levels[i - 1]

    def test_geometric_grid_validates_inputs(self):
        """Test input validation for geometric grids"""
        # Upper must be greater than lower
        with pytest.raises(ValueError, match="upper must be greater than lower"):
            calculate_geometric_levels(lower=100, upper=50, num_levels=10)

        # Lower must be positive (can't take log of negative)
        with pytest.raises(ValueError, match="lower must be positive"):
            calculate_geometric_levels(lower=-10, upper=50, num_levels=10)

        # Need at least 2 levels
        with pytest.raises(ValueError, match="num_levels must be at least 2"):
            calculate_geometric_levels(lower=45, upper=55, num_levels=1)


class TestAutoRangeCalculation:
    """Test automatic range calculation from volatility"""

    def test_auto_range_with_stable_prices(self):
        """Test auto-range with low volatility (stable price)"""
        # Simulate price oscillating between 49-51 (tight range)
        candles = [
            {"close": 49.0},
            {"close": 50.0},
            {"close": 51.0},
            {"close": 50.0},
            {"close": 49.5},
            {"close": 50.5},
            {"close": 49.8},
            {"close": 50.2},
            {"close": 50.0},
            {"close": 50.1},
        ]

        current_price = 50.0
        upper, lower = calculate_auto_range_from_volatility(candles, current_price, buffer_percent=5.0)

        # Range should be relatively tight for stable prices
        range_width = upper - lower
        assert range_width < 10.0  # Less than 10 units wide

        # Current price should be within range
        assert lower < current_price < upper

    def test_auto_range_with_volatile_prices(self):
        """Test auto-range with high volatility"""
        # Simulate price swinging between 40-60 (wide range)
        candles = [
            {"close": 40.0},
            {"close": 45.0},
            {"close": 60.0},
            {"close": 55.0},
            {"close": 42.0},
            {"close": 58.0},
            {"close": 48.0},
            {"close": 52.0},
            {"close": 44.0},
            {"close": 56.0},
        ]

        current_price = 50.0
        upper, lower = calculate_auto_range_from_volatility(candles, current_price, buffer_percent=5.0)

        # Range should be wider for volatile prices
        range_width = upper - lower
        assert range_width > 20.0  # At least 20 units wide

        # Current price should be within range
        assert lower < current_price < upper

    def test_auto_range_buffer_percentage(self):
        """Test that buffer percentage widens the range"""
        candles = [{"close": float(i)} for i in range(45, 56)]  # Simple sequence 45-55
        current_price = 50.0

        # Calculate with 0% buffer
        upper_0, lower_0 = calculate_auto_range_from_volatility(candles, current_price, buffer_percent=0.0)
        range_0 = upper_0 - lower_0

        # Calculate with 10% buffer
        upper_10, lower_10 = calculate_auto_range_from_volatility(candles, current_price, buffer_percent=10.0)
        range_10 = upper_10 - lower_10

        # 10% buffer should create wider range
        assert range_10 > range_0

    def test_auto_range_fallback_with_insufficient_data(self):
        """Test fallback behavior when not enough candles"""
        # Only 3 candles (less than minimum 7)
        candles = [
            {"close": 50.0},
            {"close": 51.0},
            {"close": 49.0},
        ]

        current_price = 50.0
        upper, lower = calculate_auto_range_from_volatility(candles, current_price)

        # Should use ±10% fallback
        assert upper == pytest.approx(current_price * 1.10)
        assert lower == pytest.approx(current_price * 0.90)

    def test_auto_range_ensures_positive_lower_bound(self):
        """Test that lower bound never goes negative"""
        # Extreme case: very high volatility
        candles = [
            {"close": 10.0},
            {"close": 5.0},
            {"close": 15.0},
            {"close": 3.0},
            {"close": 12.0},
            {"close": 2.0},
            {"close": 14.0},
            {"close": 4.0},
        ]

        current_price = 8.0
        upper, lower = calculate_auto_range_from_volatility(candles, current_price)

        # Lower bound should never be negative or zero
        assert lower > 0
        assert lower >= current_price * 0.5  # At most 50% below current


class TestGridLevelComparison:
    """Compare arithmetic vs geometric grids"""

    def test_arithmetic_vs_geometric_same_bounds(self):
        """Compare both grid types with same upper/lower bounds"""
        lower, upper = 45.0, 55.0
        num_levels = 10

        arith_levels = calculate_arithmetic_levels(lower, upper, num_levels)
        geom_levels = calculate_geometric_levels(lower, upper, num_levels)

        # Both should have same first and last levels (within floating point precision)
        assert arith_levels[0] == pytest.approx(geom_levels[0])
        assert arith_levels[-1] == pytest.approx(geom_levels[-1], rel=1e-9)

        # Middle levels should differ
        # Geometric should have lower middle values (tighter spacing at bottom)
        assert geom_levels[4] < arith_levels[4]
        assert geom_levels[5] < arith_levels[5]

    def test_percentage_spacing_consistency(self):
        """Verify geometric grid maintains constant percentage spacing"""
        levels = calculate_geometric_levels(lower=100.0, upper=200.0, num_levels=10)

        # Calculate percentage change between consecutive levels
        percentage_changes = []
        for i in range(1, 10):
            pct_change = ((levels[i] - levels[i - 1]) / levels[i - 1]) * 100
            percentage_changes.append(pct_change)

        # All percentage changes should be approximately equal
        avg_pct_change = sum(percentage_changes) / len(percentage_changes)
        for pct in percentage_changes:
            assert pct == pytest.approx(avg_pct_change, rel=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
