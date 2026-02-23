"""
Tests for backend/app/exchange_clients/coinbase_adapter.py

Tests the Coinbase adapter that wraps CoinbaseClient to implement
the ExchangeClient interface. All CoinbaseClient methods are mocked.
"""

import pytest
from unittest.mock import AsyncMock

from app.exchange_clients.coinbase_adapter import CoinbaseAdapter


# =========================================================
# Fixtures
# =========================================================


def _make_mock_coinbase_client():
    """Create a fully mocked CoinbaseClient."""
    client = AsyncMock()
    client.get_accounts = AsyncMock(return_value=[
        {
            "uuid": "acc-btc",
            "currency": "BTC",
            "available_balance": {"value": "0.5", "currency": "BTC"},
            "hold": {"value": "0.01", "currency": "BTC"},
        },
        {
            "uuid": "acc-usd",
            "currency": "USD",
            "available_balance": {"value": "10000", "currency": "USD"},
            "hold": {"value": "100", "currency": "USD"},
        },
    ])
    client.get_account = AsyncMock(return_value={"uuid": "acc-btc"})
    client.get_btc_balance = AsyncMock(return_value=0.5)
    client.get_eth_balance = AsyncMock(return_value=5.0)
    client.get_usd_balance = AsyncMock(return_value=10000.0)
    client.get_usdc_balance = AsyncMock(return_value=500.0)
    client.get_usdt_balance = AsyncMock(return_value=200.0)
    client.invalidate_balance_cache = AsyncMock()
    client.calculate_aggregate_btc_value = AsyncMock(return_value=2.5)
    client.calculate_aggregate_usd_value = AsyncMock(return_value=125000.0)
    client.list_products = AsyncMock(return_value=[{"product_id": "BTC-USD"}])
    client.get_product = AsyncMock(return_value={"product_id": "BTC-USD"})
    client.get_ticker = AsyncMock(return_value={"price": "50000"})
    client.get_current_price = AsyncMock(return_value=50000.0)
    client.get_btc_usd_price = AsyncMock(return_value=50000.0)
    client.get_eth_usd_price = AsyncMock(return_value=3000.0)
    client.get_product_stats = AsyncMock(return_value={"open": "49000"})
    client.get_candles = AsyncMock(return_value=[
        {"close": "50000"},
        {"close": "50100"},
        {"close": "49900"},
    ])
    client.get_product_book = AsyncMock(return_value={"bids": [], "asks": []})
    client.create_market_order = AsyncMock(return_value={
        "success": True,
        "order_id": "cb-order-1",
    })
    client.create_limit_order = AsyncMock(return_value={
        "success": True,
        "order_id": "cb-order-2",
    })
    client.get_order = AsyncMock(return_value={"order_id": "cb-order-1", "status": "FILLED"})
    client.cancel_order = AsyncMock(return_value={"success": True})
    client.edit_order = AsyncMock(return_value={"success": True})
    client.edit_order_preview = AsyncMock(return_value={"preview": True})
    client.list_orders = AsyncMock(return_value=[])
    client.buy_eth_with_btc = AsyncMock(return_value={"success": True})
    client.sell_eth_for_btc = AsyncMock(return_value={"success": True})
    client.buy_with_usd = AsyncMock(return_value={"success": True})
    client.sell_for_usd = AsyncMock(return_value={"success": True})
    client.test_connection = AsyncMock(return_value=True)
    client.get_portfolios = AsyncMock(return_value=[])
    client.get_portfolio_breakdown = AsyncMock(return_value={})
    return client


# =========================================================
# Initialization
# =========================================================


class TestCoinbaseAdapterInit:
    """Tests for CoinbaseAdapter initialization."""

    def test_adapter_stores_client(self):
        """Happy path: adapter stores the underlying client reference."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)
        assert adapter._client is mock_client

    def test_adapter_exchange_type_is_cex(self):
        """Happy path: exchange type is 'cex'."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)
        assert adapter.get_exchange_type() == "cex"


# =========================================================
# Balance methods
# =========================================================


