"""
Tests for backend/app/services/bot_stats_service.py

Tests PnL calculation, budget utilization, price fetching, and
aggregate value fetching for bot listings.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# fetch_aggregate_values
# ---------------------------------------------------------------------------


class TestFetchAggregateValues:
    """Tests for fetch_aggregate_values()."""

    @pytest.mark.asyncio
    async def test_happy_path_both_succeed(self):
        """Happy path: both BTC and USD aggregate values returned."""
        from app.services.bot_stats_service import fetch_aggregate_values

        coinbase = AsyncMock()
        coinbase.calculate_aggregate_btc_value = AsyncMock(return_value=1.5)
        coinbase.calculate_aggregate_usd_value = AsyncMock(return_value=75000.0)

        btc_val, usd_val = await fetch_aggregate_values(coinbase)
        assert btc_val == 1.5
        assert usd_val == 75000.0

    @pytest.mark.asyncio
    async def test_btc_fails_returns_none(self):
        """Failure: BTC fetch error returns None for BTC, USD still works."""
        from app.services.bot_stats_service import fetch_aggregate_values

        coinbase = AsyncMock()
        coinbase.calculate_aggregate_btc_value = AsyncMock(side_effect=Exception("API error"))
        coinbase.calculate_aggregate_usd_value = AsyncMock(return_value=75000.0)

        btc_val, usd_val = await fetch_aggregate_values(coinbase)
        assert btc_val is None
        assert usd_val == 75000.0

    @pytest.mark.asyncio
    async def test_both_fail_returns_none_none(self):
        """Failure: both fail returns (None, None)."""
        from app.services.bot_stats_service import fetch_aggregate_values

        coinbase = AsyncMock()
        coinbase.calculate_aggregate_btc_value = AsyncMock(side_effect=Exception("err"))
        coinbase.calculate_aggregate_usd_value = AsyncMock(side_effect=Exception("err"))

        btc_val, usd_val = await fetch_aggregate_values(coinbase)
        assert btc_val is None
        assert usd_val is None


# ---------------------------------------------------------------------------
# fetch_position_prices
# ---------------------------------------------------------------------------


class TestFetchPositionPrices:
    """Tests for fetch_position_prices()."""

    @pytest.mark.asyncio
    async def test_happy_path_all_prices(self):
        """Happy path: all products priced successfully."""
        from app.services.bot_stats_service import fetch_position_prices

        coinbase = AsyncMock()
        coinbase.get_current_price = AsyncMock(side_effect=lambda pid: 50000.0 if pid == "BTC-USD" else 3000.0)

        prices = await fetch_position_prices(coinbase, ["BTC-USD", "ETH-USD"])
        assert prices["BTC-USD"] == 50000.0
        assert prices["ETH-USD"] == 3000.0

    @pytest.mark.asyncio
    async def test_empty_products_returns_empty(self):
        """Edge case: no products returns empty dict."""
        from app.services.bot_stats_service import fetch_position_prices

        coinbase = AsyncMock()
        prices = await fetch_position_prices(coinbase, [])
        assert prices == {}

    @pytest.mark.asyncio
    async def test_failed_price_excluded(self):
        """Failure: product with price error is excluded from results."""
        from app.services.bot_stats_service import fetch_position_prices

        coinbase = AsyncMock()

        async def _get_price(pid):
            if pid == "BAD-USD":
                raise Exception("not found")
            return 100.0

        coinbase.get_current_price = AsyncMock(side_effect=_get_price)

        prices = await fetch_position_prices(coinbase, ["GOOD-USD", "BAD-USD"])
        assert "GOOD-USD" in prices
        assert "BAD-USD" not in prices

    @pytest.mark.asyncio
    async def test_batching_large_list(self):
        """Edge case: large list is batched correctly."""
        from app.services.bot_stats_service import fetch_position_prices

        coinbase = AsyncMock()
        coinbase.get_current_price = AsyncMock(return_value=100.0)

        products = [f"TOKEN{i}-USD" for i in range(30)]
        prices = await fetch_position_prices(coinbase, products, batch_size=15)
        assert len(prices) == 30


# ---------------------------------------------------------------------------
# calculate_bot_pnl
# ---------------------------------------------------------------------------


def _make_position(
    profit_usd=0.0,
    profit_quote=None,
    product_id="ETH-USD",
    btc_usd_price_at_close=None,
    btc_usd_price_at_open=None,
    total_quote_spent=100.0,
    closed_at=None,
    status="closed",
):
    """Helper to create a mock Position."""
    pos = MagicMock()
    pos.profit_usd = profit_usd
    pos.profit_quote = profit_quote
    pos.product_id = product_id
    pos.btc_usd_price_at_close = btc_usd_price_at_close
    pos.btc_usd_price_at_open = btc_usd_price_at_open
    pos.total_quote_spent = total_quote_spent
    pos.closed_at = closed_at or datetime.utcnow()
    pos.status = status
    pos.total_base_acquired = 0.0
    return pos


class TestCalculateBotPnl:
    """Tests for calculate_bot_pnl()."""

    def test_happy_path_usd_pairs(self):
        """Happy path: PnL for USD-denominated positions."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = MagicMock()
        bot.created_at = datetime.utcnow() - timedelta(days=10)

        closed = [
            _make_position(profit_usd=50.0, total_quote_spent=500.0,
                           btc_usd_price_at_close=50000.0),
            _make_position(profit_usd=-10.0, total_quote_spent=200.0,
                           btc_usd_price_at_close=50000.0),
        ]

        result = calculate_bot_pnl(bot, closed, open_positions=[])

        assert result["total_pnl_usd"] == pytest.approx(40.0)
        assert result["total_pnl_percentage"] == pytest.approx(40.0 / 700.0 * 100)
        assert result["win_rate"] == pytest.approx(50.0)
        assert result["trades_per_day"] == pytest.approx(2.0 / 10.0, rel=0.1)

    def test_no_closed_positions(self):
        """Edge case: no closed positions returns zeros."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = MagicMock()
        bot.created_at = datetime.utcnow() - timedelta(days=5)

        result = calculate_bot_pnl(bot, closed_positions=[], open_positions=[])

        assert result["total_pnl_usd"] == 0.0
        assert result["total_pnl_btc"] == 0.0
        assert result["win_rate"] == 0.0
        assert result["trades_per_day"] == 0.0

    def test_btc_pairs_use_profit_quote(self):
        """Happy path: BTC-denominated pairs use profit_quote for BTC PnL."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = MagicMock()
        bot.created_at = datetime.utcnow() - timedelta(days=1)

        closed = [
            _make_position(
                profit_usd=100.0,
                profit_quote=0.002,
                product_id="ETH-BTC",
                total_quote_spent=0.05,
                btc_usd_price_at_close=50000.0,
            ),
        ]

        result = calculate_bot_pnl(bot, closed, open_positions=[])

        assert result["total_pnl_btc"] == pytest.approx(0.002)

    def test_projection_timeframe_7d(self):
        """Edge case: 7d projection only considers recent positions."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = MagicMock()
        bot.created_at = datetime.utcnow() - timedelta(days=30)

        old_pos = _make_position(
            profit_usd=100.0,
            total_quote_spent=500.0,
            btc_usd_price_at_close=50000.0,
            closed_at=datetime.utcnow() - timedelta(days=20),
        )
        recent_pos = _make_position(
            profit_usd=50.0,
            total_quote_spent=200.0,
            btc_usd_price_at_close=50000.0,
            closed_at=datetime.utcnow() - timedelta(days=2),
        )

        result = calculate_bot_pnl(
            bot, [old_pos, recent_pos], open_positions=[], projection_timeframe="7d"
        )

        # Total PnL includes all closed positions
        assert result["total_pnl_usd"] == pytest.approx(150.0)
        # Avg daily PnL only from recent (7d period)
        assert result["avg_daily_pnl_usd"] == pytest.approx(50.0 / 7.0)

    def test_fallback_btc_price_when_none(self):
        """Edge case: missing BTC price defaults to 100000."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = MagicMock()
        bot.created_at = datetime.utcnow() - timedelta(days=1)

        closed = [
            _make_position(
                profit_usd=200.0,
                product_id="ETH-USD",
                total_quote_spent=1000.0,
                btc_usd_price_at_close=None,
                btc_usd_price_at_open=None,
            ),
        ]

        result = calculate_bot_pnl(bot, closed, open_positions=[])

        # Should use fallback 100000.0
        expected_btc_pnl = 200.0 / 100000.0
        assert result["total_pnl_btc"] == pytest.approx(expected_btc_pnl)


