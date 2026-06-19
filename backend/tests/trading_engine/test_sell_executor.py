"""
Tests for backend/app/trading_engine/sell_executor.py

Covers:
- execute_sell: market/limit sell to close long positions
- execute_sell_short: market sell to open/add to short positions
- execute_limit_sell: limit sell order placement
"""

import math
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


from app.trading_engine.sell_executor import (
    execute_sell,
    execute_sell_short,
    execute_limit_sell,
    clamp_sell_base_amount,
    _resolve_real_close_amount,
    SELL_BALANCE_HAIRCUT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot(**overrides):
    bot = MagicMock()
    bot.id = overrides.get("id", 1)
    bot.user_id = overrides.get("user_id", 10)
    bot.strategy_config = overrides.get("strategy_config", {})
    bot.last_signal_check = overrides.get("last_signal_check", None)
    return bot


def _make_position(**overrides):
    pos = MagicMock()
    pos.id = overrides.get("id", 100)
    pos.user_id = overrides.get("user_id", 10)
    pos.product_id = overrides.get("product_id", "ETH-USD")
    pos.strategy_config_snapshot = overrides.get("strategy_config_snapshot", {})
    pos.total_quote_spent = overrides.get("total_quote_spent", 1000.0)
    pos.total_base_acquired = overrides.get("total_base_acquired", 0.5)
    pos.average_buy_price = overrides.get("average_buy_price", 2000.0)
    pos.last_error_message = overrides.get("last_error_message", None)
    pos.last_error_timestamp = overrides.get("last_error_timestamp", None)
    pos.direction = overrides.get("direction", "long")
    pos.status = overrides.get("status", "open")
    pos.closing_via_limit = overrides.get("closing_via_limit", False)
    pos.limit_close_order_id = overrides.get("limit_close_order_id", None)
    pos.closed_at = overrides.get("closed_at", None)
    pos.sell_price = overrides.get("sell_price", None)
    pos.total_quote_received = overrides.get("total_quote_received", None)
    pos.profit_quote = overrides.get("profit_quote", None)
    pos.profit_percentage = overrides.get("profit_percentage", None)
    pos.profit_usd = overrides.get("profit_usd", None)
    pos.btc_usd_price_at_close = overrides.get("btc_usd_price_at_close", None)
    pos.entry_fees_quote = overrides.get("entry_fees_quote", 0.0)
    pos.exit_fees_quote = overrides.get("exit_fees_quote", 0.0)
    pos.short_entry_price = overrides.get("short_entry_price", None)
    pos.short_average_sell_price = overrides.get("short_average_sell_price", None)
    pos.short_total_sold_base = overrides.get("short_total_sold_base", None)
    pos.short_total_sold_quote = overrides.get("short_total_sold_quote", None)
    return pos


def _make_exchange(**overrides):
    exchange = AsyncMock()
    exchange.get_order = AsyncMock(return_value={
        "filled_size": "0.5",
        "filled_value": "1500.0",
        "average_filled_price": "3000.0",
    })
    exchange.get_btc_usd_price = AsyncMock(return_value=50000.0)
    exchange.get_ticker = AsyncMock(return_value={
        "best_bid": "2999.0",
        "best_ask": "3001.0",
    })
    # is_paper_trading is a sync method (not async) — must be a regular MagicMock
    # to avoid returning a truthy coroutine object in the boolean check
    exchange.is_paper_trading = MagicMock(return_value=False)
    # Default wallet is flush so the real-close clamp leaves the full size
    # alone; tests that need a shortfall override get_balance explicitly.
    exchange.get_balance = AsyncMock(return_value={"available": "1000000000", "hold": "0"})
    for k, v in overrides.items():
        setattr(exchange, k, v)
    return exchange


def _make_trading_client(**overrides):
    tc = AsyncMock()
    tc.sell = AsyncMock(return_value={
        "success": True,
        "success_response": {"order_id": "sell-order-789"},
        "error_response": {},
    })
    tc.sell_limit = AsyncMock(return_value={
        "success_response": {"order_id": "limit-sell-101"},
    })
    tc.invalidate_balance_cache = AsyncMock()
    for k, v in overrides.items():
        setattr(tc, k, v)
    return tc


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Shared patches
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_externals():
    """Patch out shutdown_manager, ws_manager, order_logger, precision."""
    sm = MagicMock()
    sm.is_shutting_down = False
    sm.increment_in_flight = AsyncMock()
    sm.decrement_in_flight = AsyncMock()

    with (
        patch("app.trading_engine.sell_executor.shutdown_manager", sm),
        patch("app.trading_engine.sell_executor.broadcast_backend", AsyncMock()),
        patch("app.trading_engine.sell_executor.log_order_to_history", new_callable=AsyncMock),
        patch("app.trading_engine.sell_executor.get_base_precision", return_value=8),
    ):
        yield sm


# ===========================================================================
# execute_sell (close long positions)
# ===========================================================================


class TestExecuteSell:
    """Tests for execute_sell() — close long positions via market/limit sell."""

    @pytest.mark.asyncio
    async def test_happy_path_market_sell_with_profit(self):
        """Happy path: profitable market sell closes position."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            total_quote_spent=1000.0,
            total_base_acquired=0.5,
            # Use market order type to go through market order path
            strategy_config_snapshot={"take_profit_order_type": "market"},
        )

        trade, profit_quote, profit_pct = await execute_sell(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            current_price=3000.0,
        )

        assert trade is not None
        assert trade.side == "sell"
        assert trade.trade_type == "sell"
        assert trade.order_id == "sell-order-789"
        # Profit: received 1500 - spent 1000 = 500
        assert profit_quote == pytest.approx(500.0)
        assert profit_pct == pytest.approx(50.0)
        assert position.status == "closed"
        assert position.closed_at is not None
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_market_sell_reports_profit_net_of_all_exchange_fees(self):
        db = _make_db()
        exchange = _make_exchange()
        exchange.get_order = AsyncMock(return_value={
            "filled_size": "0.5",
            "filled_value": "1500.0",
            "average_filled_price": "3000.0",
            "total_fees": "7.5",
        })
        position = _make_position(
            total_quote_spent=1000.0,
            total_base_acquired=0.5,
            entry_fees_quote=10.0,
            strategy_config_snapshot={"take_profit_order_type": "market"},
        )

        trade, profit_quote, profit_pct = await execute_sell(
            db=db, exchange=exchange, trading_client=_make_trading_client(),
            bot=_make_bot(), product_id="ETH-USD", position=position, current_price=3000.0,
        )

        assert trade.fee_quote == pytest.approx(7.5)
        assert position.exit_fees_quote == pytest.approx(7.5)
        assert profit_quote == pytest.approx(482.5)
        assert profit_pct == pytest.approx(47.7722772277)

    @pytest.mark.asyncio
    async def test_sell_during_shutdown_raises(self, _patch_externals):
        """Failure: sell rejected when shutdown is in progress."""
        _patch_externals.is_shutting_down = True

        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position()

        with pytest.raises(RuntimeError, match="shutdown in progress"):
            await execute_sell(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                current_price=3000.0,
            )

    @pytest.mark.asyncio
    async def test_sell_duplicate_limit_order_skipped(self):
        """Edge case: position already has pending limit close -- returns None."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(closing_via_limit=True, limit_close_order_id="existing-order")

        trade, profit, pct = await execute_sell(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            current_price=3000.0,
        )

        assert trade is None
        assert profit == 0.0
        assert pct == 0.0
        # No sell order should have been placed
        tc.sell.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sell_limit_order_path(self):
        """Happy path: limit sell order placed when take_profit_order_type is limit."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            strategy_config_snapshot={"take_profit_order_type": "limit"},
        )

        trade, profit, pct = await execute_sell(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            current_price=3000.0,
        )

        # Limit order path returns None trade
        assert trade is None
        assert profit == 0.0
        assert pct == 0.0
        # Limit sell should have been placed
        tc.sell_limit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sell_propguard_block_raises(self):
        """Failure: PropGuard blocks market sell order."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.sell = AsyncMock(return_value={
            "blocked_by": "propguard",
            "error": "Safety check failed",
        })
        bot = _make_bot()
        position = _make_position(
            strategy_config_snapshot={"take_profit_order_type": "market"},
        )

        with pytest.raises(ValueError, match="PropGuard blocked"):
            await execute_sell(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                current_price=3000.0,
            )

    @pytest.mark.asyncio
    async def test_sell_exchange_failure_no_success_flag_raises(self):
        """Failure: exchange returns success=False with error details."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.sell = AsyncMock(return_value={
            "success": False,
            "error_response": {
                "message": "Insufficient balance",
                "error_details": "Not enough ETH",
                "error": "INSUFFICIENT_FUND",
            },
        })
        bot = _make_bot()
        position = _make_position(
            strategy_config_snapshot={"take_profit_order_type": "market"},
        )

        with pytest.raises(ValueError, match="INSUFFICIENT_FUND"):
            await execute_sell(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                current_price=3000.0,
            )

    @pytest.mark.asyncio
    async def test_sell_losing_trade(self):
        """Edge case: sell at a loss (current price below average buy)."""
        db = _make_db()
        exchange = _make_exchange()
        # Fill data: sold for less than spent
        exchange.get_order = AsyncMock(return_value={
            "filled_size": "0.5",
            "filled_value": "750.0",
            "average_filled_price": "1500.0",
        })
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            total_quote_spent=1000.0,
            total_base_acquired=0.5,
            strategy_config_snapshot={"take_profit_order_type": "market"},
        )

        trade, profit_quote, profit_pct = await execute_sell(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            current_price=1500.0,
        )

        assert trade is not None
        # Received 750 - Spent 1000 = -250 loss
        assert profit_quote == pytest.approx(-250.0)
        assert profit_pct == pytest.approx(-25.0)

    @pytest.mark.asyncio
    async def test_sell_triggers_re_analysis(self):
        """After successful sell, bot.last_signal_check is reset to trigger re-analysis."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot(last_signal_check=datetime(2025, 1, 1))
        position = _make_position(
            strategy_config_snapshot={"take_profit_order_type": "market"},
        )

        trade, _, _ = await execute_sell(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            current_price=3000.0,
        )

        assert trade is not None
        assert bot.last_signal_check is None

    @pytest.mark.asyncio
    async def test_sell_limit_fallback_to_market_when_profit_sufficient(self):
        """Edge case: limit sell fails but profit is sufficient, falls back to market."""
        db = _make_db()
        exchange = _make_exchange()
        # get_ticker fails causing limit sell path to raise
        exchange.get_ticker = AsyncMock(side_effect=Exception("Ticker unavailable"))
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            total_quote_spent=1000.0,
            total_base_acquired=0.5,
            strategy_config_snapshot={
                "take_profit_order_type": "limit",
                "take_profit_percentage": 3.0,
            },
        )
        # current_price=3000 -> value = 0.5*3000 = 1500 -> profit_pct = 50% >> 3%
        trade, profit_quote, profit_pct = await execute_sell(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            current_price=3000.0,
        )

        assert trade is not None
        # Market sell was used as fallback
        tc.sell.assert_awaited()

    @pytest.mark.asyncio
    async def test_sell_limit_fallback_aborts_when_profit_too_low(self):
        """Edge case: limit sell fails and profit dropped below min -- aborts sell."""
        db = _make_db()
        exchange = _make_exchange()
        exchange.get_ticker = AsyncMock(side_effect=Exception("Ticker unavailable"))
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            total_quote_spent=1000.0,
            total_base_acquired=0.5,
            strategy_config_snapshot={
                "take_profit_order_type": "limit",
                "take_profit_percentage": 60.0,  # need 60% profit
            },
        )
        # current_price=3000 -> value = 0.5*3000 = 1500 -> profit_pct = 50% < 60%
        trade, profit_quote, profit_pct = await execute_sell(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            current_price=3000.0,
        )

        assert trade is None
        assert profit_quote == 0.0
        tc.sell.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sell_force_market_ignores_limit_config(self):
        """Stop loss sells use market even when take_profit_order_type is limit."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        pos = _make_position(strategy_config_snapshot={"take_profit_order_type": "limit"})

        trade, profit_quote, profit_pct = await execute_sell(
            db=db, exchange=exchange, trading_client=tc,
            bot=bot, product_id="ETH-USD", position=pos,
            current_price=3000.0, signal_data=None,
            force_market=True,
        )

        # Should have used market sell, not limit sell
        tc.sell.assert_awaited_once()
        tc.sell_limit.assert_not_awaited()
        assert trade is not None

    @pytest.mark.asyncio
    async def test_sell_limit_config_respected_when_not_forced(self):
        """TP sells use limit when configured and force_market is False."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        pos = _make_position(strategy_config_snapshot={"take_profit_order_type": "limit"})

        trade, profit_quote, profit_pct = await execute_sell(
            db=db, exchange=exchange, trading_client=tc,
            bot=bot, product_id="ETH-USD", position=pos,
            current_price=3000.0, signal_data=None,
            force_market=False,
        )

        # Should have used limit sell
        tc.sell_limit.assert_awaited_once()
        # Limit sell returns None trade (pending)
        assert trade is None


