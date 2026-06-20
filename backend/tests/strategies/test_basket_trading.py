"""
Tests for backend/app/strategies/basket_trading.py

Covers:
- Target weight normalization
- Current weight computation from balances + prices
- Drift computation and sorting
- Rebalance threshold logic
- analyze_signal: hold when within threshold, rebalance when exceeded
- should_buy / should_sell based on rebalance trades
- Config validation and edge cases
"""

import pytest


# =============================================================================
# Helper
# =============================================================================


def _make_strategy(composition=None, **kwargs):
    """Create a BasketTradingStrategy with config."""
    from app.strategies.basket_trading import BasketTradingStrategy

    config = {
        "basket_composition": composition or [
            {"symbol": "BTC-USD", "target_weight": 40.0},
            {"symbol": "ETH-USD", "target_weight": 30.0},
            {"symbol": "SOL-USD", "target_weight": 30.0},
        ],
        "rebalance_threshold": 5.0,
        "rebalance_interval_minutes": 60.0,
        "quote_currency": "USD",
        "base_order_size": 50.0,
        "max_concurrent_deals": 10,
    }
    config.update(kwargs)
    return BasketTradingStrategy(config)


# =============================================================================
# Target weight tests
# =============================================================================


def test_target_weights_sum_to_100():
    """Target weights are normalized to 100%."""
    strategy = _make_strategy()
    weights = strategy.get_target_weights()
    assert sum(weights.values()) == pytest.approx(100.0)
    assert weights["BTC-USD"] == pytest.approx(40.0)
    assert weights["ETH-USD"] == pytest.approx(30.0)
    assert weights["SOL-USD"] == pytest.approx(30.0)


def test_target_weights_normalize_non_100():
    """Weights that don't sum to 100 are normalized."""
    strategy = _make_strategy(composition=[
        {"symbol": "BTC-USD", "target_weight": 20.0},
        {"symbol": "ETH-USD", "target_weight": 20.0},
    ])
    weights = strategy.get_target_weights()
    assert sum(weights.values()) == pytest.approx(100.0)
    assert weights["BTC-USD"] == pytest.approx(50.0)
    assert weights["ETH-USD"] == pytest.approx(50.0)


def test_target_weights_empty_composition():
    """Empty composition returns empty dict."""
    from app.strategies.basket_trading import BasketTradingStrategy
    strategy = BasketTradingStrategy({
        "basket_composition": [],
        "rebalance_threshold": 5.0,
        "quote_currency": "USD",
        "base_order_size": 50.0,
        "max_concurrent_deals": 10,
    })
    assert strategy.get_target_weights() == {}


def test_target_weights_from_json_string():
    """Composition can be a JSON string."""
    import json
    strategy = _make_strategy(
        basket_composition=json.dumps([
            {"symbol": "BTC-USD", "target_weight": 50.0},
            {"symbol": "ETH-USD", "target_weight": 50.0},
        ])
    )
    weights = strategy.get_target_weights()
    assert weights["BTC-USD"] == pytest.approx(50.0)
    assert weights["ETH-USD"] == pytest.approx(50.0)


# =============================================================================
# Current weight computation tests
# =============================================================================


def test_compute_current_weights_basic():
    """Current weights are computed from balances and prices."""
    strategy = _make_strategy()
    balances = {"BTC": 0.5, "ETH": 5.0, "USD": 25000.0}
    prices = {"BTC-USD": 50000.0, "ETH-USD": 3000.0}

    weights = strategy.compute_current_weights(balances, prices)
    assert sum(weights.values()) == pytest.approx(100.0)
    # BTC: 0.5 * 50000 = 25000, ETH: 5 * 3000 = 15000, USD: 25000
    # Total = 65000
    assert weights["BTC"] == pytest.approx(25000 / 65000 * 100, rel=0.01)
    assert weights["ETH"] == pytest.approx(15000 / 65000 * 100, rel=0.01)
    assert weights["USD"] == pytest.approx(25000 / 65000 * 100, rel=0.01)


def test_compute_current_weights_missing_price():
    """Assets without a price are skipped."""
    strategy = _make_strategy()
    balances = {"BTC": 0.5, "USD": 25000.0}
    prices = {}  # No BTC price

    weights = strategy.compute_current_weights(balances, prices)
    assert "BTC" not in weights
    assert weights["USD"] == 100.0


def test_compute_current_weights_empty_balances():
    """Empty balances returns empty dict."""
    strategy = _make_strategy()
    weights = strategy.compute_current_weights({}, {})
    assert weights == {}


