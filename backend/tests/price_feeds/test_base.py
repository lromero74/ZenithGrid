"""
Tests for backend/app/price_feeds/base.py

Covers:
- OrderBookLevel: value property
- OrderBook: best_bid, best_ask, spread, spread_pct, product_id, get_execution_price
- PriceQuote: mid, spread, spread_pct, net_buy_price, net_sell_price, product_id
- PriceFeed: abstract interface, get_fee_estimate default
"""

import pytest
from datetime import datetime
from decimal import Decimal

from app.price_feeds.base import (
    OrderBookLevel,
    OrderBook,
    PriceQuote,
    PriceFeed,
)


# ===========================================================================
# OrderBookLevel tests
# ===========================================================================


class TestOrderBookLevel:
    """Tests for OrderBookLevel dataclass."""

    def test_value_calculation(self):
        """Happy path: value = price * quantity."""
        level = OrderBookLevel(price=Decimal("50000"), quantity=Decimal("0.1"))
        assert level.value == Decimal("5000")

    def test_value_with_zero_quantity(self):
        """Edge case: zero quantity gives zero value."""
        level = OrderBookLevel(price=Decimal("50000"), quantity=Decimal("0"))
        assert level.value == Decimal("0")

    def test_value_with_fractional_amounts(self):
        """Edge case: fractional prices and quantities."""
        level = OrderBookLevel(price=Decimal("0.001234"), quantity=Decimal("1000000"))
        assert level.value == Decimal("1234")


# ===========================================================================
# OrderBook tests
# ===========================================================================


def _make_orderbook(bids=None, asks=None, base="ETH", quote="USDT"):
    """Helper to build an OrderBook with sensible defaults."""
    return OrderBook(
        exchange="test",
        exchange_type="cex",
        base=base,
        quote=quote,
        timestamp=datetime(2025, 1, 1),
        bids=bids or [],
        asks=asks or [],
    )


class TestOrderBookProductId:
    """Tests for OrderBook.product_id property."""

    def test_product_id_format(self):
        """Happy path: product_id is BASE-QUOTE."""
        ob = _make_orderbook(base="BTC", quote="USD")
        assert ob.product_id == "BTC-USD"


class TestOrderBookBestBidAsk:
    """Tests for best_bid and best_ask properties."""

    def test_best_bid_returns_highest(self):
        """Happy path: first bid (highest) is returned."""
        bids = [
            OrderBookLevel(Decimal("50000"), Decimal("1")),
            OrderBookLevel(Decimal("49999"), Decimal("2")),
        ]
        ob = _make_orderbook(bids=bids)
        assert ob.best_bid == Decimal("50000")

    def test_best_ask_returns_lowest(self):
        """Happy path: first ask (lowest) is returned."""
        asks = [
            OrderBookLevel(Decimal("50001"), Decimal("1")),
            OrderBookLevel(Decimal("50002"), Decimal("2")),
        ]
        ob = _make_orderbook(asks=asks)
        assert ob.best_ask == Decimal("50001")

    def test_best_bid_empty_returns_none(self):
        """Edge case: no bids returns None."""
        ob = _make_orderbook(bids=[])
        assert ob.best_bid is None

    def test_best_ask_empty_returns_none(self):
        """Edge case: no asks returns None."""
        ob = _make_orderbook(asks=[])
        assert ob.best_ask is None


class TestOrderBookSpread:
    """Tests for spread and spread_pct properties."""

    def test_spread_calculation(self):
        """Happy path: spread = best_ask - best_bid."""
        bids = [OrderBookLevel(Decimal("49999"), Decimal("1"))]
        asks = [OrderBookLevel(Decimal("50001"), Decimal("1"))]
        ob = _make_orderbook(bids=bids, asks=asks)
        assert ob.spread == Decimal("2")

    def test_spread_none_when_no_bids(self):
        """Edge case: no bids means no spread."""
        asks = [OrderBookLevel(Decimal("50001"), Decimal("1"))]
        ob = _make_orderbook(asks=asks)
        assert ob.spread is None

    def test_spread_none_when_no_asks(self):
        """Edge case: no asks means no spread."""
        bids = [OrderBookLevel(Decimal("49999"), Decimal("1"))]
        ob = _make_orderbook(bids=bids)
        assert ob.spread is None

    def test_spread_pct_calculation(self):
        """Happy path: spread_pct = (spread / mid) * 100."""
        bids = [OrderBookLevel(Decimal("100"), Decimal("1"))]
        asks = [OrderBookLevel(Decimal("102"), Decimal("1"))]
        ob = _make_orderbook(bids=bids, asks=asks)
        # mid = 101, spread = 2, pct = (2/101)*100 ~ 1.98
        expected = (Decimal("2") / Decimal("101")) * 100
        assert ob.spread_pct == expected

    def test_spread_pct_none_when_no_bids(self):
        """Edge case: no bids means no spread_pct."""
        asks = [OrderBookLevel(Decimal("100"), Decimal("1"))]
        ob = _make_orderbook(asks=asks)
        assert ob.spread_pct is None


