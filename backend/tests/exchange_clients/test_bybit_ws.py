"""
Tests for backend/app/exchange_clients/bybit_ws.py

Covers:
- ByBitWSState: thread-safe state management (equity, positions, prices, wallet)
- ByBitWSManager: start/stop lifecycle, callback handlers, registry functions
- Module-level registry: get_ws_manager, register, unregister, stop_all
"""

import threading
import types
import sys
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

# =========================================================
# Mock pybit before importing bybit_ws
# pybit may not be installed in the test venv.
# =========================================================
_mock_pybit = types.ModuleType("pybit")
_mock_pybit_unified = types.ModuleType("pybit.unified_trading")
_mock_pybit_unified.HTTP = MagicMock
_mock_pybit_unified.WebSocket = MagicMock
_mock_pybit.unified_trading = _mock_pybit_unified
sys.modules.setdefault("pybit", _mock_pybit)
sys.modules.setdefault("pybit.unified_trading", _mock_pybit_unified)

from app.exchange_clients.bybit_ws import (  # noqa: E402
    ByBitWSState,
    ByBitWSManager,
    get_ws_manager,
    register_ws_manager,
    unregister_ws_manager,
    stop_all_ws_managers,
    _ws_managers,
    _ws_lock,
)


# ===========================================================================
# ByBitWSState tests
# ===========================================================================


class TestByBitWSStateInit:
    """Tests for ByBitWSState initial state."""

    def test_initial_equity_is_zero(self):
        """Happy path: equity starts at 0."""
        state = ByBitWSState()
        assert state.equity == 0.0

    def test_initial_connected_is_false(self):
        """Happy path: connected starts as False."""
        state = ByBitWSState()
        assert state.connected is False

    def test_initial_equity_timestamp_is_none(self):
        """Happy path: no timestamp before any equity update."""
        state = ByBitWSState()
        assert state.equity_timestamp is None


class TestByBitWSStateEquity:
    """Tests for equity get/set."""

    def test_set_and_get_equity(self):
        """Happy path: setting equity is readable."""
        state = ByBitWSState()
        state.equity = 12345.67
        assert state.equity == 12345.67

    def test_equity_sets_timestamp(self):
        """Setting equity records a timestamp."""
        state = ByBitWSState()
        state.equity = 100.0
        assert isinstance(state.equity_timestamp, datetime)

    def test_equity_timestamp_updates_on_each_set(self):
        """Edge case: timestamp changes on subsequent updates."""
        state = ByBitWSState()
        state.equity = 100.0
        ts1 = state.equity_timestamp
        state.equity = 200.0
        ts2 = state.equity_timestamp
        assert ts2 >= ts1

    def test_equity_zero_is_valid(self):
        """Edge case: zero is a valid equity value."""
        state = ByBitWSState()
        state.equity = 0.0
        assert state.equity == 0.0

    def test_equity_negative_is_accepted(self):
        """Edge case: negative equity (margin call scenario) is stored."""
        state = ByBitWSState()
        state.equity = -500.0
        assert state.equity == -500.0


class TestByBitWSStatePositions:
    """Tests for position tracking."""

    def test_update_and_get_position(self):
        """Happy path: store and retrieve a position."""
        state = ByBitWSState()
        pos_data = {"side": "Buy", "size": "0.1"}
        state.update_position("BTCUSDT", pos_data)
        positions = state.get_positions()
        assert "BTCUSDT" in positions
        assert positions["BTCUSDT"]["side"] == "Buy"

    def test_get_positions_returns_copy(self):
        """Edge case: returned dict is a copy, not the internal state."""
        state = ByBitWSState()
        state.update_position("BTCUSDT", {"side": "Buy"})
        p1 = state.get_positions()
        p1["ETHUSDT"] = {"side": "Sell"}
        p2 = state.get_positions()
        assert "ETHUSDT" not in p2

    def test_update_position_overwrites_existing(self):
        """Edge case: updating same symbol replaces data."""
        state = ByBitWSState()
        state.update_position("BTCUSDT", {"side": "Buy"})
        state.update_position("BTCUSDT", {"side": "Sell"})
        assert state.get_positions()["BTCUSDT"]["side"] == "Sell"

    def test_get_positions_empty_when_no_updates(self):
        """Edge case: no positions returns empty dict."""
        state = ByBitWSState()
        assert state.get_positions() == {}


