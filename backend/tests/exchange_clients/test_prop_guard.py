"""
Tests for backend/app/exchange_clients/prop_guard.py

Tests the PropGuard safety middleware that wraps exchange clients
with pre-flight safety checks for prop firm accounts.

All database interactions and inner client methods are mocked.
"""

from datetime import datetime, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.exchange_clients.prop_guard import (
    PropGuardClient,
    _get_account_lock,
)


# =========================================================
# Fixtures
# =========================================================


def _make_mock_inner_client(
    equity=95000.0,
    ticker_bid=50000.0,
    ticker_ask=50010.0,
):
    """Create a mock inner exchange client."""
    client = AsyncMock()
    client.get_equity = AsyncMock(return_value=equity)
    client.calculate_aggregate_usd_value = AsyncMock(return_value=equity)
    client.get_ticker = AsyncMock(return_value={
        "bid": str(ticker_bid),
        "ask": str(ticker_ask),
    })
    client.get_candles = AsyncMock(return_value=[
        {"close": "50000"},
        {"close": "50100"},
        {"close": "50050"},
    ])
    client.create_market_order = AsyncMock(return_value={
        "success": True,
        "order_id": "test-order-1",
    })
    client.create_limit_order = AsyncMock(return_value={
        "success": True,
        "order_id": "test-order-2",
    })
    client.get_exchange_type = MagicMock(return_value="cex")
    client.test_connection = AsyncMock(return_value=True)
    client.get_accounts = AsyncMock(return_value=[])
    client.get_account = AsyncMock(return_value={})
    client.get_btc_balance = AsyncMock(return_value=0.5)
    client.get_eth_balance = AsyncMock(return_value=5.0)
    client.get_usd_balance = AsyncMock(return_value=50000.0)
    client.get_balance = AsyncMock(return_value={"currency": "BTC", "available": "0.5"})
    client.invalidate_balance_cache = AsyncMock()
    client.calculate_aggregate_btc_value = AsyncMock(return_value=2.0)
    client.list_products = AsyncMock(return_value=[])
    client.get_product = AsyncMock(return_value={})
    client.get_current_price = AsyncMock(return_value=50000.0)
    client.get_btc_usd_price = AsyncMock(return_value=50000.0)
    client.get_eth_usd_price = AsyncMock(return_value=3000.0)
    client.get_product_stats = AsyncMock(return_value={})
    client.get_order = AsyncMock(return_value={})
    client.edit_order = AsyncMock(return_value={})
    client.cancel_order = AsyncMock(return_value={})
    client.list_orders = AsyncMock(return_value=[])
    client.close_all_positions = AsyncMock()
    return client


def _make_mock_db_session_maker(state=None):
    """Create a mock db_session_maker that returns controllable state.

    Args:
        state: A PropFirmState-like MagicMock or None.
    """
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = state

    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    # The session maker is an async context manager
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

    return mock_session_maker


def _make_prop_firm_state(
    is_killed=False,
    kill_reason=None,
    daily_start_equity=100000.0,
    daily_start_timestamp=None,
    initial_deposit=100000.0,
    current_equity=95000.0,
):
    """Create a mock PropFirmState record."""
    state = MagicMock()
    state.is_killed = is_killed
    state.kill_reason = kill_reason
    state.daily_start_equity = daily_start_equity
    state.daily_start_timestamp = (
        daily_start_timestamp or datetime.utcnow()
    )
    state.initial_deposit = initial_deposit
    state.current_equity = current_equity
    return state


# =========================================================
# Initialization & metadata
# =========================================================


