"""
Tests for MultiBotMonitor class.

Tests orchestration logic: process_bot(), get_exchange_for_bot(),
get_active_bots(), get_candles_cached(), _should_skip/_handle_bot_error patterns,
and the clear_monitor_exchange_cache() helper.
"""

import asyncio
from app.utils.timeutil import utcnow
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.multi_bot_monitor import (
    MultiBotMonitor,
    clear_monitor_exchange_cache,
    filter_pairs_by_allowed_categories,
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
    # Rebalancer gate defaults — disabled so tests don't trip on MagicMock comparisons
    bot.bot_rebalancer_enabled = False
    bot.bot_rebalancer_target_pct = 0.0

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
    exchange.calculate_market_budget = AsyncMock(return_value=0.5)
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
        # Cache key now includes the lookback size so distinct sizes don't collide.
        assert "ETH-BTC:FIVE_MINUTE:100" in monitor._candle_cache

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self):
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        cached = [{"close": 99}]
        # Set a fresh timestamp
        monitor._candle_cache["ETH-BTC:FIVE_MINUTE:100"] = (utcnow().timestamp(), cached)

        result = await monitor.get_candles_cached("ETH-BTC", "FIVE_MINUTE", 100)
        assert result is cached
        # Should not have called exchange
        exchange.get_candles.assert_not_called()

    @pytest.mark.asyncio
    async def test_larger_lookback_not_served_from_smaller_cache(self):
        """A 200-candle request must NOT be served a cached 100-candle entry — distinct
        lookbacks use distinct cache keys, so the larger request triggers its own fetch."""
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        small = [{"close": 1}] * 100
        monitor._candle_cache["ETH-BTC:FIVE_MINUTE:100"] = (utcnow().timestamp(), small)
        big = [{"open": 1, "high": 2, "low": 0.5, "close": 2, "volume": 5}] * 200
        exchange.get_candles = AsyncMock(return_value=big)

        with patch("app.multi_bot_monitor.fill_candle_gaps", return_value=big), \
             patch("app.multi_bot_monitor.timeframe_to_seconds", return_value=300):
            result = await monitor.get_candles_cached("ETH-BTC", "FIVE_MINUTE", 200)

        assert len(result) == 200            # got the larger set, not the cached 100
        exchange.get_candles.assert_awaited()  # a real fetch happened for the 200 key

    @pytest.mark.asyncio
    async def test_cache_expired_fetches_new(self):
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        old_candles = [{"close": 99}]
        # Set an old timestamp (10 minutes ago)
        expired_time = utcnow().timestamp() - 600
        monitor._candle_cache["ETH-BTC:FIVE_MINUTE:100"] = (expired_time, old_candles)

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

    @pytest.mark.asyncio
    async def test_concurrent_misses_same_key_coalesce_into_one_fetch(self):
        """N concurrent callers for the same pair/timeframe share ONE exchange
        call. Critical for the exchange rate budget — pairs are processed
        concurrently, so without coalescing a cold cache fans out N identical
        API requests."""
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        candles = [{"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}]

        async def slow_fetch(**kwargs):
            await asyncio.sleep(0.02)
            return list(candles)

        exchange.get_candles = AsyncMock(side_effect=slow_fetch)

        with patch("app.multi_bot_monitor.fill_candle_gaps", return_value=candles), \
             patch("app.multi_bot_monitor.timeframe_to_seconds", return_value=300):
            results = await asyncio.gather(*[
                monitor.get_candles_cached("ETH-BTC", "FIVE_MINUTE", 100)
                for _ in range(5)
            ])

        assert all(r == candles for r in results)
        assert exchange.get_candles.await_count == 1

    @pytest.mark.asyncio
    async def test_concurrent_misses_different_keys_fetch_independently(self):
        """Coalescing is per pair/timeframe — distinct keys still fetch in
        parallel rather than serializing behind one global lock."""
        exchange = _make_exchange()
        monitor = MultiBotMonitor(exchange=exchange)
        candles = [{"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}]

        async def slow_fetch(**kwargs):
            await asyncio.sleep(0.02)
            return list(candles)

        exchange.get_candles = AsyncMock(side_effect=slow_fetch)

        with patch("app.multi_bot_monitor.fill_candle_gaps", return_value=candles), \
             patch("app.multi_bot_monitor.timeframe_to_seconds", return_value=300):
            await asyncio.gather(
                monitor.get_candles_cached("ETH-BTC", "FIVE_MINUTE", 100),
                monitor.get_candles_cached("ADA-BTC", "FIVE_MINUTE", 100),
            )

        assert exchange.get_candles.await_count == 2


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
            await monitor.process_bot(db_session, bot)

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
    async def test_unavailable_configured_pair_is_skipped_before_processing(self, db_session):
        """Configured pairs missing from the product cache should not hit candles/API."""
        monitor = MultiBotMonitor(exchange=_make_exchange())
        bot = _make_bot(
            product_ids=["AAVE-USD", "MEDIA-USD", "SOL-USD"],
            strategy_config={"max_concurrent_deals": 5},
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)

        mock_strategy = MagicMock(spec=[])
        processed_pairs = []

        async def fake_pair(monitor_self, db, bot_, product_id, **kwargs):
            processed_pairs.append(product_id)
            return {"action": "none", "pair": product_id}

        with patch(
            "app.multi_bot_monitor.StrategyRegistry.get_strategy",
            return_value=mock_strategy,
        ), patch(
            "app.multi_bot_monitor.get_available_trading_products",
            new_callable=AsyncMock,
            return_value={"AAVE-USD", "SOL-USD"},
        ), patch(
            "app.multi_bot_monitor._process_bot_pair",
            side_effect=fake_pair,
        ), patch(
            "app.multi_bot_monitor.asyncio.sleep",
            new_callable=AsyncMock,
        ), patch(
            "app.multi_bot_monitor.async_session_maker"
        ) as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await monitor.process_bot(db_session, bot)

        assert set(processed_pairs) == {"AAVE-USD", "SOL-USD"}
        assert "MEDIA-USD" not in result

    @pytest.mark.asyncio
    async def test_unavailable_pair_with_open_position_is_still_processed(self, db_session):
        """Existing positions must remain manageable even if the pair leaves listings."""
        monitor = MultiBotMonitor(exchange=_make_exchange())
        bot = _make_bot(
            product_ids=["AAVE-USD", "MEDIA-USD"],
            strategy_config={"max_concurrent_deals": 5},
        )

        pos = _make_position(product_id="MEDIA-USD")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)

        mock_strategy = MagicMock(spec=[])
        processed_pairs = []

        async def fake_pair(monitor_self, db, bot_, product_id, **kwargs):
            processed_pairs.append(product_id)
            return {"action": "none", "pair": product_id}

        with patch(
            "app.multi_bot_monitor.StrategyRegistry.get_strategy",
            return_value=mock_strategy,
        ), patch(
            "app.multi_bot_monitor.get_available_trading_products",
            new_callable=AsyncMock,
            return_value={"AAVE-USD"},
        ), patch(
            "app.multi_bot_monitor._process_bot_pair",
            side_effect=fake_pair,
        ), patch(
            "app.multi_bot_monitor.asyncio.sleep",
            new_callable=AsyncMock,
        ), patch(
            "app.multi_bot_monitor.async_session_maker"
        ) as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await monitor.process_bot(db_session, bot)

        assert set(processed_pairs) == {"AAVE-USD", "MEDIA-USD"}
        assert "MEDIA-USD" in result

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
            await monitor.process_bot(db_session, bot)

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
        # monitor_loop must not produce a real coroutine here — create_task is
        # mocked, so the coroutine would never be awaited
        monitor.monitor_loop = MagicMock()
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


# ===========================================================================
# Class: TestConcurrentPairProcessing
# ===========================================================================


class TestConcurrentPairProcessing:
    """
    Tests that sequential pair processing uses asyncio.gather() for concurrency
    while honouring the per-bot semaphore.
    """

    @pytest.mark.asyncio
    async def test_all_pairs_processed_concurrently(self, db_session):
        """All pairs in a multi-pair bot are processed and results returned."""
        pairs = ["ETH-BTC", "SOL-BTC", "ADA-BTC", "DOT-BTC", "LINK-BTC", "MATIC-BTC"]
        monitor = MultiBotMonitor(exchange=_make_exchange())
        bot = _make_bot(
            product_ids=pairs,
            strategy_config={"max_concurrent_deals": 10},
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)

        mock_strategy = MagicMock(spec=[])  # no batch method

        call_order = []

        async def fake_pair(monitor_self, db, bot_, product_id, **kwargs):
            call_order.append(product_id)
            return {"action": "none", "pair": product_id}

        with patch("app.multi_bot_monitor.StrategyRegistry.get_strategy", return_value=mock_strategy), \
             patch("app.multi_bot_monitor._process_bot_pair", side_effect=fake_pair), \
             patch("app.multi_bot_monitor.asyncio.sleep", new_callable=AsyncMock), \
             patch("app.multi_bot_monitor.async_session_maker") as mock_session_maker:
            # Each pair call to async_session_maker yields a usable session context manager
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await monitor.process_bot(db_session, bot)

        assert set(result.keys()) == set(pairs), "All pairs must appear in results"
        assert len(call_order) == len(pairs), "Each pair must be processed exactly once"

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_pairs(self, db_session):
        """Pairs run concurrently (> 1 at once) but no more than PAIR_CONCURRENCY at a time.

        Uses real asyncio.sleep(0) by patching PAIR_PROCESSING_DELAY_SECONDS=0 so tasks
        actually yield to the event loop and we can observe true concurrency.
        """
        pairs = [f"COIN{i}-BTC" for i in range(10)]
        monitor = MultiBotMonitor(exchange=_make_exchange())
        # Force a known concurrency level — compute_dynamic_concurrency() is
        # RAM-sensitive and returns 1 on low-memory hosts (e.g. t2.micro CI),
        # which makes this test flaky. Fix it to 5 for deterministic behavior.
        monitor._pair_concurrency = 5
        bot = _make_bot(product_ids=pairs, strategy_config={"max_concurrent_deals": 20})

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)

        mock_strategy = MagicMock(spec=[])

        # Track max concurrent executions
        concurrent_count = 0
        max_concurrent = 0

        async def fake_pair(monitor_self, db, bot_, product_id, **kwargs):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0)  # real yield — lets other tasks advance
            concurrent_count -= 1
            return {"action": "none"}

        pair_concurrency = monitor._pair_concurrency

        # Patch constant to 0 so asyncio.sleep(0) is used in _process_pair_task,
        # which is a real yield and allows other tasks to interleave.
        with patch("app.multi_bot_monitor.StrategyRegistry.get_strategy", return_value=mock_strategy), \
             patch("app.multi_bot_monitor._process_bot_pair", side_effect=fake_pair), \
             patch("app.multi_bot_monitor.PAIR_PROCESSING_DELAY_SECONDS", 0), \
             patch("app.multi_bot_monitor.async_session_maker") as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await monitor.process_bot(db_session, bot)

        # Upper bound: semaphore must not be exceeded
        assert max_concurrent <= pair_concurrency, (
            f"Semaphore exceeded: expected max {pair_concurrency}, got {max_concurrent}"
        )
        # Lower bound: must achieve actual concurrency (> 1 pair at a time)
        assert max_concurrent > 1, (
            f"Expected concurrent pair execution (> 1), but max was {max_concurrent} — "
            "pairs appear to be processing sequentially"
        )

    @pytest.mark.asyncio
    async def test_one_pair_error_does_not_block_others(self, db_session):
        """An exception in one pair task returns error dict but lets other pairs complete."""
        pairs = ["ETH-BTC", "FAIL-BTC", "SOL-BTC"]
        monitor = MultiBotMonitor(exchange=_make_exchange())
        bot = _make_bot(product_ids=pairs, strategy_config={"max_concurrent_deals": 5})

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)

        mock_strategy = MagicMock(spec=[])

        async def fake_pair(monitor_self, db, bot_, product_id, **kwargs):
            if product_id == "FAIL-BTC":
                raise ValueError("simulated API failure")
            return {"action": "none", "pair": product_id}

        with patch("app.multi_bot_monitor.StrategyRegistry.get_strategy", return_value=mock_strategy), \
             patch("app.multi_bot_monitor._process_bot_pair", side_effect=fake_pair), \
             patch("app.multi_bot_monitor.asyncio.sleep", new_callable=AsyncMock), \
             patch("app.multi_bot_monitor.async_session_maker") as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await monitor.process_bot(db_session, bot)

        assert "error" in result.get("FAIL-BTC", {})
        assert result.get("ETH-BTC", {}).get("action") == "none"
        assert result.get("SOL-BTC", {}).get("action") == "none"