class TestByBitWSStatePrices:
    """Tests for price tracking."""

    def test_update_and_get_price(self):
        """Happy path: store and retrieve a price."""
        state = ByBitWSState()
        state.update_price("BTCUSDT", 50000.0)
        assert state.get_price("BTCUSDT") == 50000.0

    def test_get_price_unknown_symbol_returns_none(self):
        """Edge case: unknown symbol returns None."""
        state = ByBitWSState()
        assert state.get_price("UNKNOWN") is None

    def test_update_price_overwrites(self):
        """Edge case: newer price replaces old."""
        state = ByBitWSState()
        state.update_price("BTCUSDT", 50000.0)
        state.update_price("BTCUSDT", 51000.0)
        assert state.get_price("BTCUSDT") == 51000.0


class TestByBitWSStateWallet:
    """Tests for wallet balance tracking."""

    def test_update_and_get_wallet(self):
        """Happy path: store and retrieve wallet balances."""
        state = ByBitWSState()
        state.update_wallet("USDT", 10000.0)
        wallet = state.get_wallet()
        assert wallet["USDT"] == 10000.0

    def test_get_wallet_returns_copy(self):
        """Edge case: returned dict is a copy."""
        state = ByBitWSState()
        state.update_wallet("USDT", 5000.0)
        w = state.get_wallet()
        w["BTC"] = 1.0
        assert "BTC" not in state.get_wallet()

    def test_update_wallet_multiple_coins(self):
        """Happy path: track multiple coins."""
        state = ByBitWSState()
        state.update_wallet("USDT", 10000.0)
        state.update_wallet("BTC", 0.5)
        wallet = state.get_wallet()
        assert len(wallet) == 2
        assert wallet["BTC"] == 0.5


class TestByBitWSStateSnapshot:
    """Tests for get_snapshot()."""

    def test_snapshot_contains_all_fields(self):
        """Happy path: snapshot has expected keys."""
        state = ByBitWSState()
        snap = state.get_snapshot()
        assert set(snap.keys()) == {
            "equity", "equity_timestamp", "positions",
            "prices", "wallet", "connected"
        }

    def test_snapshot_reflects_current_state(self):
        """Happy path: snapshot captures latest values."""
        state = ByBitWSState()
        state.equity = 5000.0
        state.connected = True
        state.update_price("BTCUSDT", 60000.0)
        state.update_position("BTCUSDT", {"side": "Buy"})
        state.update_wallet("USDT", 3000.0)

        snap = state.get_snapshot()
        assert snap["equity"] == 5000.0
        assert snap["connected"] is True
        assert snap["prices"]["BTCUSDT"] == 60000.0
        assert snap["positions"]["BTCUSDT"]["side"] == "Buy"
        assert snap["wallet"]["USDT"] == 3000.0

    def test_snapshot_returns_copies(self):
        """Edge case: mutating snapshot doesn't affect state."""
        state = ByBitWSState()
        state.update_price("BTCUSDT", 50000.0)
        snap = state.get_snapshot()
        snap["prices"]["ETHUSDT"] = 3000.0
        assert state.get_price("ETHUSDT") is None


class TestByBitWSStateConnected:
    """Tests for connected property."""

    def test_set_connected_true(self):
        """Happy path: set connected to True."""
        state = ByBitWSState()
        state.connected = True
        assert state.connected is True

    def test_set_connected_false(self):
        """Happy path: set connected back to False."""
        state = ByBitWSState()
        state.connected = True
        state.connected = False
        assert state.connected is False


# ===========================================================================
# ByBitWSManager tests
# ===========================================================================


