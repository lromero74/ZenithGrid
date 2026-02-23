"""
Tests for backend/app/exchange_clients/mt5_bridge_client.py

Tests the MT5 Bridge Client that communicates with a MetaTrader 5 EA
via HTTP. All HTTP requests are mocked using httpx mocking.

Covers:
- Symbol conversion (to_mt5_symbol / from_mt5_symbol)
- HTTP request handling and error translation
- Account/balance methods
- Market data methods
- Order execution (market, limit)
- Heartbeat checking
- Error handling for connection failures, HTTP errors, timeouts
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

import httpx

from app.exchange_clients.mt5_bridge_client import (
    MT5BridgeClient,
    to_mt5_symbol,
    from_mt5_symbol,
)


# =========================================================
# Pure function tests
# =========================================================


class TestToMt5Symbol:
    """Tests for to_mt5_symbol() — ZenithGrid -> MT5 symbol mapping."""

    def test_btc_usd_maps_to_btcusd(self):
        """Happy path: BTC-USD becomes BTCUSD."""
        assert to_mt5_symbol("BTC-USD") == "BTCUSD"

    def test_eth_usd_maps_to_ethusd(self):
        """Happy path: ETH-USD becomes ETHUSD."""
        assert to_mt5_symbol("ETH-USD") == "ETHUSD"

    def test_no_dash_passes_through(self):
        """Edge case: symbol without dash is unchanged."""
        assert to_mt5_symbol("BTCUSD") == "BTCUSD"

    def test_multiple_dashes_all_removed(self):
        """Edge case: multiple dashes are all removed."""
        assert to_mt5_symbol("BTC-USD-PERP") == "BTCUSDPERP"


class TestFromMt5Symbol:
    """Tests for from_mt5_symbol() — MT5 -> ZenithGrid symbol mapping."""

    def test_btcusd_maps_to_btc_usd(self):
        """Happy path: BTCUSD becomes BTC-USD."""
        assert from_mt5_symbol("BTCUSD") == "BTC-USD"

    def test_ethusd_maps_to_eth_usd(self):
        """Happy path: ETHUSD becomes ETH-USD."""
        assert from_mt5_symbol("ETHUSD") == "ETH-USD"

    def test_eurusd_maps_to_eur_usd(self):
        """Forex pair: EURUSD becomes EUR-USD."""
        assert from_mt5_symbol("EURUSD") == "EUR-USD"

    def test_eurjpy_maps_to_eur_jpy(self):
        """JPY suffix: EURJPY becomes EUR-JPY."""
        assert from_mt5_symbol("EURJPY") == "EUR-JPY"

    def test_gbpeur_maps_to_gbp_eur(self):
        """EUR suffix: GBPEUR becomes GBP-EUR."""
        assert from_mt5_symbol("GBPEUR") == "GBP-EUR"

    def test_btcusdt_maps_to_btc_usdt(self):
        """USDT suffix: BTCUSDT becomes BTC-USDT."""
        assert from_mt5_symbol("BTCUSDT") == "BTC-USDT"

    def test_suffix_only_returns_as_is(self):
        """Edge case: symbol that IS a suffix (like 'USD') returns as-is."""
        assert from_mt5_symbol("USD") == "USD"

    def test_unrecognized_symbol_returns_as_is(self):
        """Edge case: unrecognized symbol returned unchanged."""
        assert from_mt5_symbol("X") == "X"


# =========================================================
# Fixtures
# =========================================================


@pytest.fixture
def mt5_client():
    """Create an MT5BridgeClient with a mocked httpx client."""
    client = MT5BridgeClient(
        bridge_url="http://localhost:5555",
        magic_number=99999,
        account_balance=100000.0,
        timeout=5.0,
    )
    # Replace the internal httpx client with a mock
    client._client = AsyncMock(spec=httpx.AsyncClient)
    return client


def _make_response(json_data, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        http_error = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp,
        )
        resp.raise_for_status.side_effect = http_error
    return resp


# =========================================================
# MT5BridgeClient.__init__ tests
# =========================================================


class TestMT5BridgeClientInit:
    """Tests for MT5BridgeClient initialization."""

    def test_init_strips_trailing_slash(self):
        """Happy path: trailing slash on bridge_url is stripped."""
        client = MT5BridgeClient(bridge_url="http://example.com/")
        assert client._bridge_url == "http://example.com"

    def test_init_stores_parameters(self):
        """Stores magic number and account balance."""
        client = MT5BridgeClient(
            bridge_url="http://localhost:5555",
            magic_number=42,
            account_balance=50000.0,
        )
        assert client._magic_number == 42
        assert client._account_balance == 50000.0
        assert client._last_equity == 50000.0


# =========================================================
# _request() tests
# =========================================================


class TestMT5BridgeRequest:
    """Tests for the _request() HTTP helper."""

    @pytest.mark.asyncio
    async def test_request_success(self, mt5_client):
        """Happy path: successful GET returns parsed JSON."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"alive": True})
        )
        result = await mt5_client._request("GET", "/heartbeat")
        assert result == {"alive": True}

    @pytest.mark.asyncio
    async def test_request_timeout_raises_connection_error(self, mt5_client):
        """Failure: httpx timeout raises ConnectionError."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )
        with pytest.raises(ConnectionError, match="MT5 bridge timeout"):
            await mt5_client._request("GET", "/heartbeat")

    @pytest.mark.asyncio
    async def test_request_connect_error_raises_connection_error(self, mt5_client):
        """Failure: connection refused raises ConnectionError."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        with pytest.raises(ConnectionError, match="MT5 bridge unavailable"):
            await mt5_client._request("GET", "/status")

    @pytest.mark.asyncio
    async def test_request_4xx_raises_value_error(self, mt5_client):
        """Failure: 4xx HTTP status raises ValueError."""
        bad_resp = _make_response({"error": "bad"}, status_code=400)
        mt5_client._client.request = AsyncMock(return_value=bad_resp)
        with pytest.raises(ValueError, match="MT5 bridge rejected request.*400"):
            await mt5_client._request("POST", "/order")

    @pytest.mark.asyncio
    async def test_request_5xx_raises_runtime_error(self, mt5_client):
        """Failure: 5xx HTTP status raises RuntimeError."""
        bad_resp = _make_response({"error": "internal"}, status_code=500)
        mt5_client._client.request = AsyncMock(return_value=bad_resp)
        with pytest.raises(RuntimeError, match="MT5 bridge server error.*500"):
            await mt5_client._request("GET", "/status")

    @pytest.mark.asyncio
    async def test_request_generic_exception_raises_connection_error(self, mt5_client):
        """Failure: unexpected exception wraps into ConnectionError."""
        mt5_client._client.request = AsyncMock(
            side_effect=Exception("unexpected")
        )
        with pytest.raises(ConnectionError, match="MT5 bridge unavailable"):
            await mt5_client._request("GET", "/heartbeat")


