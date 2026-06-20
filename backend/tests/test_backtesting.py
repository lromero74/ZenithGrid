"""
Tests for backend/app/backtesting/__init__.py

Covers:
- SimulatedBroker: buy, sell, DCA, equity tracking
- run_backtest: signal processing, trade execution, metrics calculation
- Edge cases: insufficient candles, no trades, all winning/losing trades
- Metrics: win rate, max drawdown, profit factor, Sharpe ratio
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.backtesting import (
    BacktestResult, BacktestPosition,
    SimulatedBroker, run_backtest, _MockPosition, _compute_metrics,
)


# =============================================================================
# SimulatedBroker tests
# =============================================================================


def test_broker_buy_creates_position():
    """Buy creates a new position and reduces cash."""
    broker = SimulatedBroker(initial_capital=1000.0)
    assert broker.buy("BTC-USD", 50000.0, 100.0, 1000)

    assert broker.position is not None
    assert broker.position.entry_price == 50000.0
    assert broker.position.total_quote_spent == 100.0
    assert broker.position.base_amount == 100.0 / 50000.0
    assert broker.cash_balance == 900.0


def test_broker_buy_dca_updates_position():
    """Second buy DCAs into the existing position."""
    broker = SimulatedBroker(initial_capital=1000.0)
    broker.buy("BTC-USD", 50000.0, 100.0, 1000)
    broker.buy("BTC-USD", 40000.0, 80.0, 2000)

    assert broker.position.safety_orders == 1
    assert broker.position.total_quote_spent == 180.0
    # Average entry: (50000*0.002 + 40000*0.002) / 0.004 = 45000
    assert broker.position.entry_price == 45000.0
    assert broker.cash_balance == 820.0


def test_broker_sell_closes_position():
    """Sell closes the position and returns cash."""
    broker = SimulatedBroker(initial_capital=1000.0)
    broker.buy("BTC-USD", 50000.0, 100.0, 1000)
    broker.sell("BTC-USD", 55000.0, 2000)

    assert broker.position is None
    assert len(broker.closed_positions) == 1
    pos = broker.closed_positions[0]
    assert pos.exit_price == 55000.0
    assert pos.profit_quote > 0
    assert pos.profit_pct > 0


def test_broker_sell_no_position_fails():
    """Sell with no open position returns False."""
    broker = SimulatedBroker(initial_capital=1000.0)
    assert broker.sell("BTC-USD", 50000.0, 1000) is False


def test_broker_buy_insufficient_funds():
    """Buy with more than available balance returns False."""
    broker = SimulatedBroker(initial_capital=100.0)
    assert broker.buy("BTC-USD", 50000.0, 200.0, 1000) is False
    assert broker.position is None
    assert broker.cash_balance == 100.0


def test_broker_fee_deduction():
    """Fees are deducted from buy and sell."""
    broker = SimulatedBroker(initial_capital=1000.0, fee_pct=0.6)
    broker.buy("BTC-USD", 50000.0, 100.0, 1000)

    # Fee = 100 * 0.006 = 0.60, total cost = 100.60
    assert broker.cash_balance == pytest.approx(899.4)

    broker.sell("BTC-USD", 55000.0, 2000)
    # Proceeds = 0.002 * 55000 = 110, fee = 0.66, net = 109.34
    # Cash = 899.4 + 109.34 = 1008.74
    assert broker.cash_balance == pytest.approx(1008.74)


def test_broker_get_equity_with_position():
    """Equity includes position value at current price."""
    broker = SimulatedBroker(initial_capital=1000.0)
    broker.buy("BTC-USD", 50000.0, 100.0, 1000)
    # Cash = 900, position = 0.002 BTC * 55000 = 110
    equity = broker.get_equity(55000.0)
    assert equity == pytest.approx(1010.0)


def test_broker_get_equity_no_position():
    """Equity is just cash when no position."""
    broker = SimulatedBroker(initial_capital=1000.0)
    assert broker.get_equity(50000.0) == 1000.0


# =============================================================================
# Metrics computation tests
# =============================================================================


def test_compute_metrics_all_wins():
    """All winning trades produce 100% win rate."""
    positions = [
        BacktestPosition("BTC-USD", 50000, 100, 0.002, 0, profit_quote=10, profit_pct=10, closed_at=100),
        BacktestPosition("BTC-USD", 51000, 100, 0.002, 200, profit_quote=5, profit_pct=5, closed_at=300),
    ]
    result = _compute_metrics(1000.0, 1015.0, positions, [], 5.0, [0.01, 0.005], [])
    assert result.num_wins == 2
    assert result.num_losses == 0
    assert result.win_rate == 100.0
    assert result.total_profit_quote == 15.0
    assert result.profit_factor == float("inf")


def test_compute_metrics_all_losses():
    """All losing trades produce 0% win rate."""
    positions = [
        BacktestPosition("BTC-USD", 50000, 100, 0.002, 0, profit_quote=-10, profit_pct=-10, closed_at=100),
    ]
    result = _compute_metrics(1000.0, 990.0, positions, [], 5.0, [-0.01], [])
    assert result.num_wins == 0
    assert result.num_losses == 1
    assert result.win_rate == 0.0
    assert result.profit_factor == 0.0


def test_compute_metrics_mixed():
    """Mixed wins and losses."""
    positions = [
        BacktestPosition("BTC-USD", 50000, 100, 0.002, 0, profit_quote=20, profit_pct=20, closed_at=100),
        BacktestPosition("BTC-USD", 51000, 100, 0.002, 200, profit_quote=-10, profit_pct=-10, closed_at=300),
    ]
    result = _compute_metrics(1000.0, 1010.0, positions, [], 5.0, [0.01, -0.005], [])
    assert result.num_wins == 1
    assert result.num_losses == 1
    assert result.win_rate == 50.0
    assert result.profit_factor == 2.0  # 20 / 10


def test_compute_metrics_no_trades():
    """No trades produces zero metrics."""
    result = _compute_metrics(1000.0, 1000.0, [], [], 0.0, [], [])
    assert result.num_trades == 0
    assert result.win_rate == 0.0
    assert result.total_profit_quote == 0.0


def test_backtest_result_to_dict():
    """to_dict produces valid JSON-serializable dict."""
    result = BacktestResult(
        total_return_pct=10.5,
        total_profit_quote=105.0,
        initial_capital=1000.0,
        final_capital=1105.0,
        num_trades=5,
        num_wins=3,
        num_losses=2,
        win_rate=60.0,
    )
    d = result.to_dict()
    assert d["total_return_pct"] == 10.5
    assert d["num_trades"] == 5
    assert d["win_rate"] == 60.0
    assert isinstance(d["trades"], list)
    assert isinstance(d["positions"], list)


# =============================================================================
# run_backtest integration tests
# =============================================================================


def _make_candles(n: int, start_price: float = 50000.0) -> list:
    """Generate n synthetic candles with a simple price pattern."""
    candles = []
    for i in range(n):
        # Simple oscillation: price goes up and down
        price = start_price + (i % 10) * 100
        candles.append({
            "start": str(i * 300),  # 5-min candles
            "open": str(price),
            "high": str(price + 50),
            "low": str(price - 50),
            "close": str(price + 30),
            "volume": "1000",
        })
    return candles


async def test_run_backtest_insufficient_candles():
    """Less than 20 candles returns empty result."""
    candles = _make_candles(10)
    result = await run_backtest(
        strategy_type="indicator_based",
        strategy_config={"base_order_percentage": 5.0, "base_order_conditions": []},
        candles=candles,
        product_id="BTC-USD",
        initial_capital=1000.0,
    )
    assert result.num_trades == 0
    assert result.initial_capital == 1000.0


async def test_run_backtest_no_signal_strategy():
    """A strategy that never produces a signal results in no trades."""
    candles = _make_candles(50)

    # Mock the strategy to always return None from analyze_signal
    mock_strategy = MagicMock()
    mock_strategy.analyze_signal = AsyncMock(return_value=None)

    with patch("app.strategies.StrategyRegistry.get_strategy", return_value=mock_strategy):
        result = await run_backtest(
            strategy_type="indicator_based",
            strategy_config={"base_order_percentage": 5.0},
            candles=candles,
            product_id="BTC-USD",
            initial_capital=1000.0,
        )

    assert result.num_trades == 0
    assert result.final_capital == 1000.0


async def test_run_backtest_with_buy_signals():
    """A strategy that produces buy signals triggers trades."""
    candles = _make_candles(50)

    # Mock strategy that produces a buy signal on the first bar, then a sell
    call_count = [0]

    async def mock_analyze(candles_data, price, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return {"signal_type": "buy", "confidence": 80}
        elif call_count[0] == 5:
            return {"signal_type": "sell", "confidence": 80}
        return None

    mock_strategy = MagicMock()
    mock_strategy.analyze_signal = mock_analyze

    with patch("app.strategies.StrategyRegistry.get_strategy", return_value=mock_strategy):
        result = await run_backtest(
            strategy_type="indicator_based",
            strategy_config={"base_order_percentage": 5.0},
            candles=candles,
            product_id="BTC-USD",
            initial_capital=1000.0,
        )

    assert result.num_trades == 1
    assert len(result.trades) == 2  # 1 buy + 1 sell
    assert result.trades[0].side == "buy"
    assert result.trades[1].side == "sell"


async def test_run_backtest_closes_open_position_at_end():
    """Any open position at the end is closed at the last candle's price."""
    candles = _make_candles(50)

    # Strategy that always says buy (never sells)
    async def mock_analyze(candles_data, price, **kwargs):
        return {"signal_type": "buy", "confidence": 80}

    mock_strategy = MagicMock()
    mock_strategy.analyze_signal = mock_analyze

    with patch("app.strategies.StrategyRegistry.get_strategy", return_value=mock_strategy):
        result = await run_backtest(
            strategy_type="indicator_based",
            strategy_config={"base_order_percentage": 5.0},
            candles=candles,
            product_id="BTC-USD",
            initial_capital=1000.0,
        )

    # Position should be closed at the end
    assert result.num_trades >= 1
    assert all(p.closed_at is not None for p in result.positions)