class TestByBitWSManagerInit:
    """Tests for ByBitWSManager initialization."""

    def test_default_symbols(self):
        """Happy path: defaults to BTCUSDT."""
        mgr = ByBitWSManager("key", "secret")
        assert mgr._symbols == ["BTCUSDT"]

    def test_custom_symbols(self):
        """Happy path: custom symbol list stored."""
        mgr = ByBitWSManager("k", "s", symbols=["ETHUSDT", "SOLUSDT"])
        assert mgr._symbols == ["ETHUSDT", "SOLUSDT"]

    def test_state_initialized(self):
        """Happy path: state object is created."""
        mgr = ByBitWSManager("k", "s")
        assert isinstance(mgr.state, ByBitWSState)

    def test_testnet_default_false(self):
        """Happy path: testnet defaults to False."""
        mgr = ByBitWSManager("k", "s")
        assert mgr._testnet is False


class TestByBitWSManagerStartStop:
    """Tests for start/stop lifecycle."""

    def test_start_creates_thread(self):
        """Happy path: start creates a daemon thread."""
        mgr = ByBitWSManager("k", "s")
        with patch.object(mgr, '_run_ws'):
            mgr.start()
            assert mgr._thread is not None
            assert mgr._thread.daemon is True
            mgr.stop()

    def test_start_twice_while_alive_warns(self):
        """Edge case: starting twice while thread is alive skips second start."""
        mgr = ByBitWSManager("k", "s")
        # Make _run_ws block until stop is signaled so thread stays alive

        def blocking_run():
            mgr._stop_event.wait()

        with patch.object(mgr, '_run_ws', side_effect=blocking_run):
            mgr.start()
            first_thread = mgr._thread
            assert first_thread.is_alive()
            mgr.start()  # Should warn, not create new thread
            assert mgr._thread is first_thread
            mgr.stop()

    def test_stop_sets_connected_false(self):
        """Happy path: stop sets state.connected to False."""
        mgr = ByBitWSManager("k", "s")
        mgr.state.connected = True
        mgr.stop()
        assert mgr.state.connected is False

    def test_stop_exits_private_ws(self):
        """Happy path: stop calls exit() on private ws."""
        mgr = ByBitWSManager("k", "s")
        mock_ws = MagicMock()
        mgr._ws_private = mock_ws
        mgr.stop()
        mock_ws.exit.assert_called_once()

    def test_stop_exits_public_ws(self):
        """Happy path: stop calls exit() on public ws."""
        mgr = ByBitWSManager("k", "s")
        mock_ws = MagicMock()
        mgr._ws_public = mock_ws
        mgr.stop()
        mock_ws.exit.assert_called_once()

    def test_stop_handles_exit_exception(self):
        """Failure: stop handles exit() throwing without crashing."""
        mgr = ByBitWSManager("k", "s")
        mock_ws = MagicMock()
        mock_ws.exit.side_effect = RuntimeError("connection lost")
        mgr._ws_private = mock_ws
        mgr.stop()  # Should not raise
        assert mgr.state.connected is False


# ===========================================================================
# Callback handler tests
# ===========================================================================


class TestOnPosition:
    """Tests for _on_position callback."""

    def test_position_update_stored(self):
        """Happy path: position data stored in state."""
        mgr = ByBitWSManager("k", "s")
        message = {"data": [{
            "symbol": "BTCUSDT",
            "side": "Buy",
            "size": "0.1",
            "avgPrice": "50000",
            "markPrice": "50100",
            "unrealisedPnl": "10",
            "leverage": "10",
            "liqPrice": "45000",
        }]}
        mgr._on_position(message)
        positions = mgr.state.get_positions()
        assert "BTCUSDT" in positions
        assert positions["BTCUSDT"]["side"] == "Buy"
        assert positions["BTCUSDT"]["entry_price"] == "50000"
        assert positions["BTCUSDT"]["unrealized_pnl"] == "10"

    def test_multiple_positions_in_single_message(self):
        """Happy path: multiple positions in one message."""
        mgr = ByBitWSManager("k", "s")
        message = {"data": [
            {"symbol": "BTCUSDT", "side": "Buy", "size": "0.1"},
            {"symbol": "ETHUSDT", "side": "Sell", "size": "1.0"},
        ]}
        mgr._on_position(message)
        positions = mgr.state.get_positions()
        assert len(positions) == 2

    def test_empty_data_does_nothing(self):
        """Edge case: empty data array causes no changes."""
        mgr = ByBitWSManager("k", "s")
        mgr._on_position({"data": []})
        assert mgr.state.get_positions() == {}

    def test_missing_data_key_does_not_crash(self):
        """Failure: message without 'data' key doesn't crash."""
        mgr = ByBitWSManager("k", "s")
        mgr._on_position({})
        assert mgr.state.get_positions() == {}

    def test_missing_fields_default_to_empty(self):
        """Edge case: missing fields get default empty strings/zeros."""
        mgr = ByBitWSManager("k", "s")
        message = {"data": [{"symbol": "BTCUSDT"}]}
        mgr._on_position(message)
        pos = mgr.state.get_positions()["BTCUSDT"]
        assert pos["side"] == ""
        assert pos["size"] == "0"