class TestOrderBookExecutionPrice:
    """Tests for get_execution_price()."""

    def test_buy_execution_walks_asks(self):
        """Happy path: buying walks up the ask levels."""
        asks = [
            OrderBookLevel(Decimal("100"), Decimal("5")),   # 5 @ 100
            OrderBookLevel(Decimal("101"), Decimal("5")),   # 5 @ 101
        ]
        ob = _make_orderbook(asks=asks)
        # Buy 8 units: 5@100 + 3@101 = 500+303 = 803, avg = 803/8
        result = ob.get_execution_price("buy", Decimal("8"))
        expected = Decimal("803") / Decimal("8")
        assert result == expected

    def test_sell_execution_walks_bids(self):
        """Happy path: selling walks down the bid levels."""
        bids = [
            OrderBookLevel(Decimal("100"), Decimal("5")),   # 5 @ 100
            OrderBookLevel(Decimal("99"), Decimal("5")),    # 5 @ 99
        ]
        ob = _make_orderbook(bids=bids)
        # Sell 7 units: 5@100 + 2@99 = 500+198 = 698, avg = 698/7
        result = ob.get_execution_price("sell", Decimal("7"))
        expected = Decimal("698") / Decimal("7")
        assert result == expected

    def test_exact_fill_at_single_level(self):
        """Happy path: exact fill at one level."""
        asks = [OrderBookLevel(Decimal("50000"), Decimal("1"))]
        ob = _make_orderbook(asks=asks)
        result = ob.get_execution_price("buy", Decimal("1"))
        assert result == Decimal("50000")

    def test_insufficient_liquidity_returns_none(self):
        """Failure: not enough liquidity returns None."""
        asks = [OrderBookLevel(Decimal("100"), Decimal("5"))]
        ob = _make_orderbook(asks=asks)
        result = ob.get_execution_price("buy", Decimal("10"))
        assert result is None

    def test_empty_book_returns_none(self):
        """Failure: empty book returns None."""
        ob = _make_orderbook()
        assert ob.get_execution_price("buy", Decimal("1")) is None

    def test_zero_quantity_returns_none(self):
        """Edge case: zero quantity returns None instead of ZeroDivisionError."""
        asks = [OrderBookLevel(Decimal("100"), Decimal("5"))]
        ob = _make_orderbook(asks=asks)
        assert ob.get_execution_price("buy", Decimal("0")) is None


# ===========================================================================
# PriceQuote tests
# ===========================================================================


def _make_quote(bid=Decimal("100"), ask=Decimal("102"), **kwargs):
    """Helper to build a PriceQuote with sensible defaults."""
    defaults = dict(
        exchange="test",
        exchange_type="cex",
        base="ETH",
        quote="USDT",
        bid=bid,
        ask=ask,
        timestamp=datetime(2025, 1, 1),
    )
    defaults.update(kwargs)
    return PriceQuote(**defaults)


class TestPriceQuoteProperties:
    """Tests for PriceQuote computed properties."""

    def test_product_id(self):
        """Happy path: product_id is BASE-QUOTE."""
        q = _make_quote(base="BTC", quote="USD")
        assert q.product_id == "BTC-USD"

    def test_mid_price(self):
        """Happy path: mid = (bid + ask) / 2."""
        q = _make_quote(bid=Decimal("100"), ask=Decimal("102"))
        assert q.mid == Decimal("101")

    def test_spread(self):
        """Happy path: spread = ask - bid."""
        q = _make_quote(bid=Decimal("100"), ask=Decimal("102"))
        assert q.spread == Decimal("2")

    def test_spread_pct(self):
        """Happy path: spread_pct = (spread / mid) * 100."""
        q = _make_quote(bid=Decimal("100"), ask=Decimal("102"))
        expected = (Decimal("2") / Decimal("101")) * 100
        assert q.spread_pct == expected

    def test_spread_pct_zero_mid(self):
        """Edge case: zero mid returns Decimal(0)."""
        q = _make_quote(bid=Decimal("0"), ask=Decimal("0"))
        assert q.spread_pct == Decimal("0")


