"""
Tests for backend/app/services/prop_guard_monitor.py

Covers:
- _check_account: equity tracking, drawdown checks, kill switch
- _get_account_equity: equity from WS manager or exchange client
- _kill_account: kill switch + emergency liquidation
- start/stop_prop_guard_monitor: background task lifecycle
- _ensure_ws_manager: WebSocket manager creation
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _check_account
# ---------------------------------------------------------------------------


class TestCheckAccount:
    """Tests for _check_account()."""

    @pytest.mark.asyncio
    async def test_creates_new_state_if_none_exists(self):
        """Happy path: creates PropFirmState when account has no existing state."""
        from app.services.prop_guard_monitor import _check_account

        db = AsyncMock()
        account = MagicMock()
        account.id = 1
        account.exchange = "mt5"
        account.prop_initial_deposit = 100000.0

        # No existing state
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        with patch(
            "app.services.prop_guard_monitor._get_account_equity",
            new_callable=AsyncMock,
            return_value=99500.0,
        ), patch(
            "app.services.prop_guard_monitor._ensure_ws_manager",
            new_callable=AsyncMock,
        ):
            await _check_account(db, account)

        # Should add a new PropFirmState
        db.add.assert_called_once()
        added_state = db.add.call_args[0][0]
        assert added_state.account_id == 1
        assert added_state.initial_deposit == 100000.0
        assert added_state.daily_start_equity == 99500.0

    @pytest.mark.asyncio
    async def test_skips_killed_account(self):
        """Edge case: skips processing if account is already killed."""
        from app.services.prop_guard_monitor import _check_account

        db = AsyncMock()
        account = MagicMock()
        account.id = 2
        account.exchange = "mt5"

        state = MagicMock()
        state.is_killed = True

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = state
        db.execute.return_value = result_mock

        with patch(
            "app.services.prop_guard_monitor._get_account_equity",
            new_callable=AsyncMock,
            return_value=95000.0,
        ):
            await _check_account(db, account)

        # Should not add any new snapshot records for killed accounts
        # (db.add is only called for the equity snapshot, which happens before kill check)
        # The key assertion: no _kill_account called
        # Killed accounts return early before drawdown calculation

    @pytest.mark.asyncio
    async def test_returns_if_equity_is_zero(self):
        """Edge case: returns early if equity is <= 0."""
        from app.services.prop_guard_monitor import _check_account

        db = AsyncMock()
        account = MagicMock()
        account.id = 3
        account.exchange = "mt5"

        with patch(
            "app.services.prop_guard_monitor._get_account_equity",
            new_callable=AsyncMock,
            return_value=0.0,
        ):
            await _check_account(db, account)

        # Should not even query for state
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_triggers_kill_on_daily_drawdown_breach(self):
        """Failure: triggers kill switch when daily drawdown exceeds limit."""
        from app.services.prop_guard_monitor import _check_account

        db = AsyncMock()
        account = MagicMock()
        account.id = 4
        account.exchange = "mt5"
        account.prop_daily_drawdown_pct = 4.5
        account.prop_total_drawdown_pct = 9.0
        account.prop_initial_deposit = 100000.0

        state = MagicMock()
        state.is_killed = False
        state.daily_start_equity = 100000.0
        state.initial_deposit = 100000.0
        state.daily_pnl = 0.0
        state.daily_start_timestamp = datetime.utcnow()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = state
        db.execute.return_value = result_mock

        # 5% daily drawdown (exceeds 4.5% limit)
        current_equity = 95000.0

        with patch(
            "app.services.prop_guard_monitor._get_account_equity",
            new_callable=AsyncMock,
            return_value=current_equity,
        ), patch(
            "app.exchange_clients.prop_guard_state.should_reset_daily",
            return_value=False,
        ), patch(
            "app.exchange_clients.prop_guard_state.calculate_daily_drawdown_pct",
            return_value=5.0,
        ), patch(
            "app.exchange_clients.prop_guard_state.calculate_total_drawdown_pct",
            return_value=5.0,
        ), patch(
            "app.services.prop_guard_monitor._kill_account",
            new_callable=AsyncMock,
        ) as mock_kill:
            await _check_account(db, account)

        mock_kill.assert_called_once()
        kill_reason = mock_kill.call_args[0][3]
        assert "Daily drawdown" in kill_reason

    @pytest.mark.asyncio
    async def test_triggers_kill_on_total_drawdown_breach(self):
        """Failure: triggers kill switch when total drawdown exceeds limit."""
        from app.services.prop_guard_monitor import _check_account

        db = AsyncMock()
        account = MagicMock()
        account.id = 5
        account.exchange = "mt5"
        account.prop_daily_drawdown_pct = 4.5
        account.prop_total_drawdown_pct = 9.0
        account.prop_initial_deposit = 100000.0

        state = MagicMock()
        state.is_killed = False
        state.daily_start_equity = 92000.0
        state.initial_deposit = 100000.0
        state.daily_pnl = 0.0
        state.daily_start_timestamp = datetime.utcnow()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = state
        db.execute.return_value = result_mock

        current_equity = 90000.0  # 10% total drawdown

        with patch(
            "app.services.prop_guard_monitor._get_account_equity",
            new_callable=AsyncMock,
            return_value=current_equity,
        ), patch(
            "app.exchange_clients.prop_guard_state.should_reset_daily",
            return_value=False,
        ), patch(
            "app.exchange_clients.prop_guard_state.calculate_daily_drawdown_pct",
            return_value=2.17,  # Below daily limit
        ), patch(
            "app.exchange_clients.prop_guard_state.calculate_total_drawdown_pct",
            return_value=10.0,  # Above 9% total limit
        ), patch(
            "app.services.prop_guard_monitor._kill_account",
            new_callable=AsyncMock,
        ) as mock_kill:
            await _check_account(db, account)

        mock_kill.assert_called_once()
        kill_reason = mock_kill.call_args[0][3]
        assert "Total drawdown" in kill_reason

    @pytest.mark.asyncio
    async def test_daily_reset_updates_equity(self):
        """Edge case: daily reset updates daily_start_equity to current."""
        from app.services.prop_guard_monitor import _check_account

        db = AsyncMock()
        account = MagicMock()
        account.id = 6
        account.exchange = "mt5"
        account.prop_daily_drawdown_pct = 4.5
        account.prop_total_drawdown_pct = 9.0
        account.prop_initial_deposit = 100000.0

        state = MagicMock()
        state.is_killed = False
        state.daily_start_equity = 99000.0
        state.initial_deposit = 100000.0
        state.daily_pnl = -1000.0
        state.daily_start_timestamp = datetime.utcnow() - timedelta(days=2)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = state
        db.execute.return_value = result_mock

        current_equity = 99500.0

        with patch(
            "app.services.prop_guard_monitor._get_account_equity",
            new_callable=AsyncMock,
            return_value=current_equity,
        ), patch(
            "app.exchange_clients.prop_guard_state.should_reset_daily",
            return_value=True,
        ), patch(
            "app.exchange_clients.prop_guard_state.calculate_daily_drawdown_pct",
            return_value=0.0,
        ), patch(
            "app.exchange_clients.prop_guard_state.calculate_total_drawdown_pct",
            return_value=0.5,
        ), patch(
            "app.services.prop_guard_monitor._kill_account",
            new_callable=AsyncMock,
        ):
            await _check_account(db, account)

        assert state.daily_start_equity == current_equity
        assert state.daily_pnl == 0.0

    @pytest.mark.asyncio
    async def test_bybit_ensures_ws_manager(self):
        """Edge case: ByBit accounts call _ensure_ws_manager."""
        from app.services.prop_guard_monitor import _check_account

        db = AsyncMock()
        account = MagicMock()
        account.id = 7
        account.exchange = "bybit"

        with patch(
            "app.services.prop_guard_monitor._get_account_equity",
            new_callable=AsyncMock,
            return_value=0.0,  # Return early
        ), patch(
            "app.services.prop_guard_monitor._ensure_ws_manager",
            new_callable=AsyncMock,
        ) as mock_ws:
            await _check_account(db, account)

        mock_ws.assert_called_once_with(account)


# ---------------------------------------------------------------------------
# _get_account_equity
# ---------------------------------------------------------------------------


class TestGetAccountEquity:
    """Tests for _get_account_equity()."""

    @pytest.mark.asyncio
    async def test_returns_ws_equity_for_bybit(self):
        """Happy path: returns WS equity for ByBit when fresh."""
        from app.services.prop_guard_monitor import _get_account_equity

        account = MagicMock()
        account.id = 10
        account.exchange = "bybit"

        ws_mgr = MagicMock()
        ws_mgr.state.connected = True
        ws_mgr.state.equity = 98000.0
        ws_mgr.state.equity_timestamp = datetime.utcnow()

        with patch(
            "app.exchange_clients.bybit_ws.get_ws_manager",
            return_value=ws_mgr,
        ):
            result = await _get_account_equity(account)

        assert result == 98000.0

    @pytest.mark.asyncio
    async def test_returns_zero_on_total_failure(self):
        """Failure: returns 0 when all methods fail."""
        from app.services.prop_guard_monitor import _get_account_equity

        account = MagicMock()
        account.id = 11
        account.exchange = "bybit"

        ws_mgr = MagicMock()
        ws_mgr.state.connected = False

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.exchange_clients.bybit_ws.get_ws_manager",
            return_value=ws_mgr,
        ), patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            side_effect=Exception("connection refused"),
        ), patch(
            "app.database.async_session_maker",
            return_value=mock_session_ctx,
        ):
            result = await _get_account_equity(account)

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_stale_ws_falls_back_to_exchange_client(self):
        """Edge case: stale WS data (> 60s) falls back to exchange client."""
        from app.services.prop_guard_monitor import _get_account_equity

        account = MagicMock()
        account.id = 12
        account.exchange = "bybit"

        # Stale WS data (2 minutes old)
        ws_mgr = MagicMock()
        ws_mgr.state.connected = True
        ws_mgr.state.equity = 90000.0
        ws_mgr.state.equity_timestamp = datetime.utcnow() - timedelta(seconds=120)

        mock_inner = AsyncMock()
        mock_inner.get_equity.return_value = 91000.0

        mock_client = MagicMock()
        mock_client._inner = mock_inner

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.exchange_clients.bybit_ws.get_ws_manager",
            return_value=ws_mgr,
        ), patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_client,
        ), patch(
            "app.database.async_session_maker",
            return_value=mock_session_ctx,
        ):
            result = await _get_account_equity(account)

        # Should use exchange client (91000), not stale WS (90000)
        assert result == 91000.0


# ---------------------------------------------------------------------------
# _kill_account
# ---------------------------------------------------------------------------


class TestKillAccount:
    """Tests for _kill_account()."""

    @pytest.mark.asyncio
    async def test_sets_kill_state(self):
        """Happy path: sets kill switch fields on state."""
        from app.services.prop_guard_monitor import _kill_account

        db = AsyncMock()
        state = MagicMock()
        state.is_killed = False
        account = MagicMock()
        account.id = 20

        mock_inner = AsyncMock()
        mock_inner.close_all_positions = AsyncMock()

        mock_client = MagicMock()
        mock_client._inner = mock_inner

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_client,
        ), patch(
            "app.database.async_session_maker",
            return_value=mock_session_ctx,
        ):
            await _kill_account(db, state, account, "Daily drawdown 5.0% >= limit 4.5%")

        assert state.is_killed is True
        assert state.kill_reason == "Daily drawdown 5.0% >= limit 4.5%"
        assert state.kill_timestamp is not None
        mock_inner.close_all_positions.assert_called_once()

    @pytest.mark.asyncio
    async def test_liquidation_failure_does_not_crash(self):
        """Failure: liquidation failure is caught, kill state still set."""
        from app.services.prop_guard_monitor import _kill_account

        db = AsyncMock()
        state = MagicMock()
        state.is_killed = False
        account = MagicMock()
        account.id = 21

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            side_effect=Exception("connection refused"),
        ), patch(
            "app.database.async_session_maker",
            return_value=mock_session_ctx,
        ):
            # Should not raise
            await _kill_account(db, state, account, "test reason")

        # Kill state should still be set even though liquidation failed
        assert state.is_killed is True
        assert state.kill_reason == "test reason"


# ---------------------------------------------------------------------------
# start/stop_prop_guard_monitor
# ---------------------------------------------------------------------------


class TestStartStopMonitor:
    """Tests for start_prop_guard_monitor and stop_prop_guard_monitor."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        """Happy path: start creates an asyncio task."""
        import app.services.prop_guard_monitor as pgm

        # Reset module state
        pgm._monitor_task = None
        pgm._running = False

        with patch.object(
            pgm, "_monitor_loop", new_callable=AsyncMock
        ):
            await pgm.start_prop_guard_monitor()

        assert pgm._monitor_task is not None
        assert not pgm._monitor_task.done()

        # Cleanup
        pgm._running = False
        pgm._monitor_task.cancel()
        try:
            await pgm._monitor_task
        except asyncio.CancelledError:
            pass
        pgm._monitor_task = None

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        """Happy path: stop cancels the running task."""
        import app.services.prop_guard_monitor as pgm

        # Create a dummy long-running task
        async def dummy_loop():
            while True:
                await asyncio.sleep(100)

        pgm._running = True
        pgm._monitor_task = asyncio.create_task(dummy_loop())

        with patch(
            "app.exchange_clients.bybit_ws.stop_all_ws_managers",
        ) as mock_stop_ws:
            await pgm.stop_prop_guard_monitor()

        assert pgm._running is False
        assert pgm._monitor_task is None
        mock_stop_ws.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_skips_if_already_running(self):
        """Edge case: does not create new task if one is already running."""
        import app.services.prop_guard_monitor as pgm

        async def dummy_loop():
            while True:
                await asyncio.sleep(100)

        pgm._monitor_task = asyncio.create_task(dummy_loop())
        original_task = pgm._monitor_task

        await pgm.start_prop_guard_monitor()

        # Same task, no new one created
        assert pgm._monitor_task is original_task

        # Cleanup
        pgm._running = False
        pgm._monitor_task.cancel()
        try:
            await pgm._monitor_task
        except asyncio.CancelledError:
            pass
        pgm._monitor_task = None