class TestOnWallet:
    """Tests for _on_wallet callback."""

    def test_wallet_equity_update(self):
        """Happy path: equity is set from wallet update."""
        mgr = ByBitWSManager("k", "s")
        message = {"data": [{
            "totalEquity": "15000.50",
            "coin": [
                {"coin": "USDT", "availableToWithdraw": "10000"},
                {"coin": "BTC", "availableToWithdraw": "0.1"},
            ]
        }]}
        mgr._on_wallet(message)
        assert mgr.state.equity == pytest.approx(15000.50)
        wallet = mgr.state.get_wallet()
        assert wallet["USDT"] == pytest.approx(10000.0)
        assert wallet["BTC"] == pytest.approx(0.1)

    def test_zero_equity_not_set(self):
        """Edge case: zero equity is ignored (condition: equity > 0)."""
        mgr = ByBitWSManager("k", "s")
        mgr.state.equity = 5000.0
        message = {"data": [{"totalEquity": "0", "coin": []}]}
        mgr._on_wallet(message)
        assert mgr.state.equity == pytest.approx(5000.0)

    def test_equity_callback_called(self):
        """Happy path: on_equity_update callback fires."""
        callback = MagicMock()
        mgr = ByBitWSManager("k", "s", on_equity_update=callback)
        message = {"data": [{"totalEquity": "8000", "coin": []}]}
        mgr._on_wallet(message)
        callback.assert_called_once_with(8000.0)

    def test_no_callback_when_none(self):
        """Edge case: no callback set, still works."""
        mgr = ByBitWSManager("k", "s", on_equity_update=None)
        message = {"data": [{"totalEquity": "8000", "coin": []}]}
        mgr._on_wallet(message)  # Should not raise
        assert mgr.state.equity == pytest.approx(8000.0)

    def test_wallet_update_empty_data(self):
        """Edge case: empty data list."""
        mgr = ByBitWSManager("k", "s")
        mgr._on_wallet({"data": []})
        assert mgr.state.get_wallet() == {}


class TestOnTicker:
    """Tests for _on_ticker callback."""

    def test_ticker_updates_price(self):
        """Happy path: ticker price stored in state."""
        mgr = ByBitWSManager("k", "s")
        message = {"data": {"symbol": "BTCUSDT", "lastPrice": "51234.56"}}
        mgr._on_ticker(message)
        assert mgr.state.get_price("BTCUSDT") == pytest.approx(51234.56)

    def test_ticker_empty_symbol_ignored(self):
        """Edge case: empty symbol string skips update."""
        mgr = ByBitWSManager("k", "s")
        message = {"data": {"symbol": "", "lastPrice": "100"}}
        mgr._on_ticker(message)
        assert mgr.state.get_price("") is None

    def test_ticker_empty_price_ignored(self):
        """Edge case: empty lastPrice string skips update."""
        mgr = ByBitWSManager("k", "s")
        message = {"data": {"symbol": "BTCUSDT", "lastPrice": ""}}
        mgr._on_ticker(message)
        assert mgr.state.get_price("BTCUSDT") is None

    def test_ticker_missing_data_key(self):
        """Failure: missing data key doesn't crash."""
        mgr = ByBitWSManager("k", "s")
        mgr._on_ticker({})
        # Should not crash, data defaults to {}


