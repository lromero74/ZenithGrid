"""
Tests for backend/app/strategies/spatial_arbitrage.py

Covers:
- SpatialArbitrageStrategy.validate_config
- SpatialArbitrageStrategy.should_buy (async)
- SpatialArbitrageStrategy.should_sell (async)
- SpatialArbitrageStrategy.calculate_optimal_size
- SpatialArbitrageStrategy.get_definition
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from app.strategies.spatial_arbitrage import SpatialArbitrageStrategy


def _make_strategy(config_overrides=None):
    """Create a SpatialArbitrageStrategy with default config."""
    config = {}
    if config_overrides:
        config.update(config_overrides)
    return SpatialArbitrageStrategy(config)


# =====================================================================
# get_definition
# =====================================================================


class TestGetDefinition:
    """Tests for get_definition()"""

    def test_returns_correct_id(self):
        strategy = _make_strategy()
        defn = strategy.get_definition()
        assert defn.id == "spatial_arbitrage"

    def test_has_parameters(self):
        strategy = _make_strategy()
        defn = strategy.get_definition()
        assert len(defn.parameters) > 0

    def test_supported_products(self):
        strategy = _make_strategy()
        defn = strategy.get_definition()
        assert "ETH-USDT" in defn.supported_products


# =====================================================================
# validate_config
# =====================================================================


class TestValidateConfig:
    """Tests for validate_config()"""

    def test_sets_defaults(self):
        strategy = _make_strategy()
        assert strategy.config["min_profit_pct"] == 0.3
        assert strategy.config["max_position_size_usd"] == 1000
        assert strategy.config["slippage_tolerance"] == 0.5

    def test_preserves_custom_values(self):
        strategy = _make_strategy({"min_profit_pct": 1.0, "target_profit_pct": 2.0})
        assert strategy.config["min_profit_pct"] == 1.0

    def test_min_profit_capped_to_target(self):
        """min_profit_pct cannot exceed target_profit_pct."""
        strategy = _make_strategy({"min_profit_pct": 5.0, "target_profit_pct": 2.0})
        assert strategy.config["min_profit_pct"] == strategy.config["target_profit_pct"]

    def test_min_position_capped_to_max(self):
        """min_position_size_usd cannot exceed max_position_size_usd."""
        strategy = _make_strategy({"min_position_size_usd": 5000, "max_position_size_usd": 1000})
        assert strategy.config["min_position_size_usd"] < strategy.config["max_position_size_usd"]


# =====================================================================
# should_buy  (async)
# =====================================================================


class TestShouldBuy:
    """Tests for should_buy()"""

    @pytest.mark.asyncio
    async def test_valid_arbitrage_signal(self):
        """Valid signal with sufficient balance => buy."""
        strategy = _make_strategy()
        signal = {
            "signal": "spatial_arbitrage",
            "buy_cost": 500.0,
            "quantity": 0.5,
            "estimated_profit_pct": 0.8,
        }

        should, amount, reason = await strategy.should_buy(signal, position=None, btc_balance=1000.0)

        assert should is True
        assert amount == 0.5
        assert "0.80%" in reason

    @pytest.mark.asyncio
    async def test_wrong_signal_type(self):
        """Non-arbitrage signal => no buy."""
        strategy = _make_strategy()
        signal = {"signal": "other_strategy"}

        should, amount, reason = await strategy.should_buy(signal, position=None, btc_balance=1000.0)

        assert should is False
        assert "Not an arbitrage signal" in reason

    @pytest.mark.asyncio
    async def test_insufficient_balance(self):
        """Balance too low for buy cost => no buy."""
        strategy = _make_strategy()
        signal = {
            "signal": "spatial_arbitrage",
            "buy_cost": 2000.0,
            "quantity": 1.0,
            "estimated_profit_pct": 0.5,
        }

        should, amount, reason = await strategy.should_buy(signal, position=None, btc_balance=500.0)

        assert should is False
        assert "Insufficient" in reason


# =====================================================================
# should_sell  (async)
# =====================================================================


class TestShouldSell:
    """Tests for should_sell()"""

    @pytest.mark.asyncio
    async def test_valid_arbitrage_signal(self):
        """Spatial arbitrage sell is always simultaneous."""
        strategy = _make_strategy()
        signal = {"signal": "spatial_arbitrage"}

        should, reason = await strategy.should_sell(signal, position=MagicMock(), current_price=100.0)

        assert should is True
        assert "Simultaneous" in reason

    @pytest.mark.asyncio
    async def test_wrong_signal_type(self):
        strategy = _make_strategy()
        signal = {"signal": "other"}

        should, reason = await strategy.should_sell(signal, position=MagicMock(), current_price=100.0)

        assert should is False


# =====================================================================
# calculate_optimal_size
# =====================================================================


class TestCalculateOptimalSize:
    """Tests for calculate_optimal_size()"""

    def test_basic_calculation(self):
        """Optimal size should be within configured bounds."""
        strategy = _make_strategy({
            "max_position_size_usd": 1000,
            "min_position_size_usd": 50,
        })

        result = strategy.calculate_optimal_size(
            buy_liquidity=Decimal("5000"),
            sell_liquidity=Decimal("3000"),
            spread_pct=Decimal("0.5"),
        )

        assert result >= Decimal("50")
        assert result <= Decimal("1000")

    def test_low_liquidity_caps_size(self):
        """Low liquidity should constrain position size."""
        strategy = _make_strategy({
            "max_position_size_usd": 10000,
            "min_position_size_usd": 10,
        })

        result = strategy.calculate_optimal_size(
            buy_liquidity=Decimal("100"),
            sell_liquidity=Decimal("200"),
            spread_pct=Decimal("0.5"),
        )

        # Limited by buy_liquidity (100) * confidence (0.5) = 50
        assert result <= Decimal("100")

    def test_wide_spread_increases_confidence(self):
        """Wider spread = higher confidence, potentially larger size."""
        strategy = _make_strategy({
            "max_position_size_usd": 10000,
            "min_position_size_usd": 10,
        })

        result_narrow = strategy.calculate_optimal_size(
            buy_liquidity=Decimal("5000"),
            sell_liquidity=Decimal("5000"),
            spread_pct=Decimal("0.2"),
        )
        result_wide = strategy.calculate_optimal_size(
            buy_liquidity=Decimal("5000"),
            sell_liquidity=Decimal("5000"),
            spread_pct=Decimal("1.0"),
        )

        assert result_wide >= result_narrow

    def test_minimum_size_enforced(self):
        """Even with tiny liquidity, result >= min_position_size."""
        strategy = _make_strategy({
            "max_position_size_usd": 1000,
            "min_position_size_usd": 50,
        })

        result = strategy.calculate_optimal_size(
            buy_liquidity=Decimal("1"),
            sell_liquidity=Decimal("1"),
            spread_pct=Decimal("0.01"),
        )

        assert result >= Decimal("50")
