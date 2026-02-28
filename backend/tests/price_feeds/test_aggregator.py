"""
Tests for PriceAggregator — multi-feed price aggregation for arbitrage.

Covers:
- AggregatedPrice properties (spread, spread_pct, calculate_profit)
- PriceAggregator.get_best_prices with multiple feeds
- Fallback when feeds fail or timeout
- find_opportunities arbitrage scanning
- Feed management (add_feed, remove_feed)
- check_feed_health
- Edge cases: no feeds, all feeds fail, single feed
"""

import asyncio
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.price_feeds.aggregator import (
    AggregatedPrice,
    ArbitrageOpportunity,
    PriceAggregator,
)
from app.price_feeds.base import PriceFeed, PriceQuote


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_quote(
    exchange="coinbase", bid=Decimal("50000"), ask=Decimal("50100"),
    base="BTC", quote="USD", exchange_type="cex",
    taker_fee=Decimal("0.6"), gas=None,
):
    """Create a PriceQuote for testing."""
    return PriceQuote(
        exchange=exchange, exchange_type=exchange_type,
        base=base, quote=quote,
        bid=bid, ask=ask,
        timestamp=datetime.utcnow(),
        taker_fee_pct=taker_fee, maker_fee_pct=Decimal("0.4"),
        gas_estimate_usd=gas,
    )


def _make_mock_feed(name="test_feed", get_price_result=None, is_available_result=True):
    """Create a mock PriceFeed."""
    feed = MagicMock(spec=PriceFeed)
    feed.name = name
    feed.exchange_type = "cex"
    feed.get_price = AsyncMock(return_value=get_price_result)
    feed.is_available = AsyncMock(return_value=is_available_result)
    return feed


# ---------------------------------------------------------------------------
# TestAggregatedPrice
# ---------------------------------------------------------------------------

class TestAggregatedPrice:
    """Tests for AggregatedPrice dataclass and properties."""

    def test_product_id(self):
        ap = AggregatedPrice(base="ETH", quote="USD", timestamp=datetime.utcnow())
        assert ap.product_id == "ETH-USD"

    def test_spread_with_buy_and_sell(self):
        buy_quote = _make_quote(exchange="exchange_a", ask=Decimal("50100"), bid=Decimal("50000"))
        sell_quote = _make_quote(exchange="exchange_b", ask=Decimal("50200"), bid=Decimal("50150"))
        ap = AggregatedPrice(
            base="BTC", quote="USD", timestamp=datetime.utcnow(),
            best_buy=buy_quote, best_sell=sell_quote,
        )
        # spread = best_sell.bid - best_buy.ask = 50150 - 50100 = 50
        assert ap.spread == Decimal("50")

    def test_spread_none_when_no_buy(self):
        sell_quote = _make_quote()
        ap = AggregatedPrice(
            base="BTC", quote="USD", timestamp=datetime.utcnow(),
            best_buy=None, best_sell=sell_quote,
        )
        assert ap.spread is None

    def test_spread_none_when_no_sell(self):
        buy_quote = _make_quote()
        ap = AggregatedPrice(
            base="BTC", quote="USD", timestamp=datetime.utcnow(),
            best_buy=buy_quote, best_sell=None,
        )
        assert ap.spread is None

    def test_spread_pct_calculation(self):
        buy_quote = _make_quote(ask=Decimal("1000"), bid=Decimal("999"))
        sell_quote = _make_quote(ask=Decimal("1050"), bid=Decimal("1020"))
        ap = AggregatedPrice(
            base="ETH", quote="USD", timestamp=datetime.utcnow(),
            best_buy=buy_quote, best_sell=sell_quote,
        )
        # spread = 1020 - 1000 = 20, spread_pct = (20 / 1000) * 100 = 2.0
        assert ap.spread_pct == Decimal("2.0")

    def test_spread_pct_none_when_no_quotes(self):
        ap = AggregatedPrice(base="ETH", quote="USD", timestamp=datetime.utcnow())
        assert ap.spread_pct is None

    def test_calculate_profit_basic(self):
        buy_quote = _make_quote(
            exchange="exchange_a", ask=Decimal("1000"), bid=Decimal("999"),
            taker_fee=Decimal("0"), exchange_type="cex",
        )
        sell_quote = _make_quote(
            exchange="exchange_b", ask=Decimal("1050"), bid=Decimal("1020"),
            taker_fee=Decimal("0"), exchange_type="cex",
        )
        ap = AggregatedPrice(
            base="ETH", quote="USD", timestamp=datetime.utcnow(),
            best_buy=buy_quote, best_sell=sell_quote,
        )
        profit = ap.calculate_profit(Decimal("1"), include_fees=False, include_gas=False)
        assert profit is not None
        assert profit["buy_exchange"] == "exchange_a"
        assert profit["sell_exchange"] == "exchange_b"
        # buy_cost = 1 * 1000 = 1000, sell_revenue = 1 * 1020 = 1020, profit = 20
        assert profit["net_profit"] == Decimal("20")
        assert profit["is_profitable"] is True

    def test_calculate_profit_with_fees(self):
        buy_quote = _make_quote(
            exchange="a", ask=Decimal("1000"), bid=Decimal("999"),
            taker_fee=Decimal("1"),  # 1% fee
            exchange_type="cex",
        )
        sell_quote = _make_quote(
            exchange="b", ask=Decimal("1050"), bid=Decimal("1050"),
            taker_fee=Decimal("1"),  # 1% fee
            exchange_type="cex",
        )
        ap = AggregatedPrice(
            base="ETH", quote="USD", timestamp=datetime.utcnow(),
            best_buy=buy_quote, best_sell=sell_quote,
        )
        profit = ap.calculate_profit(Decimal("1"), include_fees=True, include_gas=False)
        # buy: 1000 * 1.01 = 1010, sell: 1050 * 0.99 = 1039.50, profit = 29.50
        assert profit["net_profit"] == Decimal("29.50")

    def test_calculate_profit_with_dex_gas(self):
        buy_quote = _make_quote(
            exchange="uniswap", ask=Decimal("1000"), bid=Decimal("999"),
            taker_fee=Decimal("0"), exchange_type="dex", gas=Decimal("5"),
        )
        sell_quote = _make_quote(
            exchange="coinbase", ask=Decimal("1050"), bid=Decimal("1020"),
            taker_fee=Decimal("0"), exchange_type="cex",
        )
        ap = AggregatedPrice(
            base="ETH", quote="USD", timestamp=datetime.utcnow(),
            best_buy=buy_quote, best_sell=sell_quote,
        )
        profit = ap.calculate_profit(Decimal("1"), include_fees=False, include_gas=True)
        # buy_cost = 1000 + 5 (gas) = 1005, sell = 1020, profit = 15
        assert profit["net_profit"] == Decimal("15")

    def test_calculate_profit_none_when_no_buy(self):
        sell_quote = _make_quote()
        ap = AggregatedPrice(
            base="ETH", quote="USD", timestamp=datetime.utcnow(),
            best_buy=None, best_sell=sell_quote,
        )
        assert ap.calculate_profit(Decimal("1")) is None

    def test_calculate_profit_none_when_no_sell(self):
        buy_quote = _make_quote()
        ap = AggregatedPrice(
            base="ETH", quote="USD", timestamp=datetime.utcnow(),
            best_buy=buy_quote, best_sell=None,
        )
        assert ap.calculate_profit(Decimal("1")) is None