# ===========================================================================
# Class: TestCleanupCaches
# ===========================================================================


class TestCleanupCaches:
    """Tests for MultiBotMonitor.cleanup_caches() eviction."""

    def test_cleanup_evicts_expired_candles(self):
        monitor = MultiBotMonitor()
        now = utcnow().timestamp()
        # Fresh entry: should stay
        monitor._candle_cache["ETH-BTC:FIVE_MINUTE"] = (now, [{"close": 1}])
        # Old entry: should evict (TTL is CANDLE_CACHE_DEFAULT_TTL; use huge age)
        monitor._candle_cache["BTC-USD:ONE_HOUR"] = (now - 10_000_000, [{"close": 2}])

        result = monitor.cleanup_caches()
        assert result["candles_evicted"] >= 1
        assert "ETH-BTC:FIVE_MINUTE" in monitor._candle_cache

    def test_cleanup_evicts_stale_indicators(self):
        monitor = MultiBotMonitor()
        # Active bot id=1 in _bot_next_check
        monitor._bot_next_check[1] = 9999999999
        # Indicator key for active bot (stays) and stale bot (evicted)
        monitor._previous_indicators_cache[(1, "ETH-BTC")] = {"rsi": 50}
        monitor._previous_indicators_cache[(99, "DEAD-BTC")] = {"rsi": 70}

        result = monitor.cleanup_caches()
        assert (1, "ETH-BTC") in monitor._previous_indicators_cache
        assert (99, "DEAD-BTC") not in monitor._previous_indicators_cache
        assert result["indicators_evicted"] >= 1

    def test_cleanup_returns_remaining_counts(self):
        monitor = MultiBotMonitor()
        result = monitor.cleanup_caches()
        assert "candles_remaining" in result
        assert "indicators_remaining" in result
        assert "exchange_remaining" in result
        assert "bot_next_check" in result