async def test_run_backtest_equity_curve_populated():
    """Equity curve is populated with one entry per bar."""
    candles = _make_candles(30)

    mock_strategy = MagicMock()
    mock_strategy.analyze_signal = AsyncMock(return_value=None)

    with patch("app.strategies.StrategyRegistry.get_strategy", return_value=mock_strategy):
        result = await run_backtest(
            strategy_type="indicator_based",
            strategy_config={"base_order_percentage": 5.0},
            candles=candles,
            product_id="BTC-USD",
            initial_capital=1000.0,
        )

    # 30 candles - 20 warmup = 10 bars
    assert len(result.equity_curve) == 10
    assert all("equity" in e and "price" in e and "timestamp" in e for e in result.equity_curve)


# =============================================================================
# _MockPosition tests
# =============================================================================


def test_mock_position_attributes():
    """_MockPosition correctly wraps a BacktestPosition."""
    pos = BacktestPosition(
        product_id="BTC-USD", entry_price=50000.0,
        total_quote_spent=100.0, base_amount=0.002, opened_at=1000,
        safety_orders=2,
    )
    mock = _MockPosition(pos)
    assert mock.product_id == "BTC-USD"
    assert mock.average_buy_price == 50000.0
    assert mock.total_quote_spent == 100.0
    assert mock.status == "open"
    assert mock.direction == "long"
    assert mock.safety_order_count == 2
