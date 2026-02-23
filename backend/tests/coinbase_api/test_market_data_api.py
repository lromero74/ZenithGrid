"""
Tests for backend/app/coinbase_api/market_data_api.py

Covers product listing, ticker/price retrieval, candle fetching,
order book access, product stats, and connection testing.
"""

import pytest
from unittest.mock import AsyncMock

from app.coinbase_api.market_data_api import (
    get_btc_usd_price,
    get_candles,
    get_current_price,
    get_eth_usd_price,
    get_product,
    get_product_book,
    get_product_stats,
    get_ticker,
    list_products,
)
# Import with alias to avoid pytest collecting it as a test function
from app.coinbase_api.market_data_api import test_connection as _test_connection


@pytest.fixture(autouse=True)
async def clear_cache():
    """Clear the API cache before each test."""
    from app.cache import api_cache
    await api_cache.clear()
    yield
    await api_cache.clear()


# ---------------------------------------------------------------------------
# list_products
# ---------------------------------------------------------------------------


class TestListProducts:
    """Tests for list_products()"""

    @pytest.mark.asyncio
    async def test_returns_product_list(self):
        """Happy path: fetches and returns all products."""
        mock_request = AsyncMock(return_value={
            "products": [
                {"product_id": "ETH-BTC", "status": "online"},
                {"product_id": "SOL-BTC", "status": "online"},
            ],
        })

        result = await list_products(mock_request)
        assert len(result) == 2
        assert result[0]["product_id"] == "ETH-BTC"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_products_key(self):
        """Edge case: returns empty list when response has no products key."""
        mock_request = AsyncMock(return_value={})

        result = await list_products(mock_request)
        assert result == []

    @pytest.mark.asyncio
    async def test_caches_result(self):
        """Edge case: second call uses cached products (single-flight)."""
        mock_request = AsyncMock(return_value={
            "products": [{"product_id": "BTC-USD"}],
        })

        result1 = await list_products(mock_request)
        result2 = await list_products(mock_request)

        assert result1 == result2
        assert mock_request.call_count == 1


# ---------------------------------------------------------------------------
# get_product
# ---------------------------------------------------------------------------


class TestGetProduct:
    """Tests for get_product()"""

    @pytest.mark.asyncio
    async def test_returns_product_data(self):
        """Happy path: returns product details directly."""
        mock_request = AsyncMock(return_value={
            "product_id": "ETH-BTC",
            "price": "0.05",
            "volume_24h": "1000",
        })

        result = await get_product(mock_request, "ETH-BTC")
        assert result["product_id"] == "ETH-BTC"

    @pytest.mark.asyncio
    async def test_uses_default_product_id(self):
        """Edge case: defaults to ETH-BTC when no product_id specified."""
        mock_request = AsyncMock(return_value={"product_id": "ETH-BTC"})

        await get_product(mock_request)
        mock_request.assert_called_with("GET", "/api/v3/brokerage/products/ETH-BTC")


# ---------------------------------------------------------------------------
# get_ticker
# ---------------------------------------------------------------------------


class TestGetTicker:
    """Tests for get_ticker()"""

    @pytest.mark.asyncio
    async def test_returns_ticker_data(self):
        """Happy path: returns ticker with bid/ask/price."""
        mock_request = AsyncMock(return_value={
            "best_bid": "0.049",
            "best_ask": "0.051",
            "price": "0.050",
        })

        result = await get_ticker(mock_request, "ETH-BTC")
        assert result["best_bid"] == "0.049"

    @pytest.mark.asyncio
    async def test_uses_default_product_id(self):
        """Edge case: defaults to ETH-BTC."""
        mock_request = AsyncMock(return_value={})

        await get_ticker(mock_request)
        mock_request.assert_called_with("GET", "/api/v3/brokerage/products/ETH-BTC/ticker")


# ---------------------------------------------------------------------------
# get_current_price
# ---------------------------------------------------------------------------


class TestGetCurrentPrice:
    """Tests for get_current_price()"""

    @pytest.mark.asyncio
    async def test_cdp_returns_midprice(self):
        """Happy path: CDP auth calculates mid-price from bid/ask."""
        mock_request = AsyncMock(return_value={
            "best_bid": "100.0",
            "best_ask": "102.0",
        })

        result = await get_current_price(mock_request, "cdp", "BTC-USD")
        assert result == pytest.approx(101.0)

    @pytest.mark.asyncio
    async def test_cdp_falls_back_to_trade_price(self):
        """Edge case: CDP falls back to most recent trade when bid/ask are zero."""
        mock_request = AsyncMock(return_value={
            "best_bid": "0",
            "best_ask": "0",
            "trades": [{"price": "99.5"}],
        })

        result = await get_current_price(mock_request, "cdp", "ETH-USD")
        assert result == pytest.approx(99.5)

    @pytest.mark.asyncio
    async def test_cdp_returns_zero_when_no_data(self):
        """Edge case: returns 0.0 when no bid/ask and no trades."""
        mock_request = AsyncMock(return_value={
            "best_bid": "0",
            "best_ask": "0",
            "trades": [],
        })

        result = await get_current_price(mock_request, "cdp", "XYZ-USD")
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_hmac_returns_price_field(self):
        """Happy path: HMAC auth returns price field directly."""
        mock_request = AsyncMock(return_value={
            "price": "50000.50",
        })

        result = await get_current_price(mock_request, "hmac", "BTC-USD")
        assert result == pytest.approx(50000.50)

    @pytest.mark.asyncio
    async def test_hmac_returns_zero_for_missing_price(self):
        """Edge case: returns 0.0 when HMAC ticker has no price field."""
        mock_request = AsyncMock(return_value={})

        result = await get_current_price(mock_request, "hmac", "MISSING-USD")
        assert result == 0.0


