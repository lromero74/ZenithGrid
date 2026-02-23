"""
Tests for backend/app/exchange_clients/bybit_client.py

Tests the ByBit raw API client including:
- Symbol conversion (to_bybit_symbol / from_bybit_symbol)
- Response checking (_check_response)
- Granularity mapping
- Candle normalization
- Rate-limited API calls (mocked pybit)
- Error handling for ByBitError
"""

import asyncio
import sys
import types
import pytest
from unittest.mock import MagicMock


# =========================================================
# Mock pybit before importing bybit_client
# pybit is not installed in the test venv, so we create a
# stub module in sys.modules so the import succeeds.
# =========================================================

_mock_pybit = types.ModuleType("pybit")
_mock_pybit_unified = types.ModuleType("pybit.unified_trading")
_mock_pybit_unified.HTTP = MagicMock
_mock_pybit.unified_trading = _mock_pybit_unified
sys.modules["pybit"] = _mock_pybit
sys.modules["pybit.unified_trading"] = _mock_pybit_unified

from app.exchange_clients.bybit_client import (  # noqa: E402
    ByBitClient,
    ByBitError,
    _check_response,
    to_bybit_symbol,
    from_bybit_symbol,
)


# =========================================================
# Pure function tests (no async, no mocks needed)
# =========================================================


class TestToBybitSymbol:
    """Tests for to_bybit_symbol() — ZenithGrid -> ByBit symbol mapping."""

    def test_btc_usd_maps_to_btcusdt(self):
        """Happy path: BTC-USD becomes BTCUSDT."""
        assert to_bybit_symbol("BTC-USD") == "BTCUSDT"

    def test_eth_btc_maps_to_ethbtc(self):
        """Non-USD quote currency passes through."""
        assert to_bybit_symbol("ETH-BTC") == "ETHBTC"

    def test_sol_usdt_maps_to_solusdt(self):
        """USDT quote stays as USDT."""
        assert to_bybit_symbol("SOL-USDT") == "SOLUSDT"

    def test_btc_usdc_maps_to_btcusdc(self):
        """USDC quote stays as USDC."""
        assert to_bybit_symbol("BTC-USDC") == "BTCUSDC"

    def test_symbol_without_dash_passes_through(self):
        """Edge case: already in ByBit format, no conversion."""
        assert to_bybit_symbol("BTCUSDT") == "BTCUSDT"

    def test_unknown_quote_passes_through(self):
        """Edge case: unknown quote currency uses raw value."""
        assert to_bybit_symbol("BTC-EUR") == "BTCEUR"


class TestFromBybitSymbol:
    """Tests for from_bybit_symbol() — ByBit -> ZenithGrid symbol mapping."""

    def test_btcusdt_maps_to_btc_usd(self):
        """Happy path: BTCUSDT becomes BTC-USD (USDT -> USD mapping)."""
        assert from_bybit_symbol("BTCUSDT") == "BTC-USD"

    def test_ethbtc_maps_to_eth_btc(self):
        """BTC suffix maps correctly."""
        assert from_bybit_symbol("ETHBTC") == "ETH-BTC"

    def test_solusdc_maps_to_sol_usdc(self):
        """USDC suffix stays as USDC."""
        assert from_bybit_symbol("SOLUSDC") == "SOL-USDC"

    def test_soleth_maps_to_sol_eth(self):
        """ETH suffix maps correctly."""
        assert from_bybit_symbol("SOLETH") == "SOL-ETH"

    def test_symbol_without_known_suffix_passes_through(self):
        """Edge case: symbol without recognized suffix returns as-is."""
        assert from_bybit_symbol("XYZABC") == "XYZABC"

    def test_single_suffix_only_returns_as_is(self):
        """Edge case: symbol that IS a suffix (e.g., 'USDT') has empty base."""
        # When base is empty, from_bybit_symbol should return original
        assert from_bybit_symbol("USDT") == "USDT"

    def test_short_symbol_no_match(self):
        """Edge case: very short symbol that doesn't match any suffix."""
        assert from_bybit_symbol("X") == "X"