# ---------------------------------------------------------------------------
# calculate_budget_utilization
# ---------------------------------------------------------------------------


class TestCalculateBudgetUtilization:
    """Tests for calculate_budget_utilization()."""

    def test_happy_path_utilization(self):
        """Happy path: correct budget utilization percentage."""
        from app.services.bot_stats_service import calculate_budget_utilization

        bot = MagicMock()
        bot.id = 1
        bot.strategy_config = {"max_concurrent_deals": 3}
        bot.get_quote_currency = MagicMock(return_value="USD")
        bot.get_reserved_balance = MagicMock(return_value=3000.0)
        bot.budget_percentage = 10.0

        pos1 = MagicMock()
        pos1.product_id = "ETH-USD"
        pos1.total_base_acquired = 1.0
        pos1.total_quote_spent = 500.0

        prices = {"ETH-USD": 1000.0}

        result = calculate_budget_utilization(
            bot, [pos1], prices,
            aggregate_btc_value=1.0, aggregate_usd_value=30000.0,
        )

        # 1.0 * 1000 = 1000 in positions / 3000 reserved = 33.33%
        assert result["budget_utilization_percentage"] == pytest.approx(33.33, rel=0.01)

    def test_no_reserved_balance(self):
        """Edge case: zero reserved balance => 0% utilization."""
        from app.services.bot_stats_service import calculate_budget_utilization

        bot = MagicMock()
        bot.id = 1
        bot.strategy_config = {"max_concurrent_deals": 1}
        bot.get_quote_currency = MagicMock(return_value="USD")
        bot.get_reserved_balance = MagicMock(return_value=0.0)
        bot.budget_percentage = 0.0

        result = calculate_budget_utilization(
            bot, [], {}, aggregate_btc_value=0.0, aggregate_usd_value=0.0,
        )

        assert result["budget_utilization_percentage"] == 0.0

    def test_insufficient_funds_detected(self):
        """Happy path: insufficient funds detected when remaining < min per position."""
        from app.services.bot_stats_service import calculate_budget_utilization

        bot = MagicMock()
        bot.id = 1
        bot.strategy_config = {"max_concurrent_deals": 3}
        bot.get_quote_currency = MagicMock(return_value="USD")
        bot.get_reserved_balance = MagicMock(return_value=3000.0)
        bot.budget_percentage = 10.0

        # 2 open positions using most of the budget
        pos1 = MagicMock()
        pos1.product_id = "ETH-USD"
        pos1.total_base_acquired = 1.0
        pos1.total_quote_spent = 1400.0

        pos2 = MagicMock()
        pos2.product_id = "SOL-USD"
        pos2.total_base_acquired = 10.0
        pos2.total_quote_spent = 1400.0

        prices = {"ETH-USD": 1400.0, "SOL-USD": 140.0}

        result = calculate_budget_utilization(
            bot, [pos1, pos2], prices,
            aggregate_btc_value=1.0, aggregate_usd_value=30000.0,
        )

        # reserved=3000, pos1=1400, pos2=1400, available=200
        # min_per_position = 3000/3 = 1000
        # available(200) < min_per_position(1000) => insufficient
        assert result["insufficient_funds"] is True

    def test_missing_price_uses_quote_spent(self):
        """Edge case: missing price uses total_quote_spent as fallback."""
        from app.services.bot_stats_service import calculate_budget_utilization

        bot = MagicMock()
        bot.id = 1
        bot.strategy_config = {"max_concurrent_deals": 2}
        bot.get_quote_currency = MagicMock(return_value="USD")
        bot.get_reserved_balance = MagicMock(return_value=2000.0)
        bot.budget_percentage = 10.0

        pos = MagicMock()
        pos.product_id = "UNKNOWN-USD"
        pos.total_base_acquired = 5.0
        pos.total_quote_spent = 500.0

        result = calculate_budget_utilization(
            bot, [pos], {},  # empty prices
            aggregate_btc_value=1.0, aggregate_usd_value=20000.0,
        )

        # Fallback: uses 500 (total_quote_spent) / 2000 = 25%
        assert result["budget_utilization_percentage"] == pytest.approx(25.0)

    def test_error_returns_defaults(self):
        """Failure: exception during calculation returns safe defaults."""
        from app.services.bot_stats_service import calculate_budget_utilization

        bot = MagicMock()
        bot.id = 1
        bot.strategy_config = {"max_concurrent_deals": 1}
        bot.get_quote_currency = MagicMock(side_effect=Exception("boom"))

        result = calculate_budget_utilization(
            bot, [], {}, aggregate_btc_value=None, aggregate_usd_value=None,
        )

        assert result["budget_utilization_percentage"] == 0.0
        assert result["insufficient_funds"] is False

    def test_btc_quote_uses_btc_aggregate(self):
        """Happy path: BTC-quoted bot uses aggregate BTC value."""
        from app.services.bot_stats_service import calculate_budget_utilization

        bot = MagicMock()
        bot.id = 1
        bot.strategy_config = {"max_concurrent_deals": 1}
        bot.get_quote_currency = MagicMock(return_value="BTC")
        bot.get_reserved_balance = MagicMock(return_value=0.5)
        bot.budget_percentage = 50.0

        pos = MagicMock()
        pos.product_id = "ETH-BTC"
        pos.total_base_acquired = 10.0
        pos.total_quote_spent = 0.3

        prices = {"ETH-BTC": 0.03}

        result = calculate_budget_utilization(
            bot, [pos], prices,
            aggregate_btc_value=1.0, aggregate_usd_value=50000.0,
        )

        # 10 * 0.03 = 0.3 BTC in position / 0.5 reserved = 60%
        assert result["budget_utilization_percentage"] == pytest.approx(60.0)