# ===========================================================================
# execute_sell_short (open/add to short positions)
# ===========================================================================


class TestExecuteSellShort:
    """Tests for execute_sell_short() — sell to open or add to short positions."""

    @pytest.mark.asyncio
    async def test_happy_path_initial_short_sell(self):
        """Happy path: first short sell opens a short position."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            direction="short",
            short_entry_price=None,  # no existing short
            short_average_sell_price=None,
            short_total_sold_base=None,
            short_total_sold_quote=None,
        )

        with patch(
            "app.order_validation.validate_order_size",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            trade = await execute_sell_short(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="BTC-USD",
                position=position,
                base_amount=0.5,
                current_price=50000.0,
                trade_type="initial",
            )

        assert trade is not None
        assert trade.side == "sell"
        assert trade.trade_type == "initial"
        # First short: entry price set
        assert position.short_entry_price is not None
        assert position.short_total_sold_base is not None
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_short_sell_safety_order_adds_to_position(self):
        """Happy path: subsequent short sell (safety order) adds to existing short."""
        db = _make_db()
        exchange = _make_exchange()
        # Fill data shows actual execution
        exchange.get_order = AsyncMock(return_value={
            "filled_size": "0.3",
            "filled_value": "14400.0",
            "average_filled_price": "48000.0",
        })
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            direction="short",
            short_entry_price=50000.0,
            short_average_sell_price=50000.0,
            short_total_sold_base=0.5,
            short_total_sold_quote=25000.0,
        )

        with patch(
            "app.order_validation.validate_order_size",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            trade = await execute_sell_short(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="BTC-USD",
                position=position,
                base_amount=0.3,
                current_price=48000.0,
                trade_type="safety_order_1",
            )

        assert trade is not None
        # Updated total: 0.5 + 0.3 = 0.8 BTC sold
        assert position.short_total_sold_base == pytest.approx(0.8)
        # Updated total quote: 25000 + 14400 = 39400
        assert position.short_total_sold_quote == pytest.approx(39400.0)
        # Average recalculated: 39400 / 0.8 = 49250
        assert position.short_average_sell_price == pytest.approx(49250.0)

    @pytest.mark.asyncio
    async def test_short_sell_during_shutdown_raises(self, _patch_externals):
        """Failure: short sell rejected during shutdown."""
        _patch_externals.is_shutting_down = True

        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(direction="short")

        with pytest.raises(RuntimeError, match="shutdown in progress"):
            await execute_sell_short(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="BTC-USD",
                position=position,
                base_amount=0.5,
                current_price=50000.0,
                trade_type="initial",
            )

    @pytest.mark.asyncio
    async def test_short_sell_validation_failure_raises(self):
        """Failure: order size below exchange minimum."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(direction="short")

        with patch(
            "app.order_validation.validate_order_size",
            new_callable=AsyncMock,
            return_value=(False, "Order too small"),
        ):
            with pytest.raises(ValueError, match="Order validation failed"):
                await execute_sell_short(
                    db=db,
                    exchange=exchange,
                    trading_client=tc,
                    bot=bot,
                    product_id="BTC-USD",
                    position=position,
                    base_amount=0.00001,
                    current_price=50000.0,
                    trade_type="initial",
                )

    @pytest.mark.asyncio
    async def test_short_sell_propguard_block_raises(self):
        """Failure: PropGuard blocks the short sell."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.sell = AsyncMock(return_value={
            "blocked_by": "propguard",
            "error": "Safety check",
        })
        bot = _make_bot()
        position = _make_position(direction="short")

        with patch(
            "app.order_validation.validate_order_size",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            with pytest.raises(ValueError, match="PropGuard blocked"):
                await execute_sell_short(
                    db=db,
                    exchange=exchange,
                    trading_client=tc,
                    bot=bot,
                    product_id="BTC-USD",
                    position=position,
                    base_amount=0.5,
                    current_price=50000.0,
                    trade_type="initial",
                )

    @pytest.mark.asyncio
    async def test_short_sell_clears_error_status(self):
        """After successful short sell, error fields are cleared."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            direction="short",
            short_entry_price=None,
            last_error_message="Previous error",
            last_error_timestamp=datetime(2025, 6, 1),
        )

        with patch(
            "app.order_validation.validate_order_size",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            trade = await execute_sell_short(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="BTC-USD",
                position=position,
                base_amount=0.5,
                current_price=50000.0,
                trade_type="initial",
            )

        assert trade is not None
        assert position.last_error_message is None
        assert position.last_error_timestamp is None


# ===========================================================================
# execute_limit_sell
# ===========================================================================


class TestExecuteLimitSell:
    """Tests for execute_limit_sell() — place limit sell orders."""

    @pytest.mark.asyncio
    async def test_happy_path_places_limit_sell(self):
        """Happy path: limit sell order created and position marked as closing."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position()

        pending = await execute_limit_sell(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            base_amount=0.5,
            limit_price=3100.0,
        )

        assert pending is not None
        assert pending.order_id == "limit-sell-101"
        assert pending.side == "SELL"
        assert pending.order_type == "LIMIT"
        assert pending.trade_type == "limit_close"
        assert pending.status == "pending"
        assert position.closing_via_limit is True
        assert position.limit_close_order_id == "limit-sell-101"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_limit_sell_propguard_block_raises(self):
        """Failure: PropGuard blocks limit sell."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.sell_limit = AsyncMock(return_value={
            "blocked_by": "propguard",
            "error": "Daily loss limit",
        })
        bot = _make_bot()
        position = _make_position()

        with pytest.raises(ValueError, match="PropGuard blocked"):
            await execute_limit_sell(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                base_amount=0.5,
                limit_price=3100.0,
            )

    @pytest.mark.asyncio
    async def test_limit_sell_no_order_id_raises(self):
        """Failure: exchange returns no order_id."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.sell_limit = AsyncMock(return_value={
            "success_response": {"order_id": ""},
        })
        bot = _make_bot()
        position = _make_position()

        with pytest.raises(ValueError, match="No order_id"):
            await execute_limit_sell(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                base_amount=0.5,
                limit_price=3100.0,
            )

    @pytest.mark.asyncio
    async def test_limit_sell_expected_quote_amount_calculated(self):
        """Edge case: expected quote amount = base * price."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position()

        pending = await execute_limit_sell(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            base_amount=2.0,
            limit_price=3000.0,
        )

        assert pending.quote_amount == pytest.approx(6000.0)


