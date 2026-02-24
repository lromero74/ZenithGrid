"""Tests for app/strategies/grid_trading.py — calculations + strategy class"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.strategies.grid_trading import (
    calculate_arithmetic_levels,
    calculate_geometric_levels,
    calculate_auto_range_from_volatility,
    calculate_volume_weighted_levels,
    GridTradingStrategy,
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


# ────────────────────────────────────────────────────────────────────────────
# calculate_volume_weighted_levels
# ────────────────────────────────────────────────────────────────────────────


class TestCalculateVolumeWeightedLevels:
    """Tests for calculate_volume_weighted_levels()"""

    @pytest.mark.asyncio
    async def test_volume_weighted_levels_happy_path(self):
        """Happy path: sufficient trades produce volume-weighted levels."""
        mock_client = AsyncMock()
        # 200 trades concentrated around 50 (mid-range)
        trades = [
            {"price": str(45 + (i % 11)), "size": str(1.0)}
            for i in range(200)
        ]
        mock_client.get_recent_trades = AsyncMock(return_value=trades)

        levels = await calculate_volume_weighted_levels(
            product_id="ETH-BTC",
            upper=55.0,
            lower=45.0,
            num_levels=10,
            exchange_client=mock_client,
        )

        assert len(levels) == 10
        assert pytest.approx(levels[0]) == 45.0
        assert pytest.approx(levels[-1]) == 55.0

    @pytest.mark.asyncio
    async def test_volume_weighted_levels_insufficient_trades_fallback(self):
        """Edge case: < 100 trades falls back to arithmetic grid."""
        mock_client = AsyncMock()
        mock_client.get_recent_trades = AsyncMock(
            return_value=[{"price": "50", "size": "1"}] * 10
        )

        levels = await calculate_volume_weighted_levels(
            product_id="ETH-BTC",
            upper=55.0,
            lower=45.0,
            num_levels=5,
            exchange_client=mock_client,
        )

        # Should fall back to arithmetic levels
        assert len(levels) == 5
        assert pytest.approx(levels[0]) == 45.0
        assert pytest.approx(levels[-1]) == 55.0
        # Arithmetic spacing
        assert pytest.approx(levels[1] - levels[0]) == 2.5

    @pytest.mark.asyncio
    async def test_volume_weighted_levels_no_trades_fallback(self):
        """Edge case: empty trades list falls back to arithmetic grid."""
        mock_client = AsyncMock()
        mock_client.get_recent_trades = AsyncMock(return_value=[])

        levels = await calculate_volume_weighted_levels(
            product_id="ETH-BTC",
            upper=55.0,
            lower=45.0,
            num_levels=5,
            exchange_client=mock_client,
        )

        assert len(levels) == 5
        assert pytest.approx(levels[0]) == 45.0

    @pytest.mark.asyncio
    async def test_volume_weighted_levels_exchange_error_fallback(self):
        """Failure: exchange API error falls back to arithmetic grid."""
        mock_client = AsyncMock()
        mock_client.get_recent_trades = AsyncMock(
            side_effect=Exception("API timeout")
        )

        levels = await calculate_volume_weighted_levels(
            product_id="ETH-BTC",
            upper=55.0,
            lower=45.0,
            num_levels=5,
            exchange_client=mock_client,
        )

        # Should gracefully fall back to arithmetic
        assert len(levels) == 5
        assert pytest.approx(levels[0]) == 45.0
        assert pytest.approx(levels[-1]) == 55.0

    @pytest.mark.asyncio
    async def test_volume_weighted_levels_trades_outside_range(self):
        """Edge case: all trades outside the grid range → fallback."""
        mock_client = AsyncMock()
        # All trades at price 100, but range is 45-55
        trades = [{"price": "100", "size": "1"}] * 200
        mock_client.get_recent_trades = AsyncMock(return_value=trades)

        levels = await calculate_volume_weighted_levels(
            product_id="ETH-BTC",
            upper=55.0,
            lower=45.0,
            num_levels=5,
            exchange_client=mock_client,
        )

        # No volume in range → fallback to arithmetic
        assert len(levels) == 5
        assert pytest.approx(levels[0]) == 45.0


# ────────────────────────────────────────────────────────────────────────────
# Helper: create a GridTradingStrategy with given config
# ────────────────────────────────────────────────────────────────────────────


def _make_strategy(overrides: dict = None) -> GridTradingStrategy:
    """Build a GridTradingStrategy with sensible defaults."""
    base = {
        "grid_type": "arithmetic",
        "grid_mode": "neutral",
        "range_mode": "manual",
        "upper_limit": 55.0,
        "lower_limit": 45.0,
        "num_grid_levels": 10,
        "total_investment_quote": 0.01,
    }
    if overrides:
        base.update(overrides)
    return GridTradingStrategy(base)


# ────────────────────────────────────────────────────────────────────────────
# GridTradingStrategy.get_definition()
# ────────────────────────────────────────────────────────────────────────────


class TestGetDefinition:
    """Tests for GridTradingStrategy.get_definition()"""

    def test_get_definition_returns_valid_definition(self):
        """Happy path: definition has correct id, name, and parameters."""
        strategy = GridTradingStrategy({})
        defn = strategy.get_definition()

        assert defn.id == "grid_trading"
        assert defn.name == "Grid Trading"
        assert len(defn.parameters) > 0
        assert len(defn.supported_products) > 0

    def test_get_definition_has_required_parameters(self):
        """All expected parameter names are present."""
        strategy = GridTradingStrategy({})
        defn = strategy.get_definition()
        param_names = {p.name for p in defn.parameters}

        expected = {
            "grid_type", "grid_mode", "range_mode",
            "upper_limit", "lower_limit", "num_grid_levels",
            "total_investment_quote",
        }
        assert expected.issubset(param_names)

    def test_get_definition_parameter_types(self):
        """Parameter types are valid."""
        strategy = GridTradingStrategy({})
        defn = strategy.get_definition()
        valid_types = {"float", "int", "integer", "string", "bool"}

        for p in defn.parameters:
            assert p.type in valid_types, f"{p.name} has invalid type: {p.type}"


# ────────────────────────────────────────────────────────────────────────────
# GridTradingStrategy.validate_config()
# ────────────────────────────────────────────────────────────────────────────


class TestValidateConfig:
    """Tests for GridTradingStrategy.validate_config()"""

    def test_validate_config_happy_path(self):
        """Happy path: valid config passes validation."""
        strategy = _make_strategy()
        # No exception = passes
        assert strategy.config["upper_limit"] == 55.0

    def test_validate_config_empty_config_skips(self):
        """Edge case: empty config is accepted (used during registration)."""
        strategy = GridTradingStrategy({})
        # No exception
        assert strategy.config == {}

    def test_validate_config_manual_missing_upper_raises(self):
        """Failure: manual mode without upper_limit raises."""
        with pytest.raises(ValueError, match="requires upper_limit"):
            _make_strategy({"upper_limit": None})

    def test_validate_config_manual_missing_lower_raises(self):
        """Failure: manual mode without lower_limit raises."""
        with pytest.raises(ValueError, match="requires upper_limit"):
            _make_strategy({"lower_limit": None})

    def test_validate_config_upper_less_than_lower_raises(self):
        """Failure: upper <= lower raises."""
        with pytest.raises(ValueError, match="must be greater"):
            _make_strategy({"upper_limit": 40.0, "lower_limit": 50.0})

    def test_validate_config_upper_equal_lower_raises(self):
        """Failure: upper == lower raises."""
        with pytest.raises(ValueError, match="must be greater"):
            _make_strategy({"upper_limit": 50.0, "lower_limit": 50.0})

    def test_validate_config_too_few_grid_levels_raises(self):
        """Failure: num_grid_levels < 5 raises."""
        with pytest.raises(ValueError, match="at least 5"):
            _make_strategy({"num_grid_levels": 3})

    def test_validate_config_zero_investment_raises(self):
        """Failure: zero investment raises."""
        with pytest.raises(ValueError, match="must be positive"):
            _make_strategy({"total_investment_quote": 0})

    def test_validate_config_negative_investment_raises(self):
        """Failure: negative investment raises."""
        with pytest.raises(ValueError, match="must be positive"):
            _make_strategy({"total_investment_quote": -1})

    def test_validate_config_auto_volatility_skips_range_check(self):
        """Edge case: auto_volatility mode doesn't need upper/lower."""
        strategy = _make_strategy({
            "range_mode": "auto_volatility",
            "upper_limit": None,
            "lower_limit": None,
        })
        assert strategy.config["range_mode"] == "auto_volatility"