def test_compute_current_weights_zero_balances():
    """Zero balances are skipped."""
    strategy = _make_strategy()
    balances = {"BTC": 0.0, "USD": 0.0}
    prices = {"BTC-USD": 50000.0}
    weights = strategy.compute_current_weights(balances, prices)
    assert weights == {}


# =============================================================================
# Drift computation tests
# =============================================================================


def test_compute_drift_overweight():
    """Positive drift indicates overweight (should sell)."""
    strategy = _make_strategy()
    current = {"BTC": 50.0, "ETH": 30.0, "USD": 20.0}
    target = {"BTC": 40.0, "ETH": 30.0, "USD": 30.0}

    drifts = strategy.compute_drift(current, target)
    btc_drift = next(d for d in drifts if d["currency"] == "BTC")
    assert btc_drift["drift_pct"] == pytest.approx(10.0)
    assert btc_drift["action"] == "sell"

    usd_drift = next(d for d in drifts if d["currency"] == "USD")
    assert usd_drift["drift_pct"] == pytest.approx(-10.0)
    assert usd_drift["action"] == "buy"


def test_compute_drift_sorted_by_abs():
    """Drifts are sorted by absolute drift (largest first)."""
    strategy = _make_strategy()
    current = {"BTC": 45.0, "ETH": 35.0, "USD": 20.0}
    target = {"BTC": 40.0, "ETH": 30.0, "USD": 30.0}

    drifts = strategy.compute_drift(current, target)
    assert drifts[0]["abs_drift"] >= drifts[1]["abs_drift"]
    assert drifts[1]["abs_drift"] >= drifts[2]["abs_drift"]


def test_compute_drift_currency_only_in_target():
    """Currency in target but not in current shows as underweight."""
    strategy = _make_strategy()
    current = {"BTC": 100.0}
    target = {"BTC": 50.0, "ETH": 50.0}

    drifts = strategy.compute_drift(current, target)
    eth_drift = next(d for d in drifts if d["currency"] == "ETH")
    assert eth_drift["current_pct"] == 0.0
    assert eth_drift["target_pct"] == 50.0
    assert eth_drift["action"] == "buy"


# =============================================================================
# Rebalance threshold tests
# =============================================================================


def test_needs_rebalance_within_threshold():
    """No rebalance needed when all drifts are within threshold."""
    strategy = _make_strategy(rebalance_threshold=5.0)
    drifts = [
        {"currency": "BTC", "abs_drift": 3.0, "action": "sell"},
        {"currency": "ETH", "abs_drift": 2.0, "action": "buy"},
    ]
    assert strategy.needs_rebalance(drifts) is False


def test_needs_rebalance_exceeds_threshold():
    """Rebalance needed when any drift exceeds threshold."""
    strategy = _make_strategy(rebalance_threshold=5.0)
    drifts = [
        {"currency": "BTC", "abs_drift": 8.0, "action": "sell"},
        {"currency": "ETH", "abs_drift": 2.0, "action": "buy"},
    ]
    assert strategy.needs_rebalance(drifts) is True


def test_needs_rebalance_exact_threshold():
    """Rebalance triggered at exactly the threshold."""
    strategy = _make_strategy(rebalance_threshold=5.0)
    drifts = [{"currency": "BTC", "abs_drift": 5.0, "action": "sell"}]
    assert strategy.needs_rebalance(drifts) is True


# =============================================================================
# analyze_signal tests
# =============================================================================


async def test_analyze_signal_hold_when_balanced():
    """Returns hold signal when basket is within threshold."""
    # Use a 2-asset basket: BTC 50%, USD 50%
    from app.strategies.basket_trading import BasketTradingStrategy
    strategy = BasketTradingStrategy({
        "basket_composition": [
            {"symbol": "BTC", "target_weight": 50.0},
            {"symbol": "USD", "target_weight": 50.0},
        ],
        "rebalance_threshold": 10.0,
        "quote_currency": "USD",
        "base_order_size": 50.0,
        "max_concurrent_deals": 10,
    })
    # BTC: 0.5 * 50000 = 25000, USD: 25000 = 50000 total
    # BTC: 50%, USD: 50% — perfectly balanced, 0% drift
    balances = {"BTC": 0.5, "USD": 25000.0}
    prices = {"BTC-USD": 50000.0}

    result = await strategy.analyze_signal([], 0, balances=balances, prices=prices)
    assert result["signal_type"] == "hold"
    assert "within rebalance threshold" in result["reasoning"].lower()