# ===========================================================================
# Dust close (base_amount rounds to 0)
# ===========================================================================


class TestDustClose:
    """Tests for dust close path in execute_sell — when base_amount rounds to 0."""

    @pytest.mark.asyncio
    async def test_dust_close_calculates_actual_profit(self):
        """Happy path: dust close computes profit at current price, not -100%."""
        db = _make_db()
        exchange = _make_exchange()
        # is_paper=False so we skip paper balance check
        exchange.is_paper_trading = MagicMock(return_value=False)
        tc = _make_trading_client()
        bot = _make_bot()

        # Position: bought 0.000001 ETH at $2000, spent $0.002
        position = _make_position(
            product_id="ETH-USD",
            total_base_acquired=0.000001,  # tiny amount
            total_quote_spent=0.002,
            average_buy_price=2000.0,
        )

        # Precision=8 → floor(0.000001 * 10^8) / 10^8 = 0.000001
        # But we override precision to 4 → floor(0.000001 * 10^4) / 10^4 = 0.0 → dust!
        with patch("app.trading_engine.sell_executor.get_base_precision", return_value=4):
            trade, profit, pct = await execute_sell(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                current_price=3000.0,  # price went up
                signal_data={"signal_type": "sell"},
            )

        assert trade is None  # No exchange order placed
        assert position.status == "closed"
        assert position.close_price == 3000.0
        # Actual profit: 0.000001 * 3000 - 0.002 = 0.003 - 0.002 = 0.001
        assert profit == pytest.approx(0.001, abs=1e-9)
        assert position.profit_quote == pytest.approx(0.001, abs=1e-9)
        assert position.profit_usd == pytest.approx(0.001, abs=1e-9)
        assert position.total_quote_received == pytest.approx(0.003, abs=1e-9)
        # Profit %: (0.001 / 0.002) * 100 = 50%
        assert pct == pytest.approx(50.0, abs=0.1)
        assert position.profit_percentage == pytest.approx(50.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_dust_close_loss_not_negative_100(self):
        """Edge case: dust close at a loss still computes actual loss, not -100%."""
        db = _make_db()
        exchange = _make_exchange()
        exchange.is_paper_trading = MagicMock(return_value=False)
        tc = _make_trading_client()
        bot = _make_bot()

        # Position: bought tiny ETH at $3000, price dropped to $2000
        position = _make_position(
            product_id="ETH-USD",
            total_base_acquired=0.000001,
            total_quote_spent=0.003,
            average_buy_price=3000.0,
        )

        with patch("app.trading_engine.sell_executor.get_base_precision", return_value=4):
            trade, profit, pct = await execute_sell(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                current_price=2000.0,
                signal_data={"signal_type": "sell"},
            )

        assert trade is None
        assert position.status == "closed"
        # Actual loss: 0.000001 * 2000 - 0.003 = 0.002 - 0.003 = -0.001
        assert profit == pytest.approx(-0.001, abs=1e-9)
        assert pct == pytest.approx(-33.33, abs=0.1)  # -0.001/0.003 * 100

    @pytest.mark.asyncio
    async def test_dust_close_zero_spent_defaults_to_neg100(self):
        """Failure case: zero total_quote_spent avoids division by zero."""
        db = _make_db()
        exchange = _make_exchange()
        exchange.is_paper_trading = MagicMock(return_value=False)
        tc = _make_trading_client()
        bot = _make_bot()

        position = _make_position(
            product_id="ETH-USD",
            total_base_acquired=0.000001,
            total_quote_spent=0,  # edge: zero spent
            average_buy_price=0.0,
        )

        with patch("app.trading_engine.sell_executor.get_base_precision", return_value=4):
            trade, profit, pct = await execute_sell(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                current_price=2000.0,
                signal_data={"signal_type": "sell"},
            )

        assert trade is None
        assert position.status == "closed"
        assert pct == -100.0  # Fallback for zero spent

    @pytest.mark.asyncio
    async def test_dust_close_paper_balance_topped_up_and_sells(self):
        """Edge case: paper balance is 0 but code tops it up, so normal sell proceeds."""
        db = _make_db()
        exchange = _make_exchange()
        exchange.is_paper_trading = MagicMock(return_value=True)
        exchange.get_balance = AsyncMock(return_value={"available": "0.0"})
        exchange.adjust_balance = AsyncMock()
        tc = _make_trading_client()
        bot = _make_bot()

        # Position has real holdings but paper balance is 0
        position = _make_position(
            product_id="ETH-USD",
            total_base_acquired=0.5,
            total_quote_spent=1000.0,
            average_buy_price=2000.0,
        )

        trade, profit, pct = await execute_sell(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            current_price=2100.0,
            signal_data={"signal_type": "sell"},
        )

        # Paper balance is topped up via adjust_balance, so normal sell proceeds
        exchange.adjust_balance.assert_awaited_once()
        assert trade is not None
        assert position.status == "closed"
        tc.sell.assert_awaited_once()


# ===========================================================================
# Short safety LIMIT orders (DCA adds via limit sell) — placement
# ===========================================================================


class TestShortSafetyLimitOrders:
    """execute_sell_short must place a LIMIT SELL safety order as a PendingOrder
    (an ADD), never via the close path, and never mutate the position at
    placement time. The fill is applied later by the reconciler."""

    @pytest.mark.asyncio
    async def test_limit_safety_places_pending_order_not_market(self):
        """Happy path: short safety order with dca_execution_type='limit' places a
        SELL PendingOrder, returns None, and does NOT touch the close path."""
        from app.models import PendingOrder
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            direction="short",
            strategy_config_snapshot={"dca_execution_type": "limit"},
            short_entry_price=50000.0,
            short_average_sell_price=50000.0,
            short_total_sold_base=0.5,
            short_total_sold_quote=25000.0,
        )

        with patch(
            "app.order_validation.validate_order_size",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            result = await execute_sell_short(
                db=db, exchange=exchange, trading_client=tc, bot=bot,
                product_id="BTC-USD", position=position,
                base_amount=0.3, current_price=48000.0,
                trade_type="safety_order_1",
            )

        # Limit path: no immediate trade, limit order placed, market path untouched
        assert result is None
        tc.sell_limit.assert_awaited_once()
        tc.sell.assert_not_awaited()

        # Close path must NOT be engaged
        assert position.closing_via_limit is False
        assert position.limit_close_order_id is None

        # A SELL safety PendingOrder must be recorded
        added = [c.args[0] for c in db.add.call_args_list
                 if isinstance(c.args[0], PendingOrder)]
        assert len(added) == 1
        po = added[0]
        assert po.side == "SELL"
        assert po.order_type == "LIMIT"
        assert po.trade_type == "safety_order_1"
        assert po.status == "pending"
        assert po.order_id == "limit-sell-101"
        assert po.position_id == position.id

        # Position short totals are NOT mutated at placement (only on fill)
        assert position.short_total_sold_base == 0.5
        assert position.short_total_sold_quote == 25000.0

    @pytest.mark.asyncio
    async def test_market_safety_order_unaffected_by_limit_branch(self):
        """Edge/regression: a safety order in market mode still executes a market
        short sell (limit branch must not capture it)."""
        db = _make_db()
        exchange = _make_exchange()
        exchange.get_order = AsyncMock(return_value={
            "filled_size": "0.3", "filled_value": "14400.0",
            "average_filled_price": "48000.0",
        })
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            direction="short",
            strategy_config_snapshot={"dca_execution_type": "market"},
            short_entry_price=50000.0, short_average_sell_price=50000.0,
            short_total_sold_base=0.5, short_total_sold_quote=25000.0,
        )

        with patch(
            "app.order_validation.validate_order_size",
            new_callable=AsyncMock, return_value=(True, None),
        ):
            result = await execute_sell_short(
                db=db, exchange=exchange, trading_client=tc, bot=bot,
                product_id="BTC-USD", position=position,
                base_amount=0.3, current_price=48000.0,
                trade_type="safety_order_1",
            )

        assert result is not None          # market path returns a Trade
        tc.sell.assert_awaited()           # market sell used
        tc.sell_limit.assert_not_awaited()  # limit path NOT used

    @pytest.mark.asyncio
    async def test_limit_safety_missing_order_id_raises(self):
        """Failure: exchange returns no order_id → raise, no PendingOrder leaked."""
        from app.models import PendingOrder
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.sell_limit = AsyncMock(return_value={"success_response": {}})  # no order_id
        bot = _make_bot()
        position = _make_position(
            direction="short",
            strategy_config_snapshot={"dca_execution_type": "limit"},
            short_entry_price=50000.0, short_average_sell_price=50000.0,
            short_total_sold_base=0.5, short_total_sold_quote=25000.0,
        )

        with patch(
            "app.order_validation.validate_order_size",
            new_callable=AsyncMock, return_value=(True, None),
        ):
            with pytest.raises(ValueError):
                await execute_sell_short(
                    db=db, exchange=exchange, trading_client=tc, bot=bot,
                    product_id="BTC-USD", position=position,
                    base_amount=0.3, current_price=48000.0,
                    trade_type="safety_order_1",
                )

        added = [c.args[0] for c in db.add.call_args_list
                 if isinstance(c.args[0], PendingOrder)]
        assert added == []


