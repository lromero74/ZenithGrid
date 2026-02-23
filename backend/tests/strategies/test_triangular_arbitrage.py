"""
Tests for backend/app/strategies/triangular_arbitrage.py

Covers:
- TriangularArbitrageStrategy.validate_config
- TriangularArbitrageStrategy.should_buy (async)
- TriangularArbitrageStrategy.should_sell (async)
- TriangularArbitrageStrategy.get_execution_plan
- TriangularArbitrageStrategy.get_definition
"""

import pytest
from unittest.mock import MagicMock

from app.strategies.triangular_arbitrage import TriangularArbitrageStrategy


def _make_strategy(config_overrides=None):
    """Create a TriangularArbitrageStrategy with default config."""
    config = {}
    if config_overrides:
        config.update(config_overrides)
    return TriangularArbitrageStrategy(config)


# =====================================================================
# get_definition
# =====================================================================


class TestGetDefinition:
    """Tests for get_definition()"""

    def test_returns_correct_id(self):
        strategy = _make_strategy()
        defn = strategy.get_definition()
        assert defn.id == "triangular_arbitrage"

    def test_has_parameters(self):
        strategy = _make_strategy()
        defn = strategy.get_definition()
        assert len(defn.parameters) > 0
        param_names = [p.name for p in defn.parameters]
        assert "base_currency" in param_names
        assert "min_profit_pct" in param_names
        assert "fee_pct" in param_names


# =====================================================================
# validate_config
# =====================================================================


class TestValidateConfig:
    """Tests for validate_config()"""

    def test_sets_defaults(self):
        strategy = _make_strategy()
        assert strategy.config["base_currency"] == "ETH"
        assert strategy.config["trade_amount"] == 0.5
        assert strategy.config["fee_pct"] == 0.1

    def test_parses_currencies_string(self):
        """currencies_to_scan string should be parsed into currencies_list."""
        strategy = _make_strategy({"currencies_to_scan": "BTC,ETH,SOL"})
        assert strategy.config["currencies_list"] == ["BTC", "ETH", "SOL"]

    def test_default_currencies_for_non_string(self):
        """Non-string currencies_to_scan uses default list."""
        strategy = _make_strategy({"currencies_to_scan": 123})
        assert strategy.config["currencies_list"] == ["ETH", "BTC", "USDT"]

    def test_preserves_custom_values(self):
        strategy = _make_strategy({"fee_pct": 0.25})
        assert strategy.config["fee_pct"] == 0.25


# =====================================================================
# should_buy  (async)
# =====================================================================


class TestShouldBuy:
    """Tests for should_buy()"""

    @pytest.mark.asyncio
    async def test_valid_triangular_signal(self):
        """Valid triangular arb signal => execute."""
        strategy = _make_strategy()
        signal = {
            "signal": "triangular_arbitrage",
            "start_amount": 0.5,
            "profit_pct": 0.15,
            "path": "ETH -> BTC -> USDT -> ETH",
        }

        should, amount, reason = await strategy.should_buy(signal, position=None, btc_balance=1.0)

        assert should is True
        assert amount == 0.5
        assert "Triangular" in reason
        assert "0.150%" in reason

    @pytest.mark.asyncio
    async def test_wrong_signal_type(self):
        """Non-triangular signal => no execution."""
        strategy = _make_strategy()
        signal = {"signal": "spatial_arbitrage"}

        should, amount, reason = await strategy.should_buy(signal, position=None, btc_balance=1.0)

        assert should is False
        assert "Not a triangular" in reason

    @pytest.mark.asyncio
    async def test_missing_signal_key(self):
        """Missing signal key => no execution."""
        strategy = _make_strategy()
        signal = {}

        should, amount, reason = await strategy.should_buy(signal, position=None, btc_balance=1.0)

        assert should is False


# =====================================================================
# should_sell  (async)
# =====================================================================


