"""
Tests for pair_processor.process_bot_pair().

Tests single pair processing: candle fetching, indicator calculation delegation,
signal generation, strategy dispatch, position handling, and DB commit behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.monitor.pair_processor import process_bot_pair


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot(
    bot_id=1,
    name="PairBot",
    strategy_type="macd_dca",
    is_active=True,
    account_id=10,
    user_id=1,
    strategy_config=None,
    split_budget_across_pairs=False,
):
    bot = MagicMock()
    bot.id = bot_id
    bot.name = name
    bot.strategy_type = strategy_type
    bot.is_active = is_active
    bot.account_id = account_id
    bot.user_id = user_id
    bot.strategy_config = strategy_config or {
        "max_concurrent_deals": 2,
        "max_safety_orders": 5,
        "timeframe": "FIVE_MINUTE",
        "max_simultaneous_same_pair": 1,
    }
    bot.split_budget_across_pairs = split_budget_across_pairs
    return bot


def _make_position(
    pos_id=1,
    bot_id=1,
    product_id="ETH-BTC",
    status="open",
    strategy_config_snapshot=None,
):
    pos = MagicMock()
    pos.id = pos_id
    pos.bot_id = bot_id
    pos.product_id = product_id
    pos.status = status
    pos.strategy_config_snapshot = strategy_config_snapshot
    pos.trades = []
    return pos


def _make_monitor():
    monitor = MagicMock()
    monitor.exchange = MagicMock()
    candles = [
        {"open": 0.05, "high": 0.052, "low": 0.049, "close": 0.051, "volume": 100}
    ] * 50
    monitor.get_candles_cached = AsyncMock(return_value=candles)
    monitor.exchange.get_current_price = AsyncMock(return_value=0.051)
    monitor.log_ai_decision = AsyncMock(return_value=MagicMock())
    monitor._previous_indicators_cache = {}
    return monitor


def _make_strategy(signal_data=None):
    strategy = MagicMock()
    strategy.analyze_signal = AsyncMock(
        return_value=signal_data or {
            "signal_type": "hold",
            "base_order_signal": False,
            "safety_order_signal": False,
            "take_profit_signal": False,
            "reasoning": "Technical analysis",
        }
    )
    strategy.config = {}
    return strategy


def _make_engine_result(action="none", reason="No signal"):
    return {"action": action, "reason": reason}


# ===========================================================================
# Class: TestPairProcessorHappyPath
# ===========================================================================


class TestPairProcessorHappyPath:
    """Tests for normal single pair processing flow."""

    @pytest.mark.asyncio
    async def test_no_position_processes_entry_signal(self, db_session):
        """Bot with no position processes base order entry."""
        monitor = _make_monitor()
        bot = _make_bot()
        strategy = _make_strategy()

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(
                return_value=_make_engine_result("buy", "Base order triggered")
            )
            MockEngine.return_value = mock_engine_inst

            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            result = await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        assert result["action"] == "buy"
        mock_engine_inst.process_signal.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_existing_position_processes_dca_and_exit(self, db_session):
        """Bot with existing position processes DCA/exit signals."""
        monitor = _make_monitor()
        bot = _make_bot()
        pos = _make_position(strategy_config_snapshot={"max_safety_orders": 5, "timeframe": "FIVE_MINUTE"})
        strategy = _make_strategy()

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[pos],
        ), patch(
            "app.trading_engine.position_manager.all_positions_exhausted_safety_orders",
            return_value=False,
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(
                return_value=_make_engine_result("sell", "Take profit hit")
            )
            MockEngine.return_value = mock_engine_inst

            db_session.commit = AsyncMock()

            result = await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        assert result["action"] == "sell"

    @pytest.mark.asyncio
    async def test_pre_analyzed_signal_skips_strategy_analysis(self, db_session):
        """When pre_analyzed_signal is provided, strategy.analyze_signal is NOT called."""
        monitor = _make_monitor()
        bot = _make_bot()
        strategy = _make_strategy()

        pre_signal = {"signal_type": "buy", "confidence": 90, "reasoning": "AI says buy"}

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(
                return_value=_make_engine_result("buy", "Entry triggered")
            )
            MockEngine.return_value = mock_engine_inst

            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            result = await process_bot_pair(
                monitor, db_session, bot, "ETH-BTC",
                pre_analyzed_signal=pre_signal,
                pair_data={"current_price": 0.051, "candles": [], "candles_by_timeframe": {}},
            )

        # Strategy's analyze_signal should NOT have been called
        strategy.analyze_signal.assert_not_called()
        assert result["action"] == "buy"


# ===========================================================================
# Class: TestPairProcessorPairData
# ===========================================================================


class TestPairProcessorPairData:
    """Tests for market data handling (candle fetching, pair_data usage)."""

    @pytest.mark.asyncio
    async def test_uses_provided_pair_data(self, db_session):
        """When pair_data is provided, no candle fetching occurs."""
        monitor = _make_monitor()
        bot = _make_bot()
        strategy = _make_strategy()

        pair_data = {
            "current_price": 0.060,
            "candles": [{"close": 0.060}],
            "candles_by_timeframe": {"FIVE_MINUTE": [{"close": 0.060}]},
        }

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(return_value=_make_engine_result())
            MockEngine.return_value = mock_engine_inst

            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            await process_bot_pair(
                monitor, db_session, bot, "ETH-BTC",
                pair_data=pair_data,
            )

        # Should not fetch candles since pair_data was provided
        monitor.get_candles_cached.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_candles_when_no_pair_data(self, db_session):
        """When no pair_data, candles are fetched from exchange."""
        monitor = _make_monitor()
        bot = _make_bot()
        strategy = _make_strategy()

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(return_value=_make_engine_result())
            MockEngine.return_value = mock_engine_inst

            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        monitor.get_candles_cached.assert_called()

    @pytest.mark.asyncio
    async def test_no_candles_returns_error(self, db_session):
        """When no candles available, returns error."""
        monitor = _make_monitor()
        monitor.get_candles_cached = AsyncMock(return_value=[])

        bot = _make_bot()
        strategy = _make_strategy()

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ):
            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            result = await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        assert "error" in result
        assert "No candles" in result["error"]


# ===========================================================================
# Class: TestPairProcessorStrategyConfig
# ===========================================================================


class TestPairProcessorStrategyConfig:
    """Tests for strategy config handling (frozen vs current, split budget)."""

    @pytest.mark.asyncio
    async def test_uses_frozen_config_from_position(self, db_session):
        """When position has strategy_config_snapshot, it's used instead of bot config."""
        monitor = _make_monitor()
        bot = _make_bot()
        frozen_config = {"max_safety_orders": 3, "timeframe": "ONE_HOUR", "max_simultaneous_same_pair": 1}
        pos = _make_position(strategy_config_snapshot=frozen_config)

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[pos],
        ), patch(
            "app.trading_engine.position_manager.all_positions_exhausted_safety_orders",
            return_value=False,
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=_make_strategy(),
        ) as mock_reg, patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(return_value=_make_engine_result())
            MockEngine.return_value = mock_engine_inst

            db_session.commit = AsyncMock()

            await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        # StrategyRegistry.get_strategy should be called with frozen config (+ user_id)
        call_args = mock_reg.call_args[0]
        passed_config = call_args[1]
        assert passed_config["max_safety_orders"] == 3

    @pytest.mark.asyncio
    async def test_splits_budget_across_deals(self, db_session):
        """When split_budget_across_pairs is True, percentage params are divided."""
        monitor = _make_monitor()
        bot = _make_bot(
            split_budget_across_pairs=True,
            strategy_config={
                "max_concurrent_deals": 2,
                "max_safety_orders": 5,
                "timeframe": "FIVE_MINUTE",
                "base_order_percentage": 10.0,
                "safety_order_percentage": 5.0,
                "max_btc_usage_percentage": 20.0,
                "max_simultaneous_same_pair": 1,
            },
        )

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],  # No position -> uses current bot config
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=_make_strategy(),
        ) as mock_reg, patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(return_value=_make_engine_result())
            MockEngine.return_value = mock_engine_inst

            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        # The config passed to StrategyRegistry should have split percentages
        call_args = mock_reg.call_args[0]
        passed_config = call_args[1]
        assert passed_config["base_order_percentage"] == pytest.approx(5.0)
        assert passed_config["safety_order_percentage"] == pytest.approx(2.5)
        assert passed_config["max_btc_usage_percentage"] == pytest.approx(10.0)

    @pytest.mark.asyncio
    async def test_unknown_strategy_returns_error(self, db_session):
        """When strategy_type is unknown, returns error dict."""
        monitor = _make_monitor()
        bot = _make_bot(strategy_type="nonexistent_strategy")

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            side_effect=ValueError("Unknown strategy: nonexistent_strategy"),
        ):
            result = await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        assert "error" in result