class TestPropGuardInit:
    """Tests for PropGuardClient initialization."""

    def test_init_stores_parameters(self):
        """Happy path: stores all configuration parameters."""
        inner = _make_mock_inner_client()
        db_maker = _make_mock_db_session_maker()

        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            daily_drawdown_pct=4.5,
            total_drawdown_pct=9.0,
            initial_deposit=100000.0,
        )

        assert guard._inner is inner
        assert guard._account_id == 1
        assert guard._daily_dd_limit == 4.5
        assert guard._total_dd_limit == 9.0
        assert guard._initial_deposit == 100000.0

    def test_exchange_type_delegates_to_inner(self):
        """Happy path: exchange type comes from inner client."""
        inner = _make_mock_inner_client()
        db_maker = _make_mock_db_session_maker()
        guard = PropGuardClient(inner=inner, account_id=1, db_session_maker=db_maker)

        assert guard.get_exchange_type() == "cex"


class TestAccountLock:
    """Tests for per-account locking."""

    def test_same_account_gets_same_lock(self):
        """Happy path: same account_id returns same lock object."""
        lock1 = _get_account_lock(999)
        lock2 = _get_account_lock(999)
        assert lock1 is lock2

    def test_different_accounts_get_different_locks(self):
        """Edge case: different account_ids get separate locks."""
        lock1 = _get_account_lock(1001)
        lock2 = _get_account_lock(1002)
        assert lock1 is not lock2


# =========================================================
# Pass-through methods
# =========================================================


class TestPassThroughMethods:
    """Tests that non-order methods delegate to inner client."""

    @pytest.mark.asyncio
    async def test_get_accounts_passes_through(self):
        """Happy path: get_accounts delegates to inner."""
        inner = _make_mock_inner_client()
        db_maker = _make_mock_db_session_maker()
        guard = PropGuardClient(inner=inner, account_id=1, db_session_maker=db_maker)

        await guard.get_accounts(force_fresh=True)
        inner.get_accounts.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_get_ticker_passes_through(self):
        """Happy path: get_ticker delegates to inner."""
        inner = _make_mock_inner_client()
        db_maker = _make_mock_db_session_maker()
        guard = PropGuardClient(inner=inner, account_id=1, db_session_maker=db_maker)

        await guard.get_ticker("BTC-USD")
        inner.get_ticker.assert_called_once_with("BTC-USD")

    @pytest.mark.asyncio
    async def test_test_connection_passes_through(self):
        """Happy path: test_connection delegates to inner."""
        inner = _make_mock_inner_client()
        db_maker = _make_mock_db_session_maker()
        guard = PropGuardClient(inner=inner, account_id=1, db_session_maker=db_maker)

        result = await guard.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_order_passes_through(self):
        """Happy path: get_order delegates to inner."""
        inner = _make_mock_inner_client()
        db_maker = _make_mock_db_session_maker()
        guard = PropGuardClient(inner=inner, account_id=1, db_session_maker=db_maker)

        await guard.get_order("order-1")
        inner.get_order.assert_called_once_with("order-1")


# =========================================================
# Preflight: kill switch
# =========================================================


class TestPreflightKillSwitch:
    """Tests for kill switch detection in preflight checks."""

    @pytest.mark.asyncio
    async def test_killed_account_blocks_market_order(self):
        """Happy path: killed account blocks order."""
        state = _make_prop_firm_state(is_killed=True, kill_reason="Daily DD breach")
        inner = _make_mock_inner_client()
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(inner=inner, account_id=1, db_session_maker=db_maker)

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is False
        assert "KILL SWITCH ACTIVE" in result["error"]
        assert result["blocked_by"] == "propguard"
        # Inner client should NOT have been called
        inner.create_market_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_killed_account_blocks_limit_order(self):
        """Happy path: killed account also blocks limit orders."""
        state = _make_prop_firm_state(is_killed=True, kill_reason="Total DD breach")
        inner = _make_mock_inner_client()
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(inner=inner, account_id=1, db_session_maker=db_maker)

        result = await guard.create_limit_order(
            product_id="BTC-USD", side="BUY", limit_price=49000.0, size="0.1"
        )

        assert result["success"] is False
        assert "KILL SWITCH ACTIVE" in result["error"]


# =========================================================
# Preflight: daily drawdown
# =========================================================