# =========================================================
# _heartbeat() tests
# =========================================================


class TestMT5BridgeHeartbeat:
    """Tests for _heartbeat() — EA connectivity check."""

    @pytest.mark.asyncio
    async def test_heartbeat_alive(self, mt5_client):
        """Happy path: EA is alive."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"alive": True})
        )
        assert await mt5_client._heartbeat() is True

    @pytest.mark.asyncio
    async def test_heartbeat_dead(self, mt5_client):
        """Edge case: EA responds but alive=False."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"alive": False})
        )
        assert await mt5_client._heartbeat() is False

    @pytest.mark.asyncio
    async def test_heartbeat_error_returns_false(self, mt5_client):
        """Failure: connection error returns False."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )
        assert await mt5_client._heartbeat() is False


# =========================================================
# Account / Balance tests
# =========================================================


class TestMT5BridgeAccounts:
    """Tests for account and balance methods."""

    @pytest.mark.asyncio
    async def test_get_accounts_success(self, mt5_client):
        """Happy path: returns account with status info."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({
                "equity": "95000.50",
                "free_margin": "80000.00",
            })
        )
        accounts = await mt5_client.get_accounts()
        assert len(accounts) == 1
        assert accounts[0]["uuid"] == "mt5-99999"
        assert accounts[0]["currency"] == "USD"
        assert accounts[0]["available_balance"]["value"] == "80000.00"

    @pytest.mark.asyncio
    async def test_get_accounts_connection_failure_uses_last_equity(self, mt5_client):
        """Edge case: connection failure falls back to last known equity."""
        mt5_client._last_equity = 75000.0
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )
        accounts = await mt5_client.get_accounts()
        assert accounts[0]["available_balance"]["value"] == "75000.0"

    @pytest.mark.asyncio
    async def test_get_account_returns_first_account(self, mt5_client):
        """get_account returns first account from get_accounts."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({
                "equity": "100000", "free_margin": "90000"
            })
        )
        account = await mt5_client.get_account("any-id")
        assert account["uuid"] == "mt5-99999"

    @pytest.mark.asyncio
    async def test_get_btc_balance_returns_zero(self, mt5_client):
        """MT5 bridge doesn't hold BTC."""
        assert await mt5_client.get_btc_balance() == 0.0

    @pytest.mark.asyncio
    async def test_get_eth_balance_returns_zero(self, mt5_client):
        """MT5 bridge doesn't hold ETH."""
        assert await mt5_client.get_eth_balance() == 0.0

    @pytest.mark.asyncio
    async def test_get_usd_balance_success(self, mt5_client):
        """Happy path: returns free margin as USD balance."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"free_margin": "45000.25"})
        )
        balance = await mt5_client.get_usd_balance()
        assert balance == 45000.25

    @pytest.mark.asyncio
    async def test_get_usd_balance_connection_failure(self, mt5_client):
        """Failure: returns 0.0 on connection error."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        assert await mt5_client.get_usd_balance() == 0.0

    @pytest.mark.asyncio
    async def test_get_balance_usd(self, mt5_client):
        """get_balance for USD returns structured dict."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"free_margin": "5000"})
        )
        result = await mt5_client.get_balance("USD")
        assert result["currency"] == "USD"
        assert result["available"] == "5000.0"
        assert result["hold"] == "0.00"

    @pytest.mark.asyncio
    async def test_get_balance_non_usd_returns_zero(self, mt5_client):
        """get_balance for non-USD returns zero."""
        result = await mt5_client.get_balance("BTC")
        assert result["currency"] == "BTC"
        assert result["available"] == "0"

    @pytest.mark.asyncio
    async def test_invalidate_balance_cache_is_noop(self, mt5_client):
        """invalidate_balance_cache does nothing (no caching)."""
        await mt5_client.invalidate_balance_cache()  # Should not raise

    @pytest.mark.asyncio
    async def test_calculate_aggregate_btc_value_returns_zero(self, mt5_client):
        """MT5 operates in USD only."""
        assert await mt5_client.calculate_aggregate_btc_value() == 0.0

    @pytest.mark.asyncio
    async def test_calculate_aggregate_usd_value_success(self, mt5_client):
        """Happy path: returns equity from status."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"equity": "110000"})
        )
        result = await mt5_client.calculate_aggregate_usd_value()
        assert result == 110000.0
        assert mt5_client._last_equity == 110000.0

    @pytest.mark.asyncio
    async def test_calculate_aggregate_usd_value_fallback(self, mt5_client):
        """Failure: returns last equity on connection error."""
        mt5_client._last_equity = 88000.0
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )
        assert await mt5_client.calculate_aggregate_usd_value() == 88000.0