# ===========================================================================
# Class: TestGetActiveBots
# ===========================================================================


class TestGetActiveBots:
    """Tests for MultiBotMonitor.get_active_bots()."""

    @pytest.mark.asyncio
    async def test_returns_active_bots_only(self, db_session):
        """Happy path: returns active bots plus inactive ones with open positions."""
        from app.models import Bot as BotModel
        active = BotModel(
            id=1, name="Active", user_id=1, strategy_type="macd_dca",
            is_active=True, strategy_config={}, check_interval_seconds=300,
            budget_percentage=10.0, product_ids=["ETH-BTC"],
        )
        inactive_no_pos = BotModel(
            id=2, name="Inactive", user_id=1, strategy_type="macd_dca",
            is_active=False, strategy_config={}, check_interval_seconds=300,
            budget_percentage=10.0, product_ids=["SOL-BTC"],
        )
        db_session.add_all([active, inactive_no_pos])
        await db_session.flush()

        monitor = MultiBotMonitor()
        result = await monitor.get_active_bots(db_session)
        ids = {b.id for b in result}
        assert 1 in ids
        assert 2 not in ids  # inactive with no positions is excluded

    @pytest.mark.asyncio
    async def test_empty_when_no_bots(self, db_session):
        """Edge case: no bots returns empty list."""
        monitor = MultiBotMonitor()
        result = await monitor.get_active_bots(db_session)
        assert result == []


