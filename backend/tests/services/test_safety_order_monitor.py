"""Tests for the safety-order reconciler (backend/app/services/safety_order_monitor.py).

A filled limit DCA safety order must ADD to its position (grow base/quote,
recompute average entry) and NEVER mark the position closed or book P&L —
unlike the close path in limit_order_monitor.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _short_position(**ov):
    """An open SHORT position mid-DCA."""
    return SimpleNamespace(
        id=ov.get("id", 100),
        user_id=ov.get("user_id", 10),
        product_id="BTC-USD",
        status="open",
        direction="short",
        closing_via_limit=False,
        limit_close_order_id=None,
        short_entry_price=ov.get("short_entry_price", 50000.0),
        short_average_sell_price=ov.get("short_average_sell_price", 50000.0),
        short_total_sold_base=ov.get("short_total_sold_base", 0.5),
        short_total_sold_quote=ov.get("short_total_sold_quote", 25000.0),
        last_error_message=None,
        last_error_timestamp=None,
    )


def _long_position(**ov):
    """An open LONG position mid-DCA."""
    return SimpleNamespace(
        id=ov.get("id", 200),
        user_id=ov.get("user_id", 10),
        product_id="ETH-USD",
        status="open",
        direction="long",
        closing_via_limit=False,
        limit_close_order_id=None,
        total_quote_spent=ov.get("total_quote_spent", 1000.0),
        total_base_acquired=ov.get("total_base_acquired", 0.5),
        average_buy_price=ov.get("average_buy_price", 2000.0),
        user_deal_number=ov.get("user_deal_number", 7),  # set → skips deal-number DB call
        last_error_message=None,
        last_error_timestamp=None,
    )


def _pending(side, **ov):
    return SimpleNamespace(
        id=ov.get("id", 1),
        position_id=ov.get("position_id", 100 if side == "SELL" else 200),
        bot_id=ov.get("bot_id", 1),
        order_id=ov.get("order_id", "limit-sell-101"),
        product_id="BTC-USD" if side == "SELL" else "ETH-USD",
        side=side,
        order_type="LIMIT",
        limit_price=ov.get("limit_price", 48000.0),
        base_amount=ov.get("base_amount", 0.3),
        quote_amount=ov.get("quote_amount", 14400.0),
        trade_type=ov.get("trade_type", "safety_order_1"),
        status=ov.get("status", "pending"),
        filled_base_amount=ov.get("filled_base_amount", None),
        filled_quote_amount=ov.get("filled_quote_amount", None),
        filled_price=ov.get("filled_price", None),
        filled_at=ov.get("filled_at", None),
        canceled_at=ov.get("canceled_at", None),
    )


def _exchange(order_data):
    ex = AsyncMock()
    ex.get_order = AsyncMock(return_value=order_data)
    return ex


# ---------------------------------------------------------------------------
# SELL add (short) — the headline case
# ---------------------------------------------------------------------------


class TestSafetyOrderReconciler:
    @pytest.mark.asyncio
    async def test_filled_sell_grows_short_and_never_closes(self):
        from app.services.safety_order_monitor import SafetyOrderMonitor
        db = _make_db()
        ex = _exchange({
            "status": "FILLED", "filled_size": "0.3", "filled_value": "14400.0",
        })
        pos = _short_position()
        po = _pending("SELL", base_amount=0.3)

        mon = SafetyOrderMonitor(db, ex)
        await mon.process_pending_safety_order(po, pos)

        # Short grew by the fill; average recomputed; position still OPEN
        assert pos.short_total_sold_base == pytest.approx(0.8)        # 0.5 + 0.3
        assert pos.short_total_sold_quote == pytest.approx(39400.0)   # 25000 + 14400
        assert pos.status == "open"
        assert pos.closing_via_limit is False
        # P&L must NOT be booked
        assert not hasattr(pos, "profit_quote") or getattr(pos, "profit_quote", None) is None
        # PendingOrder finalized
        assert po.status == "filled"
        assert po.filled_base_amount == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_filled_buy_grows_long(self):
        from app.services.safety_order_monitor import SafetyOrderMonitor
        db = _make_db()
        ex = _exchange({
            "status": "FILLED", "filled_size": "0.5", "filled_value": "900.0",
        })
        pos = _long_position()
        po = _pending("BUY", order_id="limit-buy-55", base_amount=0.5)

        mon = SafetyOrderMonitor(db, ex)
        await mon.process_pending_safety_order(po, pos)

        assert pos.total_base_acquired == pytest.approx(1.0)     # 0.5 + 0.5
        assert pos.total_quote_spent == pytest.approx(1900.0)    # 1000 + 900
        assert pos.average_buy_price == pytest.approx(1900.0)    # 1900 / 1.0
        assert pos.status == "open"
        assert po.status == "filled"

    @pytest.mark.asyncio
    async def test_partial_then_full_applies_only_deltas(self):
        from app.services.safety_order_monitor import SafetyOrderMonitor
        db = _make_db()
        pos = _short_position()
        po = _pending("SELL", base_amount=0.3)

        # First check: 0.1 of 0.3 filled
        mon = SafetyOrderMonitor(db, _exchange({
            "status": "OPEN", "filled_size": "0.1", "filled_value": "4800.0",
        }))
        await mon.process_pending_safety_order(po, pos)
        assert pos.short_total_sold_base == pytest.approx(0.6)    # 0.5 + 0.1
        assert po.status == "partially_filled"

        # Second check: now fully filled (0.3 total) — apply only the 0.2 delta
        mon2 = SafetyOrderMonitor(db, _exchange({
            "status": "FILLED", "filled_size": "0.3", "filled_value": "14400.0",
        }))
        await mon2.process_pending_safety_order(po, pos)
        assert pos.short_total_sold_base == pytest.approx(0.8)    # 0.6 + 0.2 (not +0.3)
        assert po.status == "filled"

    @pytest.mark.asyncio
    async def test_idempotent_on_repeat_filled(self):
        from app.services.safety_order_monitor import SafetyOrderMonitor
        db = _make_db()
        pos = _short_position()
        po = _pending("SELL", base_amount=0.3)
        order_data = {"status": "FILLED", "filled_size": "0.3", "filled_value": "14400.0"}

        mon = SafetyOrderMonitor(db, _exchange(order_data))
        await mon.process_pending_safety_order(po, pos)
        base_after_first = pos.short_total_sold_base

        # Re-run with identical fill data — must NOT double-apply
        mon2 = SafetyOrderMonitor(db, _exchange(order_data))
        await mon2.process_pending_safety_order(po, pos)
        assert pos.short_total_sold_base == pytest.approx(base_after_first)

    @pytest.mark.asyncio
    async def test_cancelled_leaves_position_untouched(self):
        from app.services.safety_order_monitor import SafetyOrderMonitor
        db = _make_db()
        pos = _short_position()
        po = _pending("SELL", base_amount=0.3)

        mon = SafetyOrderMonitor(db, _exchange({"status": "CANCELLED"}))
        await mon.process_pending_safety_order(po, pos)

        assert pos.short_total_sold_base == pytest.approx(0.5)    # unchanged
        assert pos.status == "open"
        assert po.status in ("cancelled", "canceled")

    @pytest.mark.asyncio
    async def test_paper_order_auto_resolves_as_filled(self):
        from app.services.safety_order_monitor import SafetyOrderMonitor
        db = _make_db()
        pos = _short_position()
        po = _pending("SELL", order_id="paper-xyz", base_amount=0.3, limit_price=48000.0)
        # exchange.get_order should NOT be needed for paper orders
        ex = AsyncMock()
        ex.get_order = AsyncMock(side_effect=AssertionError("paper orders must not hit get_order"))

        mon = SafetyOrderMonitor(db, ex)
        await mon.process_pending_safety_order(po, pos)

        assert pos.short_total_sold_base == pytest.approx(0.8)    # 0.5 + 0.3
        assert po.status == "filled"


# ---------------------------------------------------------------------------
# Query-scope guard (integration): the reconciler must select ONLY pending
# safety orders on OPEN positions — never close orders, never closed positions.
# ---------------------------------------------------------------------------


class TestSafetyOrderQueryScope:
    @pytest.mark.asyncio
    async def test_only_open_safety_orders_are_processed(self, db_session):
        from app.services import safety_order_monitor as som
        from app.models import Position, PendingOrder

        # open position with a SAFETY sell order → should be processed
        open_pos = Position(status="open", account_id=1, product_id="BTC-USD")
        # closed position with a safety order → must be ignored
        closed_pos = Position(status="closed", account_id=1, product_id="BTC-USD")
        db_session.add_all([open_pos, closed_pos])
        await db_session.flush()

        def _po(position_id, order_id, trade_type, status="pending"):
            return PendingOrder(
                position_id=position_id, bot_id=1, order_id=order_id,
                product_id="BTC-USD", side="SELL", order_type="LIMIT",
                limit_price=48000.0, quote_amount=14400.0,
                trade_type=trade_type, status=status,
            )

        db_session.add_all([
            _po(open_pos.id, "safety-open", "safety_order_1"),    # ✅ should process
            _po(open_pos.id, "close-open", "limit_close"),        # ❌ close order
            _po(closed_pos.id, "safety-closed", "safety_order_1"),  # ❌ closed position
        ])
        await db_session.flush()

        queried_order_ids = []

        async def _fake_get_order(order_id):
            queried_order_ids.append(order_id)
            return {"status": "OPEN", "filled_size": "0", "filled_value": "0"}

        fake_exchange = AsyncMock()
        fake_exchange.get_order = _fake_get_order

        async def _fake_get_client(db, account_id):
            return fake_exchange

        with __import__("unittest").mock.patch.object(
            som, "get_exchange_client_for_account", _fake_get_client
        ):
            await som.check_all_pending_safety_orders(db_session)

        # Only the open-position safety order should have been polled
        assert queried_order_ids == ["safety-open"]