# ===========================================================================
# Class: TestPairProcessorCommitBehavior
# ===========================================================================


class TestPairProcessorCommitBehavior:
    """Tests for commit parameter behavior."""

    @pytest.mark.asyncio
    async def test_commit_true_commits_session(self, db_session):
        """Default commit=True commits the DB session."""
        monitor = _make_monitor()
        bot = _make_bot()

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=_make_strategy(),
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(return_value=_make_engine_result())
            MockEngine.return_value = mock_engine_inst

            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            await process_bot_pair(monitor, db_session, bot, "ETH-BTC", commit=True)

        db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_commit_false_does_not_commit(self, db_session):
        """commit=False skips the final DB commit (for batch mode)."""
        monitor = _make_monitor()
        bot = _make_bot()

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=_make_strategy(),
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(return_value=_make_engine_result())
            MockEngine.return_value = mock_engine_inst

            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            await process_bot_pair(
                monitor, db_session, bot, "ETH-BTC",
                pre_analyzed_signal={"signal_type": "hold"},
                pair_data={"current_price": 0.05, "candles": [{"close": 0.05}], "candles_by_timeframe": {}},
                commit=False,
            )

        db_session.commit.assert_not_called()


# ===========================================================================
# Class: TestPairProcessorIndicatorCache
# ===========================================================================


