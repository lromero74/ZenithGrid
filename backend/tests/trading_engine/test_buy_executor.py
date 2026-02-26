"""
Tests for backend/app/trading_engine/buy_executor.py

Covers:
- execute_buy: market buy order execution (happy path, validation failure, exchange error, shutdown)
- execute_limit_buy: limit buy order placement (happy path, propguard block, no order_id)
- execute_buy_close_short: closing short positions via market buy (happy path, zero BTC, shutdown)
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.trading_engine.buy_executor import (
    execute_buy,
    execute_limit_buy,
    execute_buy_close_short,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal ORM-like objects for testing
# ---------------------------------------------------------------------------


def _make_bot(**overrides):
    bot = MagicMock()
    bot.id = overrides.get("id", 1)
    bot.user_id = overrides.get("user_id", 10)
    bot.strategy_config = overrides.get("strategy_config", {})
    return bot


def _make_position(**overrides):
    pos = MagicMock()
    pos.id = overrides.get("id", 100)
    pos.user_id = overrides.get("user_id", 10)
    pos.product_id = overrides.get("product_id", "ETH-USD")
    pos.strategy_config_snapshot = overrides.get("strategy_config_snapshot", {})
    pos.total_quote_spent = overrides.get("total_quote_spent", 0.0)
    pos.total_base_acquired = overrides.get("total_base_acquired", 0.0)
    pos.average_buy_price = overrides.get("average_buy_price", 0.0)
    pos.last_error_message = overrides.get("last_error_message", None)
    pos.last_error_timestamp = overrides.get("last_error_timestamp", None)
    # Default to non-None so get_next_user_deal_number is NOT called in most tests
    pos.user_deal_number = overrides.get("user_deal_number", 1)
    pos.user_attempt_number = overrides.get("user_attempt_number", 1)
    pos.direction = overrides.get("direction", "long")
    pos.status = overrides.get("status", "open")
    pos.short_total_sold_base = overrides.get("short_total_sold_base", None)
    pos.short_total_sold_quote = overrides.get("short_total_sold_quote", None)
    pos.short_average_sell_price = overrides.get("short_average_sell_price", None)
    pos.closing_via_limit = overrides.get("closing_via_limit", False)
    pos.limit_close_order_id = overrides.get("limit_close_order_id", None)
    pos.closed_at = overrides.get("closed_at", None)
    pos.profit_quote = overrides.get("profit_quote", None)
    pos.profit_percentage = overrides.get("profit_percentage", None)
    pos.profit_usd = overrides.get("profit_usd", None)
    return pos


def _make_exchange(**overrides):
    exchange = AsyncMock()
    exchange.get_order = AsyncMock(return_value={
        "filled_size": "1.0",
        "filled_value": "3000.0",
        "average_filled_price": "3000.0",
        "total_fees": "4.5",
    })
    exchange.get_btc_usd_price = AsyncMock(return_value=50000.0)
    exchange.get_ticker = AsyncMock(return_value={
        "best_bid": "2999.0",
        "best_ask": "3001.0",
    })
    for k, v in overrides.items():
        setattr(exchange, k, v)
    return exchange


def _make_trading_client(**overrides):
    tc = AsyncMock()
    tc.buy = AsyncMock(return_value={
        "success_response": {"order_id": "order-abc-123"},
        "error_response": {},
    })
    tc.buy_limit = AsyncMock(return_value={
        "success_response": {"order_id": "limit-order-456"},
    })
    tc.sell = AsyncMock()
    tc.invalidate_balance_cache = AsyncMock()
    tc.get_order = AsyncMock(return_value={
        "filled_size": 1.0,
        "average_filled_price": 3000.0,
    })
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
# Common patches applied to every test in this module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_externals():
    """Patch out shutdown_manager, ws_manager, order_logger, validate_order_size, etc."""
    sm = MagicMock()
    sm.is_shutting_down = False
    sm.increment_in_flight = AsyncMock()
    sm.decrement_in_flight = AsyncMock()

    with (
        patch("app.trading_engine.buy_executor.shutdown_manager", sm),
        patch("app.trading_engine.buy_executor.ws_manager", AsyncMock()),
        patch("app.trading_engine.buy_executor.log_order_to_history", new_callable=AsyncMock),
        patch("app.trading_engine.buy_executor.validate_order_size", new_callable=AsyncMock, return_value=(True, None)),
        patch("app.trading_engine.fill_reconciler.get_base_precision", return_value=8),
    ):
        yield sm


# ===========================================================================
# execute_buy
# ===========================================================================


class TestExecuteBuy:
    """Tests for execute_buy() — market buy order execution."""

    @pytest.mark.asyncio
    async def test_happy_path_market_buy_creates_trade(self):
        """Happy path: market buy succeeds and returns a Trade-like object."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position()

        trade = await execute_buy(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            quote_amount=100.0,
            current_price=3000.0,
            trade_type="initial",
        )

        assert trade is not None
        assert trade.side == "buy"
        assert trade.trade_type == "initial"
        assert trade.order_id == "order-abc-123"
        # Position totals should be updated
        assert position.total_quote_spent == 3000.0
        assert position.total_base_acquired == 1.0
        # DB should be committed
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_buy_updates_average_price(self):
        """When adding to an existing position, average buy price is recalculated."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        # Existing position that already has some holdings
        position = _make_position(total_quote_spent=1000.0, total_base_acquired=0.5)

        trade = await execute_buy(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            quote_amount=100.0,
            current_price=3000.0,
            trade_type="dca",
        )

        assert trade is not None
        # Position should now have 1000 + 3000 = 4000 spent, 0.5 + 1.0 = 1.5 acquired
        assert position.total_quote_spent == pytest.approx(4000.0)
        assert position.total_base_acquired == pytest.approx(1.5)
        assert position.average_buy_price == pytest.approx(4000.0 / 1.5)

    @pytest.mark.asyncio
    async def test_buy_during_shutdown_raises_runtime_error(self, _patch_externals):
        """Failure: orders rejected when shutdown is in progress."""
        _patch_externals.is_shutting_down = True

        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position()

        with pytest.raises(RuntimeError, match="shutdown in progress"):
            await execute_buy(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                quote_amount=100.0,
                current_price=3000.0,
                trade_type="initial",
            )

    @pytest.mark.asyncio
    async def test_buy_validation_failure_raises_value_error(self):
        """Failure: order validation fails (below minimum size)."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position()

        with patch(
            "app.trading_engine.buy_executor.validate_order_size",
            new_callable=AsyncMock,
            return_value=(False, "Order too small"),
        ):
            with pytest.raises(ValueError, match="Order too small"):
                await execute_buy(
                    db=db,
                    exchange=exchange,
                    trading_client=tc,
                    bot=bot,
                    product_id="ETH-USD",
                    position=position,
                    quote_amount=0.001,
                    current_price=3000.0,
                    trade_type="initial",
                    commit_on_error=True,
                )

    @pytest.mark.asyncio
    async def test_buy_exchange_returns_no_order_id_raises(self):
        """Failure: exchange returns empty order_id (order rejected)."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.buy = AsyncMock(return_value={
            "success_response": {"order_id": ""},
            "error_response": {"message": "Insufficient funds", "error": "INSUFFICIENT_FUND"},
        })
        bot = _make_bot()
        position = _make_position()

        with pytest.raises(ValueError, match="Exchange order failed"):
            await execute_buy(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                quote_amount=100.0,
                current_price=3000.0,
                trade_type="initial",
            )

    @pytest.mark.asyncio
    async def test_buy_propguard_block_raises_value_error(self):
        """Failure: PropGuard blocks the buy order."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.buy = AsyncMock(return_value={
            "blocked_by": "propguard",
            "error": "Daily loss limit exceeded",
        })
        bot = _make_bot()
        position = _make_position()

        with pytest.raises(ValueError, match="PropGuard blocked"):
            await execute_buy(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                quote_amount=100.0,
                current_price=3000.0,
                trade_type="initial",
            )

    @pytest.mark.asyncio
    async def test_safety_order_limit_route(self):
        """Edge case: safety order with limit config routes to execute_limit_buy."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            strategy_config_snapshot={"dca_execution_type": "limit"}
        )

        # execute_limit_buy returns a PendingOrder, execute_buy should return None for limit orders
        trade = await execute_buy(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            quote_amount=50.0,
            current_price=2900.0,
            trade_type="safety_order_1",
        )

        assert trade is None
        tc.buy_limit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_buy_clears_previous_errors_on_success(self):
        """After a successful buy, position error fields are cleared."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            last_error_message="Previous DCA failed",
            last_error_timestamp=datetime(2025, 1, 1),
        )

        trade = await execute_buy(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            quote_amount=100.0,
            current_price=3000.0,
            trade_type="dca",
        )

        assert trade is not None
        assert position.last_error_message is None
        assert position.last_error_timestamp is None

    @pytest.mark.asyncio
    async def test_buy_btc_pair_fee_adjustment(self):
        """Edge case: BTC-denominated pair applies fee deduction to base amount."""
        db = _make_db()
        exchange = _make_exchange()
        # For BTC pair, fees are deducted from base amount
        exchange.get_order = AsyncMock(return_value={
            "filled_size": "10.0",
            "filled_value": "0.001",
            "average_filled_price": "0.0001",
            "total_fees": "0.0000015",  # fee in quote (BTC)
        })
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position()

        trade = await execute_buy(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-BTC",
            position=position,
            quote_amount=0.001,
            current_price=0.0001,
            trade_type="initial",
        )

        assert trade is not None
        # base_amount should be less than gross due to fee adjustment
        assert trade.base_amount < 10.0

    @pytest.mark.asyncio
    async def test_buy_assigns_deal_number_on_first_trade(self):
        """First successful trade assigns a user_deal_number."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(user_deal_number=None)

        # The lazy import inside execute_buy does:
        #   from app.trading_engine.position_manager import get_next_user_deal_number
        # We mock the function at its source module
        with patch(
            "app.trading_engine.position_manager.get_next_user_deal_number",
            new_callable=AsyncMock,
            return_value=42,
        ):
            trade = await execute_buy(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                quote_amount=100.0,
                current_price=3000.0,
                trade_type="initial",
            )

        assert trade is not None
        assert position.user_deal_number == 42

    @pytest.mark.asyncio
    async def test_base_execution_type_limit_routes_to_limit_buy(self):
        """Base order with base_execution_type='limit' routes to execute_limit_buy."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            strategy_config_snapshot={"base_execution_type": "limit"}
        )

        trade = await execute_buy(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            quote_amount=100.0,
            current_price=3000.0,
            trade_type="initial",
        )

        # Limit order path returns None trade
        assert trade is None
        tc.buy_limit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_base_execution_type_market_routes_to_market_buy(self):
        """Base order with base_execution_type='market' (default) uses market buy."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            strategy_config_snapshot={"base_execution_type": "market"}
        )

        trade = await execute_buy(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            quote_amount=100.0,
            current_price=3000.0,
            trade_type="initial",
        )

        assert trade is not None
        tc.buy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dca_execution_type_limit_routes_to_limit_buy(self):
        """DCA order with dca_execution_type='limit' routes to execute_limit_buy."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            strategy_config_snapshot={"dca_execution_type": "limit"}
        )

        trade = await execute_buy(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            quote_amount=50.0,
            current_price=2900.0,
            trade_type="safety_order_1",
        )

        assert trade is None
        tc.buy_limit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dca_execution_type_market_uses_market_buy(self):
        """DCA order with dca_execution_type='market' (default) uses market buy."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            strategy_config_snapshot={"dca_execution_type": "market"}
        )

        trade = await execute_buy(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            quote_amount=50.0,
            current_price=2900.0,
            trade_type="safety_order_1",
        )

        assert trade is not None
        tc.buy.assert_awaited_once()


# ===========================================================================
# execute_limit_buy
# ===========================================================================


class TestExecuteLimitBuy:
    """Tests for execute_limit_buy() — limit buy order placement."""

    @pytest.mark.asyncio
    async def test_happy_path_places_limit_order(self):
        """Happy path: limit order placed and PendingOrder record created."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position()

        pending = await execute_limit_buy(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            quote_amount=100.0,
            limit_price=2900.0,
            trade_type="safety_order_1",
        )

        assert pending is not None
        assert pending.order_id == "limit-order-456"
        assert pending.side == "BUY"
        assert pending.order_type == "LIMIT"
        assert pending.limit_price == 2900.0
        assert pending.status == "pending"
        db.add.assert_called()
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_limit_buy_propguard_block_raises(self):
        """Failure: PropGuard blocks the limit buy order."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.buy_limit = AsyncMock(return_value={
            "blocked_by": "propguard",
            "error": "Safety check failed",
        })
        bot = _make_bot()
        position = _make_position()

        with pytest.raises(ValueError, match="PropGuard blocked"):
            await execute_limit_buy(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                quote_amount=100.0,
                limit_price=2900.0,
                trade_type="safety_order_1",
            )

    @pytest.mark.asyncio
    async def test_limit_buy_no_order_id_raises(self):
        """Failure: exchange returns no order_id for limit order."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.buy_limit = AsyncMock(return_value={
            "success_response": {"order_id": ""},
        })
        bot = _make_bot()
        position = _make_position()

        with pytest.raises(ValueError, match="No order_id"):
            await execute_limit_buy(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="ETH-USD",
                position=position,
                quote_amount=100.0,
                limit_price=2900.0,
                trade_type="safety_order_2",
            )

    @pytest.mark.asyncio
    async def test_limit_buy_calculates_base_amount(self):
        """Edge case: base_amount is correctly computed from quote/price."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position()

        pending = await execute_limit_buy(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="ETH-USD",
            position=position,
            quote_amount=2900.0,
            limit_price=2900.0,
            trade_type="safety_order_1",
        )

        assert pending.base_amount == pytest.approx(1.0)


# ===========================================================================
# execute_buy_close_short
# ===========================================================================


class TestExecuteBuyCloseShort:
    """Tests for execute_buy_close_short() — closing short positions."""

    @pytest.mark.asyncio
    async def test_happy_path_close_short_profitable(self):
        """Happy path: profitable short close (bought back cheaper than sold)."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        # Order details fetched by trading_client
        tc.get_order = AsyncMock(return_value={
            "filled_size": 0.5,
            "average_filled_price": 2800.0,
        })
        bot = _make_bot()
        position = _make_position(
            direction="short",
            short_total_sold_base=0.5,
            short_total_sold_quote=1500.0,  # sold 0.5 BTC at $3000 avg
            short_average_sell_price=3000.0,
        )

        trade, profit_quote, profit_pct = await execute_buy_close_short(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="BTC-USD",
            position=position,
            current_price=2800.0,
        )

        assert trade is not None
        assert trade.side == "buy"
        assert trade.trade_type == "close_short"
        # Profit: sold for 1500, bought back for 0.5 * 2800 = 1400, profit = 100
        assert profit_quote == pytest.approx(100.0)
        assert profit_pct == pytest.approx(100.0 / 1500.0 * 100)
        assert position.status == "closed"
        assert position.closed_at is not None

    @pytest.mark.asyncio
    async def test_close_short_no_btc_to_buy_back_raises(self):
        """Failure: position has no BTC to buy back."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            direction="short",
            short_total_sold_base=0.0,
        )

        with pytest.raises(ValueError, match="no BTC to buy back"):
            await execute_buy_close_short(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="BTC-USD",
                position=position,
                current_price=2800.0,
            )

    @pytest.mark.asyncio
    async def test_close_short_during_shutdown_raises(self, _patch_externals):
        """Failure: reject close-short during shutdown."""
        _patch_externals.is_shutting_down = True

        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        bot = _make_bot()
        position = _make_position(
            direction="short",
            short_total_sold_base=0.5,
            short_total_sold_quote=1500.0,
        )

        with pytest.raises(RuntimeError, match="shutdown in progress"):
            await execute_buy_close_short(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="BTC-USD",
                position=position,
                current_price=2800.0,
            )

    @pytest.mark.asyncio
    async def test_close_short_propguard_block_raises(self):
        """Failure: PropGuard blocks the close-short buy order."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.buy = AsyncMock(return_value={
            "blocked_by": "propguard",
            "error": "Position size limit exceeded",
        })
        bot = _make_bot()
        position = _make_position(
            direction="short",
            short_total_sold_base=0.5,
            short_total_sold_quote=1500.0,
        )

        with pytest.raises(ValueError, match="PropGuard blocked"):
            await execute_buy_close_short(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="BTC-USD",
                position=position,
                current_price=2800.0,
            )

    @pytest.mark.asyncio
    async def test_close_short_losing_trade(self):
        """Edge case: unprofitable short close (price went up)."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.get_order = AsyncMock(return_value={
            "filled_size": 0.5,
            "average_filled_price": 3200.0,  # bought back higher than sold
        })
        bot = _make_bot()
        position = _make_position(
            direction="short",
            short_total_sold_base=0.5,
            short_total_sold_quote=1500.0,  # sold at $3000 avg
            short_average_sell_price=3000.0,
        )

        trade, profit_quote, profit_pct = await execute_buy_close_short(
            db=db,
            exchange=exchange,
            trading_client=tc,
            bot=bot,
            product_id="BTC-USD",
            position=position,
            current_price=3200.0,
        )

        assert trade is not None
        # Loss: sold for 1500, bought back for 0.5 * 3200 = 1600, loss = -100
        assert profit_quote == pytest.approx(-100.0)
        assert profit_pct < 0
        assert position.status == "closed"

    @pytest.mark.asyncio
    async def test_close_short_exchange_error_no_order_id_raises(self):
        """Failure: exchange returns no order_id on close-short buy."""
        db = _make_db()
        exchange = _make_exchange()
        tc = _make_trading_client()
        tc.buy = AsyncMock(return_value={
            "success_response": {"order_id": ""},
            "error_response": {"message": "Rejected", "error_details": "No funds"},
        })
        bot = _make_bot()
        position = _make_position(
            direction="short",
            short_total_sold_base=0.5,
            short_total_sold_quote=1500.0,
        )

        with pytest.raises(ValueError, match="Close-short buy failed"):
            await execute_buy_close_short(
                db=db,
                exchange=exchange,
                trading_client=tc,
                bot=bot,
                product_id="BTC-USD",
                position=position,
                current_price=2800.0,
            )
