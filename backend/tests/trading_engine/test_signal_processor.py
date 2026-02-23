"""
Tests for backend/app/trading_engine/signal_processor.py

Covers:
- _is_duplicate_failed_order: dedup logic for failed order logging
- _calculate_market_context_with_indicators: indicator calculation from candles
- process_signal: the main orchestrator (buy/sell/hold decisions)
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.trading_engine.signal_processor import (
    _is_duplicate_failed_order,
    _calculate_market_context_with_indicators,
    process_signal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot(**overrides):
    bot = MagicMock()
    bot.id = overrides.get("id", 1)
    bot.user_id = overrides.get("user_id", 10)
    bot.is_active = overrides.get("is_active", True)
    bot.strategy_type = overrides.get("strategy_type", "macd_dca")
    bot.strategy_config = overrides.get("strategy_config", {"max_concurrent_deals": 1})
    bot.budget_percentage = overrides.get("budget_percentage", 0.0)
    bot.split_budget_across_pairs = overrides.get("split_budget_across_pairs", False)
    bot.reserved_btc_balance = overrides.get("reserved_btc_balance", 0.0)
    bot.reserved_usd_balance = overrides.get("reserved_usd_balance", 0.0)
    bot.last_signal_check = overrides.get("last_signal_check", None)
    bot.market_type = overrides.get("market_type", "spot")

    def get_reserved_balance(aggregate_value=None):
        if bot.budget_percentage > 0 and aggregate_value is not None:
            return aggregate_value * (bot.budget_percentage / 100.0)
        return bot.reserved_usd_balance or bot.reserved_btc_balance

    bot.get_reserved_balance = MagicMock(side_effect=get_reserved_balance)
    return bot


def _make_position(**overrides):
    pos = MagicMock()
    pos.id = overrides.get("id", 100)
    pos.user_id = overrides.get("user_id", 10)
    pos.product_id = overrides.get("product_id", "ETH-USD")
    pos.bot_id = overrides.get("bot_id", 1)
    pos.status = overrides.get("status", "open")
    pos.direction = overrides.get("direction", "long")
    pos.total_quote_spent = overrides.get("total_quote_spent", 1000.0)
    pos.total_base_acquired = overrides.get("total_base_acquired", 0.5)
    pos.average_buy_price = overrides.get("average_buy_price", 2000.0)
    pos.strategy_config_snapshot = overrides.get("strategy_config_snapshot", {})
    pos.closing_via_limit = overrides.get("closing_via_limit", False)
    pos.limit_close_order_id = overrides.get("limit_close_order_id", None)
    pos.max_quote_allowed = overrides.get("max_quote_allowed", None)
    pos.short_total_sold_base = overrides.get("short_total_sold_base", None)
    pos.short_total_sold_quote = overrides.get("short_total_sold_quote", None)
    pos.short_average_sell_price = overrides.get("short_average_sell_price", None)
    pos.last_error_message = overrides.get("last_error_message", None)
    pos.last_error_timestamp = overrides.get("last_error_timestamp", None)
    return pos


def _make_exchange(**overrides):
    exchange = AsyncMock()
    exchange.get_btc_usd_price = AsyncMock(return_value=50000.0)
    exchange.get_ticker = AsyncMock(return_value={
        "best_bid": "2999.0",
        "best_ask": "3001.0",
    })
    exchange.calculate_aggregate_usd_value = AsyncMock(return_value=10000.0)
    exchange.calculate_aggregate_btc_value = AsyncMock(return_value=1.0)
    for k, v in overrides.items():
        setattr(exchange, k, v)
    return exchange


def _make_trading_client(**overrides):
    tc = AsyncMock()
    tc.get_quote_balance = AsyncMock(return_value=5000.0)
    tc.buy = AsyncMock(return_value={
        "success_response": {"order_id": "order-abc-123"},
        "error_response": {},
    })
    tc.invalidate_balance_cache = AsyncMock()
    for k, v in overrides.items():
        setattr(tc, k, v)
    return tc


def _make_strategy(**overrides):
    strategy = AsyncMock()
    strategy.config = overrides.get("config", {"max_concurrent_deals": 1})
    strategy.analyze_signal = AsyncMock(return_value={
        "signal_type": "buy",
        "confidence": 80,
        "direction": "long",
        "_already_logged": True,
    })
    strategy.should_buy = AsyncMock(return_value=(True, 100.0, "Signal strong"))
    strategy.should_sell = AsyncMock(return_value=(False, "Not at target"))
    strategy.should_sell_failsafe = AsyncMock(return_value=(False, "Not triggered"))
    for k, v in overrides.items():
        setattr(strategy, k, v)
    return strategy


def _make_db():
    """Create a mock DB session that supports SQLAlchemy-style query chains.

    process_signal does things like:
        result = await db.execute(query)
        open_positions = result.scalars().all()

    We need the mock chain to return sensible defaults.
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    # Make db.execute() return a mock whose .scalars().all() returns []
    # and .scalars().first() returns None
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    scalars_mock.first.return_value = None

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    db.execute = AsyncMock(return_value=result_mock)
    return db