# ===========================================================================
# Class: TestRebalancerFlags
# ===========================================================================


class TestRebalancerFlags:
    """Tests for is_rebalancer_gated() and is_rebalancer_bot_overweight()."""

    def test_is_rebalancer_gated_false_by_default(self):
        from app.multi_bot_monitor import is_rebalancer_gated
        # Use a bot_id unlikely to be set by prior tests
        assert is_rebalancer_gated(98765) is False

    def test_is_rebalancer_gated_true_when_added(self):
        import app.multi_bot_monitor as mod
        from app.multi_bot_monitor import is_rebalancer_gated
        mod._rebalancer_gated_bots.add(99)
        try:
            assert is_rebalancer_gated(99) is True
        finally:
            mod._rebalancer_gated_bots.discard(99)

    def test_is_rebalancer_bot_overweight_false_by_default(self):
        from app.multi_bot_monitor import is_rebalancer_bot_overweight
        assert is_rebalancer_bot_overweight(98765) is False

    def test_is_rebalancer_bot_overweight_true_when_added(self):
        import app.multi_bot_monitor as mod
        from app.multi_bot_monitor import is_rebalancer_bot_overweight
        mod._rebalancer_bot_overweight.add(77)
        try:
            assert is_rebalancer_bot_overweight(77) is True
        finally:
            mod._rebalancer_bot_overweight.discard(77)


# ===========================================================================
# Class: TestGetBotRebalancerGroup
# ===========================================================================


class TestGetBotRebalancerGroup:
    """Tests for _get_bot_rebalancer_group() caching + DB fetch."""

    @pytest.mark.asyncio
    async def test_fetches_from_db_on_cache_miss(self, db_session):
        """Happy path: DB query runs on cache miss."""
        import app.multi_bot_monitor as mod
        mod._rebalancer_group_cache.clear()

        from app.multi_bot_monitor import _get_bot_rebalancer_group

        # Mock the DB query path: return a fake group
        fake_group = MagicMock()
        fake_group.overweight_tolerance_pct = 7.0
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_group
        db = MagicMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await _get_bot_rebalancer_group(db, 42, "USD")
        assert result is fake_group
        # Cache is populated
        assert (42, "USD") in mod._rebalancer_group_cache

    @pytest.mark.asyncio
    async def test_returns_cached_when_fresh(self, db_session):
        """Edge case: cached value returned without DB hit."""
        import time
        import app.multi_bot_monitor as mod
        mod._rebalancer_group_cache.clear()

        cached_group = MagicMock()
        mod._rebalancer_group_cache[(42, "USD")] = (cached_group, time.monotonic())

        from app.multi_bot_monitor import _get_bot_rebalancer_group
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("should not be called"))

        result = await _get_bot_rebalancer_group(db, 42, "USD")
        assert result is cached_group
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_refetches_when_cache_expired(self, db_session):
        """Edge case: expired cache triggers re-fetch."""
        import app.multi_bot_monitor as mod
        mod._rebalancer_group_cache.clear()

        # Seed with a very old cache entry
        old_group = MagicMock()
        mod._rebalancer_group_cache[(42, "USD")] = (old_group, 0.0)  # monotonic=0 is ancient

        fresh_group = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fresh_group
        db = MagicMock()
        db.execute = AsyncMock(return_value=mock_result)

        from app.multi_bot_monitor import _get_bot_rebalancer_group
        result = await _get_bot_rebalancer_group(db, 42, "USD")
        assert result is fresh_group


# ===========================================================================
# Class: TestGetStatus
# ===========================================================================


class TestGetStatus:
    """Tests for MultiBotMonitor.get_status()."""

    @pytest.mark.asyncio
    async def test_get_status_returns_summary(self, db_session):
        """Happy path: returns running state and bot summary."""
        from app.models import Bot as BotModel
        active = BotModel(
            id=10, name="StatusBot", user_id=1, strategy_type="macd_dca",
            is_active=True, strategy_config={}, check_interval_seconds=300,
            budget_percentage=10.0, product_ids=["ETH-BTC"],
        )
        db_session.add(active)
        await db_session.flush()

        monitor = MultiBotMonitor()
        monitor.running = True

        with patch("app.multi_bot_monitor.async_session_maker") as mock_sm:
            mock_sm.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_sm.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await monitor.get_status()

        assert result["running"] is True
        assert result["active_bots"] >= 1
        assert any(b["name"] == "StatusBot" for b in result["bots"])

    @pytest.mark.asyncio
    async def test_get_status_catches_exception(self):
        """Failure case: DB exception does not propagate (returns falsy / error dict)."""
        monitor = MultiBotMonitor()

        broken_sm = MagicMock()
        broken_sm.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("DB down"))
        broken_sm.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.multi_bot_monitor.async_session_maker", broken_sm):
            # Should not raise
            result = await monitor.get_status()
        # Method returns None on exception (logger.error path); assert it didn't raise
        assert result is None or isinstance(result, dict)