async def test_analyze_signal_rebalance_when_drift_exceeds():
    """Returns rebalance signal when drift exceeds threshold."""
    strategy = _make_strategy(rebalance_threshold=3.0)
    balances = {"BTC": 1.0, "USD": 0.0}
    prices = {"BTC-USD": 50000.0}
    # BTC: 100%, target 40% — drift is 60%, well above 3%

    result = await strategy.analyze_signal([], 0, balances=balances, prices=prices)
    assert result["signal_type"] == "sell"  # BTC is overweight
    assert "rebalance" in result["reasoning"].lower()
    assert "rebalance_trades" in result
    assert len(result["rebalance_trades"]) > 0


async def test_analyze_signal_no_balances():
    """Returns None when no balances provided."""
    strategy = _make_strategy()
    result = await strategy.analyze_signal([], 0, balances={}, prices={})
    assert result is None


async def test_analyze_signal_no_target():
    """Returns None when no composition configured."""
    from app.strategies.basket_trading import BasketTradingStrategy
    strategy = BasketTradingStrategy({
        "basket_composition": [],
        "rebalance_threshold": 5.0,
        "quote_currency": "USD",
        "base_order_size": 50.0,
        "max_concurrent_deals": 10,
    })
    balances = {"BTC": 1.0}
    prices = {"BTC-USD": 50000.0}
    result = await strategy.analyze_signal([], 0, balances=balances, prices=prices)
    assert result is None


async def test_analyze_signal_includes_drifts():
    """Signal includes detailed drift information."""
    strategy = _make_strategy(rebalance_threshold=3.0)
    balances = {"BTC": 1.0, "USD": 0.0}
    prices = {"BTC-USD": 50000.0}

    result = await strategy.analyze_signal([], 0, balances=balances, prices=prices)
    assert "indicators" in result
    assert "drifts" in result["indicators"]
    assert "current_weights" in result["indicators"]
    assert "target_weights" in result["indicators"]
    assert "max_drift" in result["indicators"]


# =============================================================================
# should_buy / should_sell tests
# =============================================================================


async def test_should_buy_returns_true_for_underweight():
    """should_buy returns True when there are buy trades in the signal."""
    strategy = _make_strategy()
    signal = {
        "signal_type": "buy",
        "rebalance_trades": [
            {"currency": "ETH", "action": "buy", "drift_pct": -10.0},
        ],
    }
    should, amount, reason = await strategy.should_buy(signal, None, 1000.0)
    assert should is True
    assert amount == 50.0  # base_order_size
    assert "ETH" in reason


async def test_should_buy_returns_false_when_no_buy_trades():
    """should_buy returns False when no buy trades needed."""
    strategy = _make_strategy()
    signal = {
        "signal_type": "sell",
        "rebalance_trades": [
            {"currency": "BTC", "action": "sell", "drift_pct": 10.0},
        ],
    }
    should, amount, reason = await strategy.should_buy(signal, None, 1000.0)
    assert should is False
    assert "No buy" in reason


async def test_should_sell_returns_true_for_overweight():
    """should_sell returns True when there are sell trades in the signal."""
    strategy = _make_strategy()
    signal = {
        "signal_type": "sell",
        "rebalance_trades": [
            {"currency": "BTC", "action": "sell", "drift_pct": 10.0},
        ],
    }
    should, reason = await strategy.should_sell(signal, None, 50000.0)
    assert should is True
    assert "BTC" in reason


async def test_should_sell_returns_false_when_no_sell_trades():
    """should_sell returns False when no sell trades needed."""
    strategy = _make_strategy()
    signal = {
        "signal_type": "buy",
        "rebalance_trades": [
            {"currency": "ETH", "action": "buy", "drift_pct": -10.0},
        ],
    }
    should, reason = await strategy.should_sell(signal, None, 50000.0)
    assert should is False
    assert "No sell" in reason


# =============================================================================
# Strategy registration test
# =============================================================================


def test_strategy_registered_in_registry():
    """BasketTradingStrategy is registered in StrategyRegistry."""
    from app.strategies import StrategyRegistry
    definition = StrategyRegistry.get_definition("basket_trading")
    assert definition.id == "basket_trading"
    assert "basket" in definition.name.lower()


def test_strategy_get_definition():
    """get_definition returns the expected parameters."""
    strategy = _make_strategy()
    defn = strategy.get_definition()
    assert defn.id == "basket_trading"
    param_names = [p.name for p in defn.parameters]
    assert "basket_composition" in param_names
    assert "rebalance_threshold" in param_names
    assert "base_order_size" in param_names
    assert "max_concurrent_deals" in param_names