# ---------------------------------------------------------------------------
# Clamp-to-available balance on close (INSUFFICIENT_FUND protection)
# ---------------------------------------------------------------------------


class TestClampSellBaseAmount:
    """Pure helper: never sell more base than the wallet actually holds."""

    def test_wallet_covers_recorded_sells_full_amount(self):
        # Happy path: available >= recorded -> sell the full recorded amount,
        # floored to precision, no clamp.
        amount, clamped = clamp_sell_base_amount(
            recorded=10.0, available=12.0, precision=2,
        )
        assert clamped is False
        assert amount == 10.0

    def test_exact_match_is_not_clamped(self):
        # Edge: available == recorded -> full amount, no haircut.
        amount, clamped = clamp_sell_base_amount(
            recorded=5.5, available=5.5, precision=1,
        )
        assert clamped is False
        assert amount == 5.5

    def test_wallet_short_clamps_with_haircut_and_floor(self):
        # Failure/drift: wallet holds less than recorded -> sell available
        # minus the haircut, floored to precision. FOX-style 65% shortfall.
        amount, clamped = clamp_sell_base_amount(
            recorded=865.8, available=296.7, precision=2,
        )
        assert clamped is True
        expected = math.floor(296.7 * SELL_BALANCE_HAIRCUT * 100) / 100
        assert amount == expected
        assert amount <= 296.7  # never exceeds the real balance

    def test_available_below_precision_floor_rounds_to_zero(self):
        # A shortfall so deep the survivable amount is below one precision step
        # floors to 0 -> caller closes it as dust (no doomed exchange order).
        amount, clamped = clamp_sell_base_amount(
            recorded=3.3, available=0.000001, precision=2,
        )
        assert clamped is True
        assert amount == 0.0

    def test_partial_survivor_above_precision_floor_is_sold(self):
        # JTO-style 95% shortfall but precision high enough to keep the residue:
        # sell what's actually there rather than failing outright.
        amount, clamped = clamp_sell_base_amount(
            recorded=3.3, available=0.15573171, precision=8,
        )
        assert clamped is True
        assert 0 < amount <= 0.15573171

    def test_negative_available_clamps_to_zero(self):
        amount, clamped = clamp_sell_base_amount(
            recorded=1.0, available=-0.5, precision=8,
        )
        assert clamped is True
        assert amount == 0.0