class TestPreflightDailyDrawdown:
    """Tests for daily drawdown detection."""

    @pytest.mark.asyncio
    async def test_daily_drawdown_triggers_kill(self):
        """Happy path: daily drawdown exceeding limit triggers kill."""
        # daily_start=100000, current=95000 -> 5% DD > 4.5% limit
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
            current_equity=95000.0,
        )
        inner = _make_mock_inner_client(equity=95000.0)
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            daily_drawdown_pct=4.5,
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is False
        assert "KILL SWITCH TRIGGERED" in result["error"]
        assert "Daily drawdown" in result["error"]

    @pytest.mark.asyncio
    async def test_daily_drawdown_within_limit_passes(self):
        """Happy path: drawdown within limit allows order."""
        # daily_start=100000, current=97000 -> 3% DD < 4.5% limit
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=97000.0)
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            daily_drawdown_pct=4.5,
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is True
        inner.create_market_order.assert_called_once()


# =========================================================
# Preflight: total drawdown
# =========================================================


class TestPreflightTotalDrawdown:
    """Tests for total drawdown detection."""

    @pytest.mark.asyncio
    async def test_total_drawdown_triggers_kill(self):
        """Happy path: total drawdown exceeding limit triggers kill."""
        # initial=100000, daily_start=90000 (already lost 10% total)
        # current=90000 -> 0% daily DD (won't trigger daily)
        # but total DD = (100000-90000)/100000 = 10% > 9% limit
        state = _make_prop_firm_state(
            daily_start_equity=90000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=90000.0)
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            daily_drawdown_pct=10.0,  # Won't trigger daily (0% DD)
            total_drawdown_pct=9.0,   # Will trigger total (10% > 9%)
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is False
        assert "Total drawdown" in result["error"]


# =========================================================
# Preflight: spread guard
# =========================================================


class TestPreflightSpreadGuard:
    """Tests for spread guard checks."""

    @pytest.mark.asyncio
    async def test_wide_spread_defers_order(self):
        """Happy path: wide spread defers the trade."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        # Spread = (50100 - 50000) / 50000 = 0.2% < 0.5% default
        # But we set a 0.1% threshold to trigger deferral at 0.2%
        inner = _make_mock_inner_client(
            equity=99000.0,
            ticker_bid=50000.0,
            ticker_ask=50100.0,
        )
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            spread_threshold_pct=0.1,
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is False
        assert "Spread too wide" in result["error"]

    @pytest.mark.asyncio
    async def test_narrow_spread_passes(self):
        """Happy path: narrow spread allows order."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(
            equity=99000.0,
            ticker_bid=50000.0,
            ticker_ask=50010.0,  # 0.02% spread < 0.5%
        )
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_zero_bid_defers_order(self):
        """Edge case: zero bid defers the order for safety."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=99000.0)
        inner.get_ticker = AsyncMock(return_value={"bid": "0", "ask": "50000"})
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is False
        assert "Cannot verify spread" in result["error"]

    @pytest.mark.asyncio
    async def test_ticker_failure_defers_order(self):
        """Failure case: ticker fetch failure defers the order."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=99000.0)
        inner.get_ticker = AsyncMock(side_effect=Exception("Network error"))
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is False
        assert "Spread check failed" in result["error"]


# =========================================================
# Preflight: equity checks
# =========================================================