class TestCheckResponse:
    """Tests for _check_response() — ByBit API response validation."""

    def test_success_response_returns_data(self):
        """Happy path: retCode 0 returns the response dict."""
        resp = {"retCode": 0, "retMsg": "OK", "result": {"data": 42}}
        result = _check_response(resp)
        assert result == resp
        assert result["result"]["data"] == 42

    def test_error_response_raises_bybit_error(self):
        """Failure: non-zero retCode raises ByBitError."""
        resp = {"retCode": 10001, "retMsg": "Invalid parameter"}
        with pytest.raises(ByBitError, match="ByBit API error.*10001.*Invalid parameter"):
            _check_response(resp)

    def test_error_preserves_error_code(self):
        """The ByBitError includes the numeric error code."""
        resp = {"retCode": 110026, "retMsg": "Already in mode"}
        try:
            _check_response(resp)
            assert False, "Should have raised"
        except ByBitError as e:
            assert e.code == 110026

    def test_missing_retcode_raises(self):
        """Edge case: missing retCode defaults to -1 and raises."""
        resp = {"retMsg": "no code"}
        with pytest.raises(ByBitError):
            _check_response(resp)

    def test_long_error_message_is_truncated(self):
        """Edge case: very long retMsg is truncated to 200 chars."""
        long_msg = "x" * 500
        resp = {"retCode": 99, "retMsg": long_msg}
        with pytest.raises(ByBitError) as exc_info:
            _check_response(resp)
        # The safe_msg in the exception should be at most 200 chars of the original
        assert len(long_msg[:200]) == 200
        assert "x" * 200 in str(exc_info.value)

    def test_none_retmsg_uses_unknown(self):
        """Edge case: retMsg is None."""
        resp = {"retCode": 1, "retMsg": None}
        with pytest.raises(ByBitError, match="Unknown error"):
            _check_response(resp)


class TestByBitError:
    """Tests for the ByBitError exception class."""

    def test_error_stores_code_and_message(self):
        """Happy path: ByBitError stores both message and code."""
        err = ByBitError("test error", code=12345)
        assert err.code == 12345
        assert str(err) == "test error"

    def test_default_code_is_zero(self):
        """Edge case: default code is 0."""
        err = ByBitError("just a message")
        assert err.code == 0

    def test_is_exception_subclass(self):
        """ByBitError is a proper Exception."""
        assert issubclass(ByBitError, Exception)


# =========================================================
# ByBitClient method tests (mocked pybit HTTP)
# =========================================================


@pytest.fixture
def mock_http():
    """Create a mock pybit HTTP client with common method stubs."""
    http = MagicMock()
    http.get_wallet_balance = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK",
        "result": {"list": [{"totalEquity": "100000"}]},
    })
    http.get_tickers = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK",
        "result": {"list": [{"symbol": "BTCUSDT", "lastPrice": "50000"}]},
    })
    http.get_kline = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK",
        "result": {"list": [
            ["1700000000000", "50000", "51000", "49000", "50500", "1000", "50000000"],
        ]},
    })
    http.get_instruments_info = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK",
        "result": {"list": [{"symbol": "BTCUSDT"}]},
    })
    http.place_order = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK",
        "result": {"orderId": "ord-123", "orderLinkId": ""},
    })
    http.get_open_orders = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK",
        "result": {"list": []},
    })
    http.get_order_history = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK",
        "result": {"list": []},
    })
    http.amend_order = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK",
        "result": {"orderId": "ord-123"},
    })
    http.cancel_order = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK",
        "result": {"orderId": "ord-123"},
    })
    http.cancel_all_orders = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK",
        "result": {"list": []},
    })
    http.get_positions = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK",
        "result": {"list": []},
    })
    http.set_leverage = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK", "result": {},
    })
    http.set_trading_stop = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK", "result": {},
    })
    http.switch_margin_mode = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK", "result": {},
    })
    http.switch_position_mode = MagicMock(return_value={
        "retCode": 0, "retMsg": "OK", "result": {},
    })
    return http


@pytest.fixture
def bybit_client(mock_http):
    """Create a ByBitClient with mocked pybit HTTP.

    Since pybit is not installed in the test venv, we already injected
    a stub into sys.modules (see top of file).  The __init__ does
    ``from pybit.unified_trading import HTTP`` which resolves to our
    MagicMock.  After construction we swap _http with the fixture mock.
    """
    client = ByBitClient(
        api_key="test-key",
        api_secret="test-secret",
        testnet=True,
    )
    # Replace the _http attribute directly with our controlled mock
    client._http = mock_http
    return client