# ---------------------------------------------------------------------------
# get_btc_usd_price / get_eth_usd_price
# ---------------------------------------------------------------------------


class TestConveniencePriceFunctions:
    """Tests for get_btc_usd_price() and get_eth_usd_price()"""

    @pytest.mark.asyncio
    async def test_btc_usd_price(self):
        """Happy path: returns BTC-USD price."""
        mock_request = AsyncMock(return_value={"price": "65000"})

        result = await get_btc_usd_price(mock_request, "hmac")
        assert result == pytest.approx(65000.0)

    @pytest.mark.asyncio
    async def test_eth_usd_price(self):
        """Happy path: returns ETH-USD price."""
        mock_request = AsyncMock(return_value={"price": "3500"})

        result = await get_eth_usd_price(mock_request, "hmac")
        assert result == pytest.approx(3500.0)


# ---------------------------------------------------------------------------
# get_product_stats
# ---------------------------------------------------------------------------


class TestGetProductStats:
    """Tests for get_product_stats()"""

    @pytest.mark.asyncio
    async def test_returns_24h_stats(self):
        """Happy path: returns volume and price change stats."""
        mock_request = AsyncMock(return_value={
            "volume_24h": "5000.5",
            "volume_percentage_change_24h": "12.3",
            "price_percentage_change_24h": "-2.1",
        })

        result = await get_product_stats(mock_request, "ETH-BTC")
        assert result["volume_24h"] == pytest.approx(5000.5)
        assert result["price_percentage_change_24h"] == pytest.approx(-2.1)

    @pytest.mark.asyncio
    async def test_defaults_to_zero_for_missing_fields(self):
        """Edge case: missing fields default to 0."""
        mock_request = AsyncMock(return_value={})

        result = await get_product_stats(mock_request, "NEW-BTC")
        assert result["volume_24h"] == 0.0
        assert result["volume_percentage_change_24h"] == 0.0


# ---------------------------------------------------------------------------
# get_candles
# ---------------------------------------------------------------------------


class TestGetCandles:
    """Tests for get_candles()"""

    @pytest.mark.asyncio
    async def test_returns_candle_data(self):
        """Happy path: returns list of candles."""
        mock_request = AsyncMock(return_value={
            "candles": [
                {"start": "1700000000", "open": "0.05", "close": "0.051"},
                {"start": "1700000300", "open": "0.051", "close": "0.052"},
            ],
        })

        result = await get_candles(mock_request, "ETH-BTC", 1700000000, 1700000600)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_passes_granularity_param(self):
        """Edge case: custom granularity is passed to the API."""
        mock_request = AsyncMock(return_value={"candles": []})

        await get_candles(mock_request, "BTC-USD", 100, 200, granularity="ONE_HOUR")
        call_kwargs = mock_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["granularity"] == "ONE_HOUR"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_candles(self):
        """Edge case: returns empty list when no candles key."""
        mock_request = AsyncMock(return_value={})

        result = await get_candles(mock_request, "ETH-BTC", 100, 200)
        assert result == []


# ---------------------------------------------------------------------------
# get_product_book
# ---------------------------------------------------------------------------


class TestGetProductBook:
    """Tests for get_product_book()"""

    @pytest.mark.asyncio
    async def test_returns_order_book(self):
        """Happy path: returns pricebook with bids and asks."""
        mock_request = AsyncMock(return_value={
            "pricebook": {
                "bids": [{"price": "0.049", "size": "10"}],
                "asks": [{"price": "0.051", "size": "5"}],
            },
        })

        result = await get_product_book(mock_request, "ETH-BTC")
        assert "pricebook" in result

    @pytest.mark.asyncio
    async def test_custom_limit(self):
        """Edge case: custom limit parameter is passed."""
        mock_request = AsyncMock(return_value={})

        await get_product_book(mock_request, "ETH-BTC", limit=10)
        call_kwargs = mock_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["limit"] == "10"


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


class TestApiTestConnection:
    """Tests for test_connection()"""

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        """Happy path: returns True when API responds successfully."""
        mock_request = AsyncMock(return_value={
            "accounts": [], "cursor": "",
        })

        result = await _test_connection(mock_request)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_failure(self):
        """Failure: returns False when API call fails."""
        mock_request = AsyncMock(side_effect=Exception("Connection refused"))

        result = await _test_connection(mock_request)
        assert result is False