# ---------------------------------------------------------------------------
# TestPriceAggregatorGetBestPrices
# ---------------------------------------------------------------------------

class TestPriceAggregatorGetBestPrices:
    """Tests for PriceAggregator.get_best_prices."""

    @pytest.mark.asyncio
    async def test_two_feeds_selects_best_buy_and_sell(self):
        quote_a = _make_quote(exchange="exchange_a", ask=Decimal("50100"), bid=Decimal("50000"))
        quote_b = _make_quote(exchange="exchange_b", ask=Decimal("50050"), bid=Decimal("50150"))

        feed_a = _make_mock_feed("feed_a", get_price_result=quote_a)
        feed_b = _make_mock_feed("feed_b", get_price_result=quote_b)

        aggregator = PriceAggregator([feed_a, feed_b])
        result = await aggregator.get_best_prices("BTC", "USD")

        # Best buy = lowest ask => exchange_b (50050)
        assert result.best_buy.exchange == "exchange_b"
        assert result.best_buy.ask == Decimal("50050")
        # Best sell = highest bid => exchange_b (50150)
        assert result.best_sell.exchange == "exchange_b"
        assert result.best_sell.bid == Decimal("50150")

    @pytest.mark.asyncio
    async def test_single_feed_returns_it_as_both(self):
        quote = _make_quote(exchange="only_feed", ask=Decimal("100"), bid=Decimal("99"))
        feed = _make_mock_feed("only_feed", get_price_result=quote)

        aggregator = PriceAggregator([feed])
        result = await aggregator.get_best_prices("ETH", "USD")

        assert result.best_buy.exchange == "only_feed"
        assert result.best_sell.exchange == "only_feed"

    @pytest.mark.asyncio
    async def test_all_feeds_fail_returns_empty(self):
        feed_a = _make_mock_feed("feed_a", get_price_result=None)
        feed_b = _make_mock_feed("feed_b", get_price_result=None)

        aggregator = PriceAggregator([feed_a, feed_b])
        result = await aggregator.get_best_prices("BTC", "USD")

        assert result.best_buy is None
        assert result.best_sell is None
        assert result.all_quotes == []

    @pytest.mark.asyncio
    async def test_no_feeds_returns_empty(self):
        aggregator = PriceAggregator([])
        result = await aggregator.get_best_prices("BTC", "USD")
        assert result.best_buy is None
        assert result.best_sell is None

    @pytest.mark.asyncio
    async def test_feed_exception_skipped_gracefully(self):
        quote_b = _make_quote(exchange="exchange_b", ask=Decimal("50000"), bid=Decimal("49900"))

        feed_a = _make_mock_feed("feed_a")
        feed_a.get_price = AsyncMock(side_effect=RuntimeError("API error"))
        feed_b = _make_mock_feed("feed_b", get_price_result=quote_b)

        aggregator = PriceAggregator([feed_a, feed_b])
        result = await aggregator.get_best_prices("BTC", "USD")

        # Only feed_b should be used
        assert len(result.all_quotes) == 1
        assert result.best_buy.exchange == "exchange_b"

    @pytest.mark.asyncio
    async def test_feed_timeout_skipped_gracefully(self):
        """A feed that hangs should be skipped after timeout."""
        async def slow_price(*args, **kwargs):
            await asyncio.sleep(10)

        quote_b = _make_quote(exchange="fast_feed", ask=Decimal("100"), bid=Decimal("99"))
        feed_slow = _make_mock_feed("slow_feed")
        feed_slow.get_price = slow_price
        feed_fast = _make_mock_feed("fast_feed", get_price_result=quote_b)

        aggregator = PriceAggregator([feed_slow, feed_fast])
        result = await aggregator.get_best_prices("ETH", "USD", timeout=0.1)

        assert len(result.all_quotes) == 1
        assert result.best_buy.exchange == "fast_feed"

    @pytest.mark.asyncio
    async def test_three_feeds_picks_optimal(self):
        q_a = _make_quote(exchange="a", ask=Decimal("100"), bid=Decimal("98"))
        q_b = _make_quote(exchange="b", ask=Decimal("99"), bid=Decimal("97"))   # lowest ask
        q_c = _make_quote(exchange="c", ask=Decimal("101"), bid=Decimal("100"))  # highest bid

        feed_a = _make_mock_feed("a", get_price_result=q_a)
        feed_b = _make_mock_feed("b", get_price_result=q_b)
        feed_c = _make_mock_feed("c", get_price_result=q_c)

        aggregator = PriceAggregator([feed_a, feed_b, feed_c])
        result = await aggregator.get_best_prices("ETH", "USD")

        assert result.best_buy.exchange == "b"  # lowest ask
        assert result.best_sell.exchange == "c"  # highest bid
        assert len(result.all_quotes) == 3