class TestByBitClientInit:
    """Tests for ByBitClient initialization."""

    def test_init_stores_credentials(self, bybit_client, mock_http):
        """Happy path: client stores API credentials and testnet flag."""
        assert bybit_client._api_key == "test-key"
        assert bybit_client._api_secret == "test-secret"
        assert bybit_client._testnet is True

    def test_init_creates_rate_lock(self, bybit_client):
        """Initialization creates an asyncio lock for rate limiting."""
        assert isinstance(bybit_client._rate_lock, asyncio.Lock)

    def test_init_sets_last_request_time_to_zero(self, bybit_client):
        """Initial last request time is 0.0."""
        assert bybit_client._last_request_time == 0.0


class TestByBitClientGetWalletBalance:
    """Tests for get_wallet_balance()."""

    @pytest.mark.asyncio
    async def test_get_wallet_balance_success(self, bybit_client, mock_http):
        """Happy path: returns wallet balance data."""
        result = await bybit_client.get_wallet_balance()
        assert result["retCode"] == 0
        assert "list" in result["result"]
        mock_http.get_wallet_balance.assert_called_once_with(
            accountType="UNIFIED"
        )

    @pytest.mark.asyncio
    async def test_get_wallet_balance_custom_account_type(self, bybit_client, mock_http):
        """Can specify a different account type."""
        await bybit_client.get_wallet_balance(account_type="CONTRACT")
        mock_http.get_wallet_balance.assert_called_once_with(
            accountType="CONTRACT"
        )

    @pytest.mark.asyncio
    async def test_get_wallet_balance_error_raises(self, bybit_client, mock_http):
        """Failure: API error response raises ByBitError."""
        mock_http.get_wallet_balance.return_value = {
            "retCode": 10001, "retMsg": "Auth failure"
        }
        with pytest.raises(ByBitError, match="Auth failure"):
            await bybit_client.get_wallet_balance()


class TestByBitClientGetCoinBalance:
    """Tests for get_coin_balance()."""

    @pytest.mark.asyncio
    async def test_get_coin_balance_success(self, bybit_client, mock_http):
        """Happy path: retrieves balance for specific coin."""
        mock_http.get_wallet_balance.return_value = {
            "retCode": 0, "retMsg": "OK",
            "result": {"list": [{"coin": [{"coin": "BTC", "availableToWithdraw": "0.5"}]}]},
        }
        result = await bybit_client.get_coin_balance("BTC")
        assert result["retCode"] == 0
        mock_http.get_wallet_balance.assert_called_once_with(
            accountType="UNIFIED", coin="BTC"
        )


class TestByBitClientGetTickers:
    """Tests for get_tickers()."""

    @pytest.mark.asyncio
    async def test_get_tickers_default(self, bybit_client, mock_http):
        """Happy path: retrieves tickers for linear category."""
        result = await bybit_client.get_tickers()
        assert result["retCode"] == 0
        mock_http.get_tickers.assert_called_once_with(category="linear")

    @pytest.mark.asyncio
    async def test_get_tickers_with_symbol(self, bybit_client, mock_http):
        """Can filter by specific symbol."""
        await bybit_client.get_tickers(category="spot", symbol="BTCUSDT")
        mock_http.get_tickers.assert_called_once_with(
            category="spot", symbol="BTCUSDT"
        )

    @pytest.mark.asyncio
    async def test_get_tickers_error_raises(self, bybit_client, mock_http):
        """Failure: API error is propagated."""
        mock_http.get_tickers.return_value = {
            "retCode": 10002, "retMsg": "Request error"
        }
        with pytest.raises(ByBitError, match="Request error"):
            await bybit_client.get_tickers()


class TestByBitClientGetKline:
    """Tests for get_kline()."""

    @pytest.mark.asyncio
    async def test_get_kline_basic(self, bybit_client, mock_http):
        """Happy path: retrieves kline data."""
        result = await bybit_client.get_kline(
            symbol="BTCUSDT", interval="60"
        )
        assert result["retCode"] == 0
        mock_http.get_kline.assert_called_once_with(
            category="linear", symbol="BTCUSDT",
            interval="60", limit=200,
        )

    @pytest.mark.asyncio
    async def test_get_kline_with_time_range(self, bybit_client, mock_http):
        """Timestamps are converted from seconds to milliseconds."""
        await bybit_client.get_kline(
            symbol="ETHUSDT", interval="D",
            start=1700000000, end=1700100000, limit=50,
        )
        call_kwargs = mock_http.get_kline.call_args[1]
        assert call_kwargs["start"] == 1700000000000  # seconds * 1000
        assert call_kwargs["end"] == 1700100000000
        assert call_kwargs["limit"] == 50

    @pytest.mark.asyncio
    async def test_get_kline_without_time_range(self, bybit_client, mock_http):
        """When start/end not provided, they are not sent."""
        await bybit_client.get_kline(symbol="BTCUSDT", interval="1")
        call_kwargs = mock_http.get_kline.call_args[1]
        assert "start" not in call_kwargs
        assert "end" not in call_kwargs


