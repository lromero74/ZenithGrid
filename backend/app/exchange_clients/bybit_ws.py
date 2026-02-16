"""
ByBit WebSocket Manager

Real-time streams via pybit WebSocket for:
- Position changes (unrealized P&L updates)
- Order fills and rejections
- Wallet balance changes
- Public ticker for mark price

PropGuard reads shared state for sub-second drawdown monitoring.
pybit handles reconnection + re-subscription automatically.
"""

import logging
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ByBitWSState:
    """Thread-safe shared state updated by WebSocket callbacks."""

    def __init__(self):
        self._lock = threading.Lock()
        self._equity: float = 0.0
        self._equity_ts: Optional[datetime] = None
        self._positions: Dict[str, dict] = {}
        self._last_price: Dict[str, float] = {}
        self._wallet_balance: Dict[str, float] = {}
        self._connected: bool = False

    @property
    def equity(self) -> float:
        with self._lock:
            return self._equity

    @equity.setter
    def equity(self, value: float):
        with self._lock:
            self._equity = value
            self._equity_ts = datetime.utcnow()

    @property
    def equity_timestamp(self) -> Optional[datetime]:
        with self._lock:
            return self._equity_ts

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @connected.setter
    def connected(self, value: bool):
        with self._lock:
            self._connected = value

    def update_position(self, symbol: str, data: dict):
        with self._lock:
            self._positions[symbol] = data

    def get_positions(self) -> Dict[str, dict]:
        with self._lock:
            return dict(self._positions)

    def update_price(self, symbol: str, price: float):
        with self._lock:
            self._last_price[symbol] = price

    def get_price(self, symbol: str) -> Optional[float]:
        with self._lock:
            return self._last_price.get(symbol)

    def update_wallet(self, coin: str, available: float):
        with self._lock:
            self._wallet_balance[coin] = available

    def get_wallet(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._wallet_balance)

    def get_snapshot(self) -> dict:
        """Get a point-in-time snapshot of all state."""
        with self._lock:
            return {
                "equity": self._equity,
                "equity_timestamp": self._equity_ts,
                "positions": dict(self._positions),
                "prices": dict(self._last_price),
                "wallet": dict(self._wallet_balance),
                "connected": self._connected,
            }


