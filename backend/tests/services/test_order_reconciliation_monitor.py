"""
Tests for backend/app/services/order_reconciliation_monitor.py

Tests the OrderReconciliationMonitor and MissingOrderDetector services
that detect and fix positions with missing fill data.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.order_reconciliation_monitor import (
    OrderReconciliationMonitor,
    MissingOrderDetector,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_position(**overrides):
    """Create a mock Position with sensible defaults."""
    pos = MagicMock()
    pos.id = overrides.get("id", 1)
    pos.account_id = overrides.get("account_id", 1)
    pos.product_id = overrides.get("product_id", "ETH-BTC")
    pos.status = overrides.get("status", "open")
    pos.total_base_acquired = overrides.get("total_base_acquired", 0)
    pos.total_quote_spent = overrides.get("total_quote_spent", 0.0)
    pos.average_buy_price = overrides.get("average_buy_price", 0.0)
    pos.opened_at = overrides.get("opened_at", datetime.utcnow())
    pos.closed_at = overrides.get("closed_at", None)
    pos.last_error_message = overrides.get("last_error_message", None)
    pos.last_error_timestamp = overrides.get("last_error_timestamp", None)
    return pos


def _make_trade(**overrides):
    """Create a mock Trade with sensible defaults."""
    trade = MagicMock()
    trade.id = overrides.get("id", 1)
    trade.position_id = overrides.get("position_id", 1)
    trade.order_id = overrides.get("order_id", "order-abc")
    trade.side = overrides.get("side", "buy")
    trade.trade_type = overrides.get("trade_type", "initial")
    trade.base_amount = overrides.get("base_amount", 0)
    trade.quote_amount = overrides.get("quote_amount", 0)
    trade.price = overrides.get("price", 0.0)
    return trade


# ---------------------------------------------------------------------------
# OrderReconciliationMonitor.__init__ tests
# ---------------------------------------------------------------------------

class TestOrderReconciliationMonitorInit:
    """Tests for OrderReconciliationMonitor initialization."""

    def test_init_with_defaults(self):
        """Happy path: monitor initializes with expected defaults."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = OrderReconciliationMonitor(db, exchange)
        assert monitor.db is db
        assert monitor.exchange is exchange
        assert monitor.account_id is None

    def test_init_with_account_id(self):
        """Happy path: monitor initializes with specific account_id."""
        db = AsyncMock()
        exchange = AsyncMock()
        monitor = OrderReconciliationMonitor(db, exchange, account_id=42)
        assert monitor.account_id == 42


# ---------------------------------------------------------------------------
# check_and_fix_orphaned_positions tests
# ---------------------------------------------------------------------------

class TestCheckAndFixOrphanedPositions:
    """Tests for OrderReconciliationMonitor.check_and_fix_orphaned_positions()."""

    @pytest.mark.asyncio
    async def test_no_orphaned_positions_found(self):
        """Edge case: no orphaned positions exist."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        monitor = OrderReconciliationMonitor(db, exchange)

        await monitor.check_and_fix_orphaned_positions()
        # Should not call _reconcile_position
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_orphaned_position_triggers_reconciliation(self):
        """Happy path: orphaned position found, _reconcile_position called."""
        db = AsyncMock()
        orphaned_pos = _make_position(total_base_acquired=0)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [orphaned_pos]
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        monitor = OrderReconciliationMonitor(db, exchange)

        with patch.object(monitor, '_reconcile_position', new_callable=AsyncMock) as mock_reconcile:
            await monitor.check_and_fix_orphaned_positions()
            mock_reconcile.assert_awaited_once_with(orphaned_pos)

    @pytest.mark.asyncio
    async def test_exception_caught_and_logged(self):
        """Failure: database error does not propagate."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB connection lost"))

        exchange = AsyncMock()
        monitor = OrderReconciliationMonitor(db, exchange)

        # Should not raise
        await monitor.check_and_fix_orphaned_positions()


# ---------------------------------------------------------------------------
# _reconcile_position tests
# ---------------------------------------------------------------------------