# ────────────────────────────────────────────────────────────────────────────
# GridTradingStrategy.analyze_signal()
# ────────────────────────────────────────────────────────────────────────────


class TestAnalyzeSignal:
    """Tests for GridTradingStrategy.analyze_signal()"""

    @pytest.mark.asyncio
    async def test_analyze_signal_initialize_grid_manual(self):
        """Happy path: first call with manual range returns initialize_grid."""
        strategy = _make_strategy()
        candles = [{"close": 50 + (i % 5 - 2)} for i in range(30)]

        result = await strategy.analyze_signal(candles, 50.0)

        assert result["action"] == "initialize_grid"
        assert result["grid_type"] == "arithmetic"
        assert result["grid_mode"] == "neutral"
        assert pytest.approx(result["upper_limit"]) == 55.0
        assert pytest.approx(result["lower_limit"]) == 45.0
        assert len(result["levels"]) == 10
        assert result["breakout_direction"] is None

    @pytest.mark.asyncio
    async def test_analyze_signal_geometric_grid(self):
        """Happy path: geometric grid type produces geometric levels."""
        strategy = _make_strategy({"grid_type": "geometric"})
        candles = [{"close": 50}] * 10

        result = await strategy.analyze_signal(candles, 50.0)

        levels = result["levels"]
        assert len(levels) == 10
        # Geometric has increasing dollar gaps
        gap1 = levels[1] - levels[0]
        gap2 = levels[2] - levels[1]
        assert gap2 > gap1

    @pytest.mark.asyncio
    async def test_analyze_signal_auto_volatility_range(self):
        """Happy path: auto_volatility mode calculates range from candles."""
        strategy = _make_strategy({
            "range_mode": "auto_volatility",
            "upper_limit": None,
            "lower_limit": None,
        })
        candles = [{"close": 100 + (i % 7 - 3)} for i in range(30)]

        result = await strategy.analyze_signal(candles, 100.0)

        assert result["action"] == "initialize_grid"
        assert result["upper_limit"] > 100.0
        assert result["lower_limit"] < 100.0

    @pytest.mark.asyncio
    async def test_analyze_signal_monitor_with_grid_state(self):
        """Happy path: existing grid in range returns 'monitor'."""
        strategy = _make_strategy()
        candles = [{"close": 50}] * 10

        result = await strategy.analyze_signal(
            candles, 50.0,
            bot_config={
                "grid_state": {
                    "current_range_upper": 55.0,
                    "current_range_lower": 45.0,
                }
            }
        )

        assert result["action"] == "monitor"
        assert result["breakout_direction"] is None

    @pytest.mark.asyncio
    async def test_analyze_signal_breakout_upward(self):
        """Happy path: price above upper + threshold triggers upward breakout."""
        strategy = _make_strategy({
            "enable_dynamic_adjustment": True,
            "breakout_threshold_percent": 5.0,
        })
        candles = [{"close": 60}] * 10
        # Current upper = 55, threshold = 5% → 55 * 1.05 = 57.75
        # Price 60 > 57.75 → breakout
        result = await strategy.analyze_signal(
            candles, 60.0,
            bot_config={
                "grid_state": {
                    "current_range_upper": 55.0,
                    "current_range_lower": 45.0,
                }
            }
        )

        assert result["action"] == "rebalance"
        assert result["breakout_direction"] == "upward"

    @pytest.mark.asyncio
    async def test_analyze_signal_breakout_downward(self):
        """Happy path: price below lower - threshold triggers downward breakout."""
        strategy = _make_strategy({
            "enable_dynamic_adjustment": True,
            "breakout_threshold_percent": 5.0,
        })
        candles = [{"close": 40}] * 10
        # Current lower = 45, threshold = 5% → 45 * 0.95 = 42.75
        # Price 40 < 42.75 → breakout
        result = await strategy.analyze_signal(
            candles, 40.0,
            bot_config={
                "grid_state": {
                    "current_range_upper": 55.0,
                    "current_range_lower": 45.0,
                }
            }
        )

        assert result["action"] == "rebalance"
        assert result["breakout_direction"] == "downward"

    @pytest.mark.asyncio
    async def test_analyze_signal_breakout_within_cooldown_no_rebalance(self):
        """Edge case: breakout during cooldown period does not trigger rebalance."""
        strategy = _make_strategy({
            "enable_dynamic_adjustment": True,
            "breakout_threshold_percent": 5.0,
            "rebalance_cooldown_minutes": 15,
        })
        candles = [{"close": 60}] * 10
        # Last breakout was 5 min ago, cooldown is 15 min
        recent_time = (datetime.utcnow() - timedelta(minutes=5)).isoformat()

        result = await strategy.analyze_signal(
            candles, 60.0,
            bot_config={
                "grid_state": {
                    "current_range_upper": 55.0,
                    "current_range_lower": 45.0,
                    "last_breakout_time": recent_time,
                }
            }
        )

        # Still in cooldown → monitor, not rebalance
        assert result["action"] == "monitor"
        assert result["breakout_direction"] is None

    @pytest.mark.asyncio
    async def test_analyze_signal_breakout_after_cooldown_rebalances(self):
        """Happy path: breakout after cooldown expires triggers rebalance."""
        strategy = _make_strategy({
            "enable_dynamic_adjustment": True,
            "breakout_threshold_percent": 5.0,
            "rebalance_cooldown_minutes": 15,
        })
        candles = [{"close": 60}] * 10
        # Last breakout was 20 min ago, cooldown is 15 min → expired
        old_time = (datetime.utcnow() - timedelta(minutes=20)).isoformat()

        result = await strategy.analyze_signal(
            candles, 60.0,
            bot_config={
                "grid_state": {
                    "current_range_upper": 55.0,
                    "current_range_lower": 45.0,
                    "last_breakout_time": old_time,
                }
            }
        )

        assert result["action"] == "rebalance"
        assert result["breakout_direction"] == "upward"

    @pytest.mark.asyncio
    async def test_analyze_signal_dynamic_adjustment_disabled_no_breakout(self):
        """Edge case: dynamic adjustment off → never detects breakout."""
        strategy = _make_strategy({"enable_dynamic_adjustment": False})
        candles = [{"close": 60}] * 10

        result = await strategy.analyze_signal(
            candles, 60.0,
            bot_config={
                "grid_state": {
                    "current_range_upper": 55.0,
                    "current_range_lower": 45.0,
                }
            }
        )

        assert result["action"] == "monitor"
        assert result["breakout_direction"] is None

    @pytest.mark.asyncio
    async def test_analyze_signal_unsupported_range_mode_raises(self):
        """Failure: unsupported range_mode raises ValueError."""
        strategy = _make_strategy({
            "range_mode": "magic_8_ball",
            "upper_limit": None,
            "lower_limit": None,
        })

        with pytest.raises(ValueError, match="Unsupported range_mode"):
            await strategy.analyze_signal([], 50.0)

    @pytest.mark.asyncio
    async def test_analyze_signal_unsupported_grid_type_raises(self):
        """Failure: unsupported grid_type raises ValueError."""
        strategy = _make_strategy({"grid_type": "fibonacci"})

        with pytest.raises(ValueError, match="Unsupported grid_type"):
            await strategy.analyze_signal([], 50.0)

    @pytest.mark.asyncio
    async def test_analyze_signal_ai_optimization_due(self):
        """Happy path: AI optimization scheduled when interval elapsed."""
        strategy = _make_strategy({
            "enable_ai_optimization": True,
            "ai_adjustment_interval_minutes": 60,
        })
        candles = [{"close": 50}] * 10
        old_time = (datetime.utcnow() - timedelta(minutes=120)).isoformat()

        result = await strategy.analyze_signal(
            candles, 50.0,
            bot_config={
                "grid_state": {
                    "current_range_upper": 55.0,
                    "current_range_lower": 45.0,
                    "last_ai_check": old_time,
                }
            }
        )

        assert result["ai_optimization_due"] == "due"

    @pytest.mark.asyncio
    async def test_analyze_signal_ai_optimization_not_due_yet(self):
        """Edge case: AI interval not elapsed → optimization not due."""
        strategy = _make_strategy({
            "enable_ai_optimization": True,
            "ai_adjustment_interval_minutes": 120,
        })
        candles = [{"close": 50}] * 10
        recent_time = (datetime.utcnow() - timedelta(minutes=10)).isoformat()

        result = await strategy.analyze_signal(
            candles, 50.0,
            bot_config={
                "grid_state": {
                    "current_range_upper": 55.0,
                    "current_range_lower": 45.0,
                    "last_ai_check": recent_time,
                }
            }
        )

        assert result["ai_optimization_due"] is None

    @pytest.mark.asyncio
    async def test_analyze_signal_ai_optimization_first_run_is_due(self):
        """Edge case: no last_ai_check → first run is always due."""
        strategy = _make_strategy({
            "enable_ai_optimization": True,
            "ai_adjustment_interval_minutes": 120,
        })
        candles = [{"close": 50}] * 10

        result = await strategy.analyze_signal(
            candles, 50.0,
            bot_config={
                "grid_state": {
                    "current_range_upper": 55.0,
                    "current_range_lower": 45.0,
                    # No last_ai_check key
                }
            }
        )

        assert result["ai_optimization_due"] == "due"

    @pytest.mark.asyncio
    async def test_analyze_signal_volume_weighted_levels(self):
        """Happy path: volume weighting enabled uses exchange client."""
        mock_client = AsyncMock()
        trades = [
            {"price": str(45 + (i % 11)), "size": str(1.0)}
            for i in range(200)
        ]
        mock_client.get_recent_trades = AsyncMock(return_value=trades)

        strategy = _make_strategy({
            "enable_volume_weighting": True,
            "volume_analysis_hours": 24,
            "volume_clustering_strength": 1.5,
        })
        candles = [{"close": 50}] * 10

        result = await strategy.analyze_signal(
            candles, 50.0,
            exchange_client=mock_client,
            product_id="ETH-BTC",
        )

        assert result["action"] == "initialize_grid"
        assert len(result["levels"]) == 10
        mock_client.get_recent_trades.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_analyze_signal_volume_weighting_no_client_fallback(self):
        """Edge case: volume weighting enabled but no exchange client → standard grid."""
        strategy = _make_strategy({"enable_volume_weighting": True})
        candles = [{"close": 50}] * 10

        result = await strategy.analyze_signal(candles, 50.0)

        # Falls back to arithmetic since no exchange_client
        assert result["action"] == "initialize_grid"
        assert len(result["levels"]) == 10