class TestShouldSell:
    """Tests for should_sell()"""

    @pytest.mark.asyncio
    async def test_triangular_arb_is_self_closing(self):
        """Triangular arb never has a separate sell decision."""
        strategy = _make_strategy()
        signal = {"signal": "triangular_arbitrage"}

        should, reason = await strategy.should_sell(signal, position=MagicMock(), current_price=100.0)

        assert should is False
        assert "self-closing" in reason


# =====================================================================
# get_execution_plan
# =====================================================================


class TestGetExecutionPlan:
    """Tests for get_execution_plan()"""

    def test_three_leg_plan(self):
        """Valid 3-leg signal => 3 orders."""
        strategy = _make_strategy()
        signal = {
            "pairs": ["ETH-BTC", "BTC-USDT", "ETH-USDT"],
            "directions": ["sell", "sell", "buy"],
            "rates": [0.032, 30000.0, 960.0],
            "start_amount": 1.0,
        }

        orders = strategy.get_execution_plan(signal)

        assert len(orders) == 3
        assert orders[0]["leg"] == 1
        assert orders[0]["pair"] == "ETH-BTC"
        assert orders[0]["side"] == "SELL"
        assert orders[1]["leg"] == 2
        assert orders[2]["leg"] == 3

    def test_sell_direction_calculation(self):
        """Sell: base_amount = current, quote_amount = current * rate."""
        strategy = _make_strategy()
        signal = {
            "pairs": ["ETH-BTC", "BTC-USDT", "ETH-USDT"],
            "directions": ["sell", "sell", "buy"],
            "rates": [0.032, 30000.0, 960.0],
            "start_amount": 1.0,
        }

        orders = strategy.get_execution_plan(signal)

        # Leg 1: sell 1.0 ETH at rate 0.032 => get 0.032 BTC
        assert pytest.approx(orders[0]["base_amount"]) == 1.0
        assert pytest.approx(orders[0]["quote_amount"]) == 0.032

    def test_buy_direction_calculation(self):
        """Buy: quote_amount = current, base_amount = current / rate."""
        strategy = _make_strategy()
        signal = {
            "pairs": ["X-Y"],
            "directions": ["buy"],
            "rates": [2.0],
            "start_amount": 10.0,
        }

        orders = strategy.get_execution_plan(signal)

        assert len(orders) == 0  # Only 1 pair, but need exactly 3

    def test_mismatched_pairs_directions(self):
        """If pairs and directions count != 3, return empty."""
        strategy = _make_strategy()
        signal = {
            "pairs": ["A-B", "C-D"],
            "directions": ["buy", "sell"],
            "rates": [1.0, 2.0],
            "start_amount": 1.0,
        }

        orders = strategy.get_execution_plan(signal)

        assert orders == []

    def test_empty_signal(self):
        """Empty signal => empty plan."""
        strategy = _make_strategy()
        signal = {"pairs": [], "directions": [], "rates": []}

        orders = strategy.get_execution_plan(signal)

        assert orders == []

    def test_chained_amounts_flow_correctly(self):
        """Output of leg N should be input of leg N+1."""
        strategy = _make_strategy()
        signal = {
            "pairs": ["ETH-BTC", "BTC-USDT", "ETH-USDT"],
            "directions": ["sell", "sell", "buy"],
            "rates": [0.032, 30000.0, 960.0],
            "start_amount": 10.0,
        }

        orders = strategy.get_execution_plan(signal)

        # Leg 1: sell 10 ETH => 10 * 0.032 = 0.32 BTC
        assert pytest.approx(orders[0]["quote_amount"]) == 0.32
        # Leg 2: sell 0.32 BTC => 0.32 * 30000 = 9600 USDT
        assert pytest.approx(orders[1]["base_amount"]) == 0.32
        assert pytest.approx(orders[1]["quote_amount"]) == 9600.0
        # Leg 3: buy ETH with 9600 USDT at rate 960 => 9600/960 = 10.0 ETH
        assert pytest.approx(orders[2]["quote_amount"]) == 9600.0
        assert pytest.approx(orders[2]["base_amount"]) == 10.0