class TestPairProcessorIndicatorCache:
    """Tests for previous_indicators_cache update logic."""

    @pytest.mark.asyncio
    async def test_updates_indicator_cache(self, db_session):
        """When signal_data contains indicators, cache is updated."""
        monitor = _make_monitor()
        bot = _make_bot()
        strategy = _make_strategy({
            "signal_type": "hold",
            "base_order_signal": False,
            "safety_order_signal": False,
            "take_profit_signal": False,
            "indicators": {"rsi": 55.0, "macd_histogram": 0.002},
        })

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(return_value=_make_engine_result())
            MockEngine.return_value = mock_engine_inst

            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        # Check that the cache was updated
        cache_key = (bot.id, "ETH-BTC")
        assert cache_key in monitor._previous_indicators_cache
        assert monitor._previous_indicators_cache[cache_key]["rsi"] == 55.0


# ===========================================================================
# Class: TestPairProcessorSyntheticPctThreshold
# ===========================================================================


class TestPairProcessorSyntheticPctThreshold:
    """Tests for max_synthetic_pct gap-fill threshold."""

    @pytest.mark.asyncio
    async def test_skips_pair_when_gap_fill_too_high(self, db_session):
        """When gap_fill_pct exceeds max_synthetic_pct, pair is skipped."""
        monitor = _make_monitor()
        bot = _make_bot(strategy_config={
            "max_concurrent_deals": 2,
            "max_safety_orders": 5,
            "timeframe": "FIVE_MINUTE",
            "max_synthetic_pct": 30.0,
            "max_simultaneous_same_pair": 1,
        })
        strategy = _make_strategy({
            "signal_type": "hold",
            "base_order_signal": False,
            "safety_order_signal": False,
            "take_profit_signal": False,
            "indicators": {"gap_fill_pct": 50.0},  # 50% > 30% threshold
        })

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ):
            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            result = await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        assert result["action"] == "none"
        assert "Synthetic candle" in result["reason"]

    @pytest.mark.asyncio
    async def test_processes_pair_when_gap_fill_below_threshold(self, db_session):
        """When gap_fill_pct is below max_synthetic_pct, pair is processed normally."""
        monitor = _make_monitor()
        bot = _make_bot(strategy_config={
            "max_concurrent_deals": 2,
            "max_safety_orders": 5,
            "timeframe": "FIVE_MINUTE",
            "max_synthetic_pct": 50.0,
            "max_simultaneous_same_pair": 1,
        })
        strategy = _make_strategy({
            "signal_type": "hold",
            "base_order_signal": False,
            "safety_order_signal": False,
            "take_profit_signal": False,
            "indicators": {"gap_fill_pct": 20.0},  # 20% < 50% threshold
        })

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(
                return_value=_make_engine_result("none", "No signal")
            )
            MockEngine.return_value = mock_engine_inst

            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            result = await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        assert result["action"] == "none"
        assert "Synthetic candle" not in result.get("reason", "")


# ===========================================================================
# Class: TestPairProcessorSimultaneousDeals
# ===========================================================================