# =========================================================
# Market data tests
# =========================================================


class TestMT5BridgeMarketData:
    """Tests for market data methods."""

    @pytest.mark.asyncio
    async def test_list_products_returns_default_list(self, mt5_client):
        """Happy path: returns hardcoded BTC-USD and ETH-USD products."""
        products = await mt5_client.list_products()
        assert len(products) == 2
        product_ids = [p["product_id"] for p in products]
        assert "BTC-USD" in product_ids
        assert "ETH-USD" in product_ids

    @pytest.mark.asyncio
    async def test_get_product_returns_info(self, mt5_client):
        """Happy path: returns product info dict."""
        product = await mt5_client.get_product("BTC-USD")
        assert product["product_id"] == "BTC-USD"
        assert product["base_currency"] == "BTC"
        assert product["quote_currency"] == "USD"

    @pytest.mark.asyncio
    async def test_get_ticker_success(self, mt5_client):
        """Happy path: returns ticker with bid/ask from bridge."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({
                "bid": 50000.50, "ask": 50001.00, "volume": 1234
            })
        )
        ticker = await mt5_client.get_ticker("BTC-USD")
        assert ticker["product_id"] == "BTC-USD"
        assert ticker["price"] == "50000.5"
        assert ticker["bid"] == "50000.5"
        assert ticker["ask"] == "50001.0"

    @pytest.mark.asyncio
    async def test_get_ticker_connection_failure_returns_zero(self, mt5_client):
        """Failure: connection error returns price 0."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        ticker = await mt5_client.get_ticker("BTC-USD")
        assert ticker["price"] == "0"

    @pytest.mark.asyncio
    async def test_get_current_price_success(self, mt5_client):
        """Happy path: returns float price."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"bid": 3500, "ask": 3501})
        )
        price = await mt5_client.get_current_price("ETH-USD")
        assert price == 3500.0

    @pytest.mark.asyncio
    async def test_get_btc_usd_price(self, mt5_client):
        """Convenience: calls get_current_price with BTC-USD."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"bid": 60000, "ask": 60001})
        )
        price = await mt5_client.get_btc_usd_price()
        assert price == 60000.0

    @pytest.mark.asyncio
    async def test_get_eth_usd_price(self, mt5_client):
        """Convenience: calls get_current_price with ETH-USD."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"bid": 3000, "ask": 3001})
        )
        price = await mt5_client.get_eth_usd_price()
        assert price == 3000.0

    @pytest.mark.asyncio
    async def test_get_product_stats(self, mt5_client):
        """Returns stats derived from ticker."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({
                "bid": 50000, "ask": 50001, "volume": 999
            })
        )
        stats = await mt5_client.get_product_stats("BTC-USD")
        assert stats["last"] == "50000"
        assert stats["volume"] == "999"

    @pytest.mark.asyncio
    async def test_get_candles_success(self, mt5_client):
        """Happy path: returns candles from bridge."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({
                "candles": [
                    {"time": 1700000000, "open": 50000, "high": 51000,
                     "low": 49000, "close": 50500, "volume": 100},
                ]
            })
        )
        candles = await mt5_client.get_candles(
            "BTC-USD", 1700000000, 1700100000, "ONE_HOUR"
        )
        assert len(candles) == 1
        assert candles[0]["start"] == "1700000000"
        assert candles[0]["close"] == "50500"

    @pytest.mark.asyncio
    async def test_get_candles_connection_failure_returns_empty(self, mt5_client):
        """Failure: returns empty list on connection error."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        candles = await mt5_client.get_candles(
            "BTC-USD", 1700000000, 1700100000, "ONE_HOUR"
        )
        assert candles == []


