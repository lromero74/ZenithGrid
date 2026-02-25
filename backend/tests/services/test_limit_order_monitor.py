"""
Tests for backend/app/services/limit_order_monitor.py

Tests the LimitOrderMonitor service that monitors pending limit orders
and updates positions when they fill.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.limit_order_monitor import LimitOrderMonitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_position(**overrides):
    """Create a mock Position with sensible defaults."""
    pos = MagicMock()
    pos.id = overrides.get("id", 1)
    pos.bot_id = overrides.get("bot_id", 10)
    pos.user_id = overrides.get("user_id", 1)
    pos.product_id = overrides.get("product_id", "ETH-BTC")
    pos.status = overrides.get("status", "open")
    pos.limit_close_order_id = overrides.get("limit_close_order_id", "order-abc")
    pos.closing_via_limit = overrides.get("closing_via_limit", True)
    pos.total_quote_spent = overrides.get("total_quote_spent", 0.01)
    pos.total_base_acquired = overrides.get("total_base_acquired", 5.0)
    pos.total_quote_received = overrides.get("total_quote_received", None)
    pos.initial_quote_balance = overrides.get("initial_quote_balance", 0.01)
    pos.profit_quote = overrides.get("profit_quote", None)
    pos.profit_percentage = overrides.get("profit_percentage", None)
    pos.direction = overrides.get("direction", "long")
    pos.get_quote_currency = MagicMock(return_value=overrides.get("quote_currency", "BTC"))
    return pos


def _make_pending_order(**overrides):
    """Create a mock PendingOrder with sensible defaults."""
    po = MagicMock()
    po.order_id = overrides.get("order_id", "order-abc")
    po.position_id = overrides.get("position_id", 1)
    po.status = overrides.get("status", "pending")
    po.base_amount = overrides.get("base_amount", 5.0)
    po.filled_base_amount = overrides.get("filled_base_amount", None)
    po.filled_quote_amount = overrides.get("filled_quote_amount", None)
    po.remaining_base_amount = overrides.get("remaining_base_amount", None)
    po.filled_price = overrides.get("filled_price", None)
    po.limit_price = overrides.get("limit_price", 0.002)
    po.is_manual = overrides.get("is_manual", False)
    po.time_in_force = overrides.get("time_in_force", "gtc")
    po.created_at = overrides.get("created_at", datetime.utcnow() - timedelta(seconds=30))
    return po


# ---------------------------------------------------------------------------
# check_single_position_limit_order tests
# ---------------------------------------------------------------------------

class TestCheckSinglePositionLimitOrder:
    """Tests for LimitOrderMonitor.check_single_position_limit_order()."""

    @pytest.mark.asyncio
    async def test_no_order_id_returns_early(self):
        """Edge case: position has no limit_close_order_id."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position(limit_close_order_id=None)

        await monitor.check_single_position_limit_order(position)

        # Should not query DB or exchange
        db.execute.assert_not_awaited()
        exchange.get_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_pending_order_in_db_returns_early(self):
        """Edge case: no PendingOrder record found for the order ID."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()

        await monitor.check_single_position_limit_order(position)

        exchange.get_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_filled_order_triggers_completion(self):
        """Happy path: FILLED order triggers _process_order_completion."""
        db = AsyncMock()
        pending_order = _make_pending_order()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = pending_order
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        exchange.get_order = AsyncMock(return_value={
            "status": "FILLED",
            "filled_size": "5.0",
            "filled_value": "0.012",
        })

        monitor = LimitOrderMonitor(db, exchange)
        with patch.object(monitor, '_process_order_completion', new_callable=AsyncMock) as mock_complete:
            position = _make_position()
            await monitor.check_single_position_limit_order(position)
            mock_complete.assert_awaited_once_with(position, pending_order, exchange.get_order.return_value, "FILLED")

    @pytest.mark.asyncio
    async def test_open_order_checks_partial_fills_and_bid_fallback(self):
        """Happy path: OPEN order triggers partial fill check and bid fallback."""
        db = AsyncMock()
        pending_order = _make_pending_order()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = pending_order
        db.execute = AsyncMock(return_value=mock_result)

        order_data = {
            "status": "OPEN",
            "filled_size": "0",
            "filled_value": "0",
        }
        exchange = AsyncMock()
        exchange.get_order = AsyncMock(return_value=order_data)

        monitor = LimitOrderMonitor(db, exchange)
        with patch.object(monitor, '_process_partial_fills', new_callable=AsyncMock) as mock_partial, \
             patch.object(monitor, '_check_bid_fallback', new_callable=AsyncMock) as mock_fallback:
            position = _make_position()
            await monitor.check_single_position_limit_order(position)
            mock_partial.assert_awaited_once()
            mock_fallback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exchange_returns_none_order_data(self):
        """Failure: exchange returns None for order data."""
        db = AsyncMock()
        pending_order = _make_pending_order()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = pending_order
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        exchange.get_order = AsyncMock(return_value=None)

        monitor = LimitOrderMonitor(db, exchange)
        position = _make_position()

        # Should not raise
        await monitor.check_single_position_limit_order(position)


# ---------------------------------------------------------------------------
# _process_partial_fills tests
# ---------------------------------------------------------------------------

class TestProcessPartialFills:
    """Tests for LimitOrderMonitor._process_partial_fills()."""

    @pytest.mark.asyncio
    @patch('app.services.limit_order_monitor.ws_manager')
    async def test_new_partial_fill_creates_trade(self, mock_ws):
        """Happy path: new partial fill detected, trade created."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position(total_quote_received=None, total_quote_spent=0.01)
        pending_order = _make_pending_order(
            base_amount=5.0,
            filled_base_amount=0,  # No prior fills
        )

        order_data = {
            "filled_size": "2.5",
            "filled_value": "0.005",
        }

        mock_ws.broadcast_order_fill = AsyncMock()

        await monitor._process_partial_fills(position, pending_order, order_data)

        # Trade should have been added
        db.add.assert_called_once()
        trade = db.add.call_args[0][0]
        assert trade.side == "sell"
        assert trade.base_amount == pytest.approx(2.5)
        assert trade.trade_type == "limit_close_partial"

        # Pending order should be updated
        assert pending_order.filled_base_amount == pytest.approx(2.5)
        assert pending_order.status == "partially_filled"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('app.services.limit_order_monitor.ws_manager')
    async def test_no_new_fills_does_not_create_trade(self, mock_ws):
        """Edge case: filled_size unchanged from previous check."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()
        pending_order = _make_pending_order(
            base_amount=5.0,
            filled_base_amount=2.5,  # Already recorded
        )

        order_data = {
            "filled_size": "2.5",  # Same as before
            "filled_value": "0.005",
        }

        await monitor._process_partial_fills(position, pending_order, order_data)

        # No trade should be added
        db.add.assert_not_called()

    @pytest.mark.asyncio
    @patch('app.services.limit_order_monitor.ws_manager')
    async def test_zero_filled_size_does_nothing(self, mock_ws):
        """Edge case: zero filled size, no action taken."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()
        pending_order = _make_pending_order(filled_base_amount=0)

        order_data = {
            "filled_size": "0",
            "filled_value": "0",
        }

        await monitor._process_partial_fills(position, pending_order, order_data)

        db.add.assert_not_called()
        db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# _check_bid_fallback tests
