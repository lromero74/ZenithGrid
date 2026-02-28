"""
Tests for MultiBotMonitor class.

Tests orchestration logic: process_bot(), get_exchange_for_bot(),
get_active_bots(), get_candles_cached(), _should_skip/_handle_bot_error patterns,
and the clear_monitor_exchange_cache() helper.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.multi_bot_monitor import (
    MultiBotMonitor,
    clear_monitor_exchange_cache,
    filter_pairs_by_allowed_categories,
    _active_monitor_instance,
)


# ---------------------------------------------------------------------------
# Helpers — factory functions for mock objects
# ---------------------------------------------------------------------------


def _make_bot(
    bot_id=1,
    name="TestBot",
    strategy_type="macd_dca",
    is_active=True,
    account_id=10,
    user_id=1,
    strategy_config=None,
    product_ids=None,
    check_interval_seconds=300,
    budget_percentage=10.0,
    last_signal_check=None,
    last_ai_check=None,
    split_budget_across_pairs=False,
):
    bot = MagicMock()
    bot.id = bot_id
    bot.name = name
    bot.strategy_type = strategy_type
    bot.is_active = is_active
    bot.account_id = account_id
    bot.user_id = user_id
    bot.strategy_config = strategy_config or {"max_concurrent_deals": 2}
    bot.check_interval_seconds = check_interval_seconds
    bot.budget_percentage = budget_percentage
    bot.last_signal_check = last_signal_check
    bot.last_ai_check = last_ai_check
    bot.split_budget_across_pairs = split_budget_across_pairs

    # products helper (junction table)
    products = []
    for pid in (product_ids or ["ETH-BTC"]):
        bp = MagicMock()
        bp.product_id = pid
        products.append(bp)
    bot.products = products
    bot.get_trading_pairs = MagicMock(return_value=[bp.product_id for bp in products])
    bot.get_quote_currency = MagicMock(return_value="BTC")
    bot.get_reserved_balance = MagicMock(return_value=0.05)
    return bot


def _make_position(pos_id=1, bot_id=1, product_id="ETH-BTC", status="open", total_quote_spent=0.01):
    pos = MagicMock()
    pos.id = pos_id
    pos.bot_id = bot_id
    pos.product_id = product_id
    pos.status = status
    pos.total_quote_spent = total_quote_spent
    pos.total_quantity = 1.5
    pos.trades = []
    return pos


def _make_exchange():
    exchange = MagicMock()
    exchange.get_candles = AsyncMock(return_value=[
        {"open": 0.05, "high": 0.052, "low": 0.049, "close": 0.051, "volume": 100}
    ])
    exchange.get_current_price = AsyncMock(return_value=0.051)
    exchange.get_btc_balance = AsyncMock(return_value=0.5)
    exchange.get_usd_balance = AsyncMock(return_value=1000.0)
    exchange.calculate_aggregate_quote_value = AsyncMock(return_value=0.5)
    exchange.get_product_stats = AsyncMock(return_value={"volume_24h": 100.0})
    exchange.is_paper_trading = MagicMock(return_value=False)
    return exchange


# ===========================================================================
# Class: TestMultiBotMonitorInit
# ===========================================================================


class TestMultiBotMonitorInit:
    """Initialization and property tests."""

    def test_init_sets_defaults(self):
        monitor = MultiBotMonitor(exchange=None, interval_seconds=30)
        assert monitor.interval_seconds == 30
        assert monitor.running is False
        assert monitor.task is None
        assert monitor._candle_cache == {}
        assert monitor._exchange_cache == {}

    def test_init_sets_active_instance(self):
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        from app.multi_bot_monitor import _active_monitor_instance
        assert _active_monitor_instance is monitor

    def test_init_with_fallback_exchange(self):
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        assert monitor._fallback_exchange is exchange

    def test_exchange_property_returns_fallback(self):
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        assert monitor.exchange is exchange


# ===========================================================================
# Class: TestClearMonitorExchangeCache
# ===========================================================================


class TestClearMonitorExchangeCache:
    """Tests for the module-level clear_monitor_exchange_cache() function."""

    def test_clear_all_when_no_monitor(self):
        """No-op when no active monitor instance exists."""
        import app.multi_bot_monitor as mod
        original = mod._active_monitor_instance
        mod._active_monitor_instance = None
        try:
            clear_monitor_exchange_cache()  # Should not raise
        finally:
            mod._active_monitor_instance = original

    def test_clear_specific_account(self):
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        monitor._exchange_cache[10] = _make_exchange()
        monitor._exchange_cache[20] = _make_exchange()
        clear_monitor_exchange_cache(account_id=10)
        assert 10 not in monitor._exchange_cache
        assert 20 in monitor._exchange_cache

    def test_clear_all_accounts(self):
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        monitor._exchange_cache[10] = _make_exchange()
        monitor._exchange_cache[20] = _make_exchange()
        clear_monitor_exchange_cache()
        assert len(monitor._exchange_cache) == 0


# ===========================================================================
# Class: TestGetExchangeForBot
# ===========================================================================


class TestGetExchangeForBot:
    """Tests for MultiBotMonitor.get_exchange_for_bot()."""

    @pytest.mark.asyncio
    async def test_returns_cached_client(self, db_session):
        monitor = MultiBotMonitor()
        bot = _make_bot(account_id=10)
        cached_exchange = _make_exchange()
        monitor._exchange_cache[10] = cached_exchange

        result = await monitor.get_exchange_for_bot(db_session, bot)
        assert result is cached_exchange

    @pytest.mark.asyncio
    async def test_fetches_and_caches_client(self, db_session):
        """When not cached, fetches from service and caches."""
        new_exchange = _make_exchange()

        monitor = MultiBotMonitor()
        bot = _make_bot(account_id=42)

        with patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=new_exchange,
        ):
            result = await monitor.get_exchange_for_bot(db_session, bot)

        assert result is new_exchange

    @pytest.mark.asyncio
    async def test_does_not_cache_paper_trading_client(self, db_session):
        """Paper trading clients hold stale DB refs, should not be cached."""
        paper_exchange = _make_exchange()
        paper_exchange.is_paper_trading = MagicMock(return_value=True)

        with patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=paper_exchange,
        ):
            monitor = MultiBotMonitor()
            bot = _make_bot(account_id=99)
            result = await monitor.get_exchange_for_bot(db_session, bot)

        assert result is paper_exchange
        assert 99 not in monitor._exchange_cache

    @pytest.mark.asyncio
    async def test_falls_back_to_user_default(self, db_session):
        """If bot has no account_id but has user_id, fall back to user's default."""
        user_exchange = _make_exchange()
        bot = _make_bot(account_id=None, user_id=5)

        with patch(
            "app.services.exchange_service.get_exchange_client_for_user",
            new_callable=AsyncMock,
            return_value=user_exchange,
        ):
            monitor = MultiBotMonitor()
            result = await monitor.get_exchange_for_bot(db_session, bot)
            assert result is user_exchange

    @pytest.mark.asyncio
    async def test_falls_back_to_global_exchange(self, db_session):
        """If no account and no user, fall back to global."""
        global_exchange = _make_exchange()
        bot = _make_bot(account_id=None, user_id=None)

        monitor = MultiBotMonitor(exchange=global_exchange)
        result = await monitor.get_exchange_for_bot(db_session, bot)
        assert result is global_exchange

    @pytest.mark.asyncio
    async def test_returns_none_when_no_exchange_available(self, db_session):
        bot = _make_bot(account_id=None, user_id=None)
        monitor = MultiBotMonitor(exchange=None)

        with patch(
            "app.services.exchange_service.get_exchange_client_for_user",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await monitor.get_exchange_for_bot(db_session, bot)
        assert result is None


# ===========================================================================
# Class: TestGetCandlesCached
# ===========================================================================


class TestGetCandlesCached:
    """Tests for MultiBotMonitor.get_candles_cached()."""

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_and_caches(self):
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        candles = [{"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}]
        exchange.get_candles = AsyncMock(return_value=candles)

        with patch("app.multi_bot_monitor.fill_candle_gaps", return_value=candles), \
             patch("app.multi_bot_monitor.timeframe_to_seconds", return_value=300):
            result = await monitor.get_candles_cached("ETH-BTC", "FIVE_MINUTE", 100)

        assert result == candles
        assert "ETH-BTC:FIVE_MINUTE" in monitor._candle_cache

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self):
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        cached = [{"close": 99}]
        # Set a fresh timestamp
        monitor._candle_cache["ETH-BTC:FIVE_MINUTE"] = (datetime.utcnow().timestamp(), cached)

        result = await monitor.get_candles_cached("ETH-BTC", "FIVE_MINUTE", 100)
        assert result is cached
        # Should not have called exchange
        exchange.get_candles.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_expired_fetches_new(self):
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        old_candles = [{"close": 99}]
        # Set an old timestamp (10 minutes ago)
        expired_time = datetime.utcnow().timestamp() - 600
        monitor._candle_cache["ETH-BTC:FIVE_MINUTE"] = (expired_time, old_candles)

        new_candles = [{"open": 1, "high": 2, "low": 0.5, "close": 2, "volume": 50}]
        exchange.get_candles = AsyncMock(return_value=new_candles)

        with patch("app.multi_bot_monitor.fill_candle_gaps", return_value=new_candles), \
             patch("app.multi_bot_monitor.timeframe_to_seconds", return_value=300):
            result = await monitor.get_candles_cached("ETH-BTC", "FIVE_MINUTE", 100)

        assert result == new_candles

    @pytest.mark.asyncio
    async def test_synthetic_timeframe_aggregates(self):
        """Synthetic timeframes (e.g., THREE_MINUTE) aggregate from base candles."""
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        base_candles = [{"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}] * 30
        aggregated = [{"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 300}] * 10

        with patch("app.multi_bot_monitor.SYNTHETIC_TIMEFRAMES", {"THREE_MINUTE": ("ONE_MINUTE", 3)}), \
             patch.object(monitor, "get_candles_cached", new_callable=AsyncMock, return_value=base_candles), \
             patch("app.multi_bot_monitor.fill_candle_gaps", return_value=base_candles), \
             patch("app.multi_bot_monitor.aggregate_candles", return_value=aggregated), \
             patch("app.multi_bot_monitor.timeframe_to_seconds", return_value=60):
            # Call the real method by using the original class method bound to monitor
            result = await MultiBotMonitor.get_candles_cached(monitor, "ETH-BTC", "THREE_MINUTE", 100)

        assert result == aggregated

    @pytest.mark.asyncio
    async def test_returns_empty_on_exchange_error(self):
        exchange = _make_exchange()
        exchange.get_candles = AsyncMock(side_effect=Exception("API timeout"))
        monitor = MultiBotMonitor(exchange=exchange)

        with patch("app.multi_bot_monitor.SYNTHETIC_TIMEFRAMES", {}), \
             patch("app.multi_bot_monitor.timeframe_to_seconds", return_value=300):
            result = await monitor.get_candles_cached("ETH-BTC", "FIVE_MINUTE", 100)

        assert result == []


# ===========================================================================
# Class: TestProcessBot
# ===========================================================================


class TestProcessBot:
    """Tests for MultiBotMonitor.process_bot() dispatch logic."""

    @pytest.mark.asyncio
    async def test_dispatches_to_bull_flag_processor(self, db_session):
        monitor = MultiBotMonitor(exchange=_make_exchange())
        bot = _make_bot(strategy_type="bull_flag")

        with patch(
            "app.multi_bot_monitor._process_bull_flag_bot",
            new_callable=AsyncMock,
            return_value={"scanned": 5},
        ) as mock_bf:
            result = await monitor.process_bot(db_session, bot)

        mock_bf.assert_called_once_with(monitor, db_session, bot)
        assert result == {"scanned": 5}

    @pytest.mark.asyncio
    async def test_dispatches_to_batch_analysis(self, db_session):
        """When strategy supports batch analysis and >1 pairs, use batch mode."""
        monitor = MultiBotMonitor(exchange=_make_exchange())
        bot = _make_bot(product_ids=["ETH-BTC", "SOL-BTC"], strategy_config={"max_concurrent_deals": 5})

        mock_strategy = MagicMock()
        mock_strategy.analyze_multiple_pairs_batch = AsyncMock()

        # Mock the DB query for open positions
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.multi_bot_monitor.StrategyRegistry.get_strategy",
            return_value=mock_strategy,
        ), patch(
            "app.multi_bot_monitor._process_bot_batch",
            new_callable=AsyncMock,
            return_value={"ETH-BTC": {}, "SOL-BTC": {}},
        ) as mock_batch:
            result = await monitor.process_bot(db_session, bot)

        mock_batch.assert_called_once()
        assert "ETH-BTC" in result

    @pytest.mark.asyncio
    async def test_sequential_processing_single_pair(self, db_session):
        """Single-pair bot uses sequential processing (not batch)."""
        monitor = MultiBotMonitor(exchange=_make_exchange())
        bot = _make_bot(product_ids=["ETH-BTC"], strategy_config={"max_concurrent_deals": 1})

        mock_strategy = MagicMock(spec=[])  # no analyze_multiple_pairs_batch attr

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.multi_bot_monitor.StrategyRegistry.get_strategy",
            return_value=mock_strategy,
        ), patch(
            "app.multi_bot_monitor._process_bot_pair",
            new_callable=AsyncMock,
            return_value={"action": "none"},
        ) as mock_pair, patch(
            "app.multi_bot_monitor.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await monitor.process_bot(db_session, bot)

        mock_pair.assert_called_once()
        assert "ETH-BTC" in result

    @pytest.mark.asyncio
    async def test_stopped_bot_only_monitors_open_positions(self, db_session):
        """Stopped bot (is_active=False) filters to pairs with open positions only."""
        monitor = MultiBotMonitor(exchange=_make_exchange())
        bot = _make_bot(is_active=False, product_ids=["ETH-BTC", "SOL-BTC"])

        pos = _make_position(product_id="ETH-BTC")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)

        mock_strategy = MagicMock(spec=[])

        with patch(
            "app.multi_bot_monitor.StrategyRegistry.get_strategy",
            return_value=mock_strategy,
        ), patch(
            "app.multi_bot_monitor._process_bot_pair",
            new_callable=AsyncMock,
            return_value={"action": "none"},
        ) as mock_pair, patch(
            "app.multi_bot_monitor.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await monitor.process_bot(db_session, bot)

        # Should only process ETH-BTC (the one with an open position)
        assert mock_pair.call_count == 1
        call_args = mock_pair.call_args
        assert call_args[0][3] == "ETH-BTC"  # product_id argument

    @pytest.mark.asyncio
    async def test_stopped_bot_no_positions_returns_skip(self, db_session):
        """Stopped bot with no open positions returns skip."""
        monitor = MultiBotMonitor(exchange=_make_exchange())
        bot = _make_bot(is_active=False, product_ids=["ETH-BTC"])

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)

        result = await monitor.process_bot(db_session, bot)
        assert result.get("action") == "skip"

    @pytest.mark.asyncio
    async def test_process_bot_returns_error_on_exception(self, db_session):
        """Exceptions in processing are caught and returned as error dict."""
        monitor = MultiBotMonitor(exchange=_make_exchange())
        bot = _make_bot(strategy_type="unknown_strategy")
        # get_trading_pairs raises
        bot.get_trading_pairs = MagicMock(side_effect=RuntimeError("boom"))

        result = await monitor.process_bot(db_session, bot)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_at_max_capacity_only_analyzes_position_pairs(self, db_session):
        """When open_count >= max_concurrent_deals, only pairs with positions are analyzed."""
        monitor = MultiBotMonitor(exchange=_make_exchange())
        bot = _make_bot(
            product_ids=["ETH-BTC", "SOL-BTC", "ADA-BTC"],
            strategy_config={"max_concurrent_deals": 1},
        )

        pos = _make_position(product_id="SOL-BTC")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)

        mock_strategy = MagicMock(spec=[])  # no batch method

        with patch(
            "app.multi_bot_monitor.StrategyRegistry.get_strategy",
            return_value=mock_strategy,
        ), patch(
            "app.multi_bot_monitor._process_bot_pair",
            new_callable=AsyncMock,
            return_value={"action": "hold"},
        ) as mock_pair, patch(
            "app.multi_bot_monitor.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await monitor.process_bot(db_session, bot)

        # Only SOL-BTC should be processed (has position, at capacity)
        assert mock_pair.call_count == 1


# ===========================================================================
# Class: TestLogAiDecision
# ===========================================================================


class TestLogAiDecision:
    """Tests for MultiBotMonitor.log_ai_decision()."""

    @pytest.mark.asyncio
    async def test_creates_log_entry(self):
        monitor = MultiBotMonitor()
        bot = _make_bot()
        mock_db = MagicMock()
        mock_db.add = MagicMock()

        signal_data = {"signal_type": "buy", "confidence": 85, "reasoning": "Bullish MACD crossover"}
        pair_data = {"current_price": 0.051}

        with patch("app.models.AIBotLog") as MockLog:
            mock_entry = MagicMock()
            MockLog.return_value = mock_entry
            result = await monitor.log_ai_decision(mock_db, bot, "ETH-BTC", signal_data, pair_data)

        assert result is mock_entry
        mock_db.add.assert_called_once_with(mock_entry)

    @pytest.mark.asyncio
    async def test_log_links_existing_position(self):
        monitor = MultiBotMonitor()
        bot = _make_bot()
        mock_db = MagicMock()
        mock_db.add = MagicMock()

        pos = _make_position(product_id="ETH-BTC")
        signal_data = {"signal_type": "sell", "confidence": 90, "reasoning": "TP hit"}
        pair_data = {"current_price": 0.060}

        with patch("app.models.AIBotLog") as MockLog:
            mock_entry = MagicMock()
            MockLog.return_value = mock_entry
            await monitor.log_ai_decision(mock_db, bot, "ETH-BTC", signal_data, pair_data, [pos])

        # Verify position_id was set on the log entry
        assert MockLog.call_args[1]["position_id"] == pos.id

    @pytest.mark.asyncio
    async def test_log_returns_none_on_exception(self):
        """Exception in logging should not propagate — returns None."""
        monitor = MultiBotMonitor()
        bot = _make_bot()
        mock_db = MagicMock()
        mock_db.add = MagicMock(side_effect=Exception("DB error"))

        with patch("app.models.AIBotLog") as MockLog:
            MockLog.return_value = MagicMock()
            result = await monitor.log_ai_decision(
                mock_db, bot, "ETH-BTC",
                {"signal_type": "hold", "confidence": 50, "reasoning": "test"},
                {"current_price": 0.05},
            )
        assert result is None


# ===========================================================================
# Class: TestStartStop
# ===========================================================================


class TestStartStop:
    """Tests for start/stop lifecycle."""

    def test_start_sets_running(self):
        monitor = MultiBotMonitor()
        with patch("app.multi_bot_monitor.asyncio.create_task"):
            monitor.start()
        assert monitor.running is True

    def test_start_ignores_duplicate(self):
        monitor = MultiBotMonitor()
        monitor.running = True
        with patch("app.multi_bot_monitor.asyncio.create_task") as mock_create:
            monitor.start()
        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        monitor = MultiBotMonitor()
        monitor.running = True

        async def _noop():
            pass

        monitor.task = asyncio.ensure_future(_noop())
        await monitor.task  # let it complete first
        await monitor.stop()
        assert monitor.running is False

    @pytest.mark.asyncio
    async def test_stop_stops_order_monitor(self):
        monitor = MultiBotMonitor()
        monitor.running = True

        async def _noop():
            pass

        monitor.task = asyncio.ensure_future(_noop())
        await monitor.task  # let it complete first
        mock_order_monitor = MagicMock()
        mock_order_monitor.stop = AsyncMock()
        monitor.order_monitor = mock_order_monitor

        await monitor.stop()
        mock_order_monitor.stop.assert_called_once()


# ===========================================================================
# Class: TestFilterPairsByAllowedCategories
# ===========================================================================


class TestFilterPairsByAllowedCategories:
    """Tests for filter_pairs_by_allowed_categories()."""

    @pytest.mark.asyncio
    async def test_no_categories_returns_all(self, db_session):
        pairs = ["ETH-BTC", "SOL-BTC"]
        result = await filter_pairs_by_allowed_categories(db_session, pairs, None)
        assert result == pairs

    @pytest.mark.asyncio
    async def test_empty_categories_returns_all(self, db_session):
        pairs = ["ETH-BTC", "SOL-BTC"]
        result = await filter_pairs_by_allowed_categories(db_session, pairs, [])
        assert result == pairs

    @pytest.mark.asyncio
    async def test_filters_by_category(self, db_session):
        """Pairs not in allowed categories are filtered out."""
        pairs = ["ETH-BTC", "DOGE-BTC"]

        # Create mock blacklist entries
        mock_eth = MagicMock()
        mock_eth.symbol = "ETH"
        mock_eth.reason = "[APPROVED] Solid project"
        mock_eth.user_id = None

        mock_doge = MagicMock()
        mock_doge.symbol = "DOGE"
        mock_doge.reason = "[MEME] Meme coin"
        mock_doge.user_id = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_eth, mock_doge]
        db_session.execute = AsyncMock(return_value=mock_result)

        result = await filter_pairs_by_allowed_categories(db_session, pairs, ["APPROVED"])
        assert "ETH-BTC" in result
        assert "DOGE-BTC" not in result