# =========================================================
# Order execution tests
# =========================================================


class TestMT5BridgeMarketOrder:
    """Tests for create_market_order()."""

    @pytest.mark.asyncio
    async def test_market_order_with_size_success(self, mt5_client):
        """Happy path: market order with explicit size."""
        # Heartbeat response + order response
        responses = [
            _make_response({"alive": True}),    # heartbeat
            _make_response({                     # order
                "success": True, "ticket": 12345, "price": 50000.0
            }),
        ]
        mt5_client._client.request = AsyncMock(side_effect=responses)

        result = await mt5_client.create_market_order(
            product_id="BTC-USD", side="BUY", size="0.1"
        )
        assert result["success"] is True
        assert result["order_id"] == "12345"
        assert result["side"] == "BUY"
        assert result["filled_size"] == "0.1"
        assert result["average_filled_price"] == "50000.0"
        assert float(result["filled_value"]) == pytest.approx(5000.0)

    @pytest.mark.asyncio
    async def test_market_order_with_funds_calculates_volume(self, mt5_client):
        """Happy path: market order with funds calculates volume from price."""
        responses = [
            _make_response({"alive": True}),           # heartbeat
            _make_response({"bid": 50000, "ask": 50001}),  # get_current_price -> ticker
            _make_response({                            # order
                "success": True, "ticket": 67890, "price": 50000.0
            }),
        ]
        mt5_client._client.request = AsyncMock(side_effect=responses)

        result = await mt5_client.create_market_order(
            product_id="BTC-USD", side="BUY", funds="5000"
        )
        assert result["success"] is True
        # funds=5000, price=50000 -> volume = 0.1
        assert float(result["filled_size"]) == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_market_order_heartbeat_failure_raises(self, mt5_client):
        """Failure: heartbeat failure blocks the order."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )
        with pytest.raises(ConnectionError, match="MT5 bridge not responding"):
            await mt5_client.create_market_order(
                product_id="BTC-USD", side="BUY", size="0.01"
            )

    @pytest.mark.asyncio
    async def test_market_order_bridge_rejects(self, mt5_client):
        """Failure: bridge returns success=False."""
        responses = [
            _make_response({"alive": True}),
            _make_response({
                "success": False, "error": "Insufficient margin"
            }),
        ]
        mt5_client._client.request = AsyncMock(side_effect=responses)

        result = await mt5_client.create_market_order(
            product_id="BTC-USD", side="BUY", size="100"
        )
        assert result["success"] is False
        assert result["error_response"]["message"] == "Insufficient margin"
        assert result["error_response"]["error"] == "MT5_ORDER_REJECTED"

    @pytest.mark.asyncio
    async def test_market_order_default_volume(self, mt5_client):
        """Edge case: no size or funds uses default volume 0.01."""
        responses = [
            _make_response({"alive": True}),
            _make_response({
                "success": True, "ticket": 111, "price": 50000.0
            }),
        ]
        mt5_client._client.request = AsyncMock(side_effect=responses)

        result = await mt5_client.create_market_order(
            product_id="BTC-USD", side="SELL"
        )
        assert result["filled_size"] == "0.01"


class TestMT5BridgeLimitOrder:
    """Tests for create_limit_order()."""

    @pytest.mark.asyncio
    async def test_limit_order_success(self, mt5_client):
        """Happy path: limit order placed successfully."""
        responses = [
            _make_response({"alive": True}),
            _make_response({
                "success": True, "ticket": 22222
            }),
        ]
        mt5_client._client.request = AsyncMock(side_effect=responses)

        result = await mt5_client.create_limit_order(
            product_id="ETH-USD", side="BUY",
            limit_price=3000.0, size="1.0",
        )
        assert result["success"] is True
        assert result["order_id"] == "22222"
        assert result["type"] == "limit"
        assert result["limit_price"] == "3000.0"

    @pytest.mark.asyncio
    async def test_limit_order_with_funds(self, mt5_client):
        """Limit order calculates volume from funds / limit_price."""
        responses = [
            _make_response({"alive": True}),
            _make_response({"success": True, "ticket": 33333}),
        ]
        mt5_client._client.request = AsyncMock(side_effect=responses)

        result = await mt5_client.create_limit_order(
            product_id="BTC-USD", side="BUY",
            limit_price=50000.0, funds="5000",
        )
        assert result["success"] is True
        assert result["size"] == "0.1"  # 5000 / 50000

    @pytest.mark.asyncio
    async def test_limit_order_heartbeat_failure(self, mt5_client):
        """Failure: heartbeat failure blocks limit order."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )
        with pytest.raises(ConnectionError, match="MT5 bridge not responding"):
            await mt5_client.create_limit_order(
                product_id="BTC-USD", side="BUY",
                limit_price=50000.0, size="0.01",
            )

    @pytest.mark.asyncio
    async def test_limit_order_rejected(self, mt5_client):
        """Failure: bridge rejects the limit order."""
        responses = [
            _make_response({"alive": True}),
            _make_response({
                "success": False, "error": "Invalid price"
            }),
        ]
        mt5_client._client.request = AsyncMock(side_effect=responses)

        result = await mt5_client.create_limit_order(
            product_id="BTC-USD", side="BUY",
            limit_price=0.0, size="0.01",
        )
        assert result["success"] is False
        assert "Invalid price" in result["error_response"]["message"]