# ---------------------------------------------------------------------------

class TestCheckBidFallback:
    """Tests for LimitOrderMonitor._check_bid_fallback()."""

    @pytest.mark.asyncio
    async def test_manual_order_skips_fallback(self):
        """Edge case: manual orders should never be auto-adjusted."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()
        pending_order = _make_pending_order(is_manual=True)

        await monitor._check_bid_fallback(position, pending_order, {"filled_size": "0"})

        # Should not query exchange for ticker
        exchange.get_ticker.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fallback_not_enabled_returns_early(self):
        """Edge case: limit_order_fallback_enabled is False."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()
        pending_order = _make_pending_order(
            created_at=datetime.utcnow() - timedelta(seconds=120),
        )

        # Mock bot query
        mock_bot = MagicMock()
        mock_bot.strategy_config = {"limit_order_fallback_enabled": False}
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_bot
        db.execute = AsyncMock(return_value=mock_result)

        await monitor._check_bid_fallback(position, pending_order, {"filled_size": "0"})

        exchange.get_ticker.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fallback_skipped_when_not_timed_out(self):
        """Edge case: order not yet timed out."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()
        pending_order = _make_pending_order(
            created_at=datetime.utcnow() - timedelta(seconds=10),  # Only 10 seconds
        )

        mock_bot = MagicMock()
        mock_bot.strategy_config = {"limit_order_fallback_enabled": True, "limit_order_timeout_seconds": 60}
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_bot
        db.execute = AsyncMock(return_value=mock_result)

        position.strategy_config_snapshot = {"min_profit_for_conditions": 0.5}

        await monitor._check_bid_fallback(position, pending_order, {"filled_size": "0"})

        exchange.get_ticker.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fallback_skipped_for_partially_filled_order(self):
        """Edge case: partially filled order should not be adjusted."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()
        pending_order = _make_pending_order(
            created_at=datetime.utcnow() - timedelta(seconds=120),
        )

        mock_bot = MagicMock()
        mock_bot.strategy_config = {"limit_order_fallback_enabled": True, "limit_order_timeout_seconds": 60}
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_bot
        db.execute = AsyncMock(return_value=mock_result)

        position.strategy_config_snapshot = {"min_profit_for_conditions": 0.5}

        order_data = {"filled_size": "1.0"}  # Partially filled
        await monitor._check_bid_fallback(position, pending_order, order_data)

        exchange.get_ticker.assert_not_awaited()