# ────────────────────────────────────────────────────────────────────────────
# GridTradingStrategy.should_buy()
# ────────────────────────────────────────────────────────────────────────────


class TestShouldBuy:
    """Tests for GridTradingStrategy.should_buy()"""

    @pytest.mark.asyncio
    async def test_should_buy_initialize_grid_sufficient_balance(self):
        """Happy path: initialization with enough balance returns True."""
        strategy = _make_strategy({"total_investment_quote": 0.01})
        signal = {"action": "initialize_grid"}

        should, amount, reason = await strategy.should_buy(signal, None, 0.05)

        assert should is True
        assert pytest.approx(amount) == 0.01
        assert "Initializing" in reason

    @pytest.mark.asyncio
    async def test_should_buy_initialize_grid_insufficient_balance(self):
        """Failure: initialization with insufficient balance returns False."""
        strategy = _make_strategy({"total_investment_quote": 0.01})
        signal = {"action": "initialize_grid"}

        should, amount, reason = await strategy.should_buy(signal, None, 0.005)

        assert should is False
        assert amount == 0
        assert "Insufficient" in reason

    @pytest.mark.asyncio
    async def test_should_buy_rebalance_downward_breakout(self):
        """Happy path: downward breakout triggers buy for rebalance."""
        strategy = _make_strategy()
        signal = {"action": "rebalance", "breakout_direction": "downward"}

        should, amount, reason = await strategy.should_buy(signal, None, 0.05)

        assert should is True
        assert "Rebalancing" in reason
        assert "downward" in reason

    @pytest.mark.asyncio
    async def test_should_buy_rebalance_upward_breakout_no_buy(self):
        """Edge case: upward breakout does not trigger buy."""
        strategy = _make_strategy()
        signal = {"action": "rebalance", "breakout_direction": "upward"}

        should, amount, reason = await strategy.should_buy(signal, None, 0.05)

        assert should is False

    @pytest.mark.asyncio
    async def test_should_buy_monitor_no_action(self):
        """Edge case: monitor action returns no buy."""
        strategy = _make_strategy()
        signal = {"action": "monitor"}

        should, amount, reason = await strategy.should_buy(signal, None, 0.05)

        assert should is False
        assert amount == 0
        assert "monitoring" in reason.lower()