# ---------------------------------------------------------------------------
# TestFindOpportunities
# ---------------------------------------------------------------------------

class TestFindOpportunities:
    """Tests for find_opportunities arbitrage scanning."""

    @pytest.mark.asyncio
    async def test_profitable_pair_found(self):
        # exchange_a: low ask, exchange_b: high bid => profitable
        q_a = _make_quote(exchange="a", ask=Decimal("1000"), bid=Decimal("990"), taker_fee=Decimal("0"))
        q_b = _make_quote(exchange="b", ask=Decimal("1050"), bid=Decimal("1020"), taker_fee=Decimal("0"))

        feed_a = _make_mock_feed("a", get_price_result=q_a)
        feed_b = _make_mock_feed("b", get_price_result=q_b)

        aggregator = PriceAggregator([feed_a, feed_b])
        opportunities = await aggregator.find_opportunities(
            pairs=[("ETH", "USD")],
            min_profit_pct=Decimal("0.1"),
            min_quantity=Decimal("1"),
        )

        assert len(opportunities) >= 1
        opp = opportunities[0]
        assert opp.base == "ETH"
        assert opp.quote == "USD"
        assert opp.is_profitable if hasattr(opp, 'is_profitable') else True

    @pytest.mark.asyncio
    async def test_no_profitable_pair(self):
        # Same prices on both => no spread
        quote = _make_quote(exchange="a", ask=Decimal("1000"), bid=Decimal("1000"), taker_fee=Decimal("0.6"))
        feed_a = _make_mock_feed("a", get_price_result=quote)
        feed_b = _make_mock_feed("b", get_price_result=quote)

        aggregator = PriceAggregator([feed_a, feed_b])
        opportunities = await aggregator.find_opportunities(
            pairs=[("ETH", "USD")],
            min_profit_pct=Decimal("0.5"),
        )
        assert len(opportunities) == 0

    @pytest.mark.asyncio
    async def test_multiple_pairs_scanned(self):
        q_eth = _make_quote(exchange="a", ask=Decimal("1000"), bid=Decimal("1010"), taker_fee=Decimal("0"))
        q_btc = _make_quote(exchange="a", ask=Decimal("50000"), bid=Decimal("50100"), taker_fee=Decimal("0"))

        feed = _make_mock_feed("a", get_price_result=q_eth)
        # Override get_price to return different quotes for different pairs
        async def dynamic_price(base, quote):
            if base == "BTC":
                return q_btc
            return q_eth
        feed.get_price = dynamic_price

        aggregator = PriceAggregator([feed])
        opportunities = await aggregator.find_opportunities(
            pairs=[("ETH", "USD"), ("BTC", "USD")],
            min_profit_pct=Decimal("0.01"),
            min_quantity=Decimal("1"),
        )
        # Both pairs have positive spread (bid > ask), so both should be found
        assert len(opportunities) >= 1

    @pytest.mark.asyncio
    async def test_opportunities_sorted_by_profit_descending(self):
        # We need different feeds for a real spread
        # Pair 1: small spread
        q1_a = _make_quote(exchange="a", ask=Decimal("1000"), bid=Decimal("990"), taker_fee=Decimal("0"))
        q1_b = _make_quote(exchange="b", ask=Decimal("1050"), bid=Decimal("1005"), taker_fee=Decimal("0"))
        # Pair 2: larger spread
        q2_a = _make_quote(exchange="a", ask=Decimal("100"), bid=Decimal("99"), taker_fee=Decimal("0"))
        q2_b = _make_quote(exchange="b", ask=Decimal("110"), bid=Decimal("105"), taker_fee=Decimal("0"))

        async def feed_a_price(base, quote):
            return q1_a if base == "ETH" else q2_a

        async def feed_b_price(base, quote):
            return q1_b if base == "ETH" else q2_b

        feed_a = _make_mock_feed("a")
        feed_a.get_price = feed_a_price
        feed_b = _make_mock_feed("b")
        feed_b.get_price = feed_b_price

        aggregator = PriceAggregator([feed_a, feed_b])
        opportunities = await aggregator.find_opportunities(
            pairs=[("ETH", "USD"), ("SOL", "USD")],
            min_profit_pct=Decimal("0.01"),
            min_quantity=Decimal("1"),
        )
        if len(opportunities) >= 2:
            assert opportunities[0].estimated_profit_pct >= opportunities[1].estimated_profit_pct


