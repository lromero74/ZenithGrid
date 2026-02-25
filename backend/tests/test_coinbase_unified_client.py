"""
Tests for backend/app/coinbase_unified_client.py

Covers client initialization (auth detection), rate limiting, and
delegation to API submodules. All external API calls are mocked.
"""

import time

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from app.coinbase_unified_client import CoinbaseClient, _MIN_REQUEST_INTERVAL


# ---------------------------------------------------------------------------
# Initialization / auth detection
# ---------------------------------------------------------------------------


class TestCoinbaseClientInit:
    """Tests for CoinbaseClient.__init__() auth method detection."""

    def test_cdp_auth_explicit_credentials(self):
        """CDP auth is selected when key_name + private_key provided."""
        client = CoinbaseClient(
            key_name="org/key-name",
            private_key="-----BEGIN EC PRIVATE KEY-----\nfake\n-----END EC PRIVATE KEY-----",
        )
        assert client.auth_type == "cdp"
        assert client.key_name == "org/key-name"
        assert "fake" in client.private_key

    @patch("app.coinbase_api.auth.load_cdp_credentials_from_file")
    def test_cdp_auth_from_file(self, mock_load):
        """CDP auth is selected when key_file_path provided."""
        mock_load.return_value = ("file-key-name", "file-private-key")
        client = CoinbaseClient(key_file_path="/path/to/cdp_api_key.json")
        assert client.auth_type == "cdp"
        assert client.key_name == "file-key-name"
        assert client.private_key == "file-private-key"
        mock_load.assert_called_once_with("/path/to/cdp_api_key.json")

    def test_hmac_auth_explicit_credentials(self):
        """HMAC auth is selected when api_key + api_secret provided."""
        client = CoinbaseClient(api_key="my-api-key", api_secret="my-secret")
        assert client.auth_type == "hmac"
        assert client.api_key == "my-api-key"
        assert client.api_secret == "my-secret"

    @patch("app.config.settings")
    def test_fallback_to_cdp_settings(self, mock_settings):
        """Falls back to CDP from settings when available."""
        mock_settings.coinbase_cdp_key_name = "settings-key"
        mock_settings.coinbase_cdp_private_key = "settings-pkey"
        client = CoinbaseClient()
        assert client.auth_type == "cdp"
        assert client.key_name == "settings-key"

    @patch("app.config.settings")
    def test_fallback_to_hmac_settings(self, mock_settings):
        """Falls back to HMAC from settings when no CDP settings."""
        mock_settings.coinbase_cdp_key_name = ""
        mock_settings.coinbase_cdp_private_key = ""
        mock_settings.coinbase_api_key = "hmac-key-from-settings"
        mock_settings.coinbase_api_secret = "hmac-secret-from-settings"
        client = CoinbaseClient()
        assert client.auth_type == "hmac"
        assert client.api_key == "hmac-key-from-settings"

    def test_account_id_stored(self):
        """account_id is stored for per-user cache scoping."""
        client = CoinbaseClient(
            key_name="k", private_key="p", account_id=42
        )
        assert client.account_id == 42

    def test_account_id_default_none(self):
        """account_id defaults to None."""
        client = CoinbaseClient(key_name="k", private_key="p")
        assert client.account_id is None

    def test_cdp_explicit_takes_priority_over_hmac(self):
        """CDP explicit creds take priority even when HMAC creds are also provided."""
        client = CoinbaseClient(
            key_name="cdp-name",
            private_key="cdp-key",
            api_key="hmac-key",
            api_secret="hmac-secret",
        )
        assert client.auth_type == "cdp"

    def test_base_url_constant(self):
        """BASE_URL is the correct Coinbase API URL."""
        assert CoinbaseClient.BASE_URL == "https://api.coinbase.com"

    def test_rate_limit_state_initialized(self):
        """Rate limiter state is initialized to zero."""
        client = CoinbaseClient(key_name="k", private_key="p")
        assert client._last_request_time == 0


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Tests for CoinbaseClient._request() rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_min_interval(self):
        """Rapid consecutive requests are spaced by _MIN_REQUEST_INTERVAL."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.auth.authenticated_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"ok": True}

            start = time.time()
            await client._request("GET", "/api/v3/test1")
            await client._request("GET", "/api/v3/test2")
            elapsed = time.time() - start

        # Second request should have waited ~150ms
        assert elapsed >= _MIN_REQUEST_INTERVAL * 0.9  # small tolerance

    @pytest.mark.asyncio
    async def test_request_delegates_to_auth_module(self):
        """_request passes correct args to auth.authenticated_request."""
        client = CoinbaseClient(key_name="k-name", private_key="p-key")

        with patch("app.coinbase_api.auth.authenticated_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"result": "data"}

            result = await client._request(
                "POST", "/api/v3/endpoint",
                params={"foo": "bar"},
                data={"baz": 123}
            )

        assert result == {"result": "data"}
        mock_req.assert_called_once_with(
            "POST",
            "/api/v3/endpoint",
            "cdp",
            key_name="k-name",
            private_key="p-key",
            api_key=None,
            api_secret=None,
            params={"foo": "bar"},
            data={"baz": 123},
        )

    @pytest.mark.asyncio
    async def test_request_hmac_passes_hmac_credentials(self):
        """HMAC client passes api_key and api_secret, not CDP credentials."""
        client = CoinbaseClient(api_key="hk", api_secret="hs")

        with patch("app.coinbase_api.auth.authenticated_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}

            await client._request("GET", "/api/v3/test")

        mock_req.assert_called_once_with(
            "GET",
            "/api/v3/test",
            "hmac",
            key_name=None,
            private_key=None,
            api_key="hk",
            api_secret="hs",
            params=None,
            data=None,
        )

    @pytest.mark.asyncio
    async def test_first_request_no_delay(self):
        """First request should not incur a rate-limit delay."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.auth.authenticated_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"ok": True}

            start = time.time()
            await client._request("GET", "/api/v3/test")
            elapsed = time.time() - start

        # First request should be nearly instant (well under 150ms)
        assert elapsed < _MIN_REQUEST_INTERVAL

    @pytest.mark.asyncio
    async def test_last_request_time_updated(self):
        """_last_request_time is updated after each request."""
        client = CoinbaseClient(key_name="k", private_key="p")
        assert client._last_request_time == 0

        with patch("app.coinbase_api.auth.authenticated_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await client._request("GET", "/api/v3/test")

        assert client._last_request_time > 0


# ---------------------------------------------------------------------------
# Method delegation — Account & Balance
# ---------------------------------------------------------------------------


class TestAccountBalanceDelegation:
    """Tests verifying account/balance methods delegate correctly."""

    @pytest.mark.asyncio
    async def test_get_accounts_delegates(self):
        """get_accounts delegates to account_balance_api.get_accounts."""
        client = CoinbaseClient(key_name="k", private_key="p", account_id=5)

        with patch("app.coinbase_api.account_balance_api.get_accounts", new_callable=AsyncMock) as mock:
            mock.return_value = [{"id": "acc-1"}]
            result = await client.get_accounts(force_fresh=True)

        assert result == [{"id": "acc-1"}]
        mock.assert_called_once_with(client._request, True, account_id=5)

    @pytest.mark.asyncio
    async def test_get_accounts_default_no_force_fresh(self):
        """get_accounts defaults to force_fresh=False."""
        client = CoinbaseClient(key_name="k", private_key="p", account_id=None)

        with patch("app.coinbase_api.account_balance_api.get_accounts", new_callable=AsyncMock) as mock:
            mock.return_value = []
            await client.get_accounts()

        mock.assert_called_once_with(client._request, False, account_id=None)

    @pytest.mark.asyncio
    async def test_get_account_delegates(self):
        """get_account delegates to account_balance_api.get_account."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.account_balance_api.get_account", new_callable=AsyncMock) as mock:
            mock.return_value = {"uuid": "acc-uuid", "currency": "BTC"}
            result = await client.get_account("acc-uuid")

        assert result == {"uuid": "acc-uuid", "currency": "BTC"}
        mock.assert_called_once_with(client._request, "acc-uuid")

    @pytest.mark.asyncio
    async def test_get_portfolios_delegates(self):
        """get_portfolios delegates to account_balance_api.get_portfolios."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.account_balance_api.get_portfolios", new_callable=AsyncMock) as mock:
            mock.return_value = [{"name": "Default"}]
            result = await client.get_portfolios()

        assert result == [{"name": "Default"}]
        mock.assert_called_once_with(client._request)

    @pytest.mark.asyncio
    async def test_get_portfolio_breakdown_delegates(self):
        """get_portfolio_breakdown delegates with optional portfolio_uuid."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch(
            "app.coinbase_api.account_balance_api.get_portfolio_breakdown", new_callable=AsyncMock
        ) as mock:
            mock.return_value = {"breakdown": {}}
            result = await client.get_portfolio_breakdown("port-uuid")

        assert result == {"breakdown": {}}
        mock.assert_called_once_with(client._request, "port-uuid")

    @pytest.mark.asyncio
    async def test_get_portfolio_breakdown_default_none(self):
        """get_portfolio_breakdown defaults portfolio_uuid to None."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch(
            "app.coinbase_api.account_balance_api.get_portfolio_breakdown", new_callable=AsyncMock
        ) as mock:
            mock.return_value = {}
            await client.get_portfolio_breakdown()

        mock.assert_called_once_with(client._request, None)

    @pytest.mark.asyncio
    async def test_get_btc_balance_delegates(self):
        """get_btc_balance delegates with auth_type and account_id."""
        client = CoinbaseClient(key_name="k", private_key="p", account_id=3)

        with patch("app.coinbase_api.account_balance_api.get_btc_balance", new_callable=AsyncMock) as mock:
            mock.return_value = 1.5
            result = await client.get_btc_balance()

        assert result == 1.5
        mock.assert_called_once_with(client._request, "cdp", account_id=3)

    @pytest.mark.asyncio
    async def test_get_eth_balance_delegates(self):
        """get_eth_balance delegates with auth_type and account_id."""
        client = CoinbaseClient(key_name="k", private_key="p", account_id=7)

        with patch("app.coinbase_api.account_balance_api.get_eth_balance", new_callable=AsyncMock) as mock:
            mock.return_value = 10.0
            result = await client.get_eth_balance()

        assert result == 10.0
        mock.assert_called_once_with(client._request, "cdp", account_id=7)

    @pytest.mark.asyncio
    async def test_get_usd_balance_delegates(self):
        """get_usd_balance delegates with account_id."""
        client = CoinbaseClient(api_key="k", api_secret="s", account_id=2)

        with patch("app.coinbase_api.account_balance_api.get_usd_balance", new_callable=AsyncMock) as mock:
            mock.return_value = 5000.0
            result = await client.get_usd_balance()

        assert result == 5000.0
        mock.assert_called_once_with(client._request, account_id=2)

    @pytest.mark.asyncio
    async def test_get_usdc_balance_delegates(self):
        """get_usdc_balance delegates with account_id."""
        client = CoinbaseClient(key_name="k", private_key="p", account_id=1)

        with patch("app.coinbase_api.account_balance_api.get_usdc_balance", new_callable=AsyncMock) as mock:
            mock.return_value = 250.0
            result = await client.get_usdc_balance()

        assert result == 250.0
        mock.assert_called_once_with(client._request, account_id=1)

    @pytest.mark.asyncio
    async def test_get_usdt_balance_delegates(self):
        """get_usdt_balance delegates with account_id."""
        client = CoinbaseClient(key_name="k", private_key="p", account_id=4)

        with patch("app.coinbase_api.account_balance_api.get_usdt_balance", new_callable=AsyncMock) as mock:
            mock.return_value = 100.0
            result = await client.get_usdt_balance()

        assert result == 100.0
        mock.assert_called_once_with(client._request, account_id=4)

    @pytest.mark.asyncio
    async def test_invalidate_balance_cache_delegates(self):
        """invalidate_balance_cache delegates with account_id."""
        client = CoinbaseClient(key_name="k", private_key="p", account_id=9)

        with patch(
            "app.coinbase_api.account_balance_api.invalidate_balance_cache", new_callable=AsyncMock
        ) as mock:
            await client.invalidate_balance_cache()

        mock.assert_called_once_with(account_id=9)

    @pytest.mark.asyncio
    async def test_calculate_aggregate_btc_value_delegates(self):
        """calculate_aggregate_btc_value passes all expected args."""
        client = CoinbaseClient(key_name="k", private_key="p", account_id=6)

        with patch(
            "app.coinbase_api.account_balance_api.calculate_aggregate_btc_value", new_callable=AsyncMock
        ) as mock:
            mock.return_value = 2.5
            result = await client.calculate_aggregate_btc_value(bypass_cache=True)

        assert result == 2.5
        mock.assert_called_once_with(
            client._request, "cdp", client.get_current_price,
            bypass_cache=True, account_id=6,
        )

    @pytest.mark.asyncio
    async def test_calculate_aggregate_usd_value_delegates(self):
        """calculate_aggregate_usd_value passes all expected args."""
        client = CoinbaseClient(key_name="k", private_key="p", account_id=8)

        with patch(
            "app.coinbase_api.account_balance_api.calculate_aggregate_usd_value", new_callable=AsyncMock
        ) as mock:
            mock.return_value = 150000.0
            result = await client.calculate_aggregate_usd_value()

        assert result == 150000.0
        mock.assert_called_once_with(
            client._request, client.get_btc_usd_price, client.get_current_price,
            account_id=8,
        )


