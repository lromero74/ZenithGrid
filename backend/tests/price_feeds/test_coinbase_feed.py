"""
Tests for CoinbasePriceFeed — Coinbase exchange price feed implementation.

Covers:
- get_price: ticker parsing, bid/ask validation, error handling
- get_orderbook: parsing bids/asks, depth limiting, error handling
- get_supported_pairs: product fetching, caching, filtering disabled products
- is_available: health check via get_current_price
- get_fee_estimate: maker/taker fee logic
- Edge cases: None ticker, zero prices, empty orderbook, API errors
"""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.price_feeds.coinbase_feed import CoinbasePriceFeed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_client():
    """Create a mock CoinbaseClient/CoinbaseAdapter."""
    client = MagicMock()
    client.get_ticker = AsyncMock()
    client.get_orderbook = AsyncMock()
    client.get_products = AsyncMock()
    client.get_current_price = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# TestCoinbasePriceFeedInit
# ---------------------------------------------------------------------------

class TestCoinbasePriceFeedInit:
    """Tests for initialization."""

    def test_name_and_type(self):
        client = _make_mock_client()
        feed = CoinbasePriceFeed(client)
        assert feed.name == "coinbase"
        assert feed.exchange_type == "cex"

    def test_client_stored(self):
        client = _make_mock_client()
        feed = CoinbasePriceFeed(client)
        assert feed.client is client

    def test_supported_pairs_cache_initially_none(self):
        client = _make_mock_client()
        feed = CoinbasePriceFeed(client)
        assert feed._supported_pairs_cache is None


# ---------------------------------------------------------------------------
# TestGetPrice
# ---------------------------------------------------------------------------

class TestGetPrice:
    """Tests for get_price method."""

    @pytest.mark.asyncio
    async def test_valid_ticker_returns_price_quote(self):
        client = _make_mock_client()
        client.get_ticker.return_value = {"bid": "49999.00", "ask": "50001.00"}
        feed = CoinbasePriceFeed(client)

        quote = await feed.get_price("BTC", "USD")

        assert quote is not None
        assert quote.exchange == "coinbase"
        assert quote.exchange_type == "cex"
        assert quote.base == "BTC"
        assert quote.quote == "USD"
        assert quote.bid == Decimal("49999.00")
        assert quote.ask == Decimal("50001.00")
        assert quote.taker_fee_pct == Decimal("0.6")
        assert quote.maker_fee_pct == Decimal("0.4")

    @pytest.mark.asyncio
    async def test_ticker_called_with_correct_product_id(self):
        client = _make_mock_client()
        client.get_ticker.return_value = {"bid": "100", "ask": "101"}
        feed = CoinbasePriceFeed(client)

        await feed.get_price("ETH", "BTC")
        client.get_ticker.assert_awaited_once_with("ETH-BTC")

    @pytest.mark.asyncio
    async def test_none_ticker_returns_none(self):
        client = _make_mock_client()
        client.get_ticker.return_value = None
        feed = CoinbasePriceFeed(client)

        result = await feed.get_price("BTC", "USD")
        assert result is None

    @pytest.mark.asyncio
    async def test_zero_bid_returns_none(self):
        client = _make_mock_client()
        client.get_ticker.return_value = {"bid": "0", "ask": "50001.00"}
        feed = CoinbasePriceFeed(client)

        result = await feed.get_price("BTC", "USD")
        assert result is None

    @pytest.mark.asyncio
    async def test_zero_ask_returns_none(self):
        client = _make_mock_client()
        client.get_ticker.return_value = {"bid": "50000", "ask": "0"}
        feed = CoinbasePriceFeed(client)

        result = await feed.get_price("BTC", "USD")
        assert result is None

    @pytest.mark.asyncio
    async def test_negative_bid_returns_none(self):
        client = _make_mock_client()
        client.get_ticker.return_value = {"bid": "-1", "ask": "50001"}
        feed = CoinbasePriceFeed(client)

        result = await feed.get_price("BTC", "USD")
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_bid_key_treated_as_zero(self):
        client = _make_mock_client()
        client.get_ticker.return_value = {"ask": "50001"}
        feed = CoinbasePriceFeed(client)

        result = await feed.get_price("BTC", "USD")
        assert result is None  # bid defaults to 0 which is <= 0

    @pytest.mark.asyncio
    async def test_api_exception_returns_none(self):
        client = _make_mock_client()
        client.get_ticker.side_effect = RuntimeError("Connection timeout")
        feed = CoinbasePriceFeed(client)

        result = await feed.get_price("BTC", "USD")
        assert result is None

    @pytest.mark.asyncio
    async def test_timestamp_is_set(self):
        client = _make_mock_client()
        client.get_ticker.return_value = {"bid": "100", "ask": "101"}
        feed = CoinbasePriceFeed(client)

        quote = await feed.get_price("ETH", "USD")
        assert isinstance(quote.timestamp, datetime)


