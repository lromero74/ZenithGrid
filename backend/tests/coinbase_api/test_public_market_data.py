"""
Tests for backend/app/coinbase_api/public_market_data.py

Covers public (unauthenticated) market data endpoints including
rate-limited requests, product listing, ticker, pricing, stats,
candles, and the PublicMarketDataClient duck-type wrapper.
"""

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.coinbase_api.public_market_data import (
    PublicMarketDataClient,
    _public_request,
    get_btc_usd_price,
    get_candles,
    get_current_price,
    get_eth_usd_price,
    get_product,
    get_product_stats,
    get_ticker,
    list_products,
)


@pytest.fixture(autouse=True)
async def clear_cache():
    """Clear the API cache before each test."""
    from app.cache import api_cache
    await api_cache.clear()
    yield
    await api_cache.clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the module-level rate limiter between tests."""
    import app.coinbase_api.public_market_data as mod
    mod._last_request_time = 0.0


# ---------------------------------------------------------------------------
# _public_request
# ---------------------------------------------------------------------------


class TestPublicRequest:
    """Tests for _public_request()"""

    @pytest.mark.asyncio
    async def test_successful_get_request(self):
        """Happy path: returns JSON response for successful GET."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"products": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.coinbase_api.public_market_data.httpx.AsyncClient", return_value=mock_client):
            result = await _public_request("/api/v3/brokerage/market/products")

        assert result == {"products": []}

    @pytest.mark.asyncio
    async def test_retries_on_429(self):
        """Edge case: retries once after 429 rate limit response."""
        # First response: 429
        rate_limited_response = MagicMock()
        rate_limited_response.status_code = 429
        rate_limited_response.raise_for_status = MagicMock()

        # Second response: 200
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"data": "ok"}
        success_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.side_effect = [rate_limited_response, success_response]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.coinbase_api.public_market_data.httpx.AsyncClient", return_value=mock_client):
            with patch("app.coinbase_api.public_market_data.asyncio.sleep", new_callable=AsyncMock):
                result = await _public_request("/test")

        assert result == {"data": "ok"}
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self):
        """Failure: raises HTTPStatusError for non-429 errors."""
        error_response = MagicMock()
        error_response.status_code = 404
        error_response.text = "Not Found"

        http_error = httpx.HTTPStatusError("404", request=MagicMock(), response=error_response)
        error_response.raise_for_status = MagicMock(side_effect=http_error)

        mock_client = AsyncMock()
        mock_client.get.return_value = error_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.coinbase_api.public_market_data.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                await _public_request("/notfound")

    @pytest.mark.asyncio
    async def test_retries_on_generic_exception_then_raises(self):
        """Failure: retries once on generic exception, then raises."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = ConnectionError("DNS failed")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.coinbase_api.public_market_data.httpx.AsyncClient", return_value=mock_client):
            with patch("app.coinbase_api.public_market_data.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(ConnectionError):
                    await _public_request("/failing")

        # Called twice: initial + 1 retry
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_passes_query_params(self):
        """Edge case: query parameters are forwarded to httpx."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.coinbase_api.public_market_data.httpx.AsyncClient", return_value=mock_client):
            await _public_request("/test", params={"key": "value"})

        mock_client.get.assert_called_once()
        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs.get("params") == {"key": "value"}


# ---------------------------------------------------------------------------
# list_products
# ---------------------------------------------------------------------------


class TestListProducts:
    """Tests for list_products()"""

    @pytest.mark.asyncio
    async def test_returns_products(self):
        """Happy path: fetches and returns product list."""
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"products": [{"product_id": "BTC-USD"}]},
        ):
            result = await list_products()
            assert len(result) == 1
            assert result[0]["product_id"] == "BTC-USD"

    @pytest.mark.asyncio
    async def test_caches_products(self):
        """Edge case: second call returns cached products."""
        mock_request = AsyncMock(return_value={"products": [{"product_id": "BTC-USD"}]})

        with patch("app.coinbase_api.public_market_data._public_request", mock_request):
            await list_products()
            result = await list_products()

        assert len(result) == 1
        assert mock_request.call_count == 1


# ---------------------------------------------------------------------------
# get_product
# ---------------------------------------------------------------------------


class TestGetProduct:
    """Tests for get_product()"""

    @pytest.mark.asyncio
    async def test_returns_product_data(self):
        """Happy path: returns product details."""
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"product_id": "ETH-BTC", "price": "0.05"},
        ):
            result = await get_product("ETH-BTC")
            assert result["product_id"] == "ETH-BTC"


# ---------------------------------------------------------------------------
# get_ticker
# ---------------------------------------------------------------------------


class TestGetTicker:
    """Tests for get_ticker()"""

    @pytest.mark.asyncio
    async def test_returns_ticker(self):
        """Happy path: returns bid/ask ticker data."""
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"best_bid": "100", "best_ask": "101"},
        ):
            result = await get_ticker("BTC-USD")
            assert result["best_bid"] == "100"


# ---------------------------------------------------------------------------
# get_current_price
# ---------------------------------------------------------------------------


