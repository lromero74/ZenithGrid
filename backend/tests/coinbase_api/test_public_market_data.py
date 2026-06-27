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
    bulk_prices_for_products,
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


class TestBulkPricesForProducts:
    """Bulk price resolution via the cached list_products endpoint.

    This is the hot-path optimization that replaces N serial per-product
    ticker calls (each paying a ~150ms rate-limit lock) with ONE cached
    bulk fetch. Used by calculate_market_budget and fetch_position_prices
    to make the bots-list endpoint's cold call ~10x faster.
    """

    @pytest.mark.asyncio
    async def test_returns_mapping_for_requested_products(self):
        mock_request = AsyncMock(return_value={
            "products": [
                {"product_id": "BTC-USD", "price": "60000.0"},
                {"product_id": "ETH-USD", "price": "3000.0"},
                {"product_id": "SOL-USD", "price": "150.0"},
                {"product_id": "XRP-USD", "price": "0.5"},
            ]
        })
        with patch("app.coinbase_api.public_market_data._public_request", mock_request):
            result = await bulk_prices_for_products(["BTC-USD", "SOL-USD"])
        assert result == {"BTC-USD": 60000.0, "SOL-USD": 150.0}

    @pytest.mark.asyncio
    async def test_missing_products_omitted(self):
        """Delisted/unknown products just don't appear in the result —
        caller handles fallback (e.g. use position.average_buy_price)."""
        mock_request = AsyncMock(return_value={
            "products": [{"product_id": "BTC-USD", "price": "60000.0"}]
        })
        with patch("app.coinbase_api.public_market_data._public_request", mock_request):
            result = await bulk_prices_for_products(["BTC-USD", "DELISTED-USD"])
        assert result == {"BTC-USD": 60000.0}
        assert "DELISTED-USD" not in result

    @pytest.mark.asyncio
    async def test_zero_or_missing_price_filtered(self):
        """Products with price=0, empty string, or missing price field
        are excluded — they'd poison downstream valuation math."""
        mock_request = AsyncMock(return_value={
            "products": [
                {"product_id": "BTC-USD", "price": "60000.0"},
                {"product_id": "ZERO-USD", "price": "0"},
                {"product_id": "NONE-USD", "price": None},
                {"product_id": "EMPTY-USD", "price": ""},
                {"product_id": "MISSING-USD"},  # no price key at all
            ]
        })
        with patch("app.coinbase_api.public_market_data._public_request", mock_request):
            result = await bulk_prices_for_products([
                "BTC-USD", "ZERO-USD", "NONE-USD", "EMPTY-USD", "MISSING-USD",
            ])
        assert result == {"BTC-USD": 60000.0}

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_dict_without_fetch(self):
        """Short-circuit: no products to price, no API call."""
        mock_request = AsyncMock()
        with patch("app.coinbase_api.public_market_data._public_request", mock_request):
            result = await bulk_prices_for_products([])
        assert result == {}
        mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_list_products_cache(self):
        """Two calls back-to-back hit the 1-hour list_products cache —
        only one underlying HTTP fetch. This is the whole point of the
        optimization: subsequent callers don't pay the API cost."""
        mock_request = AsyncMock(return_value={
            "products": [{"product_id": "BTC-USD", "price": "60000.0"}]
        })
        with patch("app.coinbase_api.public_market_data._public_request", mock_request):
            await bulk_prices_for_products(["BTC-USD"])
            await bulk_prices_for_products(["BTC-USD"])
        assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_empty_on_list_products_error(self):
        """Upstream failure must not crash the caller — return empty dict
        so calculate_market_budget can fall back to average_buy_price."""
        with patch(
            "app.coinbase_api.public_market_data.list_products",
            new_callable=AsyncMock,
            side_effect=RuntimeError("coinbase on fire"),
        ):
            result = await bulk_prices_for_products(["BTC-USD", "ETH-USD"])
        assert result == {}


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

    @pytest.mark.asyncio
    async def test_usd_equivalent_stable_pair_skips_product_request(self):
        """USDC-USD is local valuation metadata, not a Coinbase product probe."""
        mock = AsyncMock()

        with patch("app.coinbase_api.public_market_data._public_request", mock):
            result = await get_product("USDC-USD")

        assert result["product_id"] == "USDC-USD"
        assert result["price"] == "1.0"
        mock.assert_not_called()


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
    async def test_usd_equivalent_stable_pair_skips_ticker(self):
        """USDC-USD is a valuation pair, not a Coinbase ticker call."""
        mock = AsyncMock()

        with patch("app.coinbase_api.public_market_data._public_request", mock):
            result = await get_current_price("USDC-USD")

        assert result == pytest.approx(1.0)
        mock.assert_not_called()

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


class TestGetCurrentPriceNegativeCache:
    """Tests for 404 negative caching in get_current_price()"""

    @pytest.mark.asyncio
    async def test_404_triggers_negative_cache_and_blocks_retry(self):
        """404 from ticker triggers negative cache; second call raises without API hit."""
        error_response = MagicMock()
        error_response.status_code = 404
        error_response.text = "Not Found"
        http_error = httpx.HTTPStatusError("404", request=MagicMock(), response=error_response)

        mock_request = AsyncMock(side_effect=http_error)

        with patch("app.coinbase_api.public_market_data._public_request", mock_request):
            # First call: hits API, gets 404, marks negative cache
            with pytest.raises(httpx.HTTPStatusError):
                await get_current_price("DELISTED-BTC")

        assert mock_request.call_count == 1

        # Second call: should raise ValueError (negative cached) WITHOUT hitting API
        mock_request.reset_mock()
        with patch("app.coinbase_api.public_market_data._public_request", mock_request):
            with pytest.raises(ValueError, match="not found.*negative cached"):
                await get_current_price("DELISTED-BTC")

        mock_request.assert_not_called()


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
