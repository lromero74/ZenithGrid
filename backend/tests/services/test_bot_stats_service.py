"""
Tests for backend/app/services/bot_stats_service.py

Tests PnL calculation, budget utilization, price fetching, and
aggregate value fetching for bot listings.
"""

import pytest
from app.utils.timeutil import utcnow
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


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

        async def _agg_quote(currency, **kwargs):
            return 1.5 if currency == "BTC" else 75000.0

        coinbase.calculate_market_budget = AsyncMock(side_effect=_agg_quote)

        btc_val, usd_val = await fetch_aggregate_values(coinbase)
        assert btc_val == 1.5
        assert usd_val == 75000.0

    @pytest.mark.asyncio
    async def test_uses_quote_value_not_portfolio_total(self):
        """Budget uses per-quote aggregate (free USD + USD-pair positions),
        NOT total portfolio value with all assets converted to USD."""
        from app.services.bot_stats_service import fetch_aggregate_values

        coinbase = AsyncMock()

        async def _agg_quote(currency, **kwargs):
            return 5000.0 if currency == "USD" else 0.5

        coinbase.calculate_market_budget = AsyncMock(side_effect=_agg_quote)

        btc_val, usd_val = await fetch_aggregate_values(coinbase)
        # Should use calculate_market_budget, not calculate_aggregate_usd_value
        coinbase.calculate_market_budget.assert_any_call("BTC")
        coinbase.calculate_market_budget.assert_any_call("USD")
        assert usd_val == 5000.0
        assert btc_val == 0.5

    @pytest.mark.asyncio
    async def test_btc_fails_returns_none(self):
        """Failure: BTC fetch error returns None for BTC, USD still works."""
        from app.services.bot_stats_service import fetch_aggregate_values

        coinbase = AsyncMock()

        async def _agg_quote(currency, **kwargs):
            if currency == "BTC":
                raise Exception("API error")
            return 75000.0

        coinbase.calculate_market_budget = AsyncMock(side_effect=_agg_quote)

        btc_val, usd_val = await fetch_aggregate_values(coinbase)
        assert btc_val is None
        assert usd_val == 75000.0

    @pytest.mark.asyncio
    async def test_both_fail_returns_none_none(self):
        """Failure: both fail returns (None, None)."""
        from app.services.bot_stats_service import fetch_aggregate_values

        coinbase = AsyncMock()
        coinbase.calculate_market_budget = AsyncMock(side_effect=Exception("err"))

        btc_val, usd_val = await fetch_aggregate_values(coinbase)
        assert btc_val is None
        assert usd_val is None


# ---------------------------------------------------------------------------
# fetch_position_prices
# ---------------------------------------------------------------------------


class TestFetchPositionPrices:
    """Tests for fetch_position_prices()."""

    @pytest.fixture(autouse=True)
    def _no_bulk_prices(self):
        """Default: force the per-product fallback path so tests written
        against the old serial-batched behavior still exercise it.
        Individual tests can opt into the bulk path by patching
        list_products themselves."""
        with patch(
            "app.coinbase_api.public_market_data.list_products",
            new_callable=AsyncMock,
            return_value=[],
        ):
            yield

    @pytest.mark.asyncio
    async def test_happy_path_all_prices(self):
        """Happy path: all products priced successfully via per-product fallback."""
        from app.services.bot_stats_service import fetch_position_prices

        coinbase = AsyncMock()
        coinbase.get_current_price = AsyncMock(side_effect=lambda pid: 50000.0 if pid == "BTC-USD" else 3000.0)

        prices = await fetch_position_prices(coinbase, ["BTC-USD", "ETH-USD"])
        assert prices["BTC-USD"] == 50000.0
        assert prices["ETH-USD"] == 3000.0

    @pytest.mark.asyncio
    async def test_bulk_path_skips_per_product_calls(self):
        """Optimization: when the bulk endpoint returns prices for all
        products, the per-product ticker path must NOT be called. This
        is what saves ~11s on the /api/bots/ cold path."""
        from app.services.bot_stats_service import fetch_position_prices

        coinbase = AsyncMock()
        coinbase.get_current_price = AsyncMock(return_value=9999.0)  # poisoned

        with patch(
            "app.coinbase_api.public_market_data.list_products",
            new_callable=AsyncMock,
            return_value=[
                {"product_id": "BTC-USD", "price": "60000.0"},
                {"product_id": "ETH-USD", "price": "3000.0"},
            ],
        ):
            prices = await fetch_position_prices(coinbase, ["BTC-USD", "ETH-USD"])

        assert prices == {"BTC-USD": 60000.0, "ETH-USD": 3000.0}
        coinbase.get_current_price.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_bulk_falls_back_for_missing(self):
        """Mixed: bulk covers BTC-USD, per-product handles the rest."""
        from app.services.bot_stats_service import fetch_position_prices

        coinbase = AsyncMock()
        coinbase.get_current_price = AsyncMock(return_value=42.0)

        with patch(
            "app.coinbase_api.public_market_data.list_products",
            new_callable=AsyncMock,
            return_value=[
                {"product_id": "BTC-USD", "price": "60000.0"},
            ],
        ):
            prices = await fetch_position_prices(coinbase, ["BTC-USD", "DELISTED-USD"])

        assert prices["BTC-USD"] == 60000.0
        assert prices["DELISTED-USD"] == 42.0
        coinbase.get_current_price.assert_awaited_once_with("DELISTED-USD")

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
    exit_reason=None,
):
    """Helper to create a mock Position."""
    pos = MagicMock()
    pos.profit_usd = profit_usd
    pos.profit_quote = profit_quote
    pos.product_id = product_id
    pos.btc_usd_price_at_close = btc_usd_price_at_close
    pos.btc_usd_price_at_open = btc_usd_price_at_open
    pos.total_quote_spent = total_quote_spent
    pos.closed_at = closed_at or utcnow()
    pos.status = status
    pos.exit_reason = exit_reason
    pos.total_base_acquired = 0.0
    return pos