# ────────────────────────────────────────────────────────────────────────────
# GridTradingStrategy.should_sell()
# ────────────────────────────────────────────────────────────────────────────


class TestShouldSell:
    """Tests for GridTradingStrategy.should_sell()"""

    @pytest.mark.asyncio
    async def test_should_sell_initialize_neutral_grid(self):
        """Happy path: neutral grid init places sell orders."""
        strategy = _make_strategy({"grid_mode": "neutral"})
        signal = {"action": "initialize_grid", "grid_mode": "neutral"}

        should, reason = await strategy.should_sell(signal, None, 50.0)

        assert should is True
        assert "sell orders" in reason.lower()

    @pytest.mark.asyncio
    async def test_should_sell_initialize_long_grid_no_sell(self):
        """Edge case: long grid init does NOT place sell orders."""
        strategy = _make_strategy({"grid_mode": "long"})
        signal = {"action": "initialize_grid", "grid_mode": "long"}

        should, reason = await strategy.should_sell(signal, None, 50.0)

        assert should is False

    @pytest.mark.asyncio
    async def test_should_sell_rebalance_upward_breakout(self):
        """Happy path: upward breakout triggers sell for rebalance."""
        strategy = _make_strategy()
        signal = {"action": "rebalance", "breakout_direction": "upward"}

        should, reason = await strategy.should_sell(signal, None, 60.0)

        assert should is True
        assert "Rebalancing" in reason

    @pytest.mark.asyncio
    async def test_should_sell_rebalance_downward_breakout_no_sell(self):
        """Edge case: downward breakout does not trigger sell."""
        strategy = _make_strategy()
        signal = {"action": "rebalance", "breakout_direction": "downward"}

        should, reason = await strategy.should_sell(signal, None, 40.0)

        assert should is False

    @pytest.mark.asyncio
    async def test_should_sell_monitor_no_action(self):
        """Edge case: monitor action returns no sell."""
        strategy = _make_strategy()
        signal = {"action": "monitor"}

        should, reason = await strategy.should_sell(signal, None, 50.0)

        assert should is False
        assert "monitoring" in reason.lower()