# ===========================================================================
# Class: TestFilterPairsByCategoriesAdvanced
# ===========================================================================


class TestFilterPairsByCategoriesAdvanced:
    """Additional category filter tests covering user override precedence."""

    @pytest.mark.asyncio
    async def test_user_override_takes_precedence(self, db_session):
        """User override's category wins over the global entry's category."""
        pairs = ["DOGE-BTC"]

        # Global entry: MEME (should be filtered out under APPROVED-only allow)
        # User override: APPROVED (should be allowed)
        mock_global = MagicMock()
        mock_global.symbol = "DOGE"
        mock_global.reason = "[MEME] meme coin"
        mock_global.user_id = None

        mock_override = MagicMock()
        mock_override.symbol = "DOGE"
        mock_override.reason = "[APPROVED] I like it"
        mock_override.user_id = 42

        # First call returns global entries, second call returns overrides
        call_count = {"n": 0}

        def execute_side_effect(query):
            call_count["n"] += 1
            mock_result = MagicMock()
            if call_count["n"] == 1:
                mock_result.scalars.return_value.all.return_value = [mock_global]
            else:
                mock_result.scalars.return_value.all.return_value = [mock_override]
            return mock_result

        db_session.execute = AsyncMock(side_effect=execute_side_effect)

        result = await filter_pairs_by_allowed_categories(
            db_session, pairs, ["APPROVED"], user_id=42,
        )
        assert "DOGE-BTC" in result


# ===========================================================================
# Class: TestProcessSingleBot
# ===========================================================================


class TestProcessSingleBot:
    """Tests for MultiBotMonitor._process_single_bot() error handling."""

    @pytest.mark.asyncio
    async def test_skips_when_no_exchange_available(self, db_session):
        """No exchange client = early return, no error."""
        monitor = MultiBotMonitor()
        bot = _make_bot(account_id=99)

        from app.models import Bot as BotModel
        real_bot = BotModel(
            id=bot.id, name=bot.name, user_id=bot.user_id,
            strategy_type=bot.strategy_type, is_active=True,
            account_id=bot.account_id, strategy_config={}, check_interval_seconds=300,
            budget_percentage=10.0, product_ids=["ETH-BTC"],
        )
        db_session.add(real_bot)
        await db_session.flush()

        with patch.object(monitor, "get_exchange_for_bot", new_callable=AsyncMock, return_value=None), \
             patch("app.multi_bot_monitor.async_session_maker") as mock_sm:
            mock_sm.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_sm.return_value.__aexit__ = AsyncMock(return_value=False)
            # Should not raise despite missing exchange
            await monitor._process_single_bot(bot.id, bot.name, needs_ai_analysis=False)

    @pytest.mark.asyncio
    async def test_catches_exception_in_processing(self, db_session):
        """Any inner exception is caught — method does not raise."""
        monitor = MultiBotMonitor()
        bot = _make_bot(account_id=99)
        exchange = _make_exchange()

        with patch.object(monitor, "get_exchange_for_bot", new_callable=AsyncMock, return_value=exchange), \
             patch.object(monitor, "process_bot", new_callable=AsyncMock, side_effect=RuntimeError("boom")), \
             patch("app.multi_bot_monitor.async_session_maker") as mock_sm:
            mock_sm.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_sm.return_value.__aexit__ = AsyncMock(return_value=False)

            # DB has no matching bot row → local_bot is None → returns early gracefully
            # But we still want to test the try/except path. Insert a matching bot row.
            from app.models import Bot as BotModel
            real_bot = BotModel(
                id=bot.id, name=bot.name, user_id=bot.user_id,
                strategy_type=bot.strategy_type, is_active=True,
                account_id=bot.account_id, strategy_config={}, check_interval_seconds=300,
                budget_percentage=10.0, product_ids=["ETH-BTC"],
            )
            db_session.add(real_bot)
            await db_session.flush()

            # Should not raise
            await monitor._process_single_bot(bot.id, bot.name, needs_ai_analysis=True)


# ===========================================================================
# Class: TestMonitorLoop
# ===========================================================================