class TestPreflightEquity:
    """Tests for equity determination edge cases."""

    @pytest.mark.asyncio
    async def test_zero_equity_blocks_order(self):
        """Failure case: zero equity blocks the order."""
        state = _make_prop_firm_state()
        inner = _make_mock_inner_client(equity=0.0)
        inner.get_equity = AsyncMock(return_value=0.0)
        inner.calculate_aggregate_usd_value = AsyncMock(return_value=0.0)
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is False
        assert "Cannot determine current equity" in result["error"]

    @pytest.mark.asyncio
    async def test_nan_equity_blocks_order(self):
        """Failure case: NaN equity blocks the order."""
        state = _make_prop_firm_state()
        inner = _make_mock_inner_client()
        inner.get_equity = AsyncMock(return_value=float('nan'))
        inner.calculate_aggregate_usd_value = AsyncMock(return_value=float('nan'))
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is False
        assert "invalid value" in result["error"]

    @pytest.mark.asyncio
    async def test_ws_equity_preferred_when_fresh(self):
        """Happy path: WebSocket equity used when available and fresh."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client()
        db_maker = _make_mock_db_session_maker(state=state)

        # Mock WS state
        ws_state = MagicMock()
        ws_state.connected = True
        ws_state.equity = 98000.0
        ws_state.equity_timestamp = datetime.utcnow()

        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            ws_state=ws_state,
        )

        # Run preflight -- should use WS equity (98000) not REST
        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        # 2% daily DD < 4.5% limit, should pass
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_stale_ws_equity_falls_back_to_rest(self):
        """Edge case: stale WS equity falls back to REST."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=97000.0)
        db_maker = _make_mock_db_session_maker(state=state)

        # Mock stale WS state (>60s old)
        ws_state = MagicMock()
        ws_state.connected = True
        ws_state.equity = 98000.0
        ws_state.equity_timestamp = datetime.utcnow() - timedelta(seconds=120)

        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            ws_state=ws_state,
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        # Should have fallen back to REST (equity=97000)
        assert result["success"] is True


# =========================================================
# Preflight: no state (first run)
# =========================================================


class TestPreflightNoState:
    """Tests for first-run scenario with no PropFirmState record."""

    @pytest.mark.asyncio
    async def test_no_state_record_passes_if_healthy(self):
        """Happy path: no state record, healthy equity passes."""
        inner = _make_mock_inner_client(equity=99000.0)
        db_maker = _make_mock_db_session_maker(state=None)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            initial_deposit=100000.0,
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_db_error_blocks_order(self):
        """Failure case: database error blocks order (fail-safe)."""
        inner = _make_mock_inner_client(equity=99000.0)
        db_maker = MagicMock()
        db_maker.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("DB connection failed")
        )
        db_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
        )

        result = await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )

        assert result["success"] is False
        # Should contain error about database
        assert "PropGuard" in result["error"]


# =========================================================
# Volatility adjustment
# =========================================================


class TestVolatilityAdjustment:
    """Tests for volatility-based size adjustment."""

    @pytest.mark.asyncio
    async def test_high_volatility_reduces_size(self):
        """Happy path: high vol reduces order size."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=99000.0)
        # Return candles that produce high volatility
        inner.get_candles = AsyncMock(return_value=[
            {"close": "50000"},
            {"close": "55000"},
            {"close": "45000"},
            {"close": "52000"},
        ])
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            volatility_threshold=0.1,  # Very low threshold to trigger
            volatility_reduction_pct=0.20,
        )

        await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="1.0"
        )

        # The inner client should have been called with a reduced size
        call_kwargs = inner.create_market_order.call_args[1]
        actual_size = float(call_kwargs["size"])
        assert actual_size < 1.0

    @pytest.mark.asyncio
    async def test_low_volatility_no_reduction(self):
        """Happy path: low vol keeps original size."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=99000.0)
        # Stable prices = low vol
        inner.get_candles = AsyncMock(return_value=[
            {"close": "50000"},
            {"close": "50001"},
            {"close": "50002"},
        ])
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            volatility_threshold=50.0,  # Very high threshold - won't trigger
        )

        await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="1.0"
        )

        call_kwargs = inner.create_market_order.call_args[1]
        assert call_kwargs["size"] == "1.0"

    @pytest.mark.asyncio
    async def test_candle_fetch_failure_applies_precautionary_reduction(self):
        """Failure case: candle fetch failure applies precautionary reduction."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=99000.0)
        inner.get_candles = AsyncMock(side_effect=Exception("API error"))
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            volatility_reduction_pct=0.20,
        )

        await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="1.0"
        )

        call_kwargs = inner.create_market_order.call_args[1]
        actual_size = float(call_kwargs["size"])
        assert actual_size == pytest.approx(0.8)  # 20% precautionary reduction

    @pytest.mark.asyncio
    async def test_no_candle_data_applies_precautionary_reduction(self):
        """Edge case: empty candle data applies precautionary reduction."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=99000.0)
        inner.get_candles = AsyncMock(return_value=[])
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            volatility_reduction_pct=0.20,
        )

        await guard.create_market_order(
            product_id="BTC-USD", side="BUY", size="1.0"
        )

        call_kwargs = inner.create_market_order.call_args[1]
        actual_size = float(call_kwargs["size"])
        assert actual_size == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_volatility_adjustment_on_funds(self):
        """Happy path: volatility adjustment also works on funds parameter."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=99000.0)
        inner.get_candles = AsyncMock(return_value=[])  # Empty -> precautionary
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            volatility_reduction_pct=0.20,
        )

        await guard.create_market_order(
            product_id="BTC-USD", side="BUY", funds="1000"
        )

        call_kwargs = inner.create_market_order.call_args[1]
        actual_funds = float(call_kwargs["funds"])
        assert actual_funds == pytest.approx(800.0)

    @pytest.mark.asyncio
    async def test_no_size_no_funds_skips_volatility(self):
        """Edge case: no size or funds means nothing to adjust."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=99000.0)
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
        )

        await guard.create_market_order(
            product_id="BTC-USD", side="BUY",
        )

        # Should still call inner (no adjustment, just pass None through)
        inner.create_market_order.assert_called_once()