# ---------------------------------------------------------------------------
# _process_order_completion tests
# ---------------------------------------------------------------------------

class TestProcessOrderCompletion:
    """Tests for LimitOrderMonitor._process_order_completion()."""

    @pytest.mark.asyncio
    @patch('app.services.limit_order_monitor.ws_manager')
    async def test_filled_order_closes_position(self, mock_ws):
        """Happy path: FILLED order closes position and calculates profit."""
        db = AsyncMock()
        exchange = AsyncMock()
        exchange.get_btc_usd_price = AsyncMock(return_value=50000.0)
        monitor = LimitOrderMonitor(db, exchange)

        mock_ws.broadcast_order_fill = AsyncMock()

        position = _make_position(
            total_quote_spent=0.01,
            total_quote_received=None,
            total_base_acquired=5.0,
            quote_currency="BTC",
        )
        pending_order = _make_pending_order(filled_base_amount=0)

        order_data = {
            "filled_size": "5.0",
            "filled_value": "0.012",
        }

        # Mock the bot query for returning reserved balance
        mock_bot = MagicMock()
        mock_bot.reserved_btc_balance = 0.05
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_bot
        db.execute = AsyncMock(return_value=mock_result)

        await monitor._process_order_completion(position, pending_order, order_data, "FILLED")

        assert position.status == "closed"
        assert position.closing_via_limit is False
        assert position.limit_close_order_id is None
        assert pending_order.status == "filled"
        assert position.profit_quote == pytest.approx(0.002)  # 0.012 - 0.01
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    @patch('app.services.limit_order_monitor.ws_manager')
    async def test_cancelled_order_resets_position_flags(self, mock_ws):
        """Happy path: CANCELLED order resets closing flags."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()
        pending_order = _make_pending_order()

        order_data = {"filled_size": "0", "filled_value": "0"}

        await monitor._process_order_completion(position, pending_order, order_data, "CANCELLED")

        assert position.closing_via_limit is False
        assert position.limit_close_order_id is None
        assert pending_order.status == "cancelled"
        assert pending_order.canceled_at is not None
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    @patch('app.services.limit_order_monitor.ws_manager')
    async def test_expired_order_resets_position_flags(self, mock_ws):
        """Happy path: EXPIRED order also resets flags."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()
        pending_order = _make_pending_order()

        order_data = {"filled_size": "0", "filled_value": "0"}

        await monitor._process_order_completion(position, pending_order, order_data, "EXPIRED")

        assert position.closing_via_limit is False
        assert pending_order.status == "expired"
        db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# _cancel_and_replace_order tests
# ---------------------------------------------------------------------------

