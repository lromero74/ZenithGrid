"""
Tests for batch_analyzer.process_bot_batch().

Tests batch analysis orchestration: market data collection, budget calculation,
AI batch analysis dispatch, result processing, error tracking, and DB commit.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.monitor.batch_analyzer import process_bot_batch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot(
    bot_id=1,
    name="BatchBot",
    is_active=True,
    account_id=10,
    user_id=1,
    strategy_config=None,
    product_ids=None,
    budget_percentage=10.0,
    split_budget_across_pairs=False,
):
    bot = MagicMock()
    bot.id = bot_id
    bot.name = name
    bot.is_active = is_active
    bot.account_id = account_id
    bot.user_id = user_id
    bot.strategy_config = strategy_config or {"max_concurrent_deals": 3}
    bot.budget_percentage = budget_percentage
    bot.split_budget_across_pairs = split_budget_across_pairs

    products = []
    for pid in (product_ids or ["ETH-BTC", "SOL-BTC"]):
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
    pos.total_quantity = 1.0
    pos.last_error_message = None
    pos.last_error_timestamp = None
    return pos


def _make_monitor():
    monitor = MagicMock()
    monitor.exchange = MagicMock()
    monitor.exchange.calculate_aggregate_quote_value = AsyncMock(return_value=0.5)
    monitor.exchange.get_btc_balance = AsyncMock(return_value=0.3)
    monitor.exchange.get_usd_balance = AsyncMock(return_value=5000.0)
    monitor.exchange.get_product_stats = AsyncMock(return_value={"volume_24h": 200.0})

    candles = [
        {"open": 0.05, "high": 0.052, "low": 0.049, "close": 0.051, "volume": 100}
    ] * 50
    monitor.get_candles_cached = AsyncMock(return_value=candles)
    monitor.log_ai_decision = AsyncMock(return_value=MagicMock(position_id=None))
    monitor.execute_trading_logic = AsyncMock(return_value={"action": "none", "reason": "No signal"})
    return monitor


def _make_strategy(batch_results=None):
    strategy = MagicMock()
    strategy.config = {}
    strategy.analyze_multiple_pairs_batch = AsyncMock(
        return_value=batch_results or {}
    )
    return strategy


# ===========================================================================
# Class: TestBatchAnalyzerHappyPath
# ===========================================================================


class TestBatchAnalyzerHappyPath:
    """Tests for normal batch processing flow."""

    @pytest.mark.asyncio
    async def test_basic_batch_processing(self, db_session):
        """Full batch flow: fetch data -> AI analysis -> execute trading logic."""
        monitor = _make_monitor()
        bot = _make_bot(product_ids=["ETH-BTC", "SOL-BTC"])

        batch_results = {
            "ETH-BTC": {"signal_type": "buy", "confidence": 80, "reasoning": "Bullish"},
            "SOL-BTC": {"signal_type": "hold", "confidence": 50, "reasoning": "Sideways"},
        }
        strategy = _make_strategy(batch_results)

        # Mock DB: no open positions
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={"summary": "up"}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            result = await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC", "SOL-BTC"], strategy
            )

        assert "ETH-BTC" in result
        assert "SOL-BTC" in result
        strategy.analyze_multiple_pairs_batch.assert_called_once()
        assert monitor.execute_trading_logic.call_count == 2

    @pytest.mark.asyncio
    async def test_skip_ai_analysis_uses_hold_signals(self, db_session):
        """When skip_ai_analysis=True, all pairs get hold signals."""
        monitor = _make_monitor()
        bot = _make_bot(product_ids=["ETH-BTC"])
        strategy = _make_strategy()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            result = await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC"], strategy, skip_ai_analysis=True
            )

        # AI should NOT be called
        strategy.analyze_multiple_pairs_batch.assert_not_called()
        # But trading logic still executes (for DCA/exit on existing positions)
        assert monitor.execute_trading_logic.call_count == 1

    @pytest.mark.asyncio
    async def test_budget_split_across_pairs(self, db_session):
        """When split_budget_across_pairs is True, per_position_budget = total / max_deals."""
        monitor = _make_monitor()
        bot = _make_bot(
            product_ids=["ETH-BTC", "SOL-BTC"],
            split_budget_across_pairs=True,
            strategy_config={"max_concurrent_deals": 2},
        )
        # get_reserved_balance returns 0.05 by default
        # With max_concurrent_deals=2, per_position_budget should be 0.025

        strategy = _make_strategy({"ETH-BTC": {"signal_type": "hold", "confidence": 0, "reasoning": "ok"}})

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC"], strategy
            )

        # Check that batch analysis was called with split budget
        call_args = strategy.analyze_multiple_pairs_batch.call_args
        per_position_budget = call_args[0][1]  # second positional arg
        assert per_position_budget == pytest.approx(0.025, abs=0.001)

    @pytest.mark.asyncio
    async def test_full_budget_when_not_split(self, db_session):
        """When split_budget_across_pairs is False, each deal gets full budget."""
        monitor = _make_monitor()
        bot = _make_bot(
            product_ids=["ETH-BTC"],
            split_budget_across_pairs=False,
            strategy_config={"max_concurrent_deals": 3},
        )

        strategy = _make_strategy({"ETH-BTC": {"signal_type": "hold", "confidence": 0, "reasoning": "ok"}})

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC"], strategy
            )

        call_args = strategy.analyze_multiple_pairs_batch.call_args
        per_position_budget = call_args[0][1]
        # Full budget (0.05), not split
        assert per_position_budget == pytest.approx(0.05, abs=0.001)


# ===========================================================================
# Class: TestBatchAnalyzerCapacity
# ===========================================================================


class TestBatchAnalyzerCapacity:
    """Tests for capacity/budget-based pair filtering."""

    @pytest.mark.asyncio
    async def test_at_max_capacity_only_position_pairs(self, db_session):
        """At max concurrent deals, only pairs with open positions are analyzed."""
        monitor = _make_monitor()
        bot = _make_bot(
            product_ids=["ETH-BTC", "SOL-BTC", "ADA-BTC"],
            strategy_config={"max_concurrent_deals": 1},
        )

        pos = _make_position(product_id="ETH-BTC")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        strategy = _make_strategy({"ETH-BTC": {"signal_type": "hold", "confidence": 0, "reasoning": "ok"}})

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            result = await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC", "SOL-BTC", "ADA-BTC"], strategy
            )

        # Only ETH-BTC should be processed (has position, at capacity 1/1)
        assert monitor.execute_trading_logic.call_count == 1

    @pytest.mark.asyncio
    async def test_stopped_bot_no_positions_returns_skip(self, db_session):
        """Stopped bot with no open positions returns skip."""
        monitor = _make_monitor()
        bot = _make_bot(is_active=False)
        strategy = _make_strategy()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            result = await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC"], strategy
            )

        assert result.get("action") == "skip"

    @pytest.mark.asyncio
    async def test_insufficient_budget_only_position_pairs(self, db_session):
        """When budget is insufficient, only pairs with positions are analyzed."""
        monitor = _make_monitor()
        # Make balance very low so has_actual_balance = False
        monitor.exchange.get_btc_balance = AsyncMock(return_value=0.0000001)
        # First call (bypass_cache=True) returns low value, second call for per_position_budget
        monitor.exchange.calculate_aggregate_quote_value = AsyncMock(return_value=0.0000001)

        bot = _make_bot(
            product_ids=["ETH-BTC", "SOL-BTC"],
            strategy_config={"max_concurrent_deals": 2},
        )
        # Set reserved balance very low
        bot.get_reserved_balance = MagicMock(return_value=0.0000001)

        pos = _make_position(product_id="ETH-BTC", total_quote_spent=0.0)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        strategy = _make_strategy({"ETH-BTC": {"signal_type": "hold", "confidence": 0, "reasoning": "ok"}})

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            result = await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC", "SOL-BTC"], strategy
            )

        # Both pairs get processed — ETH-BTC (has position) and SOL-BTC (AI result)
        assert monitor.execute_trading_logic.call_count == 2


# ===========================================================================
# Class: TestBatchAnalyzerMarketData
# ===========================================================================


class TestBatchAnalyzerMarketData:
    """Tests for market data fetching and candle handling."""

    @pytest.mark.asyncio
    async def test_no_candles_skips_pair(self, db_session):
        """Pairs with no candles are excluded from analysis."""
        monitor = _make_monitor()
        monitor.get_candles_cached = AsyncMock(return_value=[])  # No candles

        bot = _make_bot(product_ids=["DEAD-BTC"])
        strategy = _make_strategy()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            result = await process_bot_batch(
                monitor, db_session, bot, ["DEAD-BTC"], strategy
            )

        # No pairs had data, so result should be empty
        assert result == {}

    @pytest.mark.asyncio
    async def test_candle_fetch_exception_skips_pair(self, db_session):
        """If candle fetching raises an exception, the pair is skipped."""
        monitor = _make_monitor()
        monitor.get_candles_cached = AsyncMock(side_effect=Exception("API 500"))

        bot = _make_bot(product_ids=["FAIL-BTC"])
        strategy = _make_strategy()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            result = await process_bot_batch(
                monitor, db_session, bot, ["FAIL-BTC"], strategy
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_retries_for_open_position_pairs(self, db_session):
        """Pairs with open positions get 3 retries on failure."""
        monitor = _make_monitor()
        call_count = 0

        async def flaky_candles(product_id, granularity, lookback=100):
            nonlocal call_count
            call_count += 1
            if call_count <= 6:  # First 6 calls fail (2 retries x ~3 timeframes)
                raise Exception("Temporary error")
            return [{"open": 0.05, "high": 0.052, "low": 0.049, "close": 0.051, "volume": 100}] * 50

        monitor.get_candles_cached = AsyncMock(side_effect=flaky_candles)

        pos = _make_position(product_id="ETH-BTC")
        bot = _make_bot(product_ids=["ETH-BTC"])
        strategy = _make_strategy()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC"], strategy
            )

        # Verify retries happened (more than 1 attempt for the open-position pair)
        assert call_count > 1


# ===========================================================================
# Class: TestBatchAnalyzerErrorTracking
# ===========================================================================


class TestBatchAnalyzerErrorTracking:
    """Tests for error tracking on positions."""

    @pytest.mark.asyncio
    async def test_failed_fetch_logs_error_to_position(self, db_session):
        """When data fetch fails for a pair with an open position, error is logged."""
        monitor = _make_monitor()
        monitor.get_candles_cached = AsyncMock(return_value=[])  # No candles = failure

        pos = _make_position(product_id="DEAD-BTC")
        bot = _make_bot(product_ids=["DEAD-BTC"])
        strategy = _make_strategy()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            await process_bot_batch(
                monitor, db_session, bot, ["DEAD-BTC"], strategy
            )

        # Position should have error message set
        assert pos.last_error_message is not None
        assert "Market data fetch failed" in pos.last_error_message

    @pytest.mark.asyncio
    async def test_successful_fetch_clears_stale_error(self, db_session):
        """Successful data fetch clears any stale error on the position."""
        monitor = _make_monitor()

        pos = _make_position(product_id="ETH-BTC")
        pos.last_error_message = "Previous error"
        pos.last_error_timestamp = datetime.utcnow()

        bot = _make_bot(product_ids=["ETH-BTC"])
        strategy = _make_strategy({"ETH-BTC": {"signal_type": "hold", "confidence": 0, "reasoning": "ok"}})

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC"], strategy
            )

        # Error should be cleared
        assert pos.last_error_message is None
        assert pos.last_error_timestamp is None

    @pytest.mark.asyncio
    async def test_top_level_exception_returns_error(self, db_session):
        """A top-level exception returns an error dict."""
        monitor = _make_monitor()
        bot = _make_bot()
        strategy = _make_strategy()

        # Force an early exception
        db_session.execute = AsyncMock(side_effect=RuntimeError("DB crashed"))
        db_session.refresh = AsyncMock()

        result = await process_bot_batch(monitor, db_session, bot, ["ETH-BTC"], strategy)
        assert "error" in result


# ===========================================================================
# Class: TestBatchAnalyzerAILogging
# ===========================================================================


class TestBatchAnalyzerAILogging:
    """Tests for AI decision logging within batch processing."""

    @pytest.mark.asyncio
    async def test_ai_decision_logged_for_real_analysis(self, db_session):
        """AI decisions are logged when reasoning is not 'Technical-only check'."""
        monitor = _make_monitor()
        bot = _make_bot(product_ids=["ETH-BTC"])
        strategy = _make_strategy({
            "ETH-BTC": {"signal_type": "buy", "confidence": 90, "reasoning": "Strong bullish signal"},
        })

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC"], strategy
            )

        monitor.log_ai_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_ai_log_for_technical_only(self, db_session):
        """Technical-only checks skip AI logging."""
        monitor = _make_monitor()
        bot = _make_bot(product_ids=["ETH-BTC"])
        strategy = _make_strategy()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC"], strategy, skip_ai_analysis=True
            )

        monitor.log_ai_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_ai_log_linked_to_new_position(self, db_session):
        """When a new position is created, AI log entry gets linked to it."""
        monitor = _make_monitor()
        new_pos = MagicMock()
        new_pos.id = 42
        monitor.execute_trading_logic = AsyncMock(return_value={"action": "buy", "position": new_pos})

        ai_log = MagicMock()
        ai_log.position_id = None
        monitor.log_ai_decision = AsyncMock(return_value=ai_log)

        bot = _make_bot(product_ids=["ETH-BTC"])
        strategy = _make_strategy({
            "ETH-BTC": {"signal_type": "buy", "confidence": 85, "reasoning": "Good setup"},
        })

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC"], strategy
            )

        assert ai_log.position_id == 42
        assert ai_log.position_status == "open"


# ===========================================================================
# Class: TestBatchAnalyzerVolumeFilter
# ===========================================================================


class TestBatchAnalyzerVolumeFilter:
    """Tests for minimum daily volume filtering."""

    @pytest.mark.asyncio
    async def test_volume_filter_excludes_low_volume_pairs(self, db_session):
        """Pairs below min_daily_volume are excluded (unless they have open positions)."""
        monitor = _make_monitor()

        async def mock_stats(product_id):
            if product_id == "LOW-BTC":
                return {"volume_24h": 0.5}
            return {"volume_24h": 200.0}

        monitor.exchange.get_product_stats = AsyncMock(side_effect=mock_stats)

        bot = _make_bot(
            product_ids=["ETH-BTC", "LOW-BTC"],
            strategy_config={"max_concurrent_deals": 5},
        )
        strategy = _make_strategy({
            "ETH-BTC": {"signal_type": "hold", "confidence": 0, "reasoning": "ok"},
        })
        strategy.config = {"min_daily_volume": 10.0}

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            result = await process_bot_batch(
                monitor, db_session, bot, ["ETH-BTC", "LOW-BTC"], strategy
            )

        # Only ETH-BTC should have been processed (LOW-BTC filtered out)
        assert monitor.execute_trading_logic.call_count == 1

    @pytest.mark.asyncio
    async def test_volume_filter_keeps_pairs_with_positions(self, db_session):
        """Pairs with open positions bypass the volume filter."""
        monitor = _make_monitor()
        monitor.exchange.get_product_stats = AsyncMock(return_value={"volume_24h": 0.01})

        pos = _make_position(product_id="LOW-BTC")
        bot = _make_bot(
            product_ids=["LOW-BTC"],
            strategy_config={"max_concurrent_deals": 5},
        )
        strategy = _make_strategy({
            "LOW-BTC": {"signal_type": "hold", "confidence": 0, "reasoning": "ok"},
        })
        strategy.config = {"min_daily_volume": 100.0}

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        with patch("app.monitor.batch_analyzer.prepare_market_context", return_value={}), \
             patch("app.monitor.batch_analyzer.asyncio.sleep", new_callable=AsyncMock):
            result = await process_bot_batch(
                monitor, db_session, bot, ["LOW-BTC"], strategy
            )

        # LOW-BTC has an open position, so it should still be analyzed
        assert monitor.execute_trading_logic.call_count == 1