class TestReconcilePosition:
    """Tests for OrderReconciliationMonitor._reconcile_position()."""

    @pytest.mark.asyncio
    async def test_no_initial_trade_skips(self):
        """Edge case: position has no initial trade with order_id."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        monitor = OrderReconciliationMonitor(db, exchange)

        position = _make_position()
        await monitor._reconcile_position(position)

        exchange.get_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_trade_already_has_fill_data_skips(self):
        """Edge case: trade already has base_amount > 0, no reconciliation needed."""
        db = AsyncMock()
        trade = _make_trade(base_amount=5.0)  # Already has fill data
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = trade
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        monitor = OrderReconciliationMonitor(db, exchange)

        position = _make_position()
        await monitor._reconcile_position(position)

        exchange.get_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_filled_order_reconciles_position(self):
        """Happy path: exchange order is FILLED, position gets reconciled."""
        db = AsyncMock()
        trade = _make_trade(base_amount=0, order_id="order-xyz")  # No fill data
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = trade
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        exchange.get_order = AsyncMock(return_value={
            "status": "FILLED",
            "filled_size": "10.0",
            "filled_value": "0.025",
            "average_filled_price": "0.0025",
        })

        monitor = OrderReconciliationMonitor(db, exchange)
        position = _make_position()

        await monitor._reconcile_position(position)

        # Position should be updated
        assert position.total_base_acquired == pytest.approx(10.0)
        assert position.total_quote_spent == pytest.approx(0.025)
        assert position.average_buy_price == pytest.approx(0.0025)
        assert position.last_error_message is None
        assert position.last_error_timestamp is None

        # Trade should be updated
        assert trade.base_amount == pytest.approx(10.0)
        assert trade.quote_amount == pytest.approx(0.025)
        assert trade.price == pytest.approx(0.0025)

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancelled_order_with_no_fills_marks_failed(self):
        """Happy path: CANCELLED order with zero fills marks position as failed."""
        db = AsyncMock()
        trade = _make_trade(base_amount=0, order_id="order-cancelled")
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = trade
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        exchange.get_order = AsyncMock(return_value={
            "status": "CANCELLED",
            "filled_size": "0",
            "filled_value": "0",
            "average_filled_price": "0",
        })

        monitor = OrderReconciliationMonitor(db, exchange)
        position = _make_position()

        await monitor._reconcile_position(position)

        assert position.status == "failed"
        assert position.closed_at is not None
        assert "CANCELLED" in position.last_error_message
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pending_order_skips_reconciliation(self):
        """Edge case: order still PENDING, not ready for reconciliation."""
        db = AsyncMock()
        trade = _make_trade(base_amount=0, order_id="order-pending")
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = trade
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        exchange.get_order = AsyncMock(return_value={
            "status": "PENDING",
            "filled_size": "0",
            "filled_value": "0",
            "average_filled_price": "0",
        })

        monitor = OrderReconciliationMonitor(db, exchange)
        position = _make_position()

        await monitor._reconcile_position(position)

        # Position should NOT be updated
        assert position.total_base_acquired == 0
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_filled_status_zero_fills_logs_warning(self):
        """Edge case: FILLED status but zero filled_size -- cannot reconcile."""
        db = AsyncMock()
        trade = _make_trade(base_amount=0, order_id="order-weird")
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = trade
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        exchange.get_order = AsyncMock(return_value={
            "status": "FILLED",
            "filled_size": "0",
            "filled_value": "0",
            "average_filled_price": "0",
        })

        monitor = OrderReconciliationMonitor(db, exchange)
        position = _make_position()

        await monitor._reconcile_position(position)

        # Position should NOT be updated
        assert position.total_base_acquired == 0
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exchange_returns_none_skips(self):
        """Failure: exchange returns None for order data."""
        db = AsyncMock()
        trade = _make_trade(base_amount=0, order_id="order-none")
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = trade
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        exchange.get_order = AsyncMock(return_value=None)

        monitor = OrderReconciliationMonitor(db, exchange)
        position = _make_position()

        await monitor._reconcile_position(position)

        assert position.total_base_acquired == 0
        db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# MissingOrderDetector tests
# ---------------------------------------------------------------------------

class TestMissingOrderDetectorInit:
    """Tests for MissingOrderDetector initialization."""

    def test_init_defaults(self):
        """Happy path: detector initializes with expected defaults."""
        db = AsyncMock()
        exchange = AsyncMock()
        detector = MissingOrderDetector(db, exchange)
        assert detector.db is db
        assert detector.exchange is exchange
        assert detector.account_id is None
        assert detector.alert_threshold_btc == pytest.approx(0.0001)

    def test_init_with_account_id(self):
        """Happy path: detector scoped to a specific account."""
        db = AsyncMock()
        exchange = AsyncMock()
        detector = MissingOrderDetector(db, exchange, account_id=7)
        assert detector.account_id == 7


class TestCheckForMissingOrders:
    """Tests for MissingOrderDetector.check_for_missing_orders()."""

    @pytest.mark.asyncio
    async def test_no_positions_returns_early(self):
        """Edge case: no positions found, returns immediately."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        exchange = AsyncMock()
        detector = MissingOrderDetector(db, exchange)

        # Should not raise, should not call exchange
        await detector.check_for_missing_orders()
        exchange.list_orders.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_detects_missing_buy_order(self):
        """Happy path: detects a buy order on exchange not recorded in trades."""
        db = AsyncMock()

        # Position
        pos = _make_position(id=1, product_id="ETH-BTC")
        pos_result = MagicMock()
        pos_result.scalars.return_value.all.return_value = [pos]

        # Trade query returns empty (no recorded order_ids)
        trade_result = MagicMock()
        trade_result.fetchall.return_value = []

        # PendingOrder query returns empty
        pending_result = MagicMock()
        pending_result.fetchall.return_value = []

        db.execute = AsyncMock(side_effect=[pos_result, trade_result, pending_result])

        # Exchange has a filled buy order not in our DB
        exchange = AsyncMock()
        exchange.list_orders = AsyncMock(return_value=[
            {
                "order_id": "missing-buy-1",
                "filled_size": 2.5,
                "filled_value": 0.005,
                "side": "BUY",
                "created_time": "2025-01-01T12:00:00Z",
            }
        ])

        detector = MissingOrderDetector(db, exchange)

        # Should not raise (just logs warning)
        await detector.check_for_missing_orders()

    @pytest.mark.asyncio
    async def test_exception_caught_and_logged(self):
        """Failure: exception during detection does not propagate."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB error"))

        exchange = AsyncMock()
        detector = MissingOrderDetector(db, exchange)

        # Should not raise
        await detector.check_for_missing_orders()