# =========================================================
# Convenience methods route through preflight
# =========================================================


class TestConvenienceMethodsRouteThroughPreflight:
    """Tests that convenience methods go through preflight checks."""

    @pytest.mark.asyncio
    async def test_buy_eth_with_btc_uses_create_market_order(self):
        """Happy path: convenience method routes through create_market_order."""
        state = _make_prop_firm_state(is_killed=True, kill_reason="Test kill")
        inner = _make_mock_inner_client()
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
        )

        # Should be blocked by kill switch
        result = await guard.buy_eth_with_btc(0.5)
        assert result["success"] is False
        assert "KILL SWITCH" in result["error"]

    @pytest.mark.asyncio
    async def test_sell_for_usd_uses_create_market_order(self):
        """Happy path: sell_for_usd routes through preflight."""
        state = _make_prop_firm_state(is_killed=True, kill_reason="Test kill")
        inner = _make_mock_inner_client()
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
        )

        result = await guard.sell_for_usd(0.1, "BTC-USD")
        assert result["success"] is False


# =========================================================
# PropGuard status
# =========================================================


class TestPropGuardStatus:
    """Tests for get_propguard_status API response."""

    @pytest.mark.asyncio
    async def test_status_with_active_state(self):
        """Happy path: returns full status when state exists."""
        state = _make_prop_firm_state(
            daily_start_equity=100000.0,
            initial_deposit=100000.0,
        )
        inner = _make_mock_inner_client(equity=97000.0)
        db_maker = _make_mock_db_session_maker(state=state)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            daily_drawdown_pct=4.5,
            total_drawdown_pct=9.0,
            initial_deposit=100000.0,
        )

        status = await guard.get_propguard_status()

        assert status["account_id"] == 1
        assert status["current_equity"] == 97000.0
        assert status["daily_drawdown_pct"] == 3.0  # (100000-97000)/100000*100
        assert status["total_drawdown_pct"] == 3.0
        assert status["daily_drawdown_limit"] == 4.5
        assert status["total_drawdown_limit"] == 9.0
        assert status["is_killed"] is False

    @pytest.mark.asyncio
    async def test_status_with_no_state(self):
        """Edge case: no state record returns defaults."""
        inner = _make_mock_inner_client(equity=100000.0)
        db_maker = _make_mock_db_session_maker(state=None)
        guard = PropGuardClient(
            inner=inner,
            account_id=1,
            db_session_maker=db_maker,
            initial_deposit=100000.0,
        )

        status = await guard.get_propguard_status()

        assert status["is_killed"] is False
        assert status["daily_drawdown_pct"] == 0.0