# ---------------------------------------------------------------------------
# TestGetOrderbook
# ---------------------------------------------------------------------------

class TestGetOrderbook:
    """Tests for get_orderbook method."""

    @pytest.mark.asyncio
    async def test_valid_orderbook_parsed(self):
        client = _make_mock_client()
        client.get_orderbook.return_value = {
            "bids": [["50000", "0.5", 1], ["49990", "1.0", 2]],
            "asks": [["50010", "0.3", 1], ["50020", "0.8", 1]],
        }
        feed = CoinbasePriceFeed(client)

        book = await feed.get_orderbook("BTC", "USD", depth=5)

        assert book is not None
        assert book.exchange == "coinbase"
        assert book.base == "BTC"
        assert book.quote == "USD"
        assert len(book.bids) == 2
        assert len(book.asks) == 2
        assert book.bids[0].price == Decimal("50000")
        assert book.bids[0].quantity == Decimal("0.5")
        assert book.asks[0].price == Decimal("50010")
        assert book.asks[0].quantity == Decimal("0.3")

    @pytest.mark.asyncio
    async def test_orderbook_depth_limiting(self):
        client = _make_mock_client()
        client.get_orderbook.return_value = {
            "bids": [
                ["50000", "0.5", 1], ["49990", "1.0", 2],
                ["49980", "0.8", 1], ["49970", "0.3", 1],
            ],
            "asks": [
                ["50010", "0.3", 1], ["50020", "0.8", 1],
                ["50030", "0.6", 1], ["50040", "0.2", 1],
            ],
        }
        feed = CoinbasePriceFeed(client)

        book = await feed.get_orderbook("BTC", "USD", depth=2)

        assert len(book.bids) == 2
        assert len(book.asks) == 2

    @pytest.mark.asyncio
    async def test_orderbook_called_with_level_2(self):
        client = _make_mock_client()
        client.get_orderbook.return_value = {"bids": [], "asks": []}
        feed = CoinbasePriceFeed(client)

        await feed.get_orderbook("BTC", "USD")
        client.get_orderbook.assert_awaited_once_with("BTC-USD", level=2)

    @pytest.mark.asyncio
    async def test_none_orderbook_returns_none(self):
        client = _make_mock_client()
        client.get_orderbook.return_value = None
        feed = CoinbasePriceFeed(client)

        result = await feed.get_orderbook("BTC", "USD")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_bids_and_asks(self):
        client = _make_mock_client()
        client.get_orderbook.return_value = {"bids": [], "asks": []}
        feed = CoinbasePriceFeed(client)

        book = await feed.get_orderbook("BTC", "USD")
        assert book is not None
        assert len(book.bids) == 0
        assert len(book.asks) == 0

    @pytest.mark.asyncio
    async def test_orderbook_api_exception_returns_none(self):
        client = _make_mock_client()
        client.get_orderbook.side_effect = RuntimeError("API error")
        feed = CoinbasePriceFeed(client)

        result = await feed.get_orderbook("BTC", "USD")
        assert result is None


# ---------------------------------------------------------------------------
# TestGetSupportedPairs
# ---------------------------------------------------------------------------