class TestOnOrder:
    """Tests for _on_order callback."""

    def test_order_update_logs(self):
        """Happy path: order update processes without error."""
        mgr = ByBitWSManager("k", "s")
        message = {"data": [{
            "symbol": "BTCUSDT",
            "side": "Buy",
            "orderStatus": "Filled",
        }]}
        mgr._on_order(message)  # Primarily logs, just verify no crash

    def test_order_empty_data(self):
        """Edge case: empty data list."""
        mgr = ByBitWSManager("k", "s")
        mgr._on_order({"data": []})  # Should not crash

    def test_order_missing_data_key(self):
        """Failure: missing data key."""
        mgr = ByBitWSManager("k", "s")
        mgr._on_order({})  # Should not crash


# ===========================================================================
# Module-level registry tests
# ===========================================================================


class TestWSManagerRegistry:
    """Tests for get/register/unregister/stop_all functions."""

    def setup_method(self):
        """Clear registry before each test."""
        with _ws_lock:
            # Stop any existing managers
            for m in _ws_managers.values():
                try:
                    m.stop()
                except Exception:
                    pass
            _ws_managers.clear()

    def test_get_ws_manager_returns_none_when_empty(self):
        """Happy path: no manager registered returns None."""
        assert get_ws_manager(999) is None

    def test_register_and_get_ws_manager(self):
        """Happy path: register then retrieve."""
        mgr = ByBitWSManager("k", "s")
        register_ws_manager(1, mgr)
        assert get_ws_manager(1) is mgr

    def test_register_stops_existing_manager(self):
        """Edge case: registering same account_id stops old manager."""
        old_mgr = MagicMock(spec=ByBitWSManager)
        register_ws_manager(1, old_mgr)
        new_mgr = ByBitWSManager("k", "s")
        register_ws_manager(1, new_mgr)
        old_mgr.stop.assert_called_once()
        assert get_ws_manager(1) is new_mgr

    def test_unregister_stops_and_removes(self):
        """Happy path: unregister stops manager and removes it."""
        mgr = MagicMock(spec=ByBitWSManager)
        register_ws_manager(2, mgr)
        unregister_ws_manager(2)
        mgr.stop.assert_called_once()
        assert get_ws_manager(2) is None

    def test_unregister_nonexistent_does_nothing(self):
        """Edge case: unregistering unknown ID doesn't crash."""
        unregister_ws_manager(9999)  # Should not raise

    def test_stop_all_clears_registry(self):
        """Happy path: stop_all stops everything and clears."""
        mgr1 = MagicMock(spec=ByBitWSManager)
        mgr2 = MagicMock(spec=ByBitWSManager)
        register_ws_manager(1, mgr1)
        register_ws_manager(2, mgr2)
        stop_all_ws_managers()
        mgr1.stop.assert_called()
        mgr2.stop.assert_called()
        assert get_ws_manager(1) is None
        assert get_ws_manager(2) is None


class TestByBitWSStateThreadSafety:
    """Verify thread-safe access to state."""

    def test_concurrent_equity_updates(self):
        """Edge case: concurrent writes don't corrupt state."""
        state = ByBitWSState()
        errors = []

        def writer(val):
            try:
                for _ in range(100):
                    state.equity = val
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=writer, args=(100.0,))
        t2 = threading.Thread(target=writer, args=(200.0,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0
        assert state.equity in (100.0, 200.0)

    def test_concurrent_price_updates(self):
        """Edge case: concurrent price writes don't crash."""
        state = ByBitWSState()
        errors = []

        def writer(symbol, val):
            try:
                for _ in range(100):
                    state.update_price(symbol, val)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=writer, args=("BTCUSDT", 50000.0))
        t2 = threading.Thread(target=writer, args=("ETHUSDT", 3000.0))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0
        assert state.get_price("BTCUSDT") == 50000.0
        assert state.get_price("ETHUSDT") == 3000.0