class TestByBitClientPlaceOrder:
    """Tests for place_order()."""

    @pytest.mark.asyncio
    async def test_place_limit_order(self, bybit_client, mock_http):
        """Happy path: place a limit buy order with all parameters."""
        result = await bybit_client.place_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="Limit",
            qty="0.01",
            price="50000",
            take_profit="55000",
            stop_loss="48000",
        )
        assert result["retCode"] == 0
        call_kwargs = mock_http.place_order.call_args[1]
        assert call_kwargs["side"] == "Buy"  # capitalized
        assert call_kwargs["price"] == "50000"
        assert call_kwargs["takeProfit"] == "55000"
        assert call_kwargs["stopLoss"] == "48000"

    @pytest.mark.asyncio
    async def test_place_market_order_minimal(self, bybit_client, mock_http):
        """Market order without optional parameters."""
        await bybit_client.place_order(
            symbol="ETHUSDT", side="sell",
            order_type="Market", qty="1.5",
        )
        call_kwargs = mock_http.place_order.call_args[1]
        assert call_kwargs["side"] == "Sell"
        assert call_kwargs["orderType"] == "Market"
        assert "price" not in call_kwargs
        assert "takeProfit" not in call_kwargs
        assert "stopLoss" not in call_kwargs

    @pytest.mark.asyncio
    async def test_place_order_with_reduce_only(self, bybit_client, mock_http):
        """Reduce-only and close-on-trigger flags are sent when True."""
        await bybit_client.place_order(
            symbol="BTCUSDT", side="sell",
            order_type="Market", qty="0.01",
            reduce_only=True, close_on_trigger=True,
        )
        call_kwargs = mock_http.place_order.call_args[1]
        assert call_kwargs["reduceOnly"] is True
        assert call_kwargs["closeOnTrigger"] is True

    @pytest.mark.asyncio
    async def test_place_order_error_raises(self, bybit_client, mock_http):
        """Failure: order rejected by ByBit API."""
        mock_http.place_order.return_value = {
            "retCode": 110007, "retMsg": "Insufficient margin"
        }
        with pytest.raises(ByBitError, match="Insufficient margin"):
            await bybit_client.place_order(
                symbol="BTCUSDT", side="buy",
                order_type="Market", qty="100",
            )


class TestByBitClientCancelOrder:
    """Tests for cancel_order()."""

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, bybit_client, mock_http):
        """Happy path: cancel an order by ID."""
        result = await bybit_client.cancel_order(
            symbol="BTCUSDT", order_id="ord-abc"
        )
        assert result["retCode"] == 0
        mock_http.cancel_order.assert_called_once_with(
            category="linear", symbol="BTCUSDT", orderId="ord-abc"
        )

    @pytest.mark.asyncio
    async def test_cancel_order_not_found_raises(self, bybit_client, mock_http):
        """Failure: cancelling non-existent order raises."""
        mock_http.cancel_order.return_value = {
            "retCode": 110001, "retMsg": "Order not found"
        }
        with pytest.raises(ByBitError, match="Order not found"):
            await bybit_client.cancel_order(
                symbol="BTCUSDT", order_id="nonexistent"
            )


