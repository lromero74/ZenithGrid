"""
Backtesting Engine

Replays historical candle data through any strategy class and produces
a performance report (P&L, win rate, max drawdown, Sharpe ratio, trade list).

The engine reuses the existing TradingStrategy base class — strategies don't
need modification. A simulated broker handles order fills, position tracking,
and P&L calculation.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.strategies import StrategyRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BacktestTrade:
    """A single simulated trade."""
    product_id: str
    side: str  # "buy" or "sell"
    price: float
    quote_amount: float
    base_amount: float
    timestamp: int
    trade_type: str  # "initial" or "dca" or "sell"


@dataclass
class BacktestPosition:
    """A simulated position."""
    product_id: str
    entry_price: float
    total_quote_spent: float
    base_amount: float
    opened_at: int
    safety_orders: int = 0
    closed_at: Optional[int] = None
    exit_price: Optional[float] = None
    profit_quote: float = 0.0
    profit_pct: float = 0.0


@dataclass
class BacktestResult:
    """Aggregated backtest performance metrics."""
    total_return_pct: float = 0.0
    total_profit_quote: float = 0.0
    initial_capital: float = 0.0
    final_capital: float = 0.0
    num_trades: int = 0
    num_wins: int = 0
    num_losses: int = 0
    win_rate: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    avg_trade_profit: float = 0.0
    avg_trade_duration_bars: float = 0.0
    profit_factor: float = 0.0
    trades: List[BacktestTrade] = field(default_factory=list)
    positions: List[BacktestPosition] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_return_pct": round(self.total_return_pct, 4),
            "total_profit_quote": round(self.total_profit_quote, 6),
            "initial_capital": self.initial_capital,
            "final_capital": round(self.final_capital, 6),
            "num_trades": self.num_trades,
            "num_wins": self.num_wins,
            "num_losses": self.num_losses,
            "win_rate": round(self.win_rate, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4) if not math.isnan(self.sharpe_ratio) else 0.0,
            "avg_trade_profit": round(self.avg_trade_profit, 6),
            "avg_trade_duration_bars": round(self.avg_trade_duration_bars, 2),
            "profit_factor": round(self.profit_factor, 4) if not math.isnan(self.profit_factor) else 0.0,
            "trades": [
                {
                    "product_id": t.product_id, "side": t.side,
                    "price": t.price, "quote_amount": round(t.quote_amount, 6),
                    "base_amount": round(t.base_amount, 8),
                    "timestamp": t.timestamp, "trade_type": t.trade_type,
                }
                for t in self.trades
            ],
            "positions": [
                {
                    "product_id": p.product_id,
                    "entry_price": p.entry_price,
                    "exit_price": p.exit_price,
                    "total_quote_spent": round(p.total_quote_spent, 6),
                    "profit_quote": round(p.profit_quote, 6),
                    "profit_pct": round(p.profit_pct, 4),
                    "opened_at": p.opened_at,
                    "closed_at": p.closed_at,
                    "safety_orders": p.safety_orders,
                }
                for p in self.positions
            ],
            "equity_curve": self.equity_curve,
        }


# ---------------------------------------------------------------------------
# Simulated broker
# ---------------------------------------------------------------------------

class SimulatedBroker:
    """Handles simulated order fills, position tracking, and balance management.

    Simplified compared to the real trading engine: no soft ceiling, no
    budget splitting, no blacklist checks. Just basic order execution
    with position tracking for backtesting purposes.
    """

    def __init__(self, initial_capital: float, fee_pct: float = 0.0):
        self.cash_balance = initial_capital
        self.fee_pct = fee_pct
        self.position: Optional[BacktestPosition] = None
        self.trades: List[BacktestTrade] = []
        self.closed_positions: List[BacktestPosition] = []

    def buy(self, product_id: str, price: float, quote_amount: float,
            timestamp: int, trade_type: str = "initial") -> bool:
        """Execute a simulated buy order."""
        if quote_amount <= 0 or quote_amount > self.cash_balance:
            return False

        fee = quote_amount * self.fee_pct / 100.0
        effective_cost = quote_amount + fee
        if effective_cost > self.cash_balance:
            return False

        base_amount = quote_amount / price if price > 0 else 0

        self.cash_balance -= effective_cost
        self.trades.append(BacktestTrade(
            product_id=product_id, side="buy", price=price,
            quote_amount=quote_amount, base_amount=base_amount,
            timestamp=timestamp, trade_type=trade_type,
        ))

        if self.position is None:
            self.position = BacktestPosition(
                product_id=product_id, entry_price=price,
                total_quote_spent=quote_amount, base_amount=base_amount,
                opened_at=timestamp,
            )
        else:
            # DCA — update average entry
            old_base = self.position.base_amount
            new_base = old_base + base_amount
            self.position.entry_price = (
                (self.position.entry_price * old_base + price * base_amount) / new_base
                if new_base > 0 else price
            )
            self.position.total_quote_spent += quote_amount
            self.position.base_amount = new_base
            self.position.safety_orders += 1

        return True

    def sell(self, product_id: str, price: float, timestamp: int) -> bool:
        """Execute a simulated sell (close entire position)."""
        if self.position is None or self.position.base_amount <= 0:
            return False

        proceeds = self.position.base_amount * price
        fee = proceeds * self.fee_pct / 100.0
        net_proceeds = proceeds - fee

        self.cash_balance += net_proceeds
        profit = net_proceeds - self.position.total_quote_spent
        profit_pct = (
            profit / self.position.total_quote_spent * 100.0
            if self.position.total_quote_spent > 0 else 0.0
        )

        self.trades.append(BacktestTrade(
            product_id=product_id, side="sell", price=price,
            quote_amount=net_proceeds, base_amount=self.position.base_amount,
            timestamp=timestamp, trade_type="sell",
        ))

        self.position.exit_price = price
        self.position.closed_at = timestamp
        self.position.profit_quote = profit
        self.position.profit_pct = profit_pct
        self.closed_positions.append(self.position)
        self.position = None

        return True

    def get_equity(self, current_price: float) -> float:
        """Current total equity (cash + position value)."""
        if self.position and self.position.base_amount > 0:
            return self.cash_balance + self.position.base_amount * current_price
        return self.cash_balance


# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------

async def run_backtest(
    strategy_type: str,
    strategy_config: Dict[str, Any],
    candles: List[Dict[str, Any]],
    product_id: str,
    initial_capital: float = 1000.0,
    fee_pct: float = 0.0,
    user_id: Optional[int] = None,
    account_id: Optional[int] = None,
) -> BacktestResult:
    """Run a backtest by replaying candles through a strategy.

    Args:
        strategy_type: Strategy ID (e.g., "indicator_based", "grid_trading")
        strategy_config: Strategy configuration dict
        candles: Historical candle data (sorted oldest-first)
        product_id: Trading pair being backtested
        initial_capital: Starting quote currency balance
        fee_pct: Trading fee as percentage (e.g., 0.6 for 0.6%)
        user_id: For account scoping (passed to strategy)
        account_id: For account scoping (passed to strategy)

    Returns:
        BacktestResult with all metrics and trade history
    """
    if not candles or len(candles) < 20:
        return BacktestResult(
            initial_capital=initial_capital,
            final_capital=initial_capital,
        )

    # Instantiate strategy
    strategy = StrategyRegistry.get_strategy(strategy_type, strategy_config)
    broker = SimulatedBroker(initial_capital, fee_pct)

    # Warm-up period: need enough candles for indicators
    min_candles = 20
    equity_curve: List[Dict[str, Any]] = []

    # Track peak equity for drawdown calculation
    peak_equity = initial_capital
    max_drawdown = 0.0

    # Track equity over time for Sharpe ratio
    equity_returns: List[float] = []

    prev_equity = initial_capital

    for i in range(min_candles, len(candles)):
        # Slice candles up to current bar (simulating real-time)
        historical = candles[:i + 1]
        current_candle = candles[i]
        current_price = float(current_candle.get("close", 0))
        timestamp = int(float(current_candle.get("start", current_candle.get("time", i * 60))))

        # Build a mock position object for the strategy
        mock_position = None
        if broker.position is not None:
            mock_position = _MockPosition(broker.position)

        # Analyze signal
        try:
            signal_data = await strategy.analyze_signal(
                historical, current_price,
                position=mock_position,
                action_context="hold" if mock_position else "open",
                db=None, user_id=user_id, bot=None, account_id=account_id,
            )
        except Exception as e:
            logger.debug(f"Backtest: analyze_signal error at bar {i}: {e}")
            signal_data = None

        if signal_data is None:
            # No signal — record equity and continue
            equity = broker.get_equity(current_price)
            equity_curve.append({"timestamp": timestamp, "equity": round(equity, 6), "price": current_price})
            _update_drawdown_and_returns(equity, peak_equity, max_drawdown, prev_equity, equity_returns)
            if equity > peak_equity:
                peak_equity = equity
            prev_equity = equity
            continue

        # Check buy signal
        signal_type = signal_data.get("signal_type", signal_data.get("signal", "")).lower()
        should_buy = signal_type == "buy"
        should_sell = signal_type == "sell"

        # If no explicit signal, try should_buy / should_sell
        if not should_buy and not should_sell:
            try:
                should_buy_result = await strategy.should_buy(
                    signal_data, mock_position, broker.cash_balance,
                )
                should_buy = should_buy_result[0] if isinstance(should_buy_result, tuple) else False
            except Exception:
                should_buy = False

            if mock_position and not should_buy:
                try:
                    should_sell_result = await strategy.should_sell(
                        signal_data, mock_position, current_price,
                    )
                    should_sell = should_sell_result[0] if isinstance(should_sell_result, tuple) else False
                except Exception:
                    should_sell = False

        # Execute trades
        if should_buy and broker.cash_balance > 0:
            # Use a reasonable order size (10% of available cash for initial, 5% for DCA)
            if broker.position is None:
                order_size = broker.cash_balance * 0.10
            else:
                order_size = broker.cash_balance * 0.05
            broker.buy(product_id, current_price, order_size, timestamp,
                       "initial" if broker.position is None else "dca")

        if should_sell and broker.position is not None:
            broker.sell(product_id, current_price, timestamp)

        # Record equity
        equity = broker.get_equity(current_price)
        equity_curve.append({"timestamp": timestamp, "equity": round(equity, 6), "price": current_price})
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity * 100.0 if peak_equity > 0 else 0.0
        if dd > max_drawdown:
            max_drawdown = dd
        if prev_equity > 0:
            equity_returns.append((equity - prev_equity) / prev_equity)
        prev_equity = equity

    # Close any remaining position at the last candle's close price
    final_price = float(candles[-1].get("close", 0))
    if broker.position is not None and final_price > 0:
        broker.sell(product_id, final_price, int(float(candles[-1].get("start", 0))))

    final_capital = broker.cash_balance

    # Calculate metrics
    return _compute_metrics(
        initial_capital, final_capital, broker.closed_positions,
        broker.trades, max_drawdown, equity_returns, equity_curve,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockPosition:
    """Lightweight mock position for strategy.evaluate() during backtesting.

    Provides the minimal attributes that strategies check: product_id,
    average_buy_price, total_quote_spent, status, direction, and a few
    DCA-related fields.
    """

    def __init__(self, pos: BacktestPosition):
        self.id = 0
        self.product_id = pos.product_id
        self.average_buy_price = pos.entry_price
        self.total_quote_spent = pos.total_quote_spent
        self.base_amount = pos.base_amount
        self.status = "open"
        self.direction = "long"
        self.max_quote_allowed = pos.total_quote_spent * 2  # Allow DCA room
        self.safety_order_count = pos.safety_orders
        self.short_average_sell_price = None
        self.closing_via_limit = False
        self.limit_close_order_id = None
        self.opened_at = pos.opened_at
        self.closed_at = None
        self.profit_quote = None
        self.profit_percentage = None


def _update_drawdown_and_returns(
    equity: float, peak: float, current_max_dd: float,
    prev_equity: float, returns_list: List[float],
) -> None:
    """Append equity return to list. Caller tracks max drawdown separately."""
    if prev_equity > 0:
        returns_list.append((equity - prev_equity) / prev_equity)


def _compute_metrics(
    initial: float, final: float,
    closed_positions: List[BacktestPosition],
    trades: List[BacktestTrade],
    max_drawdown: float,
    equity_returns: List[float],
    equity_curve: List[Dict[str, Any]],
) -> BacktestResult:
    """Compute all performance metrics from backtest results."""
    total_profit = final - initial
    total_return_pct = (total_profit / initial * 100.0) if initial > 0 else 0.0

    wins = [p for p in closed_positions if p.profit_quote > 0]
    losses = [p for p in closed_positions if p.profit_quote <= 0]
    num_trades = len(closed_positions)
    win_rate = (len(wins) / num_trades * 100.0) if num_trades > 0 else 0.0

    # Profit factor: gross profit / gross loss
    gross_profit = sum(p.profit_quote for p in wins)
    gross_loss = abs(sum(p.profit_quote for p in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

    # Average trade profit and duration
    avg_profit = (total_profit / num_trades) if num_trades > 0 else 0.0
    avg_duration = 0.0
    if closed_positions:
        durations = []
        for p in closed_positions:
            if p.closed_at and p.opened_at:
                durations.append(p.closed_at - p.opened_at)
        avg_duration = (sum(durations) / len(durations)) if durations else 0.0

    # Sharpe ratio (simplified — using equity returns, no risk-free rate)
    sharpe = 0.0
    if len(equity_returns) > 1:
        mean_return = sum(equity_returns) / len(equity_returns)
        variance = sum((r - mean_return) ** 2 for r in equity_returns) / len(equity_returns)
        std_dev = math.sqrt(variance)
        # Annualized (assuming 5-min bars: 252 days * 24h * 12 bars/h)
        sharpe = (mean_return / std_dev * math.sqrt(252 * 24 * 12)) if std_dev > 0 else 0.0

    return BacktestResult(
        total_return_pct=total_return_pct,
        total_profit_quote=total_profit,
        initial_capital=initial,
        final_capital=final,
        num_trades=num_trades,
        num_wins=len(wins),
        num_losses=len(losses),
        win_rate=win_rate,
        max_drawdown_pct=max_drawdown,
        sharpe_ratio=sharpe,
        avg_trade_profit=avg_profit,
        avg_trade_duration_bars=avg_duration,
        profit_factor=profit_factor,
        trades=trades,
        positions=closed_positions,
        equity_curve=equity_curve,
    )