class TestMonitorLoop:
    """Tests for MultiBotMonitor.monitor_loop() — the top-level scheduler.

    Strategy: patch async_session_maker so the loop uses a mocked db,
    patch asyncio.sleep to a no-op so the 10s interval doesn't block
    the test, and stop the loop after one iteration by flipping
    self.running=False inside a side_effect on get_active_bots.
    """

    @staticmethod
    async def _noop_sleep(*_args, **_kwargs):
        """Stand-in for asyncio.sleep so the test doesn't wait 10s."""
        return None

    def _mock_session_maker(self, mock_sm, db_session):
        mock_sm.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_sm.return_value.__aexit__ = AsyncMock(return_value=False)

    @pytest.mark.asyncio
    async def test_empty_bot_list_logs_warning_and_continues(self, db_session):
        """Happy path: no active bots → logs warning, sleeps, exits cleanly
        when running flips to False."""
        monitor = MultiBotMonitor()
        monitor.running = True

        async def _get_bots_then_stop(*_args, **_kwargs):
            monitor.running = False
            return []

        with patch("app.multi_bot_monitor.async_session_maker") as mock_sm, \
             patch.object(monitor, "get_active_bots", side_effect=_get_bots_then_stop), \
             patch("app.multi_bot_monitor.asyncio.sleep", new=self._noop_sleep):
            self._mock_session_maker(mock_sm, db_session)
            await monitor.monitor_loop()

        assert monitor.running is False

    @pytest.mark.asyncio
    async def test_processes_due_bot_skips_not_due_bot(self, db_session):
        """Due bots (current_ts >= _bot_next_check) get scheduled; bots
        with future _bot_next_check are skipped with no _process_single_bot
        call for them."""
        monitor = MultiBotMonitor()
        monitor.running = True

        due_bot = _make_bot(bot_id=1, name="Due")
        not_due_bot = _make_bot(bot_id=2, name="NotDue")

        current_ts = int(utcnow().timestamp())
        monitor._bot_next_check = {
            due_bot.id: current_ts - 60,        # 60s overdue
            not_due_bot.id: current_ts + 600,   # 10min in the future
        }

        process_calls = []

        async def _track_process(bot_id, bot_name, needs_ai_analysis, **_kwargs):
            process_calls.append(bot_id)

        async def _get_bots_then_stop(*_args, **_kwargs):
            monitor.running = False
            return [due_bot, not_due_bot]

        with patch("app.multi_bot_monitor.async_session_maker") as mock_sm, \
             patch.object(monitor, "get_active_bots", side_effect=_get_bots_then_stop), \
             patch.object(monitor, "_process_single_bot", side_effect=_track_process), \
             patch("app.multi_bot_monitor.asyncio.sleep", new=self._noop_sleep):
            self._mock_session_maker(mock_sm, db_session)
            await monitor.monitor_loop()

        assert due_bot.id in process_calls
        assert not_due_bot.id not in process_calls

    @pytest.mark.asyncio
    async def test_parent_session_closes_before_processing_due_bots(self, db_session):
        """Trader scheduler should not hold the parent DB transaction while
        per-bot processing runs in isolated sessions."""
        monitor = MultiBotMonitor()
        monitor.running = True
        due_bot = _make_bot(bot_id=1, name="Due")
        session_exited = {"value": False}

        async def _get_bots_then_stop(*_args, **_kwargs):
            monitor.running = False
            return [due_bot]

        async def _track_process(bot_id, bot_name, needs_ai_analysis, **_kwargs):
            assert session_exited["value"] is True
            assert bot_id == due_bot.id
            assert bot_name == due_bot.name

        async def _exit(*_args, **_kwargs):
            session_exited["value"] = True
            return False

        with patch("app.multi_bot_monitor.async_session_maker") as mock_sm, \
             patch.object(monitor, "get_active_bots", side_effect=_get_bots_then_stop), \
             patch.object(monitor, "_process_single_bot", side_effect=_track_process), \
             patch("app.multi_bot_monitor.asyncio.sleep", new=self._noop_sleep):
            mock_sm.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_sm.return_value.__aexit__ = AsyncMock(side_effect=_exit)
            await monitor.monitor_loop()

        assert session_exited["value"] is True

    @pytest.mark.asyncio
    async def test_staggers_first_iteration_when_many_bots(self, db_session):
        """Edge case: first iteration with >5 bots and empty _bot_next_check
        staggers bots in groups of 5 every 2s to avoid DB contention."""
        monitor = MultiBotMonitor()
        monitor.running = True
        monitor._bot_next_check = {}  # empty = first iteration

        bots = [_make_bot(bot_id=i, name=f"B{i}") for i in range(1, 12)]  # 11 bots

        async def _get_bots_then_stop(*_args, **_kwargs):
            monitor.running = False
            return bots

        with patch("app.multi_bot_monitor.async_session_maker") as mock_sm, \
             patch.object(monitor, "get_active_bots", side_effect=_get_bots_then_stop), \
             patch.object(monitor, "_process_single_bot", new_callable=AsyncMock), \
             patch("app.multi_bot_monitor.asyncio.sleep", new=self._noop_sleep):
            self._mock_session_maker(mock_sm, db_session)
            await monitor.monitor_loop()

        # All 11 bots got scheduled entries
        assert len(monitor._bot_next_check) == 11
        # First 5 bots scheduled immediately (delay = 0), next 5 at +2s, 11th at +4s
        timestamps = sorted(monitor._bot_next_check.values())
        # Three distinct stagger groups: 0s, 2s, 4s offsets
        unique_offsets = len(set(t - timestamps[0] for t in timestamps))
        assert unique_offsets == 3

    @pytest.mark.asyncio
    async def test_adjusts_concurrency_when_capacity_changes(self, db_session):
        """Dynamic concurrency branch: when compute_dynamic_concurrency
        returns different values than cached, monitor rebuilds the
        bot semaphore and logs the adjustment."""
        monitor = MultiBotMonitor()
        monitor.running = True
        # Seed with known starting concurrency
        monitor._bot_concurrency = 3
        monitor._pair_concurrency = 5

        async def _get_bots_then_stop(*_args, **_kwargs):
            monitor.running = False
            return []

        with patch("app.multi_bot_monitor.async_session_maker") as mock_sm, \
             patch.object(monitor, "get_active_bots", side_effect=_get_bots_then_stop), \
             patch("app.multi_bot_monitor.compute_dynamic_concurrency", return_value=(7, 9)), \
             patch("app.multi_bot_monitor.asyncio.sleep", new=self._noop_sleep):
            self._mock_session_maker(mock_sm, db_session)
            await monitor.monitor_loop()

        assert monitor._bot_concurrency == 7
        assert monitor._pair_concurrency == 9
        # Semaphore rebuilt with new bot concurrency value
        assert isinstance(monitor._bot_semaphore, asyncio.Semaphore)

    @pytest.mark.asyncio
    async def test_scheduling_error_on_one_bot_does_not_break_loop(self, db_session):
        """Failure case: if per-bot scheduling logic throws, the bot is
        skipped (logged) but other bots still get processed and the loop
        continues normally."""
        monitor = MultiBotMonitor()
        monitor.running = True

        good_bot = _make_bot(bot_id=1, name="Good")
        bad_bot = _make_bot(bot_id=2, name="Bad")
        # Sabotage calculate_bot_check_interval by making strategy_config
        # non-dict — a TypeError will raise inside the scheduling try block.
        bad_bot.strategy_config = "not-a-dict"

        process_calls = []

        async def _track_process(bot_id, bot_name, needs_ai_analysis, **_kwargs):
            process_calls.append(bot_id)

        async def _get_bots_then_stop(*_args, **_kwargs):
            monitor.running = False
            return [good_bot, bad_bot]

        with patch("app.multi_bot_monitor.async_session_maker") as mock_sm, \
             patch.object(monitor, "get_active_bots", side_effect=_get_bots_then_stop), \
             patch.object(monitor, "_process_single_bot", side_effect=_track_process), \
             patch("app.multi_bot_monitor.asyncio.sleep", new=self._noop_sleep):
            self._mock_session_maker(mock_sm, db_session)
            await monitor.monitor_loop()

        assert good_bot.id in process_calls
        assert bad_bot.id not in process_calls

    @pytest.mark.asyncio
    async def test_prunes_caches_for_inactive_bots(self, db_session):
        """Cache hygiene: stale entries for bots/pairs no longer active
        are removed from _previous_indicators_cache, _bot_next_check,
        and _candle_cache each iteration."""
        monitor = MultiBotMonitor()
        monitor.running = True

        active_bot = _make_bot(bot_id=1, name="Active", product_ids=["ETH-BTC"])
        current_ts = int(utcnow().timestamp())

        # Seed caches with stale entries that no active bot references
        monitor._previous_indicators_cache = {
            (1, "ETH-BTC"): "keep-me",
            (99, "OLD-PAIR"): "drop-me",  # bot 99 not active
        }
        monitor._bot_next_check = {
            1: current_ts - 10,     # active bot, past due
            77: current_ts + 500,   # deleted bot
        }
        monitor._candle_cache = {
            "ETH-BTC:ONE_HOUR": "keep",
            "DEAD-PAIR:ONE_HOUR": "drop",
        }

        async def _get_bots_then_stop(*_args, **_kwargs):
            monitor.running = False
            return [active_bot]

        with patch("app.multi_bot_monitor.async_session_maker") as mock_sm, \
             patch.object(monitor, "get_active_bots", side_effect=_get_bots_then_stop), \
             patch.object(monitor, "_process_single_bot", new_callable=AsyncMock), \
             patch("app.multi_bot_monitor.asyncio.sleep", new=self._noop_sleep):
            self._mock_session_maker(mock_sm, db_session)
            await monitor.monitor_loop()

        # Stale entries dropped
        assert (99, "OLD-PAIR") not in monitor._previous_indicators_cache
        assert 77 not in monitor._bot_next_check
        assert "DEAD-PAIR:ONE_HOUR" not in monitor._candle_cache
        # Active entries retained
        assert (1, "ETH-BTC") in monitor._previous_indicators_cache
        assert "ETH-BTC:ONE_HOUR" in monitor._candle_cache

    @pytest.mark.asyncio
    async def test_outer_exception_logged_and_loop_continues(self, db_session):
        """Failure case: if async_session_maker itself raises, the outer
        try/except catches it, sleeps, and the loop continues. We flip
        running=False on the second call so the test terminates."""
        monitor = MultiBotMonitor()
        monitor.running = True
        call_count = {"n": 0}

        def _flaky_session_maker():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("database exploded")
            # Second iteration: flip running off and return a normal ctx mgr
            monitor.running = False
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=db_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        with patch("app.multi_bot_monitor.async_session_maker", side_effect=_flaky_session_maker), \
             patch.object(monitor, "get_active_bots", new_callable=AsyncMock, return_value=[]), \
             patch("app.multi_bot_monitor.asyncio.sleep", new=self._noop_sleep):
            await monitor.monitor_loop()

        # Reached iteration 2 → outer except branch worked
        assert call_count["n"] == 2