class ByBitWSManager:
    """
    Manages ByBit WebSocket connections for a single account.

    Starts private (authenticated) and public streams in a
    background thread. State is readable from async context
    via the shared ByBitWSState object.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        symbols: Optional[List[str]] = None,
        on_equity_update: Optional[Callable[[float], None]] = None,
    ):
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet
        self._symbols = symbols or ["BTCUSDT"]
        self._on_equity_update = on_equity_update

        self.state = ByBitWSState()
        self._ws_private = None
        self._ws_public = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        """Start WebSocket connections in background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("ByBit WS already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_ws,
            daemon=True,
            name="bybit-ws-manager",
        )
        self._thread.start()
        logger.info("ByBit WebSocket manager started")

    def stop(self):
        """Stop WebSocket connections."""
        self._stop_event.set()
        self.state.connected = False

        if self._ws_private:
            try:
                self._ws_private.exit()
            except Exception:
                pass

        if self._ws_public:
            try:
                self._ws_public.exit()
            except Exception:
                pass

        if self._thread:
            self._thread.join(timeout=5)

        logger.info("ByBit WebSocket manager stopped")

    def _run_ws(self):
        """Run WebSocket connections (blocking, in thread)."""
        try:
            from pybit.unified_trading import WebSocket

            # Private WebSocket (authenticated)
            self._ws_private = WebSocket(
                testnet=self._testnet,
                channel_type="private",
                api_key=self._api_key,
                api_secret=self._api_secret,
            )

            # Subscribe to private streams
            self._ws_private.position_stream(
                callback=self._on_position
            )
            self._ws_private.order_stream(
                callback=self._on_order
            )
            self._ws_private.wallet_stream(
                callback=self._on_wallet
            )

            # Public WebSocket (unauthenticated)
            self._ws_public = WebSocket(
                testnet=self._testnet,
                channel_type="linear",
            )

            # Subscribe to ticker for each symbol
            for symbol in self._symbols:
                self._ws_public.ticker_stream(
                    symbol=symbol,
                    callback=self._on_ticker,
                )

            self.state.connected = True
            logger.info(
                f"ByBit WS connected (symbols: {self._symbols})"
            )

            # Keep thread alive until stop signal
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=1.0)

        except Exception as e:
            logger.error(f"ByBit WebSocket error: {e}")
            self.state.connected = False

    # ----------------------------------------------------------
    # Callbacks (run in pybit's thread)
    # ----------------------------------------------------------

    def _on_position(self, message: dict):
        """Handle position updates."""
        try:
            data = message.get("data", [])
            for pos in data:
                symbol = pos.get("symbol", "")
                self.state.update_position(symbol, {
                    "side": pos.get("side", ""),
                    "size": pos.get("size", "0"),
                    "entry_price": pos.get("avgPrice", "0"),
                    "mark_price": pos.get("markPrice", "0"),
                    "unrealized_pnl": pos.get(
                        "unrealisedPnl", "0"
                    ),
                    "leverage": pos.get("leverage", "1"),
                    "liq_price": pos.get("liqPrice", "0"),
                })
        except Exception as e:
            logger.error(f"Error processing position update: {e}")

    def _on_order(self, message: dict):
        """Handle order updates (fills, rejections)."""
        try:
            data = message.get("data", [])
            for order in data:
                status = order.get("orderStatus", "")
                symbol = order.get("symbol", "")
                side = order.get("side", "")
                logger.info(
                    f"ByBit order update: {symbol} {side} "
                    f"status={status}"
                )
        except Exception as e:
            logger.error(f"Error processing order update: {e}")

    def _on_wallet(self, message: dict):
        """Handle wallet/balance updates."""
        try:
            data = message.get("data", [])
            for acct in data:
                # Update equity
                equity = float(acct.get("totalEquity", "0"))
                if equity > 0:
                    self.state.equity = equity
                    if self._on_equity_update:
                        self._on_equity_update(equity)

                # Update per-coin balances
                for coin_info in acct.get("coin", []):
                    coin = coin_info.get("coin", "")
                    available = float(
                        coin_info.get(
                            "availableToWithdraw", "0"
                        )
                    )
                    self.state.update_wallet(coin, available)
        except Exception as e:
            logger.error(f"Error processing wallet update: {e}")

    def _on_ticker(self, message: dict):
        """Handle public ticker updates."""
        try:
            data = message.get("data", {})
            symbol = data.get("symbol", "")
            last_price = data.get("lastPrice", "")
            if symbol and last_price:
                self.state.update_price(
                    symbol, float(last_price)
                )
        except Exception as e:
            logger.error(f"Error processing ticker update: {e}")


# Registry of active WS managers (account_id -> manager)
_ws_managers: Dict[int, ByBitWSManager] = {}
_ws_lock = threading.Lock()


def get_ws_manager(account_id: int) -> Optional[ByBitWSManager]:
    """Get active WS manager for an account."""
    with _ws_lock:
        return _ws_managers.get(account_id)


def register_ws_manager(
    account_id: int, manager: ByBitWSManager
):
    """Register a WS manager for an account."""
    with _ws_lock:
        # Stop existing manager if any
        existing = _ws_managers.get(account_id)
        if existing:
            existing.stop()
        _ws_managers[account_id] = manager


def unregister_ws_manager(account_id: int):
    """Stop and unregister a WS manager."""
    with _ws_lock:
        manager = _ws_managers.pop(account_id, None)
        if manager:
            manager.stop()


def stop_all_ws_managers():
    """Stop all WS managers (for shutdown)."""
    with _ws_lock:
        for manager in _ws_managers.values():
            manager.stop()
        _ws_managers.clear()
    logger.info("All ByBit WS managers stopped")