class TestPairProcessorSimultaneousDeals:
    """Tests for simultaneous same-pair deal opening."""

    @pytest.mark.asyncio
    async def test_opens_simultaneous_deal_when_sos_exhausted(self, db_session):
        """When all existing positions exhausted SOs, new simultaneous deal is evaluated."""
        monitor = _make_monitor()
        bot = _make_bot(strategy_config={
            "max_concurrent_deals": 2,
            "max_safety_orders": 2,
            "timeframe": "FIVE_MINUTE",
            "max_simultaneous_same_pair": 3,
        })
        pos = _make_position(strategy_config_snapshot={
            "max_safety_orders": 2, "timeframe": "FIVE_MINUTE", "max_simultaneous_same_pair": 3
        })
        strategy = _make_strategy({
            "signal_type": "hold",
            "base_order_signal": False,
            "safety_order_signal": False,
            "take_profit_signal": False,
        })

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[pos],
        ), patch(
            "app.trading_engine.position_manager.all_positions_exhausted_safety_orders",
            return_value=True,
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            engine_instances = []

            def make_engine(*args, **kwargs):
                inst = MagicMock()
                inst.process_signal = AsyncMock(return_value=_make_engine_result())
                engine_instances.append(inst)
                return inst

            MockEngine.side_effect = make_engine

            db_session.commit = AsyncMock()

            await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        # Should create 2 engines: one for existing position, one for new simultaneous deal
        assert len(engine_instances) == 2

    @pytest.mark.asyncio
    async def test_no_simultaneous_deal_when_sos_not_exhausted(self, db_session):
        """When SOs not exhausted, no simultaneous deal is opened."""
        monitor = _make_monitor()
        bot = _make_bot(strategy_config={
            "max_concurrent_deals": 2,
            "max_safety_orders": 5,
            "timeframe": "FIVE_MINUTE",
            "max_simultaneous_same_pair": 3,
        })
        pos = _make_position(strategy_config_snapshot={
            "max_safety_orders": 5, "timeframe": "FIVE_MINUTE", "max_simultaneous_same_pair": 3
        })
        strategy = _make_strategy()

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[pos],
        ), patch(
            "app.trading_engine.position_manager.all_positions_exhausted_safety_orders",
            return_value=False,  # Not exhausted
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_inst = MagicMock()
            mock_inst.process_signal = AsyncMock(return_value=_make_engine_result())
            MockEngine.return_value = mock_inst

            db_session.commit = AsyncMock()

            await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        # Only 1 engine: for the existing position. No simultaneous deal.
        assert MockEngine.call_count == 1


# ===========================================================================
# Class: TestPairProcessorErrorHandling
# ===========================================================================


class TestPairProcessorErrorHandling:
    """Tests for exception handling in process_bot_pair."""

    @pytest.mark.asyncio
    async def test_exception_returns_error_dict(self, db_session):
        """Top-level exceptions are caught and returned as error dict."""
        monitor = _make_monitor()
        bot = _make_bot()

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection lost"),
        ):
            result = await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        assert "error" in result
        assert "DB connection lost" in result["error"]

    @pytest.mark.asyncio
    async def test_null_signal_returns_no_signal(self, db_session):
        """When strategy returns None signal, result is 'no signal'."""
        monitor = _make_monitor()
        bot = _make_bot()
        strategy = MagicMock()
        strategy.analyze_signal = AsyncMock(return_value=None)

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ):
            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            result = await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        assert result["action"] == "none"
        assert "No signal" in result["reason"]


# ===========================================================================
# Class: TestPairProcessorAILogging
# ===========================================================================


class TestPairProcessorAILogging:
    """Tests for AI decision logging in pair processing."""

    @pytest.mark.asyncio
    async def test_logs_ai_decision_with_reasoning(self, db_session):
        """AI decisions with reasoning are logged to database."""
        monitor = _make_monitor()
        bot = _make_bot()
        strategy = _make_strategy({
            "signal_type": "buy",
            "confidence": 85,
            "reasoning": "Strong bullish divergence",
            "base_order_signal": True,
            "safety_order_signal": False,
            "take_profit_signal": False,
        })

        mock_pos_result = MagicMock()
        mock_pos_result.scalars.return_value.all.return_value = []

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(return_value=_make_engine_result())
            MockEngine.return_value = mock_engine_inst

            db_session.execute = AsyncMock(return_value=mock_pos_result)
            db_session.commit = AsyncMock()

            await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        monitor.log_ai_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_ai_log_for_technical_only(self, db_session):
        """Technical-only check (reasoning == 'Technical-only check (no AI)') skips AI log."""
        monitor = _make_monitor()
        bot = _make_bot()
        strategy = _make_strategy({
            "signal_type": "hold",
            "reasoning": "Technical-only check (no AI)",
            "base_order_signal": False,
            "safety_order_signal": False,
            "take_profit_signal": False,
        })

        with patch(
            "app.trading_engine.position_manager.get_active_positions_for_pair",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.monitor.pair_processor.StrategyRegistry.get_strategy",
            return_value=strategy,
        ), patch(
            "app.monitor.pair_processor.StrategyTradingEngine",
        ) as MockEngine:
            mock_engine_inst = MagicMock()
            mock_engine_inst.process_signal = AsyncMock(return_value=_make_engine_result())
            MockEngine.return_value = mock_engine_inst

            db_session.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            db_session.commit = AsyncMock()

            await process_bot_pair(monitor, db_session, bot, "ETH-BTC")

        monitor.log_ai_decision.assert_not_called()