# ────────────────────────────────────────────────────────────────────────────
# GridTradingStrategy._get_ai_range_suggestions() (private, but critical)
# ────────────────────────────────────────────────────────────────────────────


class TestGetAiRangeSuggestions:
    """Tests for GridTradingStrategy._get_ai_range_suggestions()"""

    @pytest.mark.asyncio
    async def test_ai_suggestions_happy_path(self):
        """Happy path: AI returns valid JSON with high confidence."""
        strategy = _make_strategy()

        mock_ai_client = AsyncMock()
        mock_ai_client.analyze = AsyncMock(return_value="""
```json
{"suggested_upper": 56.0, "suggested_lower": 44.0, "reasoning": "test", "confidence": 80}
```
""")

        with patch(
            "app.ai_service.get_ai_client",
            new_callable=AsyncMock,
            return_value=mock_ai_client,
        ):
            result = await strategy._get_ai_range_suggestions(
                candles=[{"close": 50}] * 10,
                current_price=50.0,
                auto_upper=55.0,
                auto_lower=45.0,
                kwargs={
                    "db": MagicMock(),
                    "bot_config": {"user_id": 1, "product_id": "ETH-BTC"},
                },
            )

        assert result is not None
        assert pytest.approx(result["suggested_upper"]) == 56.0
        assert pytest.approx(result["suggested_lower"]) == 44.0

    @pytest.mark.asyncio
    async def test_ai_suggestions_low_confidence_returns_none(self):
        """Edge case: AI response with low confidence returns None."""
        strategy = _make_strategy()

        mock_ai_client = AsyncMock()
        mock_ai_client.analyze = AsyncMock(return_value="""
```json
{"suggested_upper": 56.0, "suggested_lower": 44.0, "reasoning": "uncertain", "confidence": 30}
```
""")

        with patch(
            "app.ai_service.get_ai_client",
            new_callable=AsyncMock,
            return_value=mock_ai_client,
        ):
            result = await strategy._get_ai_range_suggestions(
                candles=[{"close": 50}] * 10,
                current_price=50.0,
                auto_upper=55.0,
                auto_lower=45.0,
                kwargs={
                    "db": MagicMock(),
                    "bot_config": {"user_id": 1, "product_id": "ETH-BTC"},
                },
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_ai_suggestions_missing_db_returns_none(self):
        """Failure: no db session → returns None without calling AI."""
        strategy = _make_strategy()

        result = await strategy._get_ai_range_suggestions(
            candles=[{"close": 50}] * 10,
            current_price=50.0,
            auto_upper=55.0,
            auto_lower=45.0,
            kwargs={"bot_config": {"user_id": 1}},  # No "db" key
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_ai_suggestions_missing_user_id_returns_none(self):
        """Failure: no user_id → returns None."""
        strategy = _make_strategy()

        result = await strategy._get_ai_range_suggestions(
            candles=[{"close": 50}] * 10,
            current_price=50.0,
            auto_upper=55.0,
            auto_lower=45.0,
            kwargs={"db": MagicMock(), "bot_config": {}},  # No user_id
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_ai_suggestions_ai_error_returns_none(self):
        """Failure: AI client throws → gracefully returns None."""
        strategy = _make_strategy()

        with patch(
            "app.ai_service.get_ai_client",
            new_callable=AsyncMock,
            side_effect=Exception("AI service down"),
        ):
            result = await strategy._get_ai_range_suggestions(
                candles=[{"close": 50}] * 10,
                current_price=50.0,
                auto_upper=55.0,
                auto_lower=45.0,
                kwargs={
                    "db": MagicMock(),
                    "bot_config": {"user_id": 1, "product_id": "ETH-BTC"},
                },
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_ai_suggestions_invalid_json_returns_none(self):
        """Failure: AI returns non-JSON response → returns None."""
        strategy = _make_strategy()

        mock_ai_client = AsyncMock()
        mock_ai_client.analyze = AsyncMock(
            return_value="I don't know how to format JSON properly."
        )

        with patch(
            "app.ai_service.get_ai_client",
            new_callable=AsyncMock,
            return_value=mock_ai_client,
        ):
            result = await strategy._get_ai_range_suggestions(
                candles=[{"close": 50}] * 10,
                current_price=50.0,
                auto_upper=55.0,
                auto_lower=45.0,
                kwargs={
                    "db": MagicMock(),
                    "bot_config": {"user_id": 1, "product_id": "ETH-BTC"},
                },
            )

        assert result is None