class TestGetCurrentPrice:
    """Tests for get_current_price()"""

    @pytest.mark.asyncio
    async def test_returns_midprice(self):
        """Happy path: returns mid-price from bid/ask."""
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"best_bid": "100", "best_ask": "102"},
        ):
            result = await get_current_price("BTC-USD")
            assert result == pytest.approx(101.0)

    @pytest.mark.asyncio
    async def test_falls_back_to_trade_price(self):
        """Edge case: uses trade price when bid/ask unavailable."""
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"best_bid": "0", "best_ask": "0", "trades": [{"price": "99"}]},
        ):
            result = await get_current_price("ETH-USD")
            assert result == pytest.approx(99.0)

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_data(self):
        """Edge case: returns 0.0 when no bid/ask and no trades."""
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"best_bid": "0", "best_ask": "0", "trades": []},
        ):
            result = await get_current_price("XYZ-USD")
            assert result == 0.0

    @pytest.mark.asyncio
    async def test_caches_positive_price(self):
        """Edge case: caches price > 0."""
        mock = AsyncMock(return_value={"best_bid": "50", "best_ask": "52"})

        with patch("app.coinbase_api.public_market_data._public_request", mock):
            price1 = await get_current_price("CACHE-USD")
            price2 = await get_current_price("CACHE-USD")

        assert price1 == pytest.approx(51.0)
        assert price2 == pytest.approx(51.0)
        assert mock.call_count == 1


# ---------------------------------------------------------------------------
# get_btc_usd_price / get_eth_usd_price
# ---------------------------------------------------------------------------


class TestConveniencePriceFunctions:
    """Tests for get_btc_usd_price() and get_eth_usd_price()"""

    @pytest.mark.asyncio
    async def test_btc_usd_price(self):
        """Happy path: returns BTC-USD mid-price."""
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"best_bid": "64000", "best_ask": "66000"},
        ):
            result = await get_btc_usd_price()
            assert result == pytest.approx(65000.0)

    @pytest.mark.asyncio
    async def test_eth_usd_price(self):
        """Happy path: returns ETH-USD mid-price."""
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"best_bid": "3400", "best_ask": "3600"},
        ):
            result = await get_eth_usd_price()
            assert result == pytest.approx(3500.0)


# ---------------------------------------------------------------------------
# get_product_stats
# ---------------------------------------------------------------------------


class TestGetProductStats:
    """Tests for get_product_stats()"""

    @pytest.mark.asyncio
    async def test_returns_24h_stats(self):
        """Happy path: returns volume and price change."""
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={
                "volume_24h": "8000",
                "volume_percentage_change_24h": "5.5",
                "price_percentage_change_24h": "-1.2",
            },
        ):
            result = await get_product_stats("ETH-BTC")
            assert result["volume_24h"] == pytest.approx(8000.0)
            assert result["price_percentage_change_24h"] == pytest.approx(-1.2)

    @pytest.mark.asyncio
    async def test_caches_stats(self):
        """Edge case: second call uses cache."""
        mock = AsyncMock(return_value={
            "volume_24h": "100",
            "volume_percentage_change_24h": "0",
            "price_percentage_change_24h": "0",
        })

        with patch("app.coinbase_api.public_market_data._public_request", mock):
            await get_product_stats("CACHED-BTC")
            result = await get_product_stats("CACHED-BTC")

        assert result["volume_24h"] == pytest.approx(100.0)
        assert mock.call_count == 1


# ---------------------------------------------------------------------------
# get_candles
# ---------------------------------------------------------------------------


class TestGetCandles:
    """Tests for get_candles()"""

    @pytest.mark.asyncio
    async def test_returns_candles(self):
        """Happy path: returns candle OHLCV data."""
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"candles": [{"open": "100", "close": "105"}]},
        ):
            result = await get_candles("ETH-BTC", 1000, 2000)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_passes_params_correctly(self):
        """Edge case: granularity and time range passed as params."""
        mock = AsyncMock(return_value={"candles": []})

        with patch("app.coinbase_api.public_market_data._public_request", mock):
            await get_candles("BTC-USD", 100, 200, granularity="ONE_HOUR")

        call_kwargs = mock.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[0][1]
        assert params["granularity"] == "ONE_HOUR"
        assert params["start"] == "100"
        assert params["end"] == "200"


# ---------------------------------------------------------------------------
# PublicMarketDataClient
# ---------------------------------------------------------------------------


class TestPublicMarketDataClient:
    """Tests for PublicMarketDataClient duck-type class"""

    @pytest.mark.asyncio
    async def test_list_products_delegates(self):
        """Happy path: delegates to module-level list_products."""
        client = PublicMarketDataClient()
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"products": [{"product_id": "BTC-USD"}]},
        ):
            result = await client.list_products()
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_current_price_delegates(self):
        """Happy path: delegates to module-level get_current_price."""
        client = PublicMarketDataClient()
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"best_bid": "50", "best_ask": "52"},
        ):
            result = await client.get_current_price("ETH-BTC")
            assert result == pytest.approx(51.0)

    @pytest.mark.asyncio
    async def test_get_product_book_returns_empty_structure(self):
        """Edge case: order book returns empty structure (no public endpoint)."""
        client = PublicMarketDataClient()
        result = await client.get_product_book("ETH-BTC")
        assert result == {"pricebook": {"bids": [], "asks": []}}

    @pytest.mark.asyncio
    async def test_get_btc_usd_price_delegates(self):
        """Happy path: returns BTC-USD price."""
        client = PublicMarketDataClient()
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"best_bid": "64000", "best_ask": "66000"},
        ):
            result = await client.get_btc_usd_price()
            assert result == pytest.approx(65000.0)

    @pytest.mark.asyncio
    async def test_get_candles_delegates(self):
        """Happy path: delegates to module-level get_candles."""
        client = PublicMarketDataClient()
        with patch(
            "app.coinbase_api.public_market_data._public_request",
            new_callable=AsyncMock,
            return_value={"candles": [{"open": "1"}]},
        ):
            result = await client.get_candles("BTC-USD", 100, 200)
            assert len(result) == 1