class TestCancelAndReplaceOrder:
    """Tests for LimitOrderMonitor._cancel_and_replace_order()."""

    @pytest.mark.asyncio
    async def test_successful_cancel_and_replace(self):
        """Happy path: cancel succeeds, new order placed at bid."""
        db = AsyncMock()
        exchange = AsyncMock()
        exchange.cancel_order = AsyncMock(return_value={"success": True})
        exchange.get_order = AsyncMock(return_value={"status": "CANCELLED", "filled_size": "0"})
        exchange.create_limit_order = AsyncMock(return_value={
            "success_response": {"order_id": "new-order-999"},
        })
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position(total_base_acquired=5.0)
        pending_order = _make_pending_order(
            remaining_base_amount=5.0,
            base_amount=5.0,
        )

        await monitor._cancel_and_replace_order(position, pending_order, "0.0025", 0.0025)

        exchange.cancel_order.assert_awaited_once()
        exchange.create_limit_order.assert_awaited_once()
        assert pending_order.order_id == "new-order-999"
        assert pending_order.limit_price == pytest.approx(0.0025)
        assert position.limit_close_order_id == "new-order-999"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_cancel_fails_raises_exception(self):
        """Failure: cancel returns failure, raises exception."""
        db = AsyncMock()
        exchange = AsyncMock()
        exchange.cancel_order = AsyncMock(return_value={"success": False, "error": "not found"})
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()
        pending_order = _make_pending_order(remaining_base_amount=5.0)

        with pytest.raises(Exception, match="Cancel failed"):
            await monitor._cancel_and_replace_order(position, pending_order, "0.0025", 0.0025)

    @pytest.mark.asyncio
    async def test_replacement_failure_clears_limit_flags(self):
        """Failure: replacement order fails, position flags cleared for re-evaluation."""
        db = AsyncMock()
        exchange = AsyncMock()
        exchange.cancel_order = AsyncMock(return_value={"success": True})
        exchange.get_order = AsyncMock(return_value={"status": "CANCELLED", "filled_size": "0"})
        exchange.create_limit_order = AsyncMock(side_effect=Exception("API timeout"))
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()
        pending_order = _make_pending_order(remaining_base_amount=5.0)

        with pytest.raises(Exception, match="API timeout"):
            await monitor._cancel_and_replace_order(position, pending_order, "0.0025", 0.0025)

        assert position.closing_via_limit is False
        assert position.limit_close_order_id is None
        assert pending_order.status == "cancelled"

    @pytest.mark.asyncio
    @patch.object(LimitOrderMonitor, '_process_order_completion', new_callable=AsyncMock)
    async def test_cancel_detects_filled_order(self, mock_complete):
        """Edge case: cancelled order was actually filled between check and cancel."""
        db = AsyncMock()
        exchange = AsyncMock()
        exchange.cancel_order = AsyncMock(return_value={"success": True})
        exchange.get_order = AsyncMock(return_value={
            "status": "FILLED",
            "filled_size": "5.0",
            "filled_value": "0.012",
        })
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position()
        pending_order = _make_pending_order(remaining_base_amount=5.0)

        await monitor._cancel_and_replace_order(position, pending_order, "0.0025", 0.0025)

        # Should process as fill, not place a new order
        mock_complete.assert_awaited_once()
        exchange.create_limit_order.assert_not_awaited()


# ---------------------------------------------------------------------------
# Paper order auto-resolution tests
# ---------------------------------------------------------------------------

