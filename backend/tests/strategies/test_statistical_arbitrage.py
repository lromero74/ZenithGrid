"""
Tests for backend/app/strategies/statistical_arbitrage.py

Covers:
- StatisticalArbitrageStrategy.validate_config
- StatisticalArbitrageStrategy.should_buy (async)
- StatisticalArbitrageStrategy.should_sell (async)
- StatisticalArbitrageStrategy.get_position_sizes
- StatisticalArbitrageStrategy.get_definition
"""

import pytest
from unittest.mock import MagicMock

from app.strategies.statistical_arbitrage import StatisticalArbitrageStrategy


def _make_strategy(config_overrides=None):
    """Create a StatisticalArbitrageStrategy with default config."""
    config = {}
    if config_overrides:
        config.update(config_overrides)
    return StatisticalArbitrageStrategy(config)


# =====================================================================
# get_definition
# =====================================================================


class TestGetDefinition:
    """Tests for get_definition()"""

    def test_returns_correct_id(self):
        strategy = _make_strategy()
        defn = strategy.get_definition()
        assert defn.id == "statistical_arbitrage"

    def test_has_pairs_parameters(self):
        strategy = _make_strategy()
        defn = strategy.get_definition()
        param_names = [p.name for p in defn.parameters]
        assert "pair_1" in param_names
        assert "pair_2" in param_names
        assert "z_score_entry" in param_names


# =====================================================================
# validate_config
# =====================================================================


class TestValidateConfig:
    """Tests for validate_config()"""

    def test_sets_defaults(self):
        strategy = _make_strategy()
        assert strategy.config["pair_1"] == "ETH-USD"
        assert strategy.config["pair_2"] == "ETH-BTC"
        assert strategy.config["z_score_entry"] == 2.0
        assert strategy.config["z_score_exit"] == 0.5

    def test_exit_threshold_capped_below_entry(self):
        """z_score_exit must be < z_score_entry."""
        strategy = _make_strategy({"z_score_entry": 2.0, "z_score_exit": 3.0})
        assert strategy.config["z_score_exit"] < strategy.config["z_score_entry"]

    def test_stop_loss_above_entry(self):
        """z_score_stop_loss must be > z_score_entry."""
        strategy = _make_strategy({"z_score_entry": 3.0, "z_score_stop_loss": 1.0})
        assert strategy.config["z_score_stop_loss"] > strategy.config["z_score_entry"]


# =====================================================================
# should_buy  (async)
# =====================================================================


class TestShouldBuy:
    """Tests for should_buy()"""

    @pytest.mark.asyncio
    async def test_stat_arb_entry_signal(self):
        """Valid entry signal => buy."""
        strategy = _make_strategy()
        signal = {
            "signal": "stat_arb_entry",
            "direction": "long_spread",
            "z_score": 2.5,
            "confidence": 0.85,
            "pair_1": "ETH-USD",
            "pair_2": "ETH-BTC",
            "position_size_usd": 500,
        }

        should, amount, reason = await strategy.should_buy(signal, position=None, btc_balance=1000.0)

        assert should is True
        assert amount == 500
        assert "Stat-arb" in reason

    @pytest.mark.asyncio
    async def test_non_entry_signal(self):
        """Exit signal => no buy."""
        strategy = _make_strategy()
        signal = {"signal": "stat_arb_exit", "z_score": 0.3}

        should, amount, reason = await strategy.should_buy(signal, position=None, btc_balance=1000.0)

        assert should is False
        assert "Not a stat-arb entry" in reason

    @pytest.mark.asyncio
    async def test_wrong_signal_type(self):
        """Completely wrong signal type => no buy."""
        strategy = _make_strategy()
        signal = {"signal": "spatial_arbitrage"}

        should, amount, reason = await strategy.should_buy(signal, position=None, btc_balance=1000.0)

        assert should is False


# =====================================================================
# should_sell  (async)
# =====================================================================


class TestShouldSell:
    """Tests for should_sell()"""

    @pytest.mark.asyncio
    async def test_exit_signal(self):
        """Z-score converged => sell."""
        strategy = _make_strategy()
        signal = {"signal": "stat_arb_exit", "z_score": 0.3}

        should, reason = await strategy.should_sell(signal, position=MagicMock(), current_price=100.0)

        assert should is True
        assert "converged" in reason

    @pytest.mark.asyncio
    async def test_stop_loss_signal(self):
        """Stop loss triggered => sell."""
        strategy = _make_strategy()
        signal = {"signal": "stat_arb_stop_loss", "z_score": 5.0}

        should, reason = await strategy.should_sell(signal, position=MagicMock(), current_price=100.0)

        assert should is True
        assert "Stop loss" in reason

    @pytest.mark.asyncio
    async def test_no_exit_signal(self):
        """No exit signal => hold."""
        strategy = _make_strategy()
        signal = {"signal": "stat_arb_entry"}

        should, reason = await strategy.should_sell(signal, position=MagicMock(), current_price=100.0)

        assert should is False
        assert "No exit" in reason


# =====================================================================
# get_position_sizes
# =====================================================================


class TestGetPositionSizes:
    """Tests for get_position_sizes()"""

    def test_returns_sizes_for_both_pairs(self):
        """Should return sizing for pair_1 and pair_2."""
        strategy = _make_strategy()
        signal = {
            "pair_1": "ETH-USD",
            "pair_2": "ETH-BTC",
            "pair_1_action": "buy",
            "pair_2_action": "sell",
            "pair_1_size_usd": 500,
            "pair_2_size_usd": 450,
        }

        result = strategy.get_position_sizes(signal)

        assert "ETH-USD" in result
        assert "ETH-BTC" in result
        assert result["ETH-USD"]["action"] == "buy"
        assert result["ETH-USD"]["size_usd"] == 500
        assert result["ETH-BTC"]["action"] == "sell"
        assert result["ETH-BTC"]["size_usd"] == 450

    def test_hedge_ratio_reflected_in_sizes(self):
        """pair_2_size_usd should differ from pair_1_size_usd if hedge ratio != 1."""
        strategy = _make_strategy()
        signal = {
            "pair_1": "ETH-USD",
            "pair_2": "ETH-BTC",
            "pair_1_action": "buy",
            "pair_2_action": "sell",
            "pair_1_size_usd": 500,
            "pair_2_size_usd": 600,  # Hedge ratio > 1
        }

        result = strategy.get_position_sizes(signal)

        assert result["ETH-BTC"]["size_usd"] == 600