class TestGetSupportedPairs:
    """Tests for get_supported_pairs method."""

    @pytest.mark.asyncio
    async def test_returns_product_ids(self):
        client = _make_mock_client()
        client.get_products.return_value = [
            {"product_id": "BTC-USD", "trading_disabled": False},
            {"product_id": "ETH-USD", "trading_disabled": False},
        ]
        feed = CoinbasePriceFeed(client)

        pairs = await feed.get_supported_pairs()
        assert "BTC-USD" in pairs
        assert "ETH-USD" in pairs
        assert len(pairs) == 2

    @pytest.mark.asyncio
    async def test_filters_disabled_products(self):
        client = _make_mock_client()
        client.get_products.return_value = [
            {"product_id": "BTC-USD", "trading_disabled": False},
            {"product_id": "SHIB-USD", "trading_disabled": True},
        ]
        feed = CoinbasePriceFeed(client)

        pairs = await feed.get_supported_pairs()
        assert "BTC-USD" in pairs
        assert "SHIB-USD" not in pairs

    @pytest.mark.asyncio
    async def test_caches_result(self):
        client = _make_mock_client()
        client.get_products.return_value = [
            {"product_id": "BTC-USD"},
        ]
        feed = CoinbasePriceFeed(client)

        # First call fetches from API
        await feed.get_supported_pairs()
        # Second call should use cache
        await feed.get_supported_pairs()

        client.get_products.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_api_error_returns_empty_list(self):
        client = _make_mock_client()
        client.get_products.side_effect = RuntimeError("API down")
        feed = CoinbasePriceFeed(client)

        pairs = await feed.get_supported_pairs()
        assert pairs == []

    @pytest.mark.asyncio
    async def test_product_without_trading_disabled_field_included(self):
        """Products that don't have trading_disabled set should be included."""
        client = _make_mock_client()
        client.get_products.return_value = [
            {"product_id": "BTC-USD"},  # No trading_disabled field
        ]
        feed = CoinbasePriceFeed(client)

        pairs = await feed.get_supported_pairs()
        assert "BTC-USD" in pairs


# ---------------------------------------------------------------------------
# TestIsAvailable
# ---------------------------------------------------------------------------

class TestIsAvailable:
    """Tests for is_available health check."""

    @pytest.mark.asyncio
    async def test_available_when_price_positive(self):
        client = _make_mock_client()
        client.get_current_price.return_value = 50000.0
        feed = CoinbasePriceFeed(client)

        assert await feed.is_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_when_price_none(self):
        client = _make_mock_client()
        client.get_current_price.return_value = None
        feed = CoinbasePriceFeed(client)

        assert await feed.is_available() is False

    @pytest.mark.asyncio
    async def test_unavailable_when_price_zero(self):
        client = _make_mock_client()
        client.get_current_price.return_value = 0
        feed = CoinbasePriceFeed(client)

        assert await feed.is_available() is False

    @pytest.mark.asyncio
    async def test_unavailable_on_exception(self):
        client = _make_mock_client()
        client.get_current_price.side_effect = RuntimeError("Timeout")
        feed = CoinbasePriceFeed(client)

        assert await feed.is_available() is False

    @pytest.mark.asyncio
    async def test_health_check_uses_btc_usd(self):
        client = _make_mock_client()
        client.get_current_price.return_value = 50000.0
        feed = CoinbasePriceFeed(client)

        await feed.is_available()
        client.get_current_price.assert_awaited_once_with("BTC-USD")


# ---------------------------------------------------------------------------
# TestGetFeeEstimate
# ---------------------------------------------------------------------------

class TestGetFeeEstimate:
    """Tests for get_fee_estimate method."""

    def test_taker_fee(self):
        client = _make_mock_client()
        feed = CoinbasePriceFeed(client)
        assert feed.get_fee_estimate("buy", is_maker=False) == Decimal("0.6")
        assert feed.get_fee_estimate("sell", is_maker=False) == Decimal("0.6")

    def test_maker_fee(self):
        client = _make_mock_client()
        feed = CoinbasePriceFeed(client)
        assert feed.get_fee_estimate("buy", is_maker=True) == Decimal("0.4")
        assert feed.get_fee_estimate("sell", is_maker=True) == Decimal("0.4")

    def test_fee_constants(self):
        assert CoinbasePriceFeed.TAKER_FEE_PCT == Decimal("0.6")
        assert CoinbasePriceFeed.MAKER_FEE_PCT == Decimal("0.4")
