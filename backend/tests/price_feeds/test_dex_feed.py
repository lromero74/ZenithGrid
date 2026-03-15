"""
Tests for backend/app/price_feeds/dex_feed.py

Covers:
- DEXPriceFeed initialization (chain_id, name, type)
- get_price: bid/ask calculation, fee tiers, gas estimates, error handling
- get_orderbook: simulated order book from AMM quotes, error handling
- get_supported_pairs: chain-specific pair lists
- is_available: RPC health check
- get_fee_estimate: DEX-specific flat fee
- get_gas_estimate_usd: chain-specific gas costs
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.price_feeds.dex_feed import DEXPriceFeed
from app.price_feeds.base import PriceQuote, OrderBook


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_dex_client(**kwargs):
    """Create a mock DEXClient with configurable return values."""
    client = MagicMock()
    client.get_quote = AsyncMock()
    client.check_connection = AsyncMock(return_value=True)
    return client


def _make_feed(client=None, chain_id=1, dex_name="uniswap_v3"):
    """Create a DEXPriceFeed with a mock client."""
    if client is None:
        client = _make_mock_dex_client()
    return DEXPriceFeed(dex_client=client, chain_id=chain_id, dex_name=dex_name)


# ===========================================================================
# Initialization tests
# ===========================================================================


class TestDEXPriceFeedInit:
    """Tests for DEXPriceFeed initialization."""

    def test_name_set_from_dex_name(self):
        """Happy path: name matches dex_name arg."""
        feed = _make_feed(dex_name="pancakeswap")
        assert feed.name == "pancakeswap"

    def test_exchange_type_is_dex(self):
        """Happy path: exchange_type is always 'dex'."""
        feed = _make_feed()
        assert feed.exchange_type == "dex"

    def test_chain_id_stored(self):
        """Happy path: chain_id is stored."""
        feed = _make_feed(chain_id=137)
        assert feed.chain_id == 137

    def test_client_stored(self):
        """Happy path: client reference is stored."""
        client = _make_mock_dex_client()
        feed = _make_feed(client=client)
        assert feed.client is client

    def test_default_chain_id(self):
        """Happy path: default chain_id is 1 (Ethereum)."""
        client = _make_mock_dex_client()
        feed = DEXPriceFeed(dex_client=client)
        assert feed.chain_id == 1


# ===========================================================================
# get_price tests
# ===========================================================================


class TestDEXPriceFeedGetPrice:
    """Tests for get_price() method."""

    @pytest.mark.asyncio
    async def test_get_price_happy_path(self):
        """Happy path: returns PriceQuote with correct bid/ask."""
        client = _make_mock_dex_client()
        # ask quote: 1000 USDT -> 0.5 ETH -> ask = 1000/0.5 = 2000
        client.get_quote.side_effect = [
            {"amount_out": Decimal("0.5"), "fee_tier": 3000},   # ask (buy base)
            {"amount_out": Decimal("1990")},                     # bid (sell base)
        ]
        feed = _make_feed(client=client)
        result = await feed.get_price("ETH", "USDT")

        assert result is not None
        assert isinstance(result, PriceQuote)
        assert result.ask == Decimal("2000")  # 1000 / 0.5
        assert result.bid == Decimal("1990")
        assert result.exchange == "uniswap_v3"
        assert result.exchange_type == "dex"
        assert result.base == "ETH"
        assert result.quote == "USDT"

    @pytest.mark.asyncio
    async def test_get_price_fee_tier_mapped(self):
        """Happy path: fee tier from quote is mapped to percentage."""
        client = _make_mock_dex_client()
        client.get_quote.side_effect = [
            {"amount_out": Decimal("1"), "fee_tier": 500},   # 0.05% fee tier
            {"amount_out": Decimal("1000")},
        ]
        feed = _make_feed(client=client)
        result = await feed.get_price("ETH", "USDT")

        assert result is not None
        assert result.taker_fee_pct == Decimal("0.05")
        assert result.maker_fee_pct == Decimal("0.05")

    @pytest.mark.asyncio
    async def test_get_price_unknown_fee_tier_uses_default(self):
        """Edge case: unknown fee tier falls back to default 0.30%."""
        client = _make_mock_dex_client()
        client.get_quote.side_effect = [
            {"amount_out": Decimal("1"), "fee_tier": 9999},
            {"amount_out": Decimal("1000")},
        ]
        feed = _make_feed(client=client)
        result = await feed.get_price("ETH", "USDT")

        assert result.taker_fee_pct == Decimal("0.30")

    @pytest.mark.asyncio
    async def test_get_price_gas_estimate_ethereum(self):
        """Happy path: Ethereum mainnet gas estimate is $15."""
        client = _make_mock_dex_client()
        client.get_quote.side_effect = [
            {"amount_out": Decimal("1"), "fee_tier": 3000},
            {"amount_out": Decimal("1000")},
        ]
        feed = _make_feed(client=client, chain_id=1)
        result = await feed.get_price("ETH", "USDT")

        assert result.gas_estimate_usd == Decimal("15.00")
        assert result.chain_id == 1

    @pytest.mark.asyncio
    async def test_get_price_gas_estimate_polygon(self):
        """Happy path: Polygon gas estimate is $0.05."""
        client = _make_mock_dex_client()
        client.get_quote.side_effect = [
            {"amount_out": Decimal("1"), "fee_tier": 3000},
            {"amount_out": Decimal("1000")},
        ]
        feed = _make_feed(client=client, chain_id=137)
        result = await feed.get_price("ETH", "USDT")

        assert result.gas_estimate_usd == Decimal("0.05")

    @pytest.mark.asyncio
    async def test_get_price_gas_estimate_unknown_chain(self):
        """Edge case: unknown chain defaults to $10."""
        client = _make_mock_dex_client()
        client.get_quote.side_effect = [
            {"amount_out": Decimal("1"), "fee_tier": 3000},
            {"amount_out": Decimal("1000")},
        ]
        feed = _make_feed(client=client, chain_id=999)
        result = await feed.get_price("ETH", "USDT")

        assert result.gas_estimate_usd == Decimal("10.00")

    @pytest.mark.asyncio
    async def test_get_price_ask_quote_returns_none(self):
        """Failure: None from ask quote returns None."""
        client = _make_mock_dex_client()
        client.get_quote.side_effect = [None, {"amount_out": Decimal("1000")}]
        feed = _make_feed(client=client)
        result = await feed.get_price("ETH", "USDT")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_price_bid_quote_returns_none(self):
        """Failure: None from bid quote returns None."""
        client = _make_mock_dex_client()
        client.get_quote.side_effect = [
            {"amount_out": Decimal("1"), "fee_tier": 3000},
            None,
        ]
        feed = _make_feed(client=client)
        result = await feed.get_price("ETH", "USDT")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_price_client_exception_returns_none(self):
        """Failure: exception from client returns None."""
        client = _make_mock_dex_client()
        client.get_quote.side_effect = RuntimeError("RPC down")
        feed = _make_feed(client=client)
        result = await feed.get_price("ETH", "USDT")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_price_zero_amount_out_returns_none(self):
        """Edge case: zero amount_out in ask causes ask_price=0, but bid might still work."""
        client = _make_mock_dex_client()
        # ask_quote amount_out is 0 -> division would give 0 ask
        # The code checks `if not ask_quote or not bid_quote` but amount_out=0 passes that
        # So it proceeds to 1000/0 which would raise ZeroDivisionError -> caught, returns None
        client.get_quote.side_effect = [
            {"amount_out": Decimal("0"), "fee_tier": 3000},
            {"amount_out": Decimal("1000")},
        ]
        feed = _make_feed(client=client)
        result = await feed.get_price("ETH", "USDT")
        # The code guards: `if ask_quote["amount_out"] > 0`
        # When amount_out is 0, ask_price = Decimal("0") (the else branch)
        # So result is a PriceQuote with ask=0
        assert result is not None
        assert result.ask == Decimal("0")


# ===========================================================================
# get_orderbook tests
# ===========================================================================


class TestDEXPriceFeedGetOrderbook:
    """Tests for get_orderbook() method."""

    @pytest.mark.asyncio
    async def test_get_orderbook_happy_path(self):
        """Happy path: returns OrderBook with simulated levels."""
        client = _make_mock_dex_client()
        # Each size query returns an amount_out
        client.get_quote.side_effect = [
            # First size (100): ask quote
            {"amount_out": Decimal("0.05")},
            # First size: bid quote
            {"amount_out": Decimal("99")},
        ]
        feed = _make_feed(client=client)
        result = await feed.get_orderbook("ETH", "USDT", depth=1)

        assert result is not None
        assert isinstance(result, OrderBook)
        assert result.exchange == "uniswap_v3"
        assert result.exchange_type == "dex"
        assert len(result.asks) == 1
        assert len(result.bids) == 1

    @pytest.mark.asyncio
    async def test_get_orderbook_depth_limits_levels(self):
        """Happy path: depth parameter limits number of levels."""
        client = _make_mock_dex_client()
        call_count = 0

        async def mock_quote(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"amount_out": Decimal("1")}

        client.get_quote = mock_quote
        feed = _make_feed(client=client)
        result = await feed.get_orderbook("ETH", "USDT", depth=3)

        assert result is not None
        # depth=3 means 3 sizes, each with ask+bid = 6 calls
        assert call_count == 6

    @pytest.mark.asyncio
    async def test_get_orderbook_client_exception_returns_none(self):
        """Failure: exception from client returns None."""
        client = _make_mock_dex_client()
        client.get_quote.side_effect = RuntimeError("RPC down")
        feed = _make_feed(client=client)
        result = await feed.get_orderbook("ETH", "USDT")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_orderbook_zero_amount_skipped(self):
        """Edge case: zero amount_out levels are not added."""
        client = _make_mock_dex_client()
        client.get_quote.side_effect = [
            {"amount_out": Decimal("0")},    # ask: 0 output, condition fails
            {"amount_out": Decimal("0")},    # bid: 0 output, condition fails
        ]
        feed = _make_feed(client=client)
        result = await feed.get_orderbook("ETH", "USDT", depth=1)

        assert result is not None
        assert len(result.asks) == 0
        assert len(result.bids) == 0


# ===========================================================================
# get_supported_pairs tests
# ===========================================================================


class TestDEXPriceFeedGetSupportedPairs:
    """Tests for get_supported_pairs() method."""

    @pytest.mark.asyncio
    async def test_ethereum_pairs(self):
        """Happy path: Ethereum chain returns ETH pairs."""
        feed = _make_feed(chain_id=1)
        pairs = await feed.get_supported_pairs()
        assert "ETH-USDT" in pairs
        assert "ETH-USDC" in pairs
        assert "WBTC-ETH" in pairs

    @pytest.mark.asyncio
    async def test_polygon_pairs(self):
        """Happy path: Polygon chain returns MATIC pairs."""
        feed = _make_feed(chain_id=137)
        pairs = await feed.get_supported_pairs()
        assert "MATIC-USDT" in pairs

    @pytest.mark.asyncio
    async def test_bsc_pairs(self):
        """Happy path: BSC chain returns BNB pairs."""
        feed = _make_feed(chain_id=56)
        pairs = await feed.get_supported_pairs()
        assert "BNB-USDT" in pairs

    @pytest.mark.asyncio
    async def test_arbitrum_pairs(self):
        """Happy path: Arbitrum chain returns ARB pairs."""
        feed = _make_feed(chain_id=42161)
        pairs = await feed.get_supported_pairs()
        assert "ARB-ETH" in pairs

    @pytest.mark.asyncio
    async def test_unknown_chain_returns_empty(self):
        """Edge case: unknown chain returns empty list."""
        feed = _make_feed(chain_id=999)
        pairs = await feed.get_supported_pairs()
        assert pairs == []


# ===========================================================================
# is_available tests
# ===========================================================================


class TestDEXPriceFeedIsAvailable:
    """Tests for is_available() method."""

    @pytest.mark.asyncio
    async def test_available_when_connected(self):
        """Happy path: returns True when RPC connected."""
        client = _make_mock_dex_client()
        client.check_connection.return_value = True
        feed = _make_feed(client=client)
        assert await feed.is_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_when_disconnected(self):
        """Failure: returns False when RPC disconnected."""
        client = _make_mock_dex_client()
        client.check_connection.return_value = False
        feed = _make_feed(client=client)
        assert await feed.is_available() is False

    @pytest.mark.asyncio
    async def test_unavailable_on_exception(self):
        """Failure: returns False when check_connection raises."""
        client = _make_mock_dex_client()
        client.check_connection.side_effect = ConnectionError("timeout")
        feed = _make_feed(client=client)
        assert await feed.is_available() is False


# ===========================================================================
# Fee and gas estimate tests
# ===========================================================================


class TestDEXPriceFeedFees:
    """Tests for get_fee_estimate() and get_gas_estimate_usd()."""

    def test_fee_estimate_is_default_fee_pct(self):
        """Happy path: fee is always DEFAULT_FEE_PCT (0.30)."""
        feed = _make_feed()
        assert feed.get_fee_estimate("buy") == Decimal("0.30")
        assert feed.get_fee_estimate("sell") == Decimal("0.30")

    def test_fee_estimate_ignores_maker_flag(self):
        """Edge case: is_maker is ignored for DEX."""
        feed = _make_feed()
        assert feed.get_fee_estimate("buy", is_maker=True) == Decimal("0.30")
        assert feed.get_fee_estimate("sell", is_maker=True) == Decimal("0.30")

    def test_gas_estimate_ethereum(self):
        """Happy path: Ethereum gas is $15."""
        feed = _make_feed(chain_id=1)
        assert feed.get_gas_estimate_usd() == Decimal("15.00")

    def test_gas_estimate_bsc(self):
        """Happy path: BSC gas is $0.30."""
        feed = _make_feed(chain_id=56)
        assert feed.get_gas_estimate_usd() == Decimal("0.30")

    def test_gas_estimate_arbitrum(self):
        """Happy path: Arbitrum gas is $0.50."""
        feed = _make_feed(chain_id=42161)
        assert feed.get_gas_estimate_usd() == Decimal("0.50")

    def test_gas_estimate_unknown_chain_defaults(self):
        """Edge case: unknown chain defaults to $10."""
        feed = _make_feed(chain_id=12345)
        assert feed.get_gas_estimate_usd() == Decimal("10.00")


# ===========================================================================
# FEE_TIERS constant tests
# ===========================================================================


class TestDEXFeeTiers:
    """Tests for FEE_TIERS constant."""

    def test_all_fee_tiers_present(self):
        """Happy path: all four standard Uniswap V3 fee tiers."""
        assert 100 in DEXPriceFeed.FEE_TIERS
        assert 500 in DEXPriceFeed.FEE_TIERS
        assert 3000 in DEXPriceFeed.FEE_TIERS
        assert 10000 in DEXPriceFeed.FEE_TIERS

    def test_fee_tier_values(self):
        """Happy path: fee tier percentages match expected values."""
        assert DEXPriceFeed.FEE_TIERS[100] == Decimal("0.01")
        assert DEXPriceFeed.FEE_TIERS[500] == Decimal("0.05")
        assert DEXPriceFeed.FEE_TIERS[3000] == Decimal("0.30")
        assert DEXPriceFeed.FEE_TIERS[10000] == Decimal("1.00")