# ---------------------------------------------------------------------------
# Method delegation — Market Data
# ---------------------------------------------------------------------------


class TestMarketDataDelegation:
    """Tests verifying market data methods delegate correctly."""

    @pytest.mark.asyncio
    async def test_list_products_delegates(self):
        """list_products delegates to market_data_api.list_products."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.list_products", new_callable=AsyncMock) as mock:
            mock.return_value = [{"product_id": "BTC-USD"}]
            result = await client.list_products()

        assert result == [{"product_id": "BTC-USD"}]
        mock.assert_called_once_with(client._request)

    @pytest.mark.asyncio
    async def test_get_product_delegates(self):
        """get_product delegates to market_data_api.get_product."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.get_product", new_callable=AsyncMock) as mock:
            mock.return_value = {"product_id": "ETH-BTC", "price": "0.05"}
            result = await client.get_product("ETH-BTC")

        assert result["product_id"] == "ETH-BTC"
        mock.assert_called_once_with(client._request, "ETH-BTC")

    @pytest.mark.asyncio
    async def test_get_product_default_product_id(self):
        """get_product defaults to ETH-BTC."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.get_product", new_callable=AsyncMock) as mock:
            mock.return_value = {}
            await client.get_product()

        mock.assert_called_once_with(client._request, "ETH-BTC")

    @pytest.mark.asyncio
    async def test_get_ticker_delegates(self):
        """get_ticker delegates to market_data_api.get_ticker."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.get_ticker", new_callable=AsyncMock) as mock:
            mock.return_value = {"price": "50000.00", "bid": "49999", "ask": "50001"}
            result = await client.get_ticker("BTC-USD")

        assert result["price"] == "50000.00"
        mock.assert_called_once_with(client._request, "BTC-USD")

    @pytest.mark.asyncio
    async def test_get_current_price_delegates(self):
        """get_current_price delegates to market_data_api.get_current_price."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.get_current_price", new_callable=AsyncMock) as mock:
            mock.return_value = 50000.0
            result = await client.get_current_price("BTC-USD")

        assert result == 50000.0
        mock.assert_called_once_with(client._request, "cdp", "BTC-USD")

    @pytest.mark.asyncio
    async def test_get_btc_usd_price_delegates(self):
        """get_btc_usd_price delegates to market_data_api.get_btc_usd_price."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.get_btc_usd_price", new_callable=AsyncMock) as mock:
            mock.return_value = 65000.0
            result = await client.get_btc_usd_price()

        assert result == 65000.0
        mock.assert_called_once_with(client._request, "cdp")

    @pytest.mark.asyncio
    async def test_get_eth_usd_price_delegates(self):
        """get_eth_usd_price delegates to market_data_api.get_eth_usd_price."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.get_eth_usd_price", new_callable=AsyncMock) as mock:
            mock.return_value = 3500.0
            result = await client.get_eth_usd_price()

        assert result == 3500.0
        mock.assert_called_once_with(client._request, "cdp")

    @pytest.mark.asyncio
    async def test_get_product_stats_delegates(self):
        """get_product_stats delegates to market_data_api.get_product_stats."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.get_product_stats", new_callable=AsyncMock) as mock:
            mock.return_value = {"volume_24h": "1234.5", "high_24h": "51000"}
            result = await client.get_product_stats("BTC-USD")

        assert result["volume_24h"] == "1234.5"
        mock.assert_called_once_with(client._request, "BTC-USD")

    @pytest.mark.asyncio
    async def test_get_candles_delegates(self):
        """get_candles delegates to market_data_api.get_candles."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.get_candles", new_callable=AsyncMock) as mock:
            mock.return_value = [{"open": "50000", "close": "51000"}]
            result = await client.get_candles("BTC-USD", 1000, 2000, "ONE_HOUR")

        assert len(result) == 1
        mock.assert_called_once_with(client._request, "BTC-USD", 1000, 2000, "ONE_HOUR")

    @pytest.mark.asyncio
    async def test_get_candles_default_granularity(self):
        """get_candles defaults to FIVE_MINUTE granularity."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.get_candles", new_callable=AsyncMock) as mock:
            mock.return_value = []
            await client.get_candles("ETH-USD", 100, 200)

        mock.assert_called_once_with(client._request, "ETH-USD", 100, 200, "FIVE_MINUTE")

    @pytest.mark.asyncio
    async def test_get_product_book_delegates(self):
        """get_product_book delegates to market_data_api.get_product_book."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.get_product_book", new_callable=AsyncMock) as mock:
            mock.return_value = {"bids": [], "asks": []}
            result = await client.get_product_book("BTC-USD", limit=25)

        assert result == {"bids": [], "asks": []}
        mock.assert_called_once_with(client._request, "BTC-USD", 25)

    @pytest.mark.asyncio
    async def test_test_connection_delegates(self):
        """test_connection delegates to market_data_api.test_connection."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.test_connection", new_callable=AsyncMock) as mock:
            mock.return_value = True
            result = await client.test_connection()

        assert result is True
        mock.assert_called_once_with(client._request)

    @pytest.mark.asyncio
    async def test_test_connection_returns_false_on_failure(self):
        """test_connection returns False when submodule reports failure."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.market_data_api.test_connection", new_callable=AsyncMock) as mock:
            mock.return_value = False
            result = await client.test_connection()

        assert result is False


# ---------------------------------------------------------------------------
# Method delegation — Orders
# ---------------------------------------------------------------------------


class TestOrderDelegation:
    """Tests verifying order methods delegate correctly."""

    @pytest.mark.asyncio
    async def test_create_market_order_delegates(self):
        """create_market_order delegates to order_api.create_market_order."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.create_market_order", new_callable=AsyncMock) as mock:
            mock.return_value = {"order_id": "ord-1"}
            result = await client.create_market_order("BTC-USD", "BUY", size="0.001")

        assert result["order_id"] == "ord-1"
        mock.assert_called_once_with(client._request, "BTC-USD", "BUY", "0.001", None)

    @pytest.mark.asyncio
    async def test_create_market_order_with_funds(self):
        """create_market_order passes funds when size is None."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.create_market_order", new_callable=AsyncMock) as mock:
            mock.return_value = {"order_id": "ord-2"}
            await client.create_market_order("ETH-USD", "BUY", funds="100.00")

        mock.assert_called_once_with(client._request, "ETH-USD", "BUY", None, "100.00")

    @pytest.mark.asyncio
    async def test_create_limit_order_delegates(self):
        """create_limit_order delegates to order_api.create_limit_order."""
        client = CoinbaseClient(key_name="k", private_key="p")
        end = datetime(2025, 6, 1, 12, 0, 0)

        with patch("app.coinbase_api.order_api.create_limit_order", new_callable=AsyncMock) as mock:
            mock.return_value = {"order_id": "lmt-1"}
            result = await client.create_limit_order(
                "BTC-USD", "BUY", limit_price=50000.0, size="0.01",
                time_in_force="gtd", end_time=end,
            )

        assert result["order_id"] == "lmt-1"
        mock.assert_called_once_with(
            client._request, "BTC-USD", "BUY", 50000.0, "0.01", None, "gtd", end,
        )

    @pytest.mark.asyncio
    async def test_create_limit_order_defaults(self):
        """create_limit_order uses GTC time-in-force by default."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.create_limit_order", new_callable=AsyncMock) as mock:
            mock.return_value = {}
            await client.create_limit_order("ETH-BTC", "SELL", limit_price=0.05)

        mock.assert_called_once_with(
            client._request, "ETH-BTC", "SELL", 0.05, None, None, "gtc", None,
        )

    @pytest.mark.asyncio
    async def test_get_order_delegates(self):
        """get_order delegates to order_api.get_order."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.get_order", new_callable=AsyncMock) as mock:
            mock.return_value = {"order_id": "ord-5", "status": "FILLED"}
            result = await client.get_order("ord-5")

        assert result["status"] == "FILLED"
        mock.assert_called_once_with(client._request, "cdp", "ord-5")

    @pytest.mark.asyncio
    async def test_cancel_order_delegates(self):
        """cancel_order delegates to order_api.cancel_order."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.cancel_order", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True}
            await client.cancel_order("ord-123")

        mock.assert_called_once_with(client._request, "ord-123")

    @pytest.mark.asyncio
    async def test_edit_order_delegates(self):
        """edit_order delegates to order_api.edit_order."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.edit_order", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True}
            result = await client.edit_order("ord-10", price="51000", size="0.02")

        assert result == {"success": True}
        mock.assert_called_once_with(client._request, "ord-10", "51000", "0.02")

    @pytest.mark.asyncio
    async def test_edit_order_partial_args(self):
        """edit_order works with only price or only size."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.edit_order", new_callable=AsyncMock) as mock:
            mock.return_value = {}
            await client.edit_order("ord-11", price="52000")

        mock.assert_called_once_with(client._request, "ord-11", "52000", None)

    @pytest.mark.asyncio
    async def test_edit_order_preview_delegates(self):
        """edit_order_preview delegates to order_api.edit_order_preview."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.edit_order_preview", new_callable=AsyncMock) as mock:
            mock.return_value = {"slippage": "0.01", "fees": "0.50"}
            result = await client.edit_order_preview("ord-12", price="53000")

        assert result["slippage"] == "0.01"
        mock.assert_called_once_with(client._request, "ord-12", "53000", None)

    @pytest.mark.asyncio
    async def test_list_orders_delegates(self):
        """list_orders delegates to order_api.list_orders."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.list_orders", new_callable=AsyncMock) as mock:
            mock.return_value = [{"order_id": "o1"}, {"order_id": "o2"}]
            result = await client.list_orders(product_id="BTC-USD", order_status=["OPEN"], limit=50)

        assert len(result) == 2
        mock.assert_called_once_with(client._request, "BTC-USD", ["OPEN"], 50)

    @pytest.mark.asyncio
    async def test_list_orders_defaults(self):
        """list_orders defaults to no filters, limit=100."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.list_orders", new_callable=AsyncMock) as mock:
            mock.return_value = []
            await client.list_orders()

        mock.assert_called_once_with(client._request, None, None, 100)


# ---------------------------------------------------------------------------
# Method delegation — Convenience Trading
# ---------------------------------------------------------------------------


class TestConvenienceTradingDelegation:
    """Tests for convenience trading methods (buy/sell helpers)."""

    @pytest.mark.asyncio
    async def test_buy_eth_with_btc_delegates(self):
        """buy_eth_with_btc delegates to order_api.buy_eth_with_btc."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.buy_eth_with_btc", new_callable=AsyncMock) as mock:
            mock.return_value = {"order_id": "buy-1"}
            result = await client.buy_eth_with_btc(0.5)

        assert result["order_id"] == "buy-1"
        mock.assert_called_once_with(client._request, 0.5, "ETH-BTC")

    @pytest.mark.asyncio
    async def test_buy_eth_with_btc_custom_product(self):
        """buy_eth_with_btc can use a custom product_id."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.buy_eth_with_btc", new_callable=AsyncMock) as mock:
            mock.return_value = {}
            await client.buy_eth_with_btc(1.0, product_id="AAVE-BTC")

        mock.assert_called_once_with(client._request, 1.0, "AAVE-BTC")

    @pytest.mark.asyncio
    async def test_sell_eth_for_btc_delegates(self):
        """sell_eth_for_btc delegates to order_api.sell_eth_for_btc."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.sell_eth_for_btc", new_callable=AsyncMock) as mock:
            mock.return_value = {"order_id": "sell-1"}
            result = await client.sell_eth_for_btc(2.0)

        assert result["order_id"] == "sell-1"
        mock.assert_called_once_with(client._request, 2.0, "ETH-BTC")

    @pytest.mark.asyncio
    async def test_buy_with_usd_delegates(self):
        """buy_with_usd delegates to order_api.buy_with_usd."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.buy_with_usd", new_callable=AsyncMock) as mock:
            mock.return_value = {"order_id": "usd-buy-1"}
            result = await client.buy_with_usd(500.0, "BTC-USD")

        assert result["order_id"] == "usd-buy-1"
        mock.assert_called_once_with(client._request, 500.0, "BTC-USD")

    @pytest.mark.asyncio
    async def test_sell_for_usd_delegates(self):
        """sell_for_usd delegates to order_api.sell_for_usd."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.sell_for_usd", new_callable=AsyncMock) as mock:
            mock.return_value = {"order_id": "usd-sell-1"}
            result = await client.sell_for_usd(0.01, "BTC-USD")

        assert result["order_id"] == "usd-sell-1"
        mock.assert_called_once_with(client._request, 0.01, "BTC-USD")