class TestPaperOrderAutoResolution:
    """Tests for automatic resolution of paper trading orders."""

    @pytest.mark.asyncio
    @patch('app.services.limit_order_monitor.ws_manager')
    async def test_paper_order_auto_resolved_as_filled(self, mock_ws):
        """Happy path: paper order detected and auto-resolved via _process_order_completion."""
        db = AsyncMock()
        pending_order = _make_pending_order(
            order_id="paper-abc123",
            base_amount=5.0,
            limit_price=0.002,
            filled_base_amount=0,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = pending_order
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        exchange.get_btc_usd_price = AsyncMock(return_value=50000.0)
        mock_ws.broadcast_order_fill = AsyncMock()

        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position(
            limit_close_order_id="paper-abc123",
            total_quote_spent=0.01,
            total_base_acquired=5.0,
            total_quote_received=None,
        )

        # Mock bot query for reserved balance return
        mock_bot = MagicMock()
        mock_bot.reserved_btc_balance = 0.05
        bot_result = MagicMock()
        bot_result.scalars.return_value.first.return_value = mock_bot
        db.execute = AsyncMock(side_effect=[mock_result, bot_result])

        await monitor.check_single_position_limit_order(position)

        # Should NOT call exchange.get_order (paper orders skip exchange check)
        exchange.get_order.assert_not_awaited()

        # Position should be closed
        assert position.status == "closed"
        assert position.closing_via_limit is False
        assert position.limit_close_order_id is None

        # Pending order should be filled
        assert pending_order.status == "filled"

    @pytest.mark.asyncio
    async def test_real_order_not_auto_resolved(self):
        """Edge case: real order (no paper- prefix) goes through normal flow."""
        db = AsyncMock()
        pending_order = _make_pending_order(order_id="real-order-123")
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = pending_order
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        exchange.get_order = AsyncMock(return_value={
            "status": "OPEN",
            "filled_size": "0",
            "filled_value": "0",
        })

        monitor = LimitOrderMonitor(db, exchange)
        with patch.object(monitor, '_process_partial_fills', new_callable=AsyncMock), \
             patch.object(monitor, '_check_bid_fallback', new_callable=AsyncMock):
            position = _make_position(limit_close_order_id="real-order-123")
            await monitor.check_single_position_limit_order(position)

            # SHOULD call exchange.get_order for real orders
            exchange.get_order.assert_awaited_once_with("real-order-123")

    @pytest.mark.asyncio
    @patch('app.services.limit_order_monitor.ws_manager')
    async def test_paper_order_uses_limit_price_for_fill(self, mock_ws):
        """Paper order auto-resolution uses limit_price * base_amount as fill value."""
        db = AsyncMock()
        pending_order = _make_pending_order(
            order_id="paper-xyz",
            base_amount=10.0,
            limit_price=0.003,
            filled_base_amount=0,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = pending_order
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        exchange.get_btc_usd_price = AsyncMock(return_value=50000.0)
        mock_ws.broadcast_order_fill = AsyncMock()

        monitor = LimitOrderMonitor(db, exchange)
        with patch.object(monitor, '_process_order_completion', new_callable=AsyncMock) as mock_complete:
            position = _make_position(
                limit_close_order_id="paper-xyz",
                total_base_acquired=10.0,
            )
            await monitor.check_single_position_limit_order(position)

            # Should call _process_order_completion with synthetic data
            mock_complete.assert_awaited_once()
            call_args = mock_complete.call_args
            order_data = call_args[0][2]  # Third positional arg
            assert float(order_data["filled_size"]) == pytest.approx(10.0)
            assert float(order_data["filled_value"]) == pytest.approx(0.03)  # 10.0 * 0.003
            assert call_args[0][3] == "FILLED"

    @pytest.mark.asyncio
    async def test_paper_order_no_pending_record_clears_flags(self):
        """Edge case: paper order with no PendingOrder record still returns early."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None  # No pending order
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        monitor = LimitOrderMonitor(db, exchange)

        position = _make_position(limit_close_order_id="paper-missing")
        await monitor.check_single_position_limit_order(position)

        # Should return early (no pending order)
        exchange.get_order.assert_not_awaited()


# ---------------------------------------------------------------------------
# sweep_orphaned_pending_orders tests
# ---------------------------------------------------------------------------

class TestSweepOrphanedPendingOrders:
    """Tests for the sweep_orphaned_pending_orders function."""

    @pytest.mark.asyncio
    async def test_sweep_marks_orphaned_records(self):
        """Happy path: pending orders with closed positions get marked orphaned."""
        from app.services.limit_order_monitor import sweep_orphaned_pending_orders

        po1 = _make_pending_order(order_id="order-1", status="pending")
        po2 = _make_pending_order(order_id="order-2", status="pending")

        db = AsyncMock()
        mock_result = MagicMock()
        # Return tuples of (PendingOrder, position_status)
        mock_result.all.return_value = [(po1, "closed"), (po2, "cancelled")]
        db.execute = AsyncMock(return_value=mock_result)

        count = await sweep_orphaned_pending_orders(db)

        assert count == 2
        assert po1.status == "orphaned"
        assert po2.status == "orphaned"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sweep_no_orphans_found(self):
        """Edge case: no orphaned records, nothing to clean up."""
        from app.services.limit_order_monitor import sweep_orphaned_pending_orders

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        count = await sweep_orphaned_pending_orders(db)

        assert count == 0
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sweep_handles_db_error(self):
        """Failure: DB error is caught and logged, does not raise."""
        from app.services.limit_order_monitor import sweep_orphaned_pending_orders

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB connection error"))

        count = await sweep_orphaned_pending_orders(db)

        assert count == 0
