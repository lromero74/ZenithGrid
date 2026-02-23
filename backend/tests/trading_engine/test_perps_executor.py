"""
Tests for backend/app/trading_engine/perps_executor.py

Covers:
- execute_perps_open: open a perpetual futures position with optional TP/SL
- execute_perps_close: close a perpetual futures position
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


from app.trading_engine.perps_executor import (
    execute_perps_open,
    execute_perps_close,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot(**overrides):
    bot = MagicMock()
    bot.id = overrides.get("id", 1)
    bot.user_id = overrides.get("user_id", 10)
    bot.account_id = overrides.get("account_id", 5)
    bot.strategy_config = overrides.get("strategy_config", {})
    return bot


def _make_position(**overrides):
    pos = MagicMock()
    pos.id = overrides.get("id", 100)
    pos.product_id = overrides.get("product_id", "BTC-PERP-INTX")
    pos.direction = overrides.get("direction", "long")
    pos.total_base_acquired = overrides.get("total_base_acquired", 0.001)
    pos.total_quote_spent = overrides.get("total_quote_spent", 100.0)
    pos.average_buy_price = overrides.get("average_buy_price", 100000.0)
    pos.short_total_sold_base = overrides.get("short_total_sold_base", None)
    pos.short_total_sold_quote = overrides.get("short_total_sold_quote", None)
    pos.short_average_sell_price = overrides.get("short_average_sell_price", None)
    pos.funding_fees_total = overrides.get("funding_fees_total", 0.0)
    pos.tp_order_id = overrides.get("tp_order_id", None)
    pos.sl_order_id = overrides.get("sl_order_id", None)
    pos.status = overrides.get("status", "open")
    pos.closed_at = overrides.get("closed_at", None)
    pos.sell_price = overrides.get("sell_price", None)
    pos.profit_quote = overrides.get("profit_quote", None)
    pos.profit_percentage = overrides.get("profit_percentage", None)
    pos.profit_usd = overrides.get("profit_usd", None)
    pos.exit_reason = overrides.get("exit_reason", None)
    return pos


def _make_client(**overrides):
    """Mock CoinbaseClient for perps operations."""
    client = AsyncMock()
    client.create_perps_order = AsyncMock(return_value={
        "success_response": {"order_id": "perps-order-001"},
    })
    client.close_perps_position = AsyncMock(return_value={
        "success_response": {"order_id": "perps-close-001"},
    })
    client.cancel_order = AsyncMock()
    for k, v in overrides.items():
        setattr(client, k, v)
    return client


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def _patch_shutdown():
    """Patch shutdown_manager for all tests."""
    sm = MagicMock()
    sm.is_shutting_down = False

    with patch("app.trading_engine.perps_executor.shutdown_manager", sm):
        yield sm


# ===========================================================================
# execute_perps_open
# ===========================================================================


class TestExecutePerpsOpen:
    """Tests for execute_perps_open() — open perpetual futures positions."""

    @pytest.mark.asyncio
    async def test_happy_path_long_position(self):
        """Happy path: open a long perps position with TP/SL."""
        db = _make_db()
        client = _make_client()
        bot = _make_bot()

        position, trade = await execute_perps_open(
            db=db,
            client=client,
            bot=bot,
            product_id="BTC-PERP-INTX",
            side="BUY",
            size_usdc=100.0,
            current_price=100000.0,
            leverage=5,
            margin_type="CROSS",
            tp_pct=5.0,
            sl_pct=3.0,
        )

        assert position is not None
        assert trade is not None
        assert position.direction == "long"
        assert position.product_type == "future"
        assert position.leverage == 5
        assert position.total_quote_spent == 100.0
        assert position.total_base_acquired == pytest.approx(0.001)
        assert position.average_buy_price == 100000.0
        # TP: 100000 * 1.05 = 105000
        assert position.tp_price == pytest.approx(105000.0)
        # SL: 100000 * 0.97 = 97000
        assert position.sl_price == pytest.approx(97000.0)
        assert trade.side == "buy"
        assert trade.trade_type == "initial"
        client.create_perps_order.assert_awaited_once()
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_happy_path_short_position(self):
        """Happy path: open a short perps position."""
        db = _make_db()
        client = _make_client()
        bot = _make_bot()

        position, trade = await execute_perps_open(
            db=db,
            client=client,
            bot=bot,
            product_id="BTC-PERP-INTX",
            side="SELL",
            size_usdc=200.0,
            current_price=100000.0,
            leverage=3,
            margin_type="ISOLATED",
        )

        assert position is not None
        assert position.direction == "short"
        assert position.short_entry_price == 100000.0
        assert position.short_total_sold_quote == 200.0
        assert position.short_total_sold_base == pytest.approx(0.002)
        assert trade.side == "sell"

    @pytest.mark.asyncio
    async def test_short_tp_sl_prices_inverted(self):
        """Edge case: short positions have inverted TP/SL prices."""
        db = _make_db()
        client = _make_client()
        bot = _make_bot()

        position, trade = await execute_perps_open(
            db=db,
            client=client,
            bot=bot,
            product_id="BTC-PERP-INTX",
            side="SELL",
            size_usdc=100.0,
            current_price=100000.0,
            leverage=1,
            tp_pct=5.0,
            sl_pct=3.0,
        )

        # Short TP: price goes DOWN -> 100000 * (1 - 0.05) = 95000
        assert position.tp_price == pytest.approx(95000.0)
        # Short SL: price goes UP -> 100000 * (1 + 0.03) = 103000
        assert position.sl_price == pytest.approx(103000.0)

    @pytest.mark.asyncio
    async def test_below_minimum_notional_returns_none(self):
        """Failure: notional below 10 USDC minimum returns (None, None)."""
        db = _make_db()
        client = _make_client()
        bot = _make_bot()

        position, trade = await execute_perps_open(
            db=db,
            client=client,
            bot=bot,
            product_id="BTC-PERP-INTX",
            side="BUY",
            size_usdc=5.0,  # below 10 USDC minimum
            current_price=100000.0,
        )

        assert position is None
        assert trade is None
        client.create_perps_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_shutdown_returns_none(self, _patch_shutdown):
        """Failure: shutdown in progress returns (None, None)."""
        _patch_shutdown.is_shutting_down = True

        db = _make_db()
        client = _make_client()
        bot = _make_bot()

        position, trade = await execute_perps_open(
            db=db,
            client=client,
            bot=bot,
            product_id="BTC-PERP-INTX",
            side="BUY",
            size_usdc=100.0,
            current_price=100000.0,
        )

        assert position is None
        assert trade is None

    @pytest.mark.asyncio
    async def test_exchange_error_no_order_id_returns_none(self):
        """Failure: exchange returns no order_id."""
        db = _make_db()
        client = _make_client()
        client.create_perps_order = AsyncMock(return_value={
            "success_response": {"order_id": ""},
            "error_response": {"message": "Margin insufficient"},
        })
        bot = _make_bot()

        position, trade = await execute_perps_open(
            db=db,
            client=client,
            bot=bot,
            product_id="BTC-PERP-INTX",
            side="BUY",
            size_usdc=100.0,
            current_price=100000.0,
        )

        assert position is None
        assert trade is None

    @pytest.mark.asyncio
    async def test_exchange_exception_returns_none(self):
        """Failure: exchange throws an exception."""
        db = _make_db()
        client = _make_client()
        client.create_perps_order = AsyncMock(side_effect=Exception("Network timeout"))
        bot = _make_bot()

        position, trade = await execute_perps_open(
            db=db,
            client=client,
            bot=bot,
            product_id="BTC-PERP-INTX",
            side="BUY",
            size_usdc=100.0,
            current_price=100000.0,
        )

        assert position is None
        assert trade is None
        db.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_tp_sl_when_not_provided(self):
        """Edge case: no TP/SL prices when not provided."""
        db = _make_db()
        client = _make_client()
        bot = _make_bot()

        position, trade = await execute_perps_open(
            db=db,
            client=client,
            bot=bot,
            product_id="BTC-PERP-INTX",
            side="BUY",
            size_usdc=100.0,
            current_price=100000.0,
            tp_pct=None,
            sl_pct=None,
        )

        assert position is not None
        assert position.tp_price is None
        assert position.sl_price is None


# ===========================================================================
# execute_perps_close
# ===========================================================================


class TestExecutePerpsClose:
    """Tests for execute_perps_close() — close perpetual futures positions."""

    @pytest.mark.asyncio
    async def test_happy_path_close_long_with_profit(self):
        """Happy path: close a profitable long position."""
        db = _make_db()
        client = _make_client()
        position = _make_position(
            direction="long",
            total_base_acquired=0.001,
            total_quote_spent=100.0,
            average_buy_price=100000.0,
            funding_fees_total=0.5,
        )

        # Close at 105000 -> profit = (105000 - 100000) * 0.001 = 5.0 - 0.5 fees = 4.5
        success, profit, pct = await execute_perps_close(
            db=db,
            client=client,
            position=position,
            current_price=105000.0,
            reason="signal",
        )

        assert success is True
        assert profit == pytest.approx(4.5)
        assert pct == pytest.approx(4.5 / 100.0 * 100)
        assert position.status == "closed"
        assert position.exit_reason == "signal"
        assert position.profit_usd == pytest.approx(4.5)
        # Bracket orders should be cleared
        assert position.tp_order_id is None
        assert position.sl_order_id is None
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_close_short_with_profit(self):
        """Happy path: close a profitable short position."""
        db = _make_db()
        client = _make_client()
        position = _make_position(
            direction="short",
            total_base_acquired=0.0,
            short_total_sold_base=0.001,
            short_total_sold_quote=100.0,
            short_average_sell_price=100000.0,
            funding_fees_total=0.0,
        )

        # Close at 95000 -> profit = (100000 - 95000) * 0.001 = 5.0
        success, profit, pct = await execute_perps_close(
            db=db,
            client=client,
            position=position,
            current_price=95000.0,
            reason="tp_hit",
        )

        assert success is True
        assert profit == pytest.approx(5.0)
        assert pct == pytest.approx(5.0)
        assert position.status == "closed"
        assert position.exit_reason == "tp_hit"

    @pytest.mark.asyncio
    async def test_close_cancels_bracket_orders(self):
        """Edge case: bracket TP/SL orders are cancelled before closing."""
        db = _make_db()
        client = _make_client()
        position = _make_position(
            direction="long",
            total_base_acquired=0.001,
            total_quote_spent=100.0,
            average_buy_price=100000.0,
            tp_order_id="tp-order-001",
            sl_order_id="sl-order-002",
        )

        success, _, _ = await execute_perps_close(
            db=db,
            client=client,
            position=position,
            current_price=105000.0,
        )

        assert success is True
        # Both TP and SL orders should have been cancelled
        assert client.cancel_order.await_count == 2

    @pytest.mark.asyncio
    async def test_close_during_shutdown_returns_false(self, _patch_shutdown):
        """Failure: close rejected during shutdown."""
        _patch_shutdown.is_shutting_down = True

        db = _make_db()
        client = _make_client()
        position = _make_position()

        success, profit, pct = await execute_perps_close(
            db=db,
            client=client,
            position=position,
            current_price=105000.0,
        )

        assert success is False
        assert profit == 0.0
        assert pct == 0.0

    @pytest.mark.asyncio
    async def test_close_exchange_error_returns_false(self):
        """Failure: exchange returns no order_id on close."""
        db = _make_db()
        client = _make_client()
        client.close_perps_position = AsyncMock(return_value={
            "success_response": {"order_id": ""},
            "error_response": {"message": "Position already closed"},
        })
        position = _make_position(direction="long", total_base_acquired=0.001)

        success, profit, pct = await execute_perps_close(
            db=db,
            client=client,
            position=position,
            current_price=105000.0,
        )

        assert success is False
        assert profit == 0.0

    @pytest.mark.asyncio
    async def test_close_exception_returns_false_and_rolls_back(self):
        """Failure: exception during close operation triggers rollback."""
        db = _make_db()
        client = _make_client()
        client.close_perps_position = AsyncMock(side_effect=Exception("Connection lost"))
        position = _make_position(direction="long", total_base_acquired=0.001)

        success, profit, pct = await execute_perps_close(
            db=db,
            client=client,
            position=position,
            current_price=105000.0,
        )

        assert success is False
        db.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_close_with_funding_fees_deducted(self):
        """Edge case: accumulated funding fees are deducted from profit."""
        db = _make_db()
        client = _make_client()
        position = _make_position(
            direction="long",
            total_base_acquired=0.01,
            total_quote_spent=1000.0,
            average_buy_price=100000.0,
            funding_fees_total=50.0,  # Significant funding fees
        )

        # Close at 110000 -> gross = (110000 - 100000) * 0.01 = 100 - 50 fees = 50
        success, profit, pct = await execute_perps_close(
            db=db,
            client=client,
            position=position,
            current_price=110000.0,
        )

        assert success is True
        assert profit == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_close_bracket_cancel_failure_continues(self):
        """Edge case: failing to cancel bracket orders does not block close."""
        db = _make_db()
        client = _make_client()
        client.cancel_order = AsyncMock(side_effect=Exception("Already cancelled"))
        position = _make_position(
            direction="long",
            total_base_acquired=0.001,
            total_quote_spent=100.0,
            average_buy_price=100000.0,
            tp_order_id="tp-001",
            sl_order_id="sl-002",
        )

        success, _, _ = await execute_perps_close(
            db=db,
            client=client,
            position=position,
            current_price=105000.0,
        )

        # Close should still succeed even if bracket cancel fails
        assert success is True
