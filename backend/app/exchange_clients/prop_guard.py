"""
PropGuard Safety Middleware

Decorator ExchangeClient that wraps any inner client and intercepts
order methods with pre-flight safety checks for prop firm accounts.

- Kill switch (persisted across restarts)
- Daily drawdown limit (resets at 17:00 EST)
- Total drawdown limit
- Spread guard (defer trade if spread too wide)
- BTC volatility buffer (reduce size in high vol)

All other methods pass through unchanged to the inner client.
PropGuard receives a db_session_maker callable rather than importing
database modules (avoids circular imports).
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from app.exchange_clients.base import ExchangeClient
from app.exchange_clients.prop_guard_state import (
    adjust_size_for_volatility,
    calculate_btc_volatility,
    calculate_daily_drawdown_pct,
    calculate_spread_pct,
    calculate_total_drawdown_pct,
    should_reset_daily,
)

# Per-account locks to serialize order execution through PropGuard.
# Prevents two simultaneous orders from both passing preflight checks
# independently and collectively breaching drawdown limits.
_account_locks: dict[int, asyncio.Lock] = {}


def _get_account_lock(account_id: int) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific account."""
    if account_id not in _account_locks:
        _account_locks[account_id] = asyncio.Lock()
    return _account_locks[account_id]


logger = logging.getLogger(__name__)