def _make_candles(count=30, base_price=3000.0):
    """Generate minimal candle data for tests."""
    return [
        {
            "open": base_price + i,
            "high": base_price + i + 10,
            "low": base_price + i - 10,
            "close": base_price + i + 5,
            "volume": 100.0,
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Common patches
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_externals():
    """Patch external dependencies for all signal processor tests."""
    with (
        patch("app.trading_engine.signal_processor.log_order_to_history", new_callable=AsyncMock),
        patch("app.trading_engine.signal_processor.save_ai_log", new_callable=AsyncMock),
        patch("app.trading_engine.signal_processor.log_indicator_evaluation", new_callable=AsyncMock),
    ):
        yield


# ===========================================================================
# _is_duplicate_failed_order
# ===========================================================================


class TestIsDuplicateFailedOrder:
    """Tests for _is_duplicate_failed_order() — dedup logic for failed order logging."""

    @pytest.mark.asyncio
    async def test_no_previous_error_returns_false(self, db_session):
        """Happy path: no previous failed orders means not a duplicate."""
        result = await _is_duplicate_failed_order(
            db_session, bot_id=1, product_id="ETH-USD",
            trade_type="initial", error_message="Insufficient funds",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_same_error_returns_true(self, db_session):
        """Edge case: same error message as last failed order is a duplicate."""
        from app.models import OrderHistory

        # Insert a previous failed order
        order = OrderHistory(
            bot_id=1,
            product_id="ETH-USD",
            side="BUY",
            order_type="MARKET",
            trade_type="initial",
            status="failed",
            error_message="Insufficient funds",
            quote_amount=100.0,
            price=3000.0,
            timestamp=datetime.utcnow(),
        )
        db_session.add(order)
        await db_session.commit()

        result = await _is_duplicate_failed_order(
            db_session, bot_id=1, product_id="ETH-USD",
            trade_type="initial", error_message="Insufficient funds",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_different_error_returns_false(self, db_session):
        """Edge case: different error message is not a duplicate."""
        from app.models import OrderHistory

        order = OrderHistory(
            bot_id=1,
            product_id="ETH-USD",
            side="BUY",
            order_type="MARKET",
            trade_type="initial",
            status="failed",
            error_message="Insufficient funds",
            quote_amount=100.0,
            price=3000.0,
            timestamp=datetime.utcnow(),
        )
        db_session.add(order)
        await db_session.commit()

        result = await _is_duplicate_failed_order(
            db_session, bot_id=1, product_id="ETH-USD",
            trade_type="initial", error_message="Order too small",  # Different error
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_with_position_filter(self, db_session):
        """Edge case: position-specific dedup only matches same position."""
        from app.models import OrderHistory

        pos = _make_position(id=200)

        order = OrderHistory(
            bot_id=1,
            product_id="ETH-USD",
            position_id=200,
            side="BUY",
            order_type="MARKET",
            trade_type="safety_order",
            status="failed",
            error_message="Budget exhausted",
            quote_amount=50.0,
            price=3000.0,
            timestamp=datetime.utcnow(),
        )
        db_session.add(order)
        await db_session.commit()

        # Same position, same error = duplicate
        result = await _is_duplicate_failed_order(
            db_session, bot_id=1, product_id="ETH-USD",
            trade_type="safety_order", error_message="Budget exhausted",
            position=pos,
        )
        assert result is True


# ===========================================================================
# _calculate_market_context_with_indicators
# ===========================================================================


class TestCalculateMarketContext:
    """Tests for _calculate_market_context_with_indicators()."""

    def test_empty_candles_returns_defaults(self):
        """Edge case: empty candle list returns neutral defaults."""
        result = _calculate_market_context_with_indicators([], 3000.0)

        assert result["price"] == 3000.0
        assert result["rsi"] == 50.0
        assert result["macd"] == 0.0
        assert result["bb_percent"] == 50.0

    def test_insufficient_candles_uses_defaults_for_timeframe(self):
        """Edge case: fewer than 20 candles sets defaults for that timeframe."""
        candles = _make_candles(count=10)  # not enough

        result = _calculate_market_context_with_indicators(candles, 3000.0)

        assert "FIVE_MINUTE_bb_percent" in result
        assert result["FIVE_MINUTE_bb_percent"] == 50.0

    def test_sufficient_candles_calculates_indicators(self):
        """Happy path: enough candles produces real indicator values."""
        candles = _make_candles(count=50, base_price=100.0)

        result = _calculate_market_context_with_indicators(candles, 150.0)

        # BB% should be computed (not default 50.0 necessarily, since price is above all candles)
        assert "FIVE_MINUTE_bb_percent" in result
        assert "FIVE_MINUTE_bb_upper_20_2" in result
        assert "FIVE_MINUTE_bb_lower_20_2" in result
        # RSI and MACD should also be calculated
        assert result["rsi"] != 50.0 or result["macd"] != 0.0  # at least one should change

    def test_multi_timeframe_support(self):
        """Happy path: indicators calculated for each timeframe."""
        candles_by_tf = {
            "THREE_MINUTE": _make_candles(count=30, base_price=100.0),
            "FIFTEEN_MINUTE": _make_candles(count=30, base_price=100.0),
        }

        result = _calculate_market_context_with_indicators([], 150.0, candles_by_tf)

        assert "THREE_MINUTE_bb_percent" in result
        assert "FIFTEEN_MINUTE_bb_percent" in result

    def test_exception_in_calculation_uses_defaults(self):
        """Failure: exception during indicator calculation falls back to defaults."""
        # Candles with invalid data
        bad_candles = [{"close": "not_a_number"} for _ in range(25)]

        result = _calculate_market_context_with_indicators(
            bad_candles, 3000.0, {"BAD_TF": bad_candles}
        )

        assert result["BAD_TF_bb_percent"] == 50.0


# ===========================================================================
# process_signal — orchestrator tests
# ===========================================================================


class TestProcessSignal:
    """Tests for process_signal() — the main trading decision orchestrator."""

    @pytest.mark.asyncio
    async def test_no_signal_returns_none_action(self):
        """Edge case: strategy returns no signal -> no action."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        strategy = _make_strategy()
        strategy.analyze_signal = AsyncMock(return_value=None)

        with patch(
            "app.trading_engine.signal_processor.get_active_position",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
            )

        assert result["action"] == "none"
        assert "No signal" in result["reason"]

    @pytest.mark.asyncio
    async def test_bot_inactive_no_position_skips_buy(self):
        """Edge case: inactive bot with no position does not buy."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(is_active=False)
        strategy = _make_strategy()

        with patch(
            "app.trading_engine.signal_processor.get_active_position",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
            )

        assert result["action"] == "none"

    @pytest.mark.asyncio
    async def test_buy_decision_with_new_position(self):
        """Happy path: buy signal with no existing position creates position and trade."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(reserved_usd_balance=5000.0)
        strategy = _make_strategy()

        mock_position = _make_position()
        mock_trade = MagicMock()
        mock_trade.id = 1
        mock_trade.order_id = "order-123"

        with (
            patch(
                "app.trading_engine.signal_processor.get_active_position",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.trading_engine.signal_processor.get_open_positions_count",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "app.trading_engine.signal_processor.create_position",
                new_callable=AsyncMock,
                return_value=mock_position,
            ),
            patch(
                "app.trading_engine.signal_processor.execute_buy",
                new_callable=AsyncMock,
                return_value=mock_trade,
            ),
        ):
            result = await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
            )

        assert result["action"] == "buy"
        assert result["trade"] == mock_trade

    @pytest.mark.asyncio
    async def test_max_concurrent_deals_blocks_new_position(self):
        """Edge case: max concurrent deals reached blocks new buys."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(
            reserved_usd_balance=5000.0,
            strategy_config={"max_concurrent_deals": 2},
        )
        strategy = _make_strategy(config={"max_concurrent_deals": 2})
        # strategy.should_buy is never called because max deals check happens first

        with (
            patch(
                "app.trading_engine.signal_processor.get_active_position",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.trading_engine.signal_processor.get_open_positions_count",
                new_callable=AsyncMock,
                return_value=2,  # already at max
            ),
        ):
            result = await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
            )

        # No buy action because max deals reached
        assert result["action"] != "buy"

    @pytest.mark.asyncio
    async def test_sell_decision_for_existing_position(self):
        """Happy path: sell signal for existing position executes sell."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(reserved_usd_balance=5000.0)
        strategy = _make_strategy()
        strategy.should_buy = AsyncMock(return_value=(False, 0, "No buy"))
        strategy.should_sell = AsyncMock(return_value=(True, "Take profit hit"))

        existing_position = _make_position()
        mock_trade = MagicMock()
        mock_trade.id = 2

        with (
            patch(
                "app.trading_engine.signal_processor.get_active_position",
                new_callable=AsyncMock,
                return_value=existing_position,
            ),
            patch(
                "app.trading_engine.signal_processor.execute_sell",
                new_callable=AsyncMock,
                return_value=(mock_trade, 150.0, 15.0),
            ),
        ):
            result = await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
            )

        assert result["action"] == "sell"
        assert result["profit_quote"] == 150.0
        assert result["profit_percentage"] == 15.0

    @pytest.mark.asyncio
    async def test_hold_when_sell_not_triggered(self):
        """Happy path: position exists but sell not triggered -> hold."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(reserved_usd_balance=5000.0)
        strategy = _make_strategy()
        strategy.should_buy = AsyncMock(return_value=(False, 0, "No buy signal"))
        strategy.should_sell = AsyncMock(return_value=(False, "Not at target yet"))

        existing_position = _make_position()

        with patch(
            "app.trading_engine.signal_processor.get_active_position",
            new_callable=AsyncMock,
            return_value=existing_position,
        ):
            result = await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
            )

        assert result["action"] == "hold"
        assert "Not at target" in result["reason"]

    @pytest.mark.asyncio
    async def test_limit_sell_returns_limit_close_pending(self):
        """Edge case: limit sell places order, returns limit_close_pending."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(reserved_usd_balance=5000.0)
        strategy = _make_strategy()
        strategy.should_buy = AsyncMock(return_value=(False, 0, "No buy"))
        strategy.should_sell = AsyncMock(return_value=(True, "Conditions met"))

        existing_position = _make_position()

        with (
            patch(
                "app.trading_engine.signal_processor.get_active_position",
                new_callable=AsyncMock,
                return_value=existing_position,
            ),
            patch(
                "app.trading_engine.signal_processor.execute_sell",
                new_callable=AsyncMock,
                return_value=(None, 0.0, 0.0),  # None trade = limit order placed
            ),
        ):
            result = await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
            )

        assert result["action"] == "limit_close_pending"

    @pytest.mark.asyncio
    async def test_buy_failure_marks_new_position_as_failed(self):
        """Failure: buy fails for new position -> position marked as failed."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(reserved_usd_balance=5000.0)
        strategy = _make_strategy()

        mock_position = _make_position()

        with (
            patch(
                "app.trading_engine.signal_processor.get_active_position",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.trading_engine.signal_processor.get_open_positions_count",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "app.trading_engine.signal_processor.create_position",
                new_callable=AsyncMock,
                return_value=mock_position,
            ),
            patch(
                "app.trading_engine.signal_processor.execute_buy",
                new_callable=AsyncMock,
                side_effect=ValueError("Exchange rejected order"),
            ),
        ):
            result = await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
            )

        assert result["action"] == "none"
        assert "Buy failed" in result["reason"]
        assert mock_position.status == "failed"

    @pytest.mark.asyncio
    async def test_position_override_used(self):
        """Edge case: position_override bypasses get_active_position lookup."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(reserved_usd_balance=5000.0)
        strategy = _make_strategy()
        strategy.should_buy = AsyncMock(return_value=(False, 0, "No buy"))
        strategy.should_sell = AsyncMock(return_value=(False, "Holding"))

        override_pos = _make_position(id=999)

        with patch(
            "app.trading_engine.signal_processor.get_active_position",
            new_callable=AsyncMock,
        ) as mock_get:
            result = await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
                position_override=override_pos,
            )

            # get_active_position should NOT be called
            mock_get.assert_not_awaited()

        assert result["action"] == "hold"

    @pytest.mark.asyncio
    async def test_pre_analyzed_signal_skips_analyze(self):
        """Edge case: pre_analyzed_signal skips strategy.analyze_signal call."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(reserved_usd_balance=5000.0)
        strategy = _make_strategy()
        strategy.should_buy = AsyncMock(return_value=(False, 0, "No buy"))
        strategy.should_sell = AsyncMock(return_value=(False, "Not selling"))

        existing_position = _make_position()
        pre_signal = {
            "signal_type": "hold",
            "confidence": 60,
            "_already_logged": True,
        }

        with patch(
            "app.trading_engine.signal_processor.get_active_position",
            new_callable=AsyncMock,
            return_value=existing_position,
        ):
            await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
                pre_analyzed_signal=pre_signal,
            )

        strategy.analyze_signal.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dca_buy_failure_does_not_raise(self):
        """Failure: DCA buy failure for existing position does not raise, returns none."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(reserved_usd_balance=5000.0)
        strategy = _make_strategy()
        strategy.should_buy = AsyncMock(return_value=(True, 50.0, "DCA triggered"))

        existing_position = _make_position()

        with (
            patch(
                "app.trading_engine.signal_processor.get_active_position",
                new_callable=AsyncMock,
                return_value=existing_position,
            ),
            patch(
                "app.trading_engine.signal_processor.execute_buy",
                new_callable=AsyncMock,
                side_effect=ValueError("Insufficient funds"),
            ),
        ):
            # Should NOT raise - DCA failures are caught
            result = await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
            )

        assert result["action"] == "none"
        assert "DCA buy failed" in result["reason"]

    @pytest.mark.asyncio
    async def test_closing_via_limit_blocks_sell(self):
        """Edge case: position with pending limit close order blocks new sell signals."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(reserved_usd_balance=5000.0)
        strategy = _make_strategy()
        strategy.should_buy = AsyncMock(return_value=(False, 0, "No buy"))
        strategy.should_sell = AsyncMock(return_value=(True, "TP reached"))

        existing_position = _make_position(
            closing_via_limit=True,
            limit_close_order_id="limit-close-001",
        )

        with patch(
            "app.trading_engine.signal_processor.get_active_position",
            new_callable=AsyncMock,
            return_value=existing_position,
        ):
            result = await process_signal(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                strategy=strategy,
                product_id="ETH-USD",
                candles=_make_candles(),
                current_price=3000.0,
            )

        assert result["action"] == "hold"
        assert "Limit close order already pending" in result["reason"]
