"""
Tests for backend/app/trading_engine/book_depth_guard.py

Covers:
- calculate_vwap_from_bids: VWAP for selling base currency into bids
- calculate_vwap_from_asks: VWAP for buying with quote currency from asks
- check_sell_slippage: guard for market sell orders (minimum/fixed/trailing modes)
- check_buy_slippage: guard for market buy orders
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.trading_engine.book_depth_guard import (
    calculate_vwap_from_bids,
    calculate_vwap_from_asks,
    check_sell_slippage,
    check_buy_slippage,
)


# ===========================================================================
# calculate_vwap_from_bids
# ===========================================================================


class TestCalculateVwapFromBids:
    """Tests for walking the bid side of the book."""

    def test_single_level_exact_fill(self):
        """Happy path: one level fills the entire sell amount."""
        bids = [{"price": "100.00", "size": "5.0"}]
        vwap, filled, fully = calculate_vwap_from_bids(bids, 5.0)
        assert vwap == pytest.approx(100.0)
        assert filled == pytest.approx(5.0)
        assert fully is True

    def test_single_level_partial_fill(self):
        """Sell amount exceeds the single bid level."""
        bids = [{"price": "100.00", "size": "2.0"}]
        vwap, filled, fully = calculate_vwap_from_bids(bids, 5.0)
        assert vwap == pytest.approx(100.0)
        assert filled == pytest.approx(2.0)
        assert fully is False

    def test_multiple_levels_full_fill(self):
        """Sell amount spans two levels, both used."""
        bids = [
            {"price": "100.00", "size": "3.0"},
            {"price": "99.00", "size": "5.0"},
        ]
        vwap, filled, fully = calculate_vwap_from_bids(bids, 5.0)
        # 3 @ 100 + 2 @ 99 = 300 + 198 = 498 / 5 = 99.6
        assert vwap == pytest.approx(99.6)
        assert filled == pytest.approx(5.0)
        assert fully is True

    def test_multiple_levels_partial_fill(self):
        """Sell amount exceeds total book depth."""
        bids = [
            {"price": "100.00", "size": "2.0"},
            {"price": "99.00", "size": "1.0"},
        ]
        vwap, filled, fully = calculate_vwap_from_bids(bids, 10.0)
        # 2 @ 100 + 1 @ 99 = 200 + 99 = 299 / 3 = 99.667
        assert vwap == pytest.approx(299.0 / 3.0)
        assert filled == pytest.approx(3.0)
        assert fully is False

    def test_empty_bids(self):
        """Edge case: empty order book."""
        vwap, filled, fully = calculate_vwap_from_bids([], 1.0)
        assert vwap == 0.0
        assert filled == 0.0
        assert fully is False

    def test_zero_sell_amount(self):
        """Edge case: zero amount to sell."""
        bids = [{"price": "100.00", "size": "5.0"}]
        vwap, filled, fully = calculate_vwap_from_bids(bids, 0.0)
        assert vwap == 0.0
        assert filled == 0.0
        assert fully is False

    def test_negative_sell_amount(self):
        """Edge case: negative amount to sell."""
        bids = [{"price": "100.00", "size": "5.0"}]
        vwap, filled, fully = calculate_vwap_from_bids(bids, -1.0)
        assert vwap == 0.0
        assert fully is False

    def test_skips_zero_price_levels(self):
        """Levels with zero price are skipped."""
        bids = [
            {"price": "0", "size": "100"},
            {"price": "50.00", "size": "2.0"},
        ]
        vwap, filled, fully = calculate_vwap_from_bids(bids, 2.0)
        assert vwap == pytest.approx(50.0)
        assert filled == pytest.approx(2.0)
        assert fully is True


# ===========================================================================
# calculate_vwap_from_asks
# ===========================================================================


class TestCalculateVwapFromAsks:
    """Tests for walking the ask side of the book."""

    def test_single_level_exact_fill(self):
        """Happy path: one ask level covers the entire buy amount."""
        asks = [{"price": "100.00", "size": "5.0"}]
        # 5 base @ 100 = 500 quote available, buying with 500
        vwap, filled_q, fully = calculate_vwap_from_asks(asks, 500.0)
        assert vwap == pytest.approx(100.0)
        assert filled_q == pytest.approx(500.0)
        assert fully is True

    def test_single_level_partial_fill(self):
        """Buy amount uses only part of the level."""
        asks = [{"price": "100.00", "size": "10.0"}]
        # Level has 1000 quote capacity, buying with 200
        vwap, filled_q, fully = calculate_vwap_from_asks(asks, 200.0)
        assert vwap == pytest.approx(100.0)
        assert filled_q == pytest.approx(200.0)
        assert fully is True

    def test_multiple_levels_full_fill(self):
        """Buy spans two ask levels."""
        asks = [
            {"price": "100.00", "size": "2.0"},  # 200 quote
            {"price": "101.00", "size": "5.0"},  # 505 quote
        ]
        # Buy with 300 quote: 200 @ 100 + 100 @ 101
        # base: 2.0 + (100/101) = 2.0 + 0.9901 = 2.9901
        # vwap: 300 / 2.9901 = ~100.33
        vwap, filled_q, fully = calculate_vwap_from_asks(asks, 300.0)
        expected_base = 2.0 + (100.0 / 101.0)
        expected_vwap = 300.0 / expected_base
        assert vwap == pytest.approx(expected_vwap, rel=1e-6)
        assert filled_q == pytest.approx(300.0)
        assert fully is True

    def test_multiple_levels_partial_fill(self):
        """Buy amount exceeds total ask liquidity."""
        asks = [
            {"price": "100.00", "size": "1.0"},  # 100 quote
            {"price": "102.00", "size": "1.0"},  # 102 quote
        ]
        # Total available: 202 quote, trying to buy with 500
        vwap, filled_q, fully = calculate_vwap_from_asks(asks, 500.0)
        assert filled_q == pytest.approx(202.0)
        assert fully is False

    def test_empty_asks(self):
        """Edge case: empty order book."""
        vwap, filled_q, fully = calculate_vwap_from_asks([], 100.0)
        assert vwap == 0.0
        assert filled_q == 0.0
        assert fully is False

    def test_zero_quote_amount(self):
        """Edge case: zero amount to buy."""
        asks = [{"price": "100.00", "size": "5.0"}]
        vwap, filled_q, fully = calculate_vwap_from_asks(asks, 0.0)
        assert vwap == 0.0
        assert fully is False

    def test_negative_quote_amount(self):
        """Edge case: negative amount."""
        asks = [{"price": "100.00", "size": "5.0"}]
        vwap, filled_q, fully = calculate_vwap_from_asks(asks, -10.0)
        assert vwap == 0.0
        assert fully is False

    def test_skips_zero_size_levels(self):
        """Levels with zero size are skipped."""
        asks = [
            {"price": "100.00", "size": "0"},
            {"price": "101.00", "size": "5.0"},
        ]
        vwap, filled_q, fully = calculate_vwap_from_asks(asks, 101.0)
        assert vwap == pytest.approx(101.0)
        assert fully is True


# ===========================================================================
# check_sell_slippage
# ===========================================================================


class TestCheckSellSlippage:
    """Tests for the async sell slippage guard."""

    @pytest.mark.asyncio
    async def test_passes_when_slippage_ok_fixed_mode(self):
        """Happy path: small sell with deep book — slippage within limit."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [
                    {"price": "50000.00", "size": "2.0"},
                    {"price": "49990.00", "size": "5.0"},
                ],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 0.1
        position.average_buy_price = 48000.0

        config = {
            "take_profit_mode": "fixed",
            "take_profit_percentage": 3.0,
            "max_sell_slippage_pct": 0.5,
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_blocks_on_excessive_slippage_fixed_mode(self):
        """Fixed mode: VWAP slips too far below best bid."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [
                    {"price": "50000.00", "size": "0.01"},
                    {"price": "49000.00", "size": "10.0"},  # big gap
                ],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 1.0
        position.average_buy_price = 45000.0

        config = {
            "take_profit_mode": "fixed",
            "take_profit_percentage": 3.0,
            "max_sell_slippage_pct": 0.5,
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is False
        assert "slippage" in reason.lower()

    @pytest.mark.asyncio
    async def test_blocks_on_insufficient_depth(self):
        """Not enough bids to fill the sell amount."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [{"price": "50000.00", "size": "0.001"}],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 1.0
        position.average_buy_price = 45000.0

        config = {
            "take_profit_mode": "fixed",
            "max_sell_slippage_pct": 0.5,
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is False
        assert "depth" in reason.lower()

    @pytest.mark.asyncio
    async def test_minimum_mode_blocks_when_vwap_profit_below_tp(self):
        """Minimum mode: TP% serves as the floor — VWAP profit below TP%."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [{"price": "50000.00", "size": "10.0"}],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 0.5
        position.average_buy_price = 49000.0  # profit = 2.04%

        config = {
            "take_profit_mode": "minimum",
            "take_profit_percentage": 3.0,  # need 3%, only have ~2%
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is False
        assert "VWAP profit" in reason

    @pytest.mark.asyncio
    async def test_minimum_mode_passes_when_vwap_profit_above_tp(self):
        """Minimum mode: VWAP profit exceeds TP% floor — allow sell."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [{"price": "52000.00", "size": "10.0"}],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 0.5
        position.average_buy_price = 49000.0  # profit = 6.12%

        config = {
            "take_profit_mode": "minimum",
            "take_profit_percentage": 3.0,
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_trailing_mode_uses_vwap_profit_floor(self):
        """Trailing mode: uses VWAP profit vs TP% floor, not raw slippage."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [{"price": "50000.00", "size": "10.0"}],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 0.1
        position.average_buy_price = 45000.0  # VWAP profit = 11.1%

        config = {
            "take_profit_mode": "trailing",
            "take_profit_percentage": 3.0,
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_trailing_mode_blocks_when_vwap_profit_below_tp(self):
        """Trailing mode: VWAP profit below TP% floor — blocked."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [{"price": "50000.00", "size": "10.0"}],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 0.5
        position.average_buy_price = 49000.0  # VWAP profit = 2.04% < 3%

        config = {
            "take_profit_mode": "trailing",
            "take_profit_percentage": 3.0,
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is False
        assert "VWAP profit" in reason

    @pytest.mark.asyncio
    async def test_trailing_mode_allows_high_slippage_when_profit_sufficient(self):
        """Trailing mode: large book slippage OK if VWAP profit above floor."""
        exchange = AsyncMock()
        # Best bid 50000, but thin top — VWAP will be ~49000 (2% slippage)
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [
                    {"price": "50000.00", "size": "0.01"},   # thin top
                    {"price": "49000.00", "size": "10.0"},   # bulk here
                ],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 1.0
        position.average_buy_price = 40000.0  # VWAP ~49000, profit ~22.5%

        config = {
            "take_profit_mode": "trailing",
            "take_profit_percentage": 3.0,
            "max_sell_slippage_pct": 0.5,  # would block in fixed mode
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        # 2% book slippage would block fixed mode, but trailing checks
        # VWAP profit (22.5%) vs TP floor (3%) — passes easily
        assert proceed is True

    @pytest.mark.asyncio
    async def test_trailing_mode_default_tp_floor(self):
        """Trailing mode: falls back to 3.0% default when TP% not set."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [{"price": "50000.00", "size": "10.0"}],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 0.5
        position.average_buy_price = 49000.0  # profit 2.04% < default 3.0%

        config = {
            "take_profit_mode": "trailing",
            # no take_profit_percentage — defaults to 3.0
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is False
        assert "VWAP profit" in reason

    @pytest.mark.asyncio
    async def test_minimum_mode_none_tp_percentage_uses_default(self):
        """Minimum mode: take_profit_percentage=None should fall back to 3.0%, not crash."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [{"price": "50000.00", "size": "10.0"}],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 0.5
        position.average_buy_price = 49000.0  # profit 2.04% < default 3.0%

        config = {
            "take_profit_mode": "minimum",
            "take_profit_percentage": None,  # explicitly None — was crashing
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is False
        assert "VWAP profit" in reason

    @pytest.mark.asyncio
    async def test_fixed_mode_none_max_slippage_uses_default(self):
        """Fixed mode: max_sell_slippage_pct=None should fall back to 0.5%, not crash."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [
                    {"price": "50000.00", "size": "0.01"},
                    {"price": "49000.00", "size": "10.0"},
                ],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 1.0
        position.average_buy_price = 45000.0

        config = {
            "take_profit_mode": "fixed",
            "take_profit_percentage": 3.0,
            "max_sell_slippage_pct": None,  # explicitly None
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is False
        assert "slippage" in reason.lower()

    @pytest.mark.asyncio
    async def test_skips_when_no_get_product_book(self):
        """Graceful degradation: exchange without order book support."""
        exchange = MagicMock(spec=[])  # no attributes
        position = MagicMock()
        position.total_base_acquired = 1.0

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, {})
        assert proceed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_skips_on_api_error(self):
        """Graceful degradation: API call raises exception."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(side_effect=Exception("API timeout"))

        position = MagicMock()
        position.total_base_acquired = 1.0

        config = {"take_profit_mode": "fixed", "max_sell_slippage_pct": 0.5}
        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_skips_on_empty_bids(self):
        """Graceful degradation: book response has no bids."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {"bids": [], "asks": []}
        })
        position = MagicMock()
        position.total_base_acquired = 1.0

        config = {"take_profit_mode": "fixed", "max_sell_slippage_pct": 0.5}
        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is True

    @pytest.mark.asyncio
    async def test_legacy_trailing_mode_inference(self):
        """Legacy config: trailing_take_profit=True inferred as trailing, uses profit floor."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [{"price": "50000.00", "size": "10.0"}],
                "asks": [],
            }
        })
        position = MagicMock()
        position.total_base_acquired = 0.1
        position.average_buy_price = 45000.0

        config = {
            "trailing_take_profit": True,  # legacy field
            "max_sell_slippage_pct": 0.5,
        }

        proceed, reason = await check_sell_slippage(exchange, "BTC-USD", position, config)
        assert proceed is True


# ===========================================================================
# check_buy_slippage
# ===========================================================================


class TestCheckBuySlippage:
    """Tests for the async buy slippage guard."""

    @pytest.mark.asyncio
    async def test_passes_when_slippage_ok(self):
        """Happy path: buy amount easily filled at tight spread."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [],
                "asks": [
                    {"price": "50000.00", "size": "2.0"},
                    {"price": "50010.00", "size": "5.0"},
                ],
            }
        })

        config = {"max_buy_slippage_pct": 0.5}
        proceed, reason = await check_buy_slippage(exchange, "BTC-USD", 1000.0, config)
        assert proceed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_blocks_on_excessive_slippage(self):
        """VWAP far above best ask — blocked."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [],
                "asks": [
                    {"price": "50000.00", "size": "0.001"},  # 50 quote capacity
                    {"price": "55000.00", "size": "10.0"},  # big gap
                ],
            }
        })

        config = {"max_buy_slippage_pct": 0.5}
        proceed, reason = await check_buy_slippage(exchange, "BTC-USD", 10000.0, config)
        assert proceed is False
        assert "slippage" in reason.lower()

    @pytest.mark.asyncio
    async def test_blocks_on_insufficient_depth(self):
        """Not enough asks to fill buy amount."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [],
                "asks": [{"price": "50000.00", "size": "0.0001"}],  # 5 quote
            }
        })

        config = {"max_buy_slippage_pct": 0.5}
        proceed, reason = await check_buy_slippage(exchange, "BTC-USD", 10000.0, config)
        assert proceed is False
        assert "depth" in reason.lower()

    @pytest.mark.asyncio
    async def test_skips_when_no_get_product_book(self):
        """Graceful degradation: exchange without order book support."""
        exchange = MagicMock(spec=[])

        proceed, reason = await check_buy_slippage(exchange, "BTC-USD", 1000.0, {})
        assert proceed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_skips_on_api_error(self):
        """Graceful degradation: API call raises exception."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(side_effect=RuntimeError("network error"))

        config = {"max_buy_slippage_pct": 0.5}
        proceed, reason = await check_buy_slippage(exchange, "BTC-USD", 1000.0, config)
        assert proceed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_skips_on_empty_asks(self):
        """Graceful degradation: book response has no asks."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {"bids": [], "asks": []}
        })

        config = {"max_buy_slippage_pct": 0.5}
        proceed, reason = await check_buy_slippage(exchange, "BTC-USD", 1000.0, config)
        assert proceed is True

    @pytest.mark.asyncio
    async def test_zero_quote_amount_skips(self):
        """Edge case: zero quote amount passes through."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [],
                "asks": [{"price": "50000.00", "size": "1.0"}],
            }
        })

        config = {"max_buy_slippage_pct": 0.5}
        proceed, reason = await check_buy_slippage(exchange, "BTC-USD", 0.0, config)
        assert proceed is True

    @pytest.mark.asyncio
    async def test_default_slippage_threshold(self):
        """Uses default 0.5% when max_buy_slippage_pct not in config."""
        exchange = AsyncMock()
        exchange.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [],
                "asks": [{"price": "50000.00", "size": "10.0"}],
            }
        })

        config = {}  # no max_buy_slippage_pct
        proceed, reason = await check_buy_slippage(exchange, "BTC-USD", 1000.0, config)
        assert proceed is True