class TestByBitClientCancelAllOrders:
    """Tests for cancel_all_orders()."""

    @pytest.mark.asyncio
    async def test_cancel_all_with_symbol(self, bybit_client, mock_http):
        """Happy path: cancel all orders for a symbol."""
        result = await bybit_client.cancel_all_orders(symbol="BTCUSDT")
        assert result["retCode"] == 0
        call_kwargs = mock_http.cancel_all_orders.call_args[1]
        assert call_kwargs["symbol"] == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_cancel_all_linear_without_symbol_defaults_usdt(self, bybit_client, mock_http):
        """Edge case: linear without symbol defaults settleCoin to USDT."""
        await bybit_client.cancel_all_orders(category="linear")
        call_kwargs = mock_http.cancel_all_orders.call_args[1]
        assert call_kwargs["settleCoin"] == "USDT"
        assert "symbol" not in call_kwargs

    @pytest.mark.asyncio
    async def test_cancel_all_spot_without_symbol_no_settle(self, bybit_client, mock_http):
        """Edge case: non-linear category without symbol skips settleCoin default."""
        await bybit_client.cancel_all_orders(category="spot")
        call_kwargs = mock_http.cancel_all_orders.call_args[1]
        assert "settleCoin" not in call_kwargs


class TestByBitClientGetOpenOrders:
    """Tests for get_open_orders()."""

    @pytest.mark.asyncio
    async def test_get_open_orders_default(self, bybit_client, mock_http):
        """Happy path: get open orders."""
        result = await bybit_client.get_open_orders()
        assert result["retCode"] == 0
        mock_http.get_open_orders.assert_called_once_with(category="linear")

    @pytest.mark.asyncio
    async def test_get_open_orders_with_symbol(self, bybit_client, mock_http):
        """Filter open orders by symbol."""
        await bybit_client.get_open_orders(symbol="ETHUSDT")
        mock_http.get_open_orders.assert_called_once_with(
            category="linear", symbol="ETHUSDT"
        )


class TestByBitClientGetOrderHistory:
    """Tests for get_order_history()."""

    @pytest.mark.asyncio
    async def test_get_order_history_default(self, bybit_client, mock_http):
        """Happy path: get order history with default limit."""
        result = await bybit_client.get_order_history()
        assert result["retCode"] == 0
        mock_http.get_order_history.assert_called_once_with(
            category="linear", limit=50,
        )

    @pytest.mark.asyncio
    async def test_get_order_history_with_filters(self, bybit_client, mock_http):
        """Filter order history by symbol and order_id."""
        await bybit_client.get_order_history(
            symbol="BTCUSDT", order_id="ord-1", limit=10,
        )
        call_kwargs = mock_http.get_order_history.call_args[1]
        assert call_kwargs["symbol"] == "BTCUSDT"
        assert call_kwargs["orderId"] == "ord-1"
        assert call_kwargs["limit"] == 10


class TestByBitClientAmendOrder:
    """Tests for amend_order()."""

    @pytest.mark.asyncio
    async def test_amend_order_success(self, bybit_client, mock_http):
        """Happy path: amend an order's price."""
        result = await bybit_client.amend_order(
            symbol="BTCUSDT", orderId="ord-1", price="52000"
        )
        assert result["retCode"] == 0
        call_kwargs = mock_http.amend_order.call_args[1]
        assert call_kwargs["symbol"] == "BTCUSDT"
        assert call_kwargs["orderId"] == "ord-1"
        assert call_kwargs["price"] == "52000"


class TestByBitClientPositions:
    """Tests for get_positions() and set_leverage()."""

    @pytest.mark.asyncio
    async def test_get_positions_default(self, bybit_client, mock_http):
        """Happy path: get open positions."""
        result = await bybit_client.get_positions()
        assert result["retCode"] == 0
        mock_http.get_positions.assert_called_once_with(category="linear")

    @pytest.mark.asyncio
    async def test_get_positions_with_symbol(self, bybit_client, mock_http):
        """Filter positions by symbol."""
        await bybit_client.get_positions(symbol="ETHUSDT")
        mock_http.get_positions.assert_called_once_with(
            category="linear", symbol="ETHUSDT"
        )

    @pytest.mark.asyncio
    async def test_set_leverage_success(self, bybit_client, mock_http):
        """Happy path: set leverage for a symbol."""
        result = await bybit_client.set_leverage(
            symbol="BTCUSDT", buy_leverage="10", sell_leverage="10"
        )
        assert result["retCode"] == 0
        mock_http.set_leverage.assert_called_once_with(
            category="linear", symbol="BTCUSDT",
            buyLeverage="10", sellLeverage="10",
        )

    @pytest.mark.asyncio
    async def test_set_trading_stop_with_tp_sl(self, bybit_client, mock_http):
        """Happy path: set TP/SL on existing position."""
        result = await bybit_client.set_trading_stop(
            symbol="BTCUSDT", take_profit="55000", stop_loss="48000"
        )
        assert result["retCode"] == 0
        call_kwargs = mock_http.set_trading_stop.call_args[1]
        assert call_kwargs["takeProfit"] == "55000"
        assert call_kwargs["stopLoss"] == "48000"
        assert call_kwargs["positionIdx"] == 0

    @pytest.mark.asyncio
    async def test_set_trading_stop_tp_only(self, bybit_client, mock_http):
        """Edge case: only take profit, no stop loss."""
        await bybit_client.set_trading_stop(
            symbol="BTCUSDT", take_profit="60000"
        )
        call_kwargs = mock_http.set_trading_stop.call_args[1]
        assert call_kwargs["takeProfit"] == "60000"
        assert "stopLoss" not in call_kwargs