class TestBalanceMethods:
    """Tests for balance-related delegation."""

    @pytest.mark.asyncio
    async def test_get_btc_balance(self):
        """Happy path: delegates to CoinbaseClient."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.get_btc_balance()
        assert result == 0.5
        mock_client.get_btc_balance.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_eth_balance(self):
        """Happy path: delegates to CoinbaseClient."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.get_eth_balance()
        assert result == 5.0

    @pytest.mark.asyncio
    async def test_get_usd_balance(self):
        """Happy path: delegates to CoinbaseClient."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.get_usd_balance()
        assert result == 10000.0

    @pytest.mark.asyncio
    async def test_get_balance_for_known_currency(self):
        """Happy path: returns balance dict for found currency."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.get_balance("BTC")
        assert result["currency"] == "BTC"
        assert result["available"] == "0.5"
        assert result["hold"] == "0.01"

    @pytest.mark.asyncio
    async def test_get_balance_for_unknown_currency(self):
        """Edge case: returns zero balance for unknown currency."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.get_balance("DOGE")
        assert result["currency"] == "DOGE"
        assert result["available"] == "0"
        assert result["hold"] == "0"

    @pytest.mark.asyncio
    async def test_invalidate_balance_cache(self):
        """Happy path: delegates cache invalidation."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        await adapter.invalidate_balance_cache()
        mock_client.invalidate_balance_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_calculate_aggregate_btc_value(self):
        """Happy path: delegates aggregate BTC calculation."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.calculate_aggregate_btc_value()
        assert result == 2.5

    @pytest.mark.asyncio
    async def test_calculate_aggregate_btc_value_bypass_cache(self):
        """Edge case: bypass_cache flag is forwarded."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        await adapter.calculate_aggregate_btc_value(bypass_cache=True)
        mock_client.calculate_aggregate_btc_value.assert_called_once_with(bypass_cache=True)

    @pytest.mark.asyncio
    async def test_calculate_aggregate_usd_value(self):
        """Happy path: delegates aggregate USD calculation."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.calculate_aggregate_usd_value()
        assert result == 125000.0


# =========================================================
# Market data
# =========================================================


class TestMarketDataMethods:
    """Tests for market data delegation."""

    @pytest.mark.asyncio
    async def test_get_current_price(self):
        """Happy path: delegates price query."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.get_current_price("BTC-USD")
        assert result == 50000.0

    @pytest.mark.asyncio
    async def test_get_candles_reverses_order(self):
        """Happy path: candles are reversed to oldest-first."""
        mock_client = _make_mock_coinbase_client()
        # Coinbase returns newest first
        mock_client.get_candles = AsyncMock(return_value=[
            {"close": "50200"},  # newest
            {"close": "50100"},
            {"close": "50000"},  # oldest
        ])
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.get_candles("BTC-USD", 1000, 2000, "ONE_HOUR")
        # Should be reversed to oldest-first
        assert result[0]["close"] == "50000"
        assert result[-1]["close"] == "50200"

    @pytest.mark.asyncio
    async def test_list_products(self):
        """Happy path: delegates product listing."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.list_products()
        assert len(result) == 1
        assert result[0]["product_id"] == "BTC-USD"

    @pytest.mark.asyncio
    async def test_get_ticker(self):
        """Happy path: delegates ticker query."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.get_ticker("BTC-USD")
        assert result["price"] == "50000"


# =========================================================
# Order execution
# =========================================================


class TestOrderExecution:
    """Tests for order execution delegation."""

    @pytest.mark.asyncio
    async def test_create_market_order(self):
        """Happy path: delegates market order creation."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.create_market_order(
            product_id="BTC-USD",
            side="BUY",
            size="0.1",
        )

        assert result["success"] is True
        mock_client.create_market_order.assert_called_once_with(
            product_id="BTC-USD",
            side="BUY",
            size="0.1",
            funds=None,
        )

    @pytest.mark.asyncio
    async def test_create_limit_order(self):
        """Happy path: delegates limit order creation."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.create_limit_order(
            product_id="BTC-USD",
            side="BUY",
            limit_price=49000.0,
            size="0.1",
        )

        assert result["success"] is True
        mock_client.create_limit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_order(self):
        """Happy path: delegates order status query."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.get_order("cb-order-1")
        assert result["status"] == "FILLED"

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """Happy path: delegates order cancellation."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.cancel_order("cb-order-1")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_edit_order(self):
        """Happy path: delegates order editing."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.edit_order("cb-order-1", price="51000")
        assert result["success"] is True
        mock_client.edit_order.assert_called_once_with(
            order_id="cb-order-1", price="51000", size=None
        )

    @pytest.mark.asyncio
    async def test_list_orders(self):
        """Happy path: delegates order listing."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        await adapter.list_orders(product_id="BTC-USD", order_status=["OPEN"])
        mock_client.list_orders.assert_called_once_with(
            product_id="BTC-USD",
            order_status=["OPEN"],
            limit=100,
        )


# =========================================================
# Connection
# =========================================================


class TestConnection:
    """Tests for connection testing."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """Happy path: connection test succeeds."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        """Failure case: connection test fails."""
        mock_client = _make_mock_coinbase_client()
        mock_client.test_connection = AsyncMock(return_value=False)
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.test_connection()
        assert result is False


# =========================================================
# Convenience methods
# =========================================================


class TestConvenienceMethods:
    """Tests for convenience trading methods."""

    @pytest.mark.asyncio
    async def test_buy_eth_with_btc(self):
        """Happy path: delegates to underlying client."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.buy_eth_with_btc(0.5)
        assert result["success"] is True
        mock_client.buy_eth_with_btc.assert_called_once_with(0.5, "ETH-BTC")

    @pytest.mark.asyncio
    async def test_sell_eth_for_btc(self):
        """Happy path: delegates to underlying client."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.sell_eth_for_btc(5.0)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_buy_with_usd(self):
        """Happy path: delegates to underlying client."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.buy_with_usd(10000.0, "BTC-USD")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_sell_for_usd(self):
        """Happy path: delegates to underlying client."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        result = await adapter.sell_for_usd(0.5, "BTC-USD")
        assert result["success"] is True


# =========================================================
# Coinbase-specific methods
# =========================================================


class TestCoinbaseSpecificMethods:
    """Tests for Coinbase-specific pass-through methods."""

    @pytest.mark.asyncio
    async def test_get_portfolios(self):
        """Happy path: delegates to CoinbaseClient."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        await adapter.get_portfolios()
        mock_client.get_portfolios.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_product_book(self):
        """Happy path: delegates to CoinbaseClient."""
        mock_client = _make_mock_coinbase_client()
        adapter = CoinbaseAdapter(mock_client)

        await adapter.get_product_book("BTC-USD", limit=25)
        mock_client.get_product_book.assert_called_once_with("BTC-USD", limit=25)