@pytest.mark.asyncio
class TestResolveRealCloseAmount:
    """Integration of the clamp with a (mocked) exchange balance lookup."""

    async def _exchange_with_balance(self, available):
        ex = AsyncMock()
        ex.get_balance = AsyncMock(return_value={"available": str(available), "hold": "0"})
        return ex

    async def test_clamps_when_wallet_short(self):
        ex = await self._exchange_with_balance(296.7)
        pos = _make_position(product_id="FOX-USD", total_base_acquired=865.8)
        amount, clamped = await _resolve_real_close_amount(
            ex, "FOX-USD", pos, raw_amount=865.8, precision=2,
        )
        assert clamped is True
        assert 0 < amount <= 296.7

    async def test_full_amount_when_wallet_covers(self):
        ex = await self._exchange_with_balance(1000.0)
        pos = _make_position(product_id="FOX-USD", total_base_acquired=865.8)
        amount, clamped = await _resolve_real_close_amount(
            ex, "FOX-USD", pos, raw_amount=865.8, precision=2,
        )
        assert clamped is False
        assert amount == 865.8

    async def test_balance_lookup_failure_falls_back_to_recorded(self):
        # A transient balance-API error must NOT block the close.
        ex = AsyncMock()
        ex.get_balance = AsyncMock(side_effect=RuntimeError("api down"))
        pos = _make_position(product_id="FOX-USD", total_base_acquired=865.8)
        amount, clamped = await _resolve_real_close_amount(
            ex, "FOX-USD", pos, raw_amount=865.8, precision=2,
        )
        assert clamped is False
        assert amount == 865.8

    async def test_get_balance_without_force_fresh_kwarg(self):
        # Clients whose get_balance has no force_fresh kwarg still work.
        async def _no_kwarg_get_balance(currency):
            return {"available": "296.7", "hold": "0"}
        ex = AsyncMock()
        ex.get_balance = _no_kwarg_get_balance
        pos = _make_position(product_id="FOX-USD", total_base_acquired=865.8)
        amount, clamped = await _resolve_real_close_amount(
            ex, "FOX-USD", pos, raw_amount=865.8, precision=2,
        )
        assert clamped is True
        assert 0 < amount <= 296.7