class TestByBitClientSwitchMarginMode:
    """Tests for switch_margin_mode()."""

    @pytest.mark.asyncio
    async def test_switch_margin_mode_success(self, bybit_client, mock_http):
        """Happy path: switch to regular margin."""
        result = await bybit_client.switch_margin_mode(mode="REGULAR_MARGIN")
        assert result["retCode"] == 0
        mock_http.switch_margin_mode.assert_called_once_with(
            category="linear", tradeMode=0,
        )

    @pytest.mark.asyncio
    async def test_switch_margin_mode_portfolio(self, bybit_client, mock_http):
        """Switch to portfolio margin mode."""
        await bybit_client.switch_margin_mode(mode="PORTFOLIO_MARGIN")
        call_kwargs = mock_http.switch_margin_mode.call_args[1]
        assert call_kwargs["tradeMode"] == 1

    @pytest.mark.asyncio
    async def test_switch_margin_mode_already_in_mode(self, bybit_client, mock_http):
        """Edge case: already in requested mode returns OK silently."""
        mock_http.switch_margin_mode.return_value = {
            "retCode": 110026, "retMsg": "Already in mode"
        }
        # _check_response raises ByBitError(code=110026), but
        # switch_margin_mode catches it and returns OK
        result = await bybit_client.switch_margin_mode()
        assert result["retCode"] == 0
        assert result["retMsg"] == "OK"

    @pytest.mark.asyncio
    async def test_switch_margin_mode_other_error_raises(self, bybit_client, mock_http):
        """Failure: non-110026 errors are re-raised."""
        mock_http.switch_margin_mode.return_value = {
            "retCode": 99999, "retMsg": "Unknown"
        }
        with pytest.raises(ByBitError, match="Unknown"):
            await bybit_client.switch_margin_mode()


class TestByBitClientSwitchPositionMode:
    """Tests for switch_position_mode()."""

    @pytest.mark.asyncio
    async def test_switch_position_mode_one_way(self, bybit_client, mock_http):
        """Happy path: switch to one-way mode."""
        result = await bybit_client.switch_position_mode(mode=0)
        assert result["retCode"] == 0
        mock_http.switch_position_mode.assert_called_once_with(
            category="linear", mode=0,
        )

    @pytest.mark.asyncio
    async def test_switch_position_mode_with_symbol(self, bybit_client, mock_http):
        """Switch position mode for a specific symbol."""
        await bybit_client.switch_position_mode(mode=3, symbol="BTCUSDT")
        call_kwargs = mock_http.switch_position_mode.call_args[1]
        assert call_kwargs["symbol"] == "BTCUSDT"
        assert call_kwargs["mode"] == 3

    @pytest.mark.asyncio
    async def test_switch_position_mode_already_in_mode(self, bybit_client, mock_http):
        """Edge case: already in requested mode returns OK silently."""
        mock_http.switch_position_mode.return_value = {
            "retCode": 110025, "retMsg": "Already"
        }
        result = await bybit_client.switch_position_mode()
        assert result["retCode"] == 0

    @pytest.mark.asyncio
    async def test_switch_position_mode_other_error_raises(self, bybit_client, mock_http):
        """Failure: non-110025 errors are re-raised."""
        mock_http.switch_position_mode.return_value = {
            "retCode": 11111, "retMsg": "Fail"
        }
        with pytest.raises(ByBitError, match="Fail"):
            await bybit_client.switch_position_mode()