class TestGetActiveBotsCorruption:
    """get_active_bots() degrades gracefully on PostgreSQL data corruption.

    A corrupt block in one query must not blank out the whole monitor cycle:
    the other query's results still come through, and unrelated DB errors
    still propagate (fail fast).
    """

    def _ok_result(self, items):
        result = MagicMock()
        result.scalars.return_value.all.return_value = items
        return result

    def _corruption_error(self):
        from sqlalchemy.exc import OperationalError
        return OperationalError(
            "SELECT", {},
            Exception('could not read block 3 in file "base/1/2": Input/output error'),
        )

    @pytest.mark.asyncio
    async def test_corruption_on_active_query_returns_inactive_only(self, db_session):
        """Corruption on the active-bots query → active dropped, inactive still returned."""
        monitor = MultiBotMonitor(exchange=_make_exchange())
        inactive_bot = _make_bot(bot_id=2, is_active=False)

        db_session.execute = AsyncMock(side_effect=[
            self._corruption_error(),
            self._ok_result([inactive_bot]),
        ])

        bots = await monitor.get_active_bots(db_session)
        assert bots == [inactive_bot]

    @pytest.mark.asyncio
    async def test_corruption_on_both_queries_returns_empty(self, db_session):
        """Corruption on both queries → empty list, no crash."""
        monitor = MultiBotMonitor(exchange=_make_exchange())

        db_session.execute = AsyncMock(side_effect=[
            self._corruption_error(),
            self._corruption_error(),
        ])

        bots = await monitor.get_active_bots(db_session)
        assert bots == []

    @pytest.mark.asyncio
    async def test_non_corruption_db_error_propagates(self, db_session):
        """A non-corruption DB error must NOT be swallowed (fail fast)."""
        from sqlalchemy.exc import ProgrammingError

        monitor = MultiBotMonitor(exchange=_make_exchange())
        db_session.execute = AsyncMock(side_effect=ProgrammingError(
            "SELECT", {}, Exception("relation \"bots\" does not exist"),
        ))

        with pytest.raises(ProgrammingError):
            await monitor.get_active_bots(db_session)