# ---------------------------------------------------------------------------
# Deposit/withdrawal date handling
# ---------------------------------------------------------------------------


class TestDepositWithdrawals:
    """Tests for get_deposit_withdrawals() date serialization."""

    @pytest.mark.asyncio
    async def test_with_since_date(self):
        """since datetime is converted to ISO format string."""
        client = CoinbaseClient(key_name="k", private_key="p")
        since = datetime(2024, 1, 15, 12, 0, 0)

        with patch("app.coinbase_api.transaction_api.get_all_transfers", new_callable=AsyncMock) as mock:
            mock.return_value = [{"type": "deposit"}]
            result = await client.get_deposit_withdrawals("acc-uuid", since=since)

        mock.assert_called_once_with(client._request, "acc-uuid", since_iso="2024-01-15T12:00:00")
        assert result == [{"type": "deposit"}]

    @pytest.mark.asyncio
    async def test_without_since_date(self):
        """None since passes None for since_iso."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.transaction_api.get_all_transfers", new_callable=AsyncMock) as mock:
            mock.return_value = []
            await client.get_deposit_withdrawals("acc-uuid")

        mock.assert_called_once_with(client._request, "acc-uuid", since_iso=None)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_transfers(self):
        """Returns empty list when no transfers found."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.transaction_api.get_all_transfers", new_callable=AsyncMock) as mock:
            mock.return_value = []
            result = await client.get_deposit_withdrawals("acc-uuid")

        assert result == []