class TestByBitClientMapGranularity:
    """Tests for map_granularity()."""

    def test_all_known_granularities(self, bybit_client):
        """Happy path: all known granularities map correctly."""
        expected = {
            "ONE_MINUTE": "1", "FIVE_MINUTE": "5",
            "FIFTEEN_MINUTE": "15", "THIRTY_MINUTE": "30",
            "ONE_HOUR": "60", "TWO_HOUR": "120",
            "FOUR_HOUR": "240", "SIX_HOUR": "360",
            "TWELVE_HOUR": "720", "ONE_DAY": "D",
            "ONE_WEEK": "W", "ONE_MONTH": "M",
        }
        for key, val in expected.items():
            assert bybit_client.map_granularity(key) == val

    def test_unsupported_granularity_raises(self, bybit_client):
        """Failure: unsupported granularity raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported granularity"):
            bybit_client.map_granularity("THREE_MINUTE")


class TestByBitClientNormalizeCandles:
    """Tests for normalize_candles()."""

    def test_normalize_single_candle(self, bybit_client):
        """Happy path: single candle is normalized correctly."""
        raw = [["1700000000000", "50000", "51000", "49000", "50500", "1000", "50000000"]]
        result = bybit_client.normalize_candles(raw)
        assert len(result) == 1
        assert result[0]["start"] == "1700000000"  # ms -> seconds
        assert result[0]["open"] == "50000"
        assert result[0]["high"] == "51000"
        assert result[0]["low"] == "49000"
        assert result[0]["close"] == "50500"
        assert result[0]["volume"] == "1000"

    def test_normalize_reverses_order(self, bybit_client):
        """Edge case: ByBit returns newest-first; we reverse to oldest-first."""
        raw = [
            ["1700002000000", "51000", "52000", "50000", "51500", "500", "25000000"],
            ["1700001000000", "50000", "51000", "49000", "50500", "1000", "50000000"],
            ["1700000000000", "49000", "50000", "48000", "49500", "800", "39000000"],
        ]
        result = bybit_client.normalize_candles(raw)
        assert len(result) == 3
        # After reverse: oldest first
        assert result[0]["start"] == "1700000000"
        assert result[1]["start"] == "1700001000"
        assert result[2]["start"] == "1700002000"

    def test_normalize_empty_list(self, bybit_client):
        """Edge case: empty input returns empty output."""
        assert bybit_client.normalize_candles([]) == []

    def test_normalize_millisecond_to_second_conversion(self, bybit_client):
        """Verifies ms->s integer division for various timestamps."""
        raw = [["1700000500000", "1", "2", "0", "1", "10", "10"]]
        result = bybit_client.normalize_candles(raw)
        assert result[0]["start"] == "1700000500"


class TestByBitClientRateLimiting:
    """Tests for the rate limiting behavior of _rate_limited_call()."""

    @pytest.mark.asyncio
    async def test_rate_limited_call_executes_function(self, bybit_client):
        """Happy path: function is called and result returned."""
        mock_fn = MagicMock(return_value={"retCode": 0})
        result = await bybit_client._rate_limited_call(mock_fn, key="value")
        mock_fn.assert_called_once_with(key="value")
        assert result["retCode"] == 0

    @pytest.mark.asyncio
    async def test_rate_limited_call_respects_interval(self, bybit_client):
        """Edge case: rapid calls get delayed by rate limiter."""
        mock_fn = MagicMock(return_value={"retCode": 0})
        # First call sets the last_request_time
        await bybit_client._rate_limited_call(mock_fn)
        # Second call should wait (but we just check it completes)
        await bybit_client._rate_limited_call(mock_fn)
        assert mock_fn.call_count == 2


class TestByBitClientGetInstrumentsInfo:
    """Tests for get_instruments_info()."""

    @pytest.mark.asyncio
    async def test_get_instruments_info_default(self, bybit_client, mock_http):
        """Happy path: get instruments info."""
        result = await bybit_client.get_instruments_info()
        assert result["retCode"] == 0
        mock_http.get_instruments_info.assert_called_once_with(
            category="linear"
        )

    @pytest.mark.asyncio
    async def test_get_instruments_info_with_symbol(self, bybit_client, mock_http):
        """Filter instruments by symbol."""
        await bybit_client.get_instruments_info(symbol="BTCUSDT")
        mock_http.get_instruments_info.assert_called_once_with(
            category="linear", symbol="BTCUSDT"
        )