class _AbortedTransactionSession:
    """Fake session mimicking PostgreSQL aborted-transaction semantics.

    On real PostgreSQL a failed statement aborts the transaction: every
    subsequent statement raises InFailedSQLTransaction until rollback().
    AsyncMock side-effect lists can't express that, so the earlier corruption
    tests would pass even without a rollback in get_active_bots().
    """

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)  # per-execute: an Exception to raise or a result
        self._aborted = False
        self.rollback_count = 0

    async def execute(self, *args, **kwargs):
        from sqlalchemy.exc import OperationalError
        if self._aborted:
            raise OperationalError(
                "SELECT", {},
                Exception("current transaction is aborted, commands ignored until end of transaction block"),
            )
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            self._aborted = True
            raise outcome
        return outcome

    async def rollback(self):
        self._aborted = False
        self.rollback_count += 1


class TestGetActiveBotsCorruptionRollback:
    """get_active_bots() must roll back after a corruption error.

    Without the rollback, the aborted PG transaction makes the second query
    (and everything else the monitor cycle does with the same session) fail
    with InFailedSQLTransaction — defeating the graceful degradation.
    """

    def _ok_result(self, items):
        result = MagicMock()
        result.scalars.return_value.all.return_value = items
        return result

    def _corruption_error(self):
        from sqlalchemy.exc import OperationalError
        return OperationalError(
            "SELECT", {},
            Exception('could not read block 3 in file "base/1/2": Input/output error'),
        )

    @pytest.mark.asyncio
    async def test_corruption_on_first_query_rolls_back_so_second_query_runs(self):
        """Corruption on the active-bots query → rollback → inactive query still succeeds."""
        monitor = MultiBotMonitor(exchange=_make_exchange())
        inactive_bot = _make_bot(bot_id=2, is_active=False)

        session = _AbortedTransactionSession([
            self._corruption_error(),
            self._ok_result([inactive_bot]),
        ])

        bots = await monitor.get_active_bots(session)
        assert bots == [inactive_bot]
        assert session.rollback_count == 1

    @pytest.mark.asyncio
    async def test_corruption_on_second_query_rolls_back_leaving_session_usable(self):
        """Corruption on the inactive query → rollback → caller's next query on the
        same session (the rest of the monitor cycle) still works."""
        monitor = MultiBotMonitor(exchange=_make_exchange())
        active_bot = _make_bot(bot_id=1, is_active=True)

        session = _AbortedTransactionSession([
            self._ok_result([active_bot]),
            self._corruption_error(),
            self._ok_result([]),  # the monitor cycle's next query
        ])

        bots = await monitor.get_active_bots(session)
        assert bots == [active_bot]

        follow_up = await session.execute("SELECT 1")
        assert follow_up.scalars().all() == []