def _make_bot(days_old: float = 10, total_running_seconds: float = 0.0,
              is_active: bool = False, last_started_at=None) -> MagicMock:
    """Helper: create a bot mock with all running-time fields set."""
    bot = MagicMock()
    bot.created_at = utcnow() - timedelta(days=days_old)
    bot.total_running_seconds = total_running_seconds
    bot.is_active = is_active
    bot.last_started_at = last_started_at
    return bot


class TestCalculateBotPnl:
    """Tests for calculate_bot_pnl()."""

    def test_happy_path_usd_pairs(self):
        """Happy path: PnL for USD-denominated positions."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = _make_bot(days_old=10)

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

        bot = _make_bot(days_old=5)

        result = calculate_bot_pnl(bot, closed_positions=[], open_positions=[])

        assert result["total_pnl_usd"] == 0.0
        assert result["total_pnl_btc"] == 0.0
        assert result["win_rate"] == 0.0
        assert result["trades_per_day"] == 0.0

    def test_btc_pairs_use_profit_quote(self):
        """Happy path: BTC-denominated pairs use profit_quote for BTC PnL."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = _make_bot(days_old=1)

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

        bot = _make_bot(days_old=30)

        old_pos = _make_position(
            profit_usd=100.0,
            total_quote_spent=500.0,
            btc_usd_price_at_close=50000.0,
            closed_at=utcnow() - timedelta(days=20),
        )
        recent_pos = _make_position(
            profit_usd=50.0,
            total_quote_spent=200.0,
            btc_usd_price_at_close=50000.0,
            closed_at=utcnow() - timedelta(days=2),
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

        bot = _make_bot(days_old=1)

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

    def test_aggregate_running_days_from_stored_seconds_when_stopped(self):
        """Bot that was stopped: aggregate_running_days from total_running_seconds only."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = MagicMock()
        bot.created_at = utcnow() - timedelta(days=10)
        bot.total_running_seconds = 86400.0 * 3  # 3 days stored
        bot.is_active = False
        bot.last_started_at = None

        result = calculate_bot_pnl(bot, closed_positions=[], open_positions=[])

        assert result["aggregate_running_days"] == pytest.approx(3.0, rel=0.01)

    def test_aggregate_running_days_includes_current_session(self):
        """Active bot: aggregate_running_days adds current session to stored seconds."""
        from app.services.bot_stats_service import calculate_bot_pnl

        now = utcnow()
        bot = MagicMock()
        bot.created_at = now - timedelta(days=10)
        bot.total_running_seconds = 86400.0 * 2  # 2 days previously accumulated
        bot.is_active = True
        bot.last_started_at = now - timedelta(hours=12)  # 12-hour current session

        result = calculate_bot_pnl(bot, closed_positions=[], open_positions=[])

        # 2 days + 0.5 days = 2.5 days
        assert result["aggregate_running_days"] == pytest.approx(2.5, rel=0.01)

    def test_aggregate_running_days_zero_when_never_started(self):
        """Bot that was never started: aggregate_running_days is 0."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = MagicMock()
        bot.created_at = utcnow() - timedelta(days=5)
        bot.total_running_seconds = 0.0
        bot.is_active = False
        bot.last_started_at = None

        result = calculate_bot_pnl(bot, closed_positions=[], open_positions=[])

        assert result["aggregate_running_days"] == 0.0

    def test_win_rate_excludes_manual_closes(self):
        """Manual force-closes should not count in win rate numerator or denominator."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = _make_bot(days_old=10)

        # 2 bot-driven wins + 1 manual close at profit (excluded) + 1 manual close at loss (excluded)
        closed = [
            _make_position(profit_usd=50.0, total_quote_spent=500.0),
            _make_position(profit_usd=30.0, total_quote_spent=300.0),
            _make_position(profit_usd=20.0, total_quote_spent=200.0, exit_reason="manual"),
            _make_position(profit_usd=-15.0, total_quote_spent=150.0, exit_reason="manual"),
        ]

        result = calculate_bot_pnl(bot, closed, open_positions=[])

        # Only 2 bot-driven positions in denominator, both wins → 100%
        assert result["win_rate"] == pytest.approx(100.0)

    def test_win_rate_manual_close_at_loss_not_counted(self):
        """Manual close at a loss should not reduce win rate."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = _make_bot(days_old=5)

        closed = [
            _make_position(profit_usd=100.0, total_quote_spent=1000.0),
            _make_position(profit_usd=-50.0, total_quote_spent=500.0, exit_reason="manual"),
        ]

        result = calculate_bot_pnl(bot, closed, open_positions=[])

        # Only the bot-driven win counts — 1/1 = 100%
        assert result["win_rate"] == pytest.approx(100.0)

    def test_win_rate_all_manual_closes_returns_zero(self):
        """If all closed positions are manual, win rate is 0 (no bot-driven data)."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = _make_bot(days_old=5)

        closed = [
            _make_position(profit_usd=50.0, total_quote_spent=500.0, exit_reason="manual"),
        ]

        result = calculate_bot_pnl(bot, closed, open_positions=[])

        assert result["win_rate"] == 0.0

    def test_calendar_days_since_creation_returned(self):
        """calendar_days reflects full time since bot was created."""
        from app.services.bot_stats_service import calculate_bot_pnl

        bot = MagicMock()
        bot.created_at = utcnow() - timedelta(days=7)
        bot.total_running_seconds = 0.0
        bot.is_active = False
        bot.last_started_at = None

        result = calculate_bot_pnl(bot, closed_positions=[], open_positions=[])

        assert result["calendar_days"] == pytest.approx(7.0, rel=0.05)


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


# ---------------------------------------------------------------------------
# closed_today_count logic (inline in bot_crud_router, tested here as a unit)
# ---------------------------------------------------------------------------


class TestClosedTodayCount:
    """Tests for the 'closed today' filtering logic used in list_bots()."""

    def _make_position(self, closed_at):
        pos = MagicMock()
        pos.status = "closed"
        pos.closed_at = closed_at
        return pos

    def _count_closed_today(self, closed_positions):
        """Mirror of the logic in bot_crud_router.list_bots()."""
        from datetime import timezone
        today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return [
            p for p in closed_positions
            if p.closed_at and p.closed_at.replace(tzinfo=timezone.utc) >= today_utc
        ]

    def test_position_closed_today_is_counted(self):
        """Happy path: position closed a few minutes ago is included."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        pos = self._make_position(now.replace(tzinfo=None))  # naive UTC as stored
        result = self._count_closed_today([pos])
        assert len(result) == 1

    def test_position_closed_yesterday_not_counted(self):
        """Happy path: position closed yesterday is excluded."""
        from datetime import timezone
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        pos = self._make_position(yesterday.replace(tzinfo=None))
        result = self._count_closed_today([pos])
        assert len(result) == 0

    def test_position_with_no_closed_at_excluded(self):
        """Edge case: position with closed_at=None should not appear in today count."""
        pos = MagicMock()
        pos.closed_at = None
        result = self._count_closed_today([pos])
        assert len(result) == 0

    def test_mixed_positions_only_counts_today(self):
        """Edge case: mix of today/yesterday — only today's are counted."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        today_pos = self._make_position(now.replace(tzinfo=None))
        old_pos = self._make_position((now - timedelta(days=2)).replace(tzinfo=None))
        result = self._count_closed_today([today_pos, old_pos])
        assert len(result) == 1

    def test_empty_positions_returns_zero(self):
        """Edge case: no positions → zero today."""
        result = self._count_closed_today([])
        assert len(result) == 0