# ---------------------------------------------------------------------------
# Perpetuals delegation
# ---------------------------------------------------------------------------


class TestPerpetualsDelegation:
    """Tests for perpetual futures method delegation."""

    @pytest.mark.asyncio
    async def test_get_perps_portfolio_summary_delegates(self):
        """get_perps_portfolio_summary delegates correctly."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.perpetuals_api.get_perps_portfolio_summary", new_callable=AsyncMock) as mock:
            mock.return_value = {"margin": "100.00"}
            result = await client.get_perps_portfolio_summary("port-uuid")

        mock.assert_called_once_with(client._request, "port-uuid")
        assert result == {"margin": "100.00"}

    @pytest.mark.asyncio
    async def test_list_perps_positions_delegates(self):
        """list_perps_positions delegates to perpetuals_api.list_perps_positions."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.perpetuals_api.list_perps_positions", new_callable=AsyncMock) as mock:
            mock.return_value = [{"symbol": "BTC-PERP-INTX", "size": "0.1"}]
            result = await client.list_perps_positions("port-uuid")

        assert len(result) == 1
        assert result[0]["symbol"] == "BTC-PERP-INTX"
        mock.assert_called_once_with(client._request, "port-uuid")

    @pytest.mark.asyncio
    async def test_get_perps_position_delegates(self):
        """get_perps_position delegates to perpetuals_api.get_perps_position."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.perpetuals_api.get_perps_position", new_callable=AsyncMock) as mock:
            mock.return_value = {"symbol": "BTC-PERP-INTX", "side": "LONG"}
            result = await client.get_perps_position("port-uuid", "BTC-PERP-INTX")

        assert result["side"] == "LONG"
        mock.assert_called_once_with(client._request, "port-uuid", "BTC-PERP-INTX")

    @pytest.mark.asyncio
    async def test_get_perps_balances_delegates(self):
        """get_perps_balances delegates to perpetuals_api.get_perps_portfolio_balances."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch(
            "app.coinbase_api.perpetuals_api.get_perps_portfolio_balances", new_callable=AsyncMock
        ) as mock:
            mock.return_value = {"total_balance": "10000.00"}
            result = await client.get_perps_balances("port-uuid")

        assert result["total_balance"] == "10000.00"
        mock.assert_called_once_with(client._request, "port-uuid")

    @pytest.mark.asyncio
    async def test_list_perps_products_delegates(self):
        """list_perps_products delegates to perpetuals_api.list_perpetual_products."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch(
            "app.coinbase_api.perpetuals_api.list_perpetual_products", new_callable=AsyncMock
        ) as mock:
            mock.return_value = [{"product_id": "BTC-PERP-INTX"}, {"product_id": "ETH-PERP-INTX"}]
            result = await client.list_perps_products()

        assert len(result) == 2
        mock.assert_called_once_with(client._request)

    @pytest.mark.asyncio
    async def test_create_perps_order_delegates(self):
        """create_perps_order delegates to order_api.create_bracket_order."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.create_bracket_order", new_callable=AsyncMock) as mock:
            mock.return_value = {"order_id": "perp-ord-1"}
            result = await client.create_perps_order(
                product_id="BTC-PERP-INTX",
                side="BUY",
                base_size="0.01",
                leverage="3",
                margin_type="CROSS",
                tp_price="70000",
                sl_price="60000",
                limit_price="65000",
            )

        assert result["order_id"] == "perp-ord-1"
        mock.assert_called_once_with(
            client._request,
            product_id="BTC-PERP-INTX",
            side="BUY",
            base_size="0.01",
            limit_price="65000",
            tp_price="70000",
            sl_price="60000",
            leverage="3",
            margin_type="CROSS",
        )

    @pytest.mark.asyncio
    async def test_create_perps_order_market_no_bracket(self):
        """create_perps_order with minimal args (market order, no bracket)."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.create_bracket_order", new_callable=AsyncMock) as mock:
            mock.return_value = {"order_id": "perp-ord-2"}
            await client.create_perps_order(
                product_id="ETH-PERP-INTX",
                side="SELL",
                base_size="1.0",
            )

        mock.assert_called_once_with(
            client._request,
            product_id="ETH-PERP-INTX",
            side="SELL",
            base_size="1.0",
            limit_price=None,
            tp_price=None,
            sl_price=None,
            leverage=None,
            margin_type=None,
        )

    @pytest.mark.asyncio
    async def test_close_perps_position_uses_market_order(self):
        """close_perps_position creates a market order with opposite side."""
        client = CoinbaseClient(key_name="k", private_key="p")

        with patch("app.coinbase_api.order_api.create_market_order", new_callable=AsyncMock) as mock:
            mock.return_value = {"order_id": "close-1"}
            await client.close_perps_position("BTC-PERP-INTX", "0.01", "SELL")

        mock.assert_called_once_with(
            client._request, product_id="BTC-PERP-INTX", side="SELL", size="0.01"
        )
