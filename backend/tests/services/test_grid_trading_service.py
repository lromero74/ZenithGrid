"""Tests for services/grid_trading_service.py"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.grid_trading_service import (
    calculate_new_range_after_breakout,
    cancel_grid_orders,
)


# ---------------------------------------------------------------------------
# calculate_new_range_after_breakout (pure function — no async)
# ---------------------------------------------------------------------------

class TestCalculateNewRangeAfterBreakout:
    def test_upward_breakout_centers_on_current_price(self):
        new_upper, new_lower = calculate_new_range_after_breakout(
            old_upper=55.0, old_lower=45.0,
            current_price=58.0,
            breakout_direction="upward",
            range_expansion_factor=1.2,
        )

        # old_width = 10, new_width = 12
        # new_upper = 58 + 6 = 64
        # new_lower = 58 - 6 = 52
        assert new_upper == pytest.approx(64.0)
        assert new_lower == pytest.approx(52.0)

    def test_downward_breakout_centers_on_current_price(self):
        new_upper, new_lower = calculate_new_range_after_breakout(
            old_upper=55.0, old_lower=45.0,
            current_price=40.0,
            breakout_direction="downward",
            range_expansion_factor=1.0,
        )

        # old_width = 10, new_width = 10
        # new_upper = 40 + 5 = 45
        # new_lower = 40 - 5 = 35
        assert new_upper == pytest.approx(45.0)
        assert new_lower == pytest.approx(35.0)

    def test_range_expansion_factor(self):
        new_upper, new_lower = calculate_new_range_after_breakout(
            old_upper=100.0, old_lower=80.0,
            current_price=110.0,
            breakout_direction="upward",
            range_expansion_factor=1.5,
        )

        # old_width = 20, new_width = 30
        # new_upper = 110 + 15 = 125
        # new_lower = 110 - 15 = 95
        assert new_upper == pytest.approx(125.0)
        assert new_lower == pytest.approx(95.0)

    def test_lower_bound_stays_positive(self):
        """Lower bound is at least 30% of current price"""
        new_upper, new_lower = calculate_new_range_after_breakout(
            old_upper=10.0, old_lower=0.1,
            current_price=2.0,
            breakout_direction="downward",
            range_expansion_factor=5.0,
        )

        # old_width = 9.9, new_width = 49.5
        # raw_lower = 2.0 - 24.75 = -22.75 → clamped to 2.0 * 0.3 = 0.6
        assert new_lower >= 0
        assert new_lower == pytest.approx(max(2.0 - 49.5 / 2, 2.0 * 0.3))

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="Invalid breakout_direction"):
            calculate_new_range_after_breakout(
                old_upper=100.0, old_lower=80.0,
                current_price=90.0,
                breakout_direction="sideways",
            )

    def test_no_expansion(self):
        new_upper, new_lower = calculate_new_range_after_breakout(
            old_upper=60.0, old_lower=40.0,
            current_price=65.0,
            breakout_direction="upward",
            range_expansion_factor=1.0,
        )

        # old_width = 20, new_width = 20
        # new_upper = 65 + 10 = 75
        # new_lower = 65 - 10 = 55
        assert new_upper == pytest.approx(75.0)
        assert new_lower == pytest.approx(55.0)


# ---------------------------------------------------------------------------
# cancel_grid_orders
# ---------------------------------------------------------------------------

class TestCancelGridOrders:
    @pytest.mark.asyncio
    async def test_cancels_all_pending_orders(self):
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        position = MagicMock()
        position.id = 10
        exchange = AsyncMock()

        order1 = MagicMock()
        order1.order_id = "order-111"
        order1.status = "pending"
        order2 = MagicMock()
        order2.order_id = "order-222"
        order2.status = "pending"

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [order1, order2]
        db.execute.return_value = result_mock

        count = await cancel_grid_orders(bot, position, exchange, db, reason="test")

        assert count == 2
        assert exchange.cancel_order.call_count == 2
        assert order1.status == "cancelled"
        assert order2.status == "cancelled"
        assert order1.reserved_amount_quote == 0.0
        assert order2.reserved_amount_base == 0.0
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_pending_orders(self):
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        position = MagicMock()
        position.id = 10
        exchange = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute.return_value = result_mock

        count = await cancel_grid_orders(bot, position, exchange, db, reason="test")

        assert count == 0
        exchange.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_exchange_cancel_failure_still_marks_cancelled(self):
        """Even if exchange cancel fails, mark order as cancelled in DB to release capital"""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        position = MagicMock()
        position.id = 10
        exchange = AsyncMock()
        exchange.cancel_order.side_effect = Exception("Exchange unavailable")

        order = MagicMock()
        order.order_id = "order-333"
        order.status = "pending"

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [order]
        db.execute.return_value = result_mock

        count = await cancel_grid_orders(bot, position, exchange, db, reason="test")

        assert count == 0  # Exchange cancel failed, not counted as cancelled
        assert order.status == "cancelled"  # But DB status is updated
        assert order.reserved_amount_quote == 0.0