class PropGuardClient(ExchangeClient):
    """
    Safety decorator wrapping any ExchangeClient for prop firm accounts.

    Intercepts create_market_order / create_limit_order with pre-flight
    checks. All other methods delegate to the inner client unchanged.

    Args:
        inner: The wrapped ExchangeClient (ByBitAdapter, MT5BridgeClient)
        account_id: Database account ID
        db_session_maker: Async session maker callable (avoids imports)
        daily_drawdown_pct: Max daily drawdown % before kill
        total_drawdown_pct: Max total drawdown % before kill
        initial_deposit: Starting capital for total drawdown calc
        spread_threshold_pct: Max acceptable spread % (default 0.5)
        volatility_threshold: Vol threshold for size reduction
        volatility_reduction_pct: Size reduction when vol > threshold
        ws_state: Optional ByBitWSState for real-time equity
    """

    def __init__(
        self,
        inner: ExchangeClient,
        account_id: int,
        db_session_maker: Callable,
        daily_drawdown_pct: float = 4.5,
        total_drawdown_pct: float = 9.0,
        initial_deposit: float = 100000.0,
        spread_threshold_pct: float = 0.5,
        volatility_threshold: float = 2.0,
        volatility_reduction_pct: float = 0.20,
        ws_state: Optional[Any] = None,
    ):
        self._inner = inner
        self._account_id = account_id
        self._db_session_maker = db_session_maker
        self._daily_dd_limit = daily_drawdown_pct
        self._total_dd_limit = total_drawdown_pct
        self._initial_deposit = initial_deposit
        self._spread_threshold = spread_threshold_pct
        self._vol_threshold = volatility_threshold
        self._vol_reduction = volatility_reduction_pct
        self._ws_state = ws_state
        self._order_lock = _get_account_lock(account_id)

    # ==========================================================
    # PROPGUARD PRE-FLIGHT CHECKS
    # ==========================================================

    async def _load_state(self) -> Optional[dict]:
        """Load PropFirmState from database.

        Returns:
            State dict if found, None if no state record exists.
        Raises:
            RuntimeError: If database is unavailable (fail-safe).
        """
        try:
            # Late import to avoid circular dependencies
            from sqlalchemy import select
            async with self._db_session_maker() as db:
                from app.models import PropFirmState
                result = await db.execute(
                    select(PropFirmState).where(
                        PropFirmState.account_id == self._account_id
                    )
                )
                state = result.scalar_one_or_none()
                if state:
                    return {
                        "is_killed": state.is_killed,
                        "kill_reason": state.kill_reason,
                        "daily_start_equity": state.daily_start_equity,
                        "daily_start_timestamp": state.daily_start_timestamp,
                        "initial_deposit": state.initial_deposit,
                        "current_equity": state.current_equity,
                    }
                return None
        except Exception as e:
            logger.error(
                f"PropGuard: Failed to load state "
                f"for account {self._account_id}: {e}"
            )
            # Fail-safe: if we can't verify safety state, block all orders
            raise RuntimeError(
                f"PropGuard: Database unavailable — cannot verify "
                f"safety state for account {self._account_id}"
            )

    async def _save_kill_state(
        self, reason: str
    ):
        """Save kill switch to database."""
        try:
            from sqlalchemy import select
            async with self._db_session_maker() as db:
                from app.models import PropFirmState
                result = await db.execute(
                    select(PropFirmState).where(
                        PropFirmState.account_id == self._account_id
                    )
                )
                state = result.scalar_one_or_none()
                if state:
                    state.is_killed = True
                    state.kill_reason = reason
                    state.kill_timestamp = datetime.utcnow()
                else:
                    state = PropFirmState(
                        account_id=self._account_id,
                        initial_deposit=self._initial_deposit,
                        is_killed=True,
                        kill_reason=reason,
                        kill_timestamp=datetime.utcnow(),
                    )
                    db.add(state)
                await db.commit()
        except Exception as e:
            logger.critical(
                f"PropGuard: FAILED to save kill state: {e}"
            )

    async def _update_equity(self, equity: float):
        """Update current equity in database."""
        try:
            from sqlalchemy import select
            async with self._db_session_maker() as db:
                from app.models import PropFirmState
                result = await db.execute(
                    select(PropFirmState).where(
                        PropFirmState.account_id == self._account_id
                    )
                )
                state = result.scalar_one_or_none()
                if state:
                    state.current_equity = equity
                    state.current_equity_timestamp = datetime.utcnow()
                    await db.commit()
        except Exception as e:
            logger.error(
                f"PropGuard: Failed to update equity: {e}"
            )

    # Maximum age for WS equity data before falling back to REST
    _WS_EQUITY_MAX_AGE_SECONDS = 60

    async def _get_current_equity(self) -> float:
        """Get current equity from WS state or REST.

        Returns:
            Current equity in USD. Returns 0.0 only if all sources fail,
            which will cause _preflight_check to block the order.
        """
        # Try WebSocket state first (sub-second) with staleness check
        if self._ws_state and self._ws_state.connected:
            eq = self._ws_state.equity
            eq_ts = self._ws_state.equity_timestamp
            if eq > 0 and eq_ts:
                age = (datetime.utcnow() - eq_ts).total_seconds()
                if age <= self._WS_EQUITY_MAX_AGE_SECONDS:
                    return eq
                logger.warning(
                    f"PropGuard: WS equity stale ({age:.0f}s old) "
                    f"for account {self._account_id} — falling "
                    f"back to REST"
                )

        # Fallback to REST (with error handling)
        try:
            if hasattr(self._inner, 'get_equity'):
                eq = await self._inner.get_equity()
                if eq > 0:
                    return eq
        except Exception as e:
            logger.error(
                f"PropGuard: get_equity() failed for account "
                f"{self._account_id}: {e}"
            )

        # Ultimate fallback: aggregate USD value
        try:
            return await self._inner.calculate_aggregate_usd_value()
        except Exception as e:
            logger.error(
                f"PropGuard: calculate_aggregate_usd_value() failed "
                f"for account {self._account_id}: {e}"
            )

        # All equity sources failed — return 0 which blocks orders
        # via "Cannot determine current equity" check
        return 0.0

    async def _preflight_check(
        self, product_id: str
    ) -> Optional[str]:
        """
        Run all pre-flight checks before an order.

        Returns:
            None if all checks pass.
            Error message string if order should be blocked.
        """
        # 1. Kill switch check (fail-safe: block on DB error)
        try:
            state = await self._load_state()
        except RuntimeError as e:
            return str(e)
        if state and state.get("is_killed"):
            reason = state.get("kill_reason", "Unknown")
            return f"KILL SWITCH ACTIVE: {reason}"

        # Get current equity (guard against NaN, negative, and zero)
        current_equity = await self._get_current_equity()
        import math
        if math.isnan(current_equity) or math.isinf(current_equity):
            return "Equity returned invalid value (NaN/Inf)"
        if current_equity <= 0:
            return "Cannot determine current equity"

        await self._update_equity(current_equity)

        initial_deposit = self._initial_deposit
        daily_start_equity = None
        daily_start_ts = None

        if state:
            initial_deposit = (
                state.get("initial_deposit") or self._initial_deposit
            )
            daily_start_equity = state.get("daily_start_equity")
            daily_start_ts = state.get("daily_start_timestamp")

        # 2. Daily reset check
        if should_reset_daily(daily_start_ts):
            # Snapshot new daily start equity (fail-safe: block on error)
            try:
                await self._snapshot_daily_start(current_equity)
            except RuntimeError as e:
                return str(e)
            daily_start_equity = current_equity

        # 3. Daily drawdown check
        if daily_start_equity and daily_start_equity > 0:
            daily_dd = calculate_daily_drawdown_pct(
                daily_start_equity, current_equity
            )
            if daily_dd >= self._daily_dd_limit:
                reason = (
                    f"Daily drawdown {daily_dd:.2f}% "
                    f">= limit {self._daily_dd_limit}%"
                )
                logger.critical(
                    f"PropGuard KILL: {reason} "
                    f"(account {self._account_id})"
                )
                await self._trigger_kill(reason)
                return f"KILL SWITCH TRIGGERED: {reason}"

        # 4. Total drawdown check
        if initial_deposit > 0:
            total_dd = calculate_total_drawdown_pct(
                initial_deposit, current_equity
            )
            if total_dd >= self._total_dd_limit:
                reason = (
                    f"Total drawdown {total_dd:.2f}% "
                    f">= limit {self._total_dd_limit}%"
                )
                logger.critical(
                    f"PropGuard KILL: {reason} "
                    f"(account {self._account_id})"
                )
                await self._trigger_kill(reason)
                return f"KILL SWITCH TRIGGERED: {reason}"

        # 5. Spread guard
        try:
            ticker = await self._inner.get_ticker(product_id)
            bid = float(ticker.get("bid", 0))
            ask = float(ticker.get("ask", 0))
            if bid > 0 and ask > 0:
                spread = calculate_spread_pct(bid, ask)
                if spread > self._spread_threshold:
                    return (
                        f"Spread too wide: {spread:.3f}% "
                        f"> {self._spread_threshold}% — "
                        f"deferring trade"
                    )
            else:
                # No valid bid/ask — can't verify spread safety
                logger.warning(
                    f"PropGuard: No valid bid/ask for {product_id} "
                    f"(bid={bid}, ask={ask}) — deferring trade "
                    f"for safety"
                )
                return (
                    f"Cannot verify spread for {product_id} "
                    f"(bid={bid}, ask={ask}) — deferring trade"
                )
        except Exception as e:
            logger.warning(
                f"PropGuard: Spread check failed for "
                f"{product_id}: {e} — deferring trade"
            )
            return (
                f"Spread check failed: {type(e).__name__} "
                f"— deferring trade"
            )

        # All checks passed
        return None

    async def _trigger_kill(self, reason: str):
        """Trigger kill switch: save state + liquidate."""
        await self._save_kill_state(reason)

        # Emergency liquidation
        try:
            if hasattr(self._inner, 'close_all_positions'):
                await self._inner.close_all_positions()
                logger.critical(
                    f"PropGuard: Emergency liquidation executed "
                    f"for account {self._account_id}"
                )
            else:
                logger.critical(
                    f"PropGuard: CANNOT LIQUIDATE account "
                    f"{self._account_id} — inner client "
                    f"({type(self._inner).__name__}) has no "
                    f"close_all_positions method. "
                    f"MANUAL INTERVENTION REQUIRED."
                )
        except Exception as e:
            logger.critical(
                f"PropGuard: Liquidation FAILED for account "
                f"{self._account_id}: {e}. "
                f"MANUAL INTERVENTION REQUIRED."
            )

    async def _snapshot_daily_start(self, equity: float):
        """Save new daily start equity snapshot."""
        try:
            from sqlalchemy import select
            async with self._db_session_maker() as db:
                from app.models import PropFirmState
                result = await db.execute(
                    select(PropFirmState).where(
                        PropFirmState.account_id == self._account_id
                    )
                )
                state = result.scalar_one_or_none()
                now = datetime.utcnow()
                if state:
                    state.daily_start_equity = equity
                    state.daily_start_timestamp = now
                    state.daily_pnl = 0.0
                else:
                    state = PropFirmState(
                        account_id=self._account_id,
                        initial_deposit=self._initial_deposit,
                        daily_start_equity=equity,
                        daily_start_timestamp=now,
                        current_equity=equity,
                        current_equity_timestamp=now,
                    )
                    db.add(state)
                await db.commit()
        except Exception as e:
            logger.error(
                f"PropGuard: Failed to snapshot daily start: {e}"
            )
            raise RuntimeError(
                f"PropGuard: Daily reset failed — cannot verify "
                f"drawdown baseline for account {self._account_id}"
            )

    async def _apply_volatility_adjustment(
        self,
        size_str: Optional[str],
        funds_str: Optional[str],
        product_id: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Reduce size/funds if volatility is high.

        Handles both size-based and funds-based orders.
        On failure, applies a precautionary reduction rather than
        skipping the safety check entirely.

        Returns:
            (adjusted_size, adjusted_funds) tuple.
        """
        if not size_str and not funds_str:
            return size_str, funds_str

        def _reduce(val_str: Optional[str], factor: float) -> Optional[str]:
            if not val_str:
                return val_str
            return str(float(val_str) * (1 - factor))

        try:
            import time
            now = int(time.time())
            candles = await self._inner.get_candles(
                product_id=product_id,
                start=now - 3600,
                end=now,
                granularity="ONE_HOUR",
            )
            if candles:
                vol = calculate_btc_volatility(candles)
                if vol > self._vol_threshold:
                    logger.info(
                        f"PropGuard: Vol {vol:.2f}% > "
                        f"{self._vol_threshold}%, "
                        f"reducing order by {self._vol_reduction:.0%}"
                    )
                    if size_str:
                        adjusted = adjust_size_for_volatility(
                            float(size_str),
                            vol,
                            self._vol_threshold,
                            self._vol_reduction,
                        )
                        size_str = str(adjusted)
                    if funds_str:
                        adjusted = adjust_size_for_volatility(
                            float(funds_str),
                            vol,
                            self._vol_threshold,
                            self._vol_reduction,
                        )
                        funds_str = str(adjusted)
                return size_str, funds_str
            else:
                logger.warning(
                    f"PropGuard: No candle data for {product_id} "
                    f"volatility check — applying precautionary "
                    f"{self._vol_reduction:.0%} reduction"
                )
                return (
                    _reduce(size_str, self._vol_reduction),
                    _reduce(funds_str, self._vol_reduction),
                )
        except Exception as e:
            logger.warning(
                f"PropGuard: Volatility check failed for "
                f"{product_id}: {type(e).__name__} — applying "
                f"precautionary {self._vol_reduction:.0%} reduction"
            )
            return (
                _reduce(size_str, self._vol_reduction),
                _reduce(funds_str, self._vol_reduction),
            )

    # ==========================================================
    # INTERCEPTED ORDER METHODS
    # ==========================================================

    async def create_market_order(
        self,
        product_id: str,
        side: str,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        async with self._order_lock:
            # Pre-flight check (serialized per account)
            block_reason = await self._preflight_check(product_id)
            if block_reason:
                logger.warning(
                    f"PropGuard BLOCKED order: {block_reason}"
                )
                return {
                    "success": False,
                    "error": block_reason,
                    "blocked_by": "propguard",
                }

            # Volatility adjustment (handles both size and funds)
            size, funds = await self._apply_volatility_adjustment(
                size, funds, product_id
            )

            return await self._inner.create_market_order(
                product_id=product_id,
                side=side,
                size=size,
                funds=funds,
            )

    async def create_limit_order(
        self,
        product_id: str,
        side: str,
        limit_price: float,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        async with self._order_lock:
            block_reason = await self._preflight_check(product_id)
            if block_reason:
                logger.warning(
                    f"PropGuard BLOCKED order: {block_reason}"
                )
                return {
                    "success": False,
                    "error": block_reason,
                    "blocked_by": "propguard",
                }

            size, funds = await self._apply_volatility_adjustment(
                size, funds, product_id
            )

            return await self._inner.create_limit_order(
                product_id=product_id,
                side=side,
                limit_price=limit_price,
                size=size,
                funds=funds,
            )

    # ==========================================================
    # PASS-THROUGH METHODS (delegate to inner client)
    # ==========================================================

    async def get_accounts(
        self, force_fresh: bool = False
    ) -> List[Dict[str, Any]]:
        return await self._inner.get_accounts(force_fresh)

    async def get_account(self, account_id: str) -> Dict[str, Any]:
        return await self._inner.get_account(account_id)

    async def get_btc_balance(self) -> float:
        return await self._inner.get_btc_balance()

    async def get_eth_balance(self) -> float:
        return await self._inner.get_eth_balance()

    async def get_usd_balance(self) -> float:
        return await self._inner.get_usd_balance()

    async def get_balance(self, currency: str) -> Dict[str, Any]:
        return await self._inner.get_balance(currency)

    async def invalidate_balance_cache(self):
        return await self._inner.invalidate_balance_cache()

    async def calculate_aggregate_btc_value(
        self, bypass_cache: bool = False
    ) -> float:
        return await self._inner.calculate_aggregate_btc_value(
            bypass_cache
        )

    async def calculate_aggregate_usd_value(self) -> float:
        return await self._inner.calculate_aggregate_usd_value()

    async def list_products(self) -> List[Dict[str, Any]]:
        return await self._inner.list_products()

    async def get_product(
        self, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        return await self._inner.get_product(product_id)

    async def get_ticker(
        self, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        return await self._inner.get_ticker(product_id)

    async def get_current_price(
        self, product_id: str = "ETH-BTC"
    ) -> float:
        return await self._inner.get_current_price(product_id)

    async def get_btc_usd_price(self) -> float:
        return await self._inner.get_btc_usd_price()

    async def get_eth_usd_price(self) -> float:
        return await self._inner.get_eth_usd_price()

    async def get_product_stats(
        self, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        return await self._inner.get_product_stats(product_id)

    async def get_candles(
        self,
        product_id: str,
        start: int,
        end: int,
        granularity: str,
    ) -> List[Dict[str, Any]]:
        return await self._inner.get_candles(
            product_id, start, end, granularity
        )

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        return await self._inner.get_order(order_id)

    async def edit_order(
        self,
        order_id: str,
        price: Optional[str] = None,
        size: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._inner.edit_order(
            order_id, price=price, size=size
        )

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return await self._inner.cancel_order(order_id)

    async def list_orders(
        self,
        product_id: Optional[str] = None,
        order_status: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self._inner.list_orders(
            product_id, order_status, limit
        )

    async def buy_eth_with_btc(
        self, btc_amount: float, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        return await self.create_market_order(
            product_id=product_id,
            side="BUY",
            funds=str(btc_amount),
        )

    async def sell_eth_for_btc(
        self, eth_amount: float, product_id: str = "ETH-BTC"
    ) -> Dict[str, Any]:
        return await self.create_market_order(
            product_id=product_id,
            side="SELL",
            size=str(eth_amount),
        )

    async def buy_with_usd(
        self, usd_amount: float, product_id: str
    ) -> Dict[str, Any]:
        return await self.create_market_order(
            product_id=product_id,
            side="BUY",
            funds=str(usd_amount),
        )

    async def sell_for_usd(
        self, base_amount: float, product_id: str
    ) -> Dict[str, Any]:
        return await self.create_market_order(
            product_id=product_id,
            side="SELL",
            size=str(base_amount),
        )

    def get_exchange_type(self) -> str:
        return self._inner.get_exchange_type()

    async def test_connection(self) -> bool:
        return await self._inner.test_connection()

    # ==========================================================
    # PROPGUARD STATUS (for API endpoints)
    # ==========================================================

    async def get_propguard_status(self) -> dict:
        """Get current PropGuard status for API response."""
        state = await self._load_state()
        equity = await self._get_current_equity()

        daily_dd = 0.0
        total_dd = 0.0
        daily_start = None

        if state:
            daily_start = state.get("daily_start_equity")
            initial = state.get("initial_deposit", self._initial_deposit)
            if daily_start and daily_start > 0:
                daily_dd = calculate_daily_drawdown_pct(
                    daily_start, equity
                )
            if initial > 0:
                total_dd = calculate_total_drawdown_pct(
                    initial, equity
                )

        return {
            "account_id": self._account_id,
            "current_equity": equity,
            "initial_deposit": self._initial_deposit,
            "daily_start_equity": daily_start,
            "daily_drawdown_pct": round(daily_dd, 2),
            "daily_drawdown_limit": self._daily_dd_limit,
            "total_drawdown_pct": round(total_dd, 2),
            "total_drawdown_limit": self._total_dd_limit,
            "is_killed": (
                state.get("is_killed", False) if state else False
            ),
            "kill_reason": (
                state.get("kill_reason") if state else None
            ),
        }