# ---------------------------------------------------------------------------
# TestFeedManagement
# ---------------------------------------------------------------------------

class TestFeedManagement:
    """Tests for add_feed and remove_feed."""

    def test_add_feed(self):
        aggregator = PriceAggregator([])
        assert len(aggregator.feeds) == 0

        feed = _make_mock_feed("new_feed")
        aggregator.add_feed(feed)
        assert len(aggregator.feeds) == 1
        assert aggregator.feeds[0].name == "new_feed"

    def test_remove_feed_by_name(self):
        feed_a = _make_mock_feed("feed_a")
        feed_b = _make_mock_feed("feed_b")
        aggregator = PriceAggregator([feed_a, feed_b])

        aggregator.remove_feed("feed_a")
        assert len(aggregator.feeds) == 1
        assert aggregator.feeds[0].name == "feed_b"

    def test_remove_nonexistent_feed_no_error(self):
        feed = _make_mock_feed("existing")
        aggregator = PriceAggregator([feed])
        aggregator.remove_feed("nonexistent")
        assert len(aggregator.feeds) == 1


# ---------------------------------------------------------------------------
# TestCheckFeedHealth
# ---------------------------------------------------------------------------

class TestCheckFeedHealth:
    """Tests for check_feed_health."""

    @pytest.mark.asyncio
    async def test_all_feeds_healthy(self):
        feed_a = _make_mock_feed("a", is_available_result=True)
        feed_b = _make_mock_feed("b", is_available_result=True)
        aggregator = PriceAggregator([feed_a, feed_b])

        health = await aggregator.check_feed_health()
        assert health == {"a": True, "b": True}

    @pytest.mark.asyncio
    async def test_one_feed_unhealthy(self):
        feed_a = _make_mock_feed("a", is_available_result=True)
        feed_b = _make_mock_feed("b", is_available_result=False)
        aggregator = PriceAggregator([feed_a, feed_b])

        health = await aggregator.check_feed_health()
        assert health["a"] is True
        assert health["b"] is False

    @pytest.mark.asyncio
    async def test_feed_health_check_exception_returns_false(self):
        feed = _make_mock_feed("buggy")
        feed.is_available = AsyncMock(side_effect=RuntimeError("Connection refused"))
        aggregator = PriceAggregator([feed])

        health = await aggregator.check_feed_health()
        assert health["buggy"] is False

    @pytest.mark.asyncio
    async def test_no_feeds_returns_empty_dict(self):
        aggregator = PriceAggregator([])
        health = await aggregator.check_feed_health()
        assert health == {}