class TestPriceQuoteNetPrices:
    """Tests for net_buy_price and net_sell_price."""

    def test_net_buy_price_default_fee(self):
        """Happy path: net buy = ask * (1 + 0.3/100)."""
        q = _make_quote(ask=Decimal("1000"))
        expected = Decimal("1000") * (1 + Decimal("0.3") / 100)
        assert q.net_buy_price() == expected

    def test_net_sell_price_default_fee(self):
        """Happy path: net sell = bid * (1 - 0.3/100)."""
        q = _make_quote(bid=Decimal("1000"))
        expected = Decimal("1000") * (1 - Decimal("0.3") / 100)
        assert q.net_sell_price() == expected

    def test_net_buy_price_custom_fee(self):
        """Happy path: custom taker fee applied."""
        q = _make_quote(ask=Decimal("1000"), taker_fee_pct=Decimal("0.1"))
        expected = Decimal("1000") * (1 + Decimal("0.1") / 100)
        assert q.net_buy_price() == expected

    def test_net_buy_higher_than_ask(self):
        """Sanity: net buy is always higher than raw ask."""
        q = _make_quote(ask=Decimal("5000"))
        assert q.net_buy_price() > q.ask

    def test_net_sell_lower_than_bid(self):
        """Sanity: net sell is always lower than raw bid."""
        q = _make_quote(bid=Decimal("5000"))
        assert q.net_sell_price() < q.bid


class TestPriceQuoteDefaults:
    """Tests for default field values."""

    def test_default_taker_fee(self):
        """Happy path: default taker fee is 0.3%."""
        q = _make_quote()
        assert q.taker_fee_pct == Decimal("0.3")

    def test_default_maker_fee(self):
        """Happy path: default maker fee is 0.1%."""
        q = _make_quote()
        assert q.maker_fee_pct == Decimal("0.1")

    def test_gas_estimate_default_none(self):
        """Happy path: gas_estimate_usd defaults to None."""
        q = _make_quote()
        assert q.gas_estimate_usd is None

    def test_chain_id_default_none(self):
        """Happy path: chain_id defaults to None."""
        q = _make_quote()
        assert q.chain_id is None


# ===========================================================================
# PriceFeed abstract class tests
# ===========================================================================


class ConcretePriceFeed(PriceFeed):
    """Concrete subclass for testing abstract PriceFeed."""

    async def get_price(self, base, quote):
        return None

    async def get_orderbook(self, base, quote, depth=10):
        return None

    async def get_supported_pairs(self):
        return []

    async def is_available(self):
        return True


class TestPriceFeedInterface:
    """Tests for PriceFeed base class."""

    def test_init_stores_name_and_type(self):
        """Happy path: name and exchange_type stored."""
        feed = ConcretePriceFeed("test_exchange", "cex")
        assert feed.name == "test_exchange"
        assert feed.exchange_type == "cex"

    def test_get_fee_estimate_taker(self):
        """Happy path: default taker fee is 0.3%."""
        feed = ConcretePriceFeed("test", "cex")
        assert feed.get_fee_estimate("buy", is_maker=False) == Decimal("0.3")

    def test_get_fee_estimate_maker(self):
        """Happy path: default maker fee is 0.1%."""
        feed = ConcretePriceFeed("test", "cex")
        assert feed.get_fee_estimate("sell", is_maker=True) == Decimal("0.1")

    def test_get_fee_estimate_sell_taker(self):
        """Happy path: taker fee same for buy and sell."""
        feed = ConcretePriceFeed("test", "cex")
        assert feed.get_fee_estimate("sell", is_maker=False) == Decimal("0.3")

    def test_cannot_instantiate_abstract_directly(self):
        """Failure: PriceFeed cannot be instantiated directly."""
        with pytest.raises(TypeError):
            PriceFeed("x", "cex")