# =========================================================
# Order management tests
# =========================================================


class TestMT5BridgeOrderManagement:
    """Tests for get_order, cancel_order, list_orders."""

    @pytest.mark.asyncio
    async def test_get_order_success(self, mt5_client):
        """Happy path: retrieves order details."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({
                "status": "FILLED", "volume": 0.1,
                "price": 50000.0, "commission": 5.0,
            })
        )
        result = await mt5_client.get_order("12345")
        assert result["order_id"] == "12345"
        assert result["status"] == "FILLED"
        assert result["filled_size"] == "0.1"
        assert result["total_fees"] == "5.0"

    @pytest.mark.asyncio
    async def test_get_order_failure_returns_unknown(self, mt5_client):
        """Failure: connection error returns UNKNOWN status."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        result = await mt5_client.get_order("12345")
        assert result["order_id"] == "12345"
        assert result["status"] == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, mt5_client):
        """Happy path: cancel an open order."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"success": True})
        )
        result = await mt5_client.cancel_order("12345")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, mt5_client):
        """Failure: bridge unavailable returns success=False."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        result = await mt5_client.cancel_order("12345")
        assert result["success"] is False
        assert "Bridge unavailable" in result["error"]

    @pytest.mark.asyncio
    async def test_list_orders_success(self, mt5_client):
        """Happy path: list open positions as orders."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({
                "positions": [
                    {"ticket": 111, "symbol": "BTCUSD", "type": "buy",
                     "volume": 0.1, "open_price": 50000},
                    {"ticket": 222, "symbol": "ETHUSD", "type": "sell",
                     "volume": 1.0, "open_price": 3000},
                ]
            })
        )
        orders = await mt5_client.list_orders()
        assert len(orders) == 2
        assert orders[0]["order_id"] == "111"
        assert orders[0]["product_id"] == "BTC-USD"
        assert orders[0]["side"] == "BUY"

    @pytest.mark.asyncio
    async def test_list_orders_filter_by_product(self, mt5_client):
        """Filter orders by product_id."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({
                "positions": [
                    {"ticket": 111, "symbol": "BTCUSD", "type": "buy",
                     "volume": 0.1, "open_price": 50000},
                    {"ticket": 222, "symbol": "ETHUSD", "type": "sell",
                     "volume": 1.0, "open_price": 3000},
                ]
            })
        )
        orders = await mt5_client.list_orders(product_id="ETH-USD")
        assert len(orders) == 1
        assert orders[0]["product_id"] == "ETH-USD"

    @pytest.mark.asyncio
    async def test_list_orders_failure_returns_empty(self, mt5_client):
        """Failure: connection error returns empty list."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        assert await mt5_client.list_orders() == []

    @pytest.mark.asyncio
    async def test_list_orders_respects_limit(self, mt5_client):
        """Edge case: limit parameter truncates results."""
        positions = [
            {"ticket": i, "symbol": "BTCUSD", "type": "buy",
             "volume": 0.01, "open_price": 50000}
            for i in range(10)
        ]
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"positions": positions})
        )
        orders = await mt5_client.list_orders(limit=3)
        assert len(orders) == 3


# =========================================================
# Convenience methods tests
# =========================================================


class TestMT5BridgeConvenienceMethods:
    """Tests for convenience trading methods."""

    @pytest.mark.asyncio
    async def test_buy_eth_with_btc(self, mt5_client):
        """buy_eth_with_btc delegates to create_market_order."""
        mt5_client.create_market_order = AsyncMock(return_value={"success": True})
        await mt5_client.buy_eth_with_btc(0.5)
        mt5_client.create_market_order.assert_called_once_with(
            product_id="ETH-BTC", side="BUY", funds="0.5",
        )

    @pytest.mark.asyncio
    async def test_sell_eth_for_btc(self, mt5_client):
        """sell_eth_for_btc delegates to create_market_order."""
        mt5_client.create_market_order = AsyncMock(return_value={"success": True})
        await mt5_client.sell_eth_for_btc(2.0)
        mt5_client.create_market_order.assert_called_once_with(
            product_id="ETH-BTC", side="SELL", size="2.0",
        )

    @pytest.mark.asyncio
    async def test_buy_with_usd(self, mt5_client):
        """buy_with_usd delegates to create_market_order."""
        mt5_client.create_market_order = AsyncMock(return_value={"success": True})
        await mt5_client.buy_with_usd(1000.0, "BTC-USD")
        mt5_client.create_market_order.assert_called_once_with(
            product_id="BTC-USD", side="BUY", funds="1000.0",
        )

    @pytest.mark.asyncio
    async def test_sell_for_usd(self, mt5_client):
        """sell_for_usd delegates to create_market_order."""
        mt5_client.create_market_order = AsyncMock(return_value={"success": True})
        await mt5_client.sell_for_usd(0.5, "BTC-USD")
        mt5_client.create_market_order.assert_called_once_with(
            product_id="BTC-USD", side="SELL", size="0.5",
        )


# =========================================================
# Metadata and MT5-specific tests
# =========================================================


class TestMT5BridgeMetadata:
    """Tests for metadata and MT5-specific methods."""

    def test_get_exchange_type_returns_cex(self, mt5_client):
        """MT5 bridge behaves like a CEX."""
        assert mt5_client.get_exchange_type() == "cex"

    @pytest.mark.asyncio
    async def test_test_connection_delegates_to_heartbeat(self, mt5_client):
        """test_connection delegates to _heartbeat."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"alive": True})
        )
        assert await mt5_client.test_connection() is True

    @pytest.mark.asyncio
    async def test_get_equity_success(self, mt5_client):
        """Happy path: returns equity and updates last_equity."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"equity": "105000"})
        )
        equity = await mt5_client.get_equity()
        assert equity == 105000.0
        assert mt5_client._last_equity == 105000.0

    @pytest.mark.asyncio
    async def test_get_equity_failure_returns_last(self, mt5_client):
        """Failure: returns last known equity on error."""
        mt5_client._last_equity = 95000.0
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        assert await mt5_client.get_equity() == 95000.0

    @pytest.mark.asyncio
    async def test_close_all_positions_success(self, mt5_client):
        """Happy path: sends close-all to bridge."""
        mt5_client._client.request = AsyncMock(
            return_value=_make_response({"success": True})
        )
        await mt5_client.close_all_positions()
        call_args = mt5_client._client.request.call_args
        assert "/close-all" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_close_all_positions_failure_logs_critical(self, mt5_client):
        """Failure: connection error is caught (does not raise)."""
        mt5_client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        # Should not raise, just logs critical
        await mt5_client.close_all_positions()

    @pytest.mark.asyncio
    async def test_close_releases_httpx_client(self, mt5_client):
        """close() calls aclose on the httpx client."""
        mt5_client._client.aclose = AsyncMock()
        await mt5_client.close()
        mt5_client._client.aclose.assert_called_once()
