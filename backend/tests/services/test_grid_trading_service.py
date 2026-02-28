"""Tests for services/grid_trading_service.py

Covers:
- calculate_new_range_after_breakout: range calculation (pure)
- cancel_grid_orders: cancel pending orders on exchange + DB
- initialize_grid: place buy/sell grid orders
- handle_grid_order_fill: place opposite order after fill
- detect_and_handle_breakout: breakout detection and rebalance
- check_and_run_ai_optimization: AI optimization wrapper
- check_and_run_rotation: time-based rotation wrapper
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.grid_trading_service import (
    calculate_new_range_after_breakout,
    cancel_grid_orders,
    check_and_run_ai_optimization,
    check_and_run_rotation,
    detect_and_handle_breakout,
    handle_grid_order_fill,
    initialize_grid,
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


# ---------------------------------------------------------------------------
# initialize_grid
# ---------------------------------------------------------------------------


class TestInitializeGrid:
    """Tests for initialize_grid()."""

    @pytest.mark.asyncio
    async def test_long_mode_places_buy_orders_at_all_levels(self):
        """Happy path: long mode places buy orders at every level."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        bot.product_id = "BTC-USD"
        bot.bot_config = {"total_investment_quote": 1000.0}

        position = MagicMock()
        position.id = 10

        exchange = AsyncMock()
        exchange.create_limit_order.return_value = {
            "order_id": "order-abc-123"
        }

        grid_config = {
            "grid_mode": "long",
            "grid_type": "arithmetic",
            "upper_limit": 52000.0,
            "lower_limit": 48000.0,
            "levels": [48000.0, 49000.0, 50000.0, 51000.0, 52000.0],
        }

        with patch(
            "app.services.grid_trading_service.validate_order_size",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            result = await initialize_grid(
                bot=bot,
                position=position,
                exchange_client=exchange,
                db=db,
                grid_config=grid_config,
                current_price=50500.0,
            )

        assert result["total_buy_orders"] == 5
        assert result["total_sell_orders"] == 0
        assert result["grid_mode"] == "long"
        assert result["grid_type"] == "arithmetic"
        assert exchange.create_limit_order.call_count == 5
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_neutral_mode_places_buy_and_sell_orders(self):
        """Happy path: neutral mode places buy below and sell above price."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 2
        bot.product_id = "ETH-USD"
        bot.bot_config = {"total_investment_quote": 600.0}

        position = MagicMock()
        position.id = 20

        exchange = AsyncMock()
        exchange.create_limit_order.return_value = {
            "order_id": "order-def-456"
        }

        grid_config = {
            "grid_mode": "neutral",
            "grid_type": "arithmetic",
            "upper_limit": 3500.0,
            "lower_limit": 2500.0,
            "levels": [2600.0, 2800.0, 3000.0, 3200.0, 3400.0],
        }

        with patch(
            "app.services.grid_trading_service.validate_order_size",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            result = await initialize_grid(
                bot=bot,
                position=position,
                exchange_client=exchange,
                db=db,
                grid_config=grid_config,
                current_price=3000.0,
            )

        # Buy levels: 2600, 2800 (below 3000)
        # Sell levels: 3200, 3400 (above 3000)
        assert result["total_buy_orders"] == 2
        assert result["total_sell_orders"] == 2

    @pytest.mark.asyncio
    async def test_neutral_mode_no_buy_levels_raises(self):
        """Failure: neutral mode with no levels below current price raises."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 3
        bot.product_id = "BTC-USD"
        bot.bot_config = {"total_investment_quote": 100.0}

        position = MagicMock()
        position.id = 30

        exchange = AsyncMock()

        grid_config = {
            "grid_mode": "neutral",
            "grid_type": "arithmetic",
            "upper_limit": 60000.0,
            "lower_limit": 55000.0,
            "levels": [56000.0, 57000.0, 58000.0],
        }

        with pytest.raises(ValueError, match="No buy levels"):
            await initialize_grid(
                bot=bot,
                position=position,
                exchange_client=exchange,
                db=db,
                grid_config=grid_config,
                current_price=50000.0,  # All levels above current price
            )

    @pytest.mark.asyncio
    async def test_unsupported_grid_mode_raises(self):
        """Failure: unsupported grid mode raises ValueError."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 4
        bot.product_id = "BTC-USD"
        bot.bot_config = {"total_investment_quote": 100.0}

        position = MagicMock()
        position.id = 40

        exchange = AsyncMock()

        grid_config = {
            "grid_mode": "short",
            "grid_type": "arithmetic",
            "upper_limit": 60000.0,
            "lower_limit": 50000.0,
            "levels": [52000.0, 54000.0, 56000.0],
        }

        with pytest.raises(ValueError, match="Unsupported grid_mode"):
            await initialize_grid(
                bot=bot,
                position=position,
                exchange_client=exchange,
                db=db,
                grid_config=grid_config,
                current_price=55000.0,
            )

    @pytest.mark.asyncio
    async def test_skips_levels_below_minimum_order_size(self):
        """Edge case: levels below min order size are skipped with warning."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 5
        bot.product_id = "BTC-USD"
        bot.bot_config = {"total_investment_quote": 50.0}

        position = MagicMock()
        position.id = 50

        exchange = AsyncMock()
        exchange.create_limit_order.return_value = {"order_id": "order-ok"}

        grid_config = {
            "grid_mode": "long",
            "grid_type": "arithmetic",
            "upper_limit": 55000.0,
            "lower_limit": 50000.0,
            "levels": [50000.0, 51000.0, 52000.0],
        }

        # First level fails validation, rest pass
        call_count = 0

        async def mock_validate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (False, "Below minimum")
            return (True, None)

        with patch(
            "app.services.grid_trading_service.validate_order_size",
            side_effect=mock_validate,
        ):
            result = await initialize_grid(
                bot=bot,
                position=position,
                exchange_client=exchange,
                db=db,
                grid_config=grid_config,
                current_price=55000.0,
            )

        assert result["total_buy_orders"] == 2  # 1 skipped, 2 placed

    @pytest.mark.asyncio
    async def test_exchange_order_failure_continues(self):
        """Edge case: one exchange order fails, others still get placed."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 6
        bot.product_id = "BTC-USD"
        bot.bot_config = {"total_investment_quote": 300.0}

        position = MagicMock()
        position.id = 60

        call_count = 0

        async def mock_create_limit(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Exchange timeout")
            return {"order_id": f"order-{call_count}"}

        exchange = AsyncMock()
        exchange.create_limit_order.side_effect = mock_create_limit

        grid_config = {
            "grid_mode": "long",
            "grid_type": "arithmetic",
            "upper_limit": 55000.0,
            "lower_limit": 50000.0,
            "levels": [50000.0, 51000.0, 52000.0],
        }

        with patch(
            "app.services.grid_trading_service.validate_order_size",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            result = await initialize_grid(
                bot=bot,
                position=position,
                exchange_client=exchange,
                db=db,
                grid_config=grid_config,
                current_price=55000.0,
            )

        # 2 of 3 orders placed (1 failed)
        assert result["total_buy_orders"] == 2


# ---------------------------------------------------------------------------
# handle_grid_order_fill
# ---------------------------------------------------------------------------


class TestHandleGridOrderFill:
    """Tests for handle_grid_order_fill()."""

    @pytest.mark.asyncio
    async def test_neutral_buy_fill_places_sell_order(self):
        """Happy path: neutral grid buy fill places sell at next level."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        bot.product_id = "BTC-USD"
        bot.bot_config = {
            "grid_state": {
                "grid_mode": "neutral",
                "grid_levels": [
                    {"order_type": "buy", "price": 48000, "status": "pending"},
                    {"order_type": "sell", "price": 52000, "status": "pending"},
                    {"order_type": "sell", "price": 54000, "status": "pending"},
                ],
            }
        }

        position = MagicMock()
        position.id = 10

        pending_order = MagicMock()
        pending_order.side = "BUY"
        pending_order.filled_price = 48000.0
        pending_order.filled_base_amount = 0.02
        pending_order.reserved_amount_quote = 960.0
        pending_order.reserved_amount_base = 0.0

        exchange = AsyncMock()
        exchange.create_limit_order.return_value = {"order_id": "sell-order-1"}

        result = await handle_grid_order_fill(
            pending_order=pending_order,
            bot=bot,
            position=position,
            exchange_client=exchange,
            db=db,
        )

        assert result == "sell-order-1"
        exchange.create_limit_order.assert_called_once()
        call_kwargs = exchange.create_limit_order.call_args[1]
        assert call_kwargs["side"] == "SELL"
        assert call_kwargs["limit_price"] == 52000  # Next sell level above
        # Capital reservation released
        assert pending_order.reserved_amount_quote == 0.0

    @pytest.mark.asyncio
    async def test_long_mode_accumulates_no_sell(self):
        """Happy path: long grid buy fill does NOT place sell order."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 2
        bot.product_id = "BTC-USD"
        bot.bot_config = {
            "grid_state": {"grid_mode": "long", "grid_levels": []}
        }

        position = MagicMock()
        position.id = 20

        pending_order = MagicMock()
        pending_order.side = "BUY"
        pending_order.filled_price = 49000.0
        pending_order.filled_base_amount = 0.01

        exchange = AsyncMock()

        result = await handle_grid_order_fill(
            pending_order=pending_order,
            bot=bot,
            position=position,
            exchange_client=exchange,
            db=db,
        )

        assert result is None
        exchange.create_limit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_neutral_sell_fill_places_buy_order(self):
        """Happy path: neutral grid sell fill places buy at next level down."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 3
        bot.product_id = "BTC-USD"
        bot.bot_config = {
            "grid_state": {
                "grid_mode": "neutral",
                "grid_levels": [
                    {"order_type": "buy", "price": 47000, "status": "pending"},
                    {"order_type": "buy", "price": 48000, "status": "pending"},
                    {"order_type": "sell", "price": 52000, "status": "pending"},
                ],
            }
        }

        position = MagicMock()
        position.id = 30

        pending_order = MagicMock()
        pending_order.side = "SELL"
        pending_order.filled_price = 52000.0
        pending_order.filled_base_amount = 0.02

        exchange = AsyncMock()
        exchange.create_limit_order.return_value = {"order_id": "buy-order-1"}

        result = await handle_grid_order_fill(
            pending_order=pending_order,
            bot=bot,
            position=position,
            exchange_client=exchange,
            db=db,
        )

        assert result == "buy-order-1"
        call_kwargs = exchange.create_limit_order.call_args[1]
        assert call_kwargs["side"] == "BUY"
        assert call_kwargs["limit_price"] == 48000  # Highest buy level below fill

    @pytest.mark.asyncio
    async def test_no_opposite_levels_returns_none(self):
        """Edge case: no opposite levels available returns None."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 4
        bot.product_id = "BTC-USD"
        bot.bot_config = {
            "grid_state": {
                "grid_mode": "neutral",
                "grid_levels": [],
            }
        }

        position = MagicMock()
        pending_order = MagicMock()
        pending_order.side = "BUY"
        pending_order.filled_price = 50000.0

        exchange = AsyncMock()

        result = await handle_grid_order_fill(
            pending_order=pending_order,
            bot=bot,
            position=position,
            exchange_client=exchange,
            db=db,
        )

        assert result is None


# ---------------------------------------------------------------------------
# detect_and_handle_breakout
# ---------------------------------------------------------------------------


class TestDetectAndHandleBreakout:
    """Tests for detect_and_handle_breakout()."""

    @pytest.mark.asyncio
    async def test_no_breakout_returns_false(self):
        """Happy path: price within range returns False."""
        db = AsyncMock()
        bot = MagicMock()
        bot.bot_config = {
            "enable_dynamic_adjustment": True,
            "breakout_threshold_percent": 5.0,
            "grid_state": {
                "current_range_upper": 55000.0,
                "current_range_lower": 45000.0,
            },
        }
        position = MagicMock()
        exchange = AsyncMock()

        result = await detect_and_handle_breakout(
            bot, position, exchange, db, current_price=50000.0
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_upward_breakout_triggers_rebalance(self):
        """Happy path: price above upper+threshold triggers rebalance."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        bot.product_id = "BTC-USD"
        bot.bot_config = {
            "enable_dynamic_adjustment": True,
            "breakout_threshold_percent": 5.0,
            "grid_type": "arithmetic",
            "num_grid_levels": 5,
            "total_investment_quote": 1000.0,
            "grid_state": {
                "current_range_upper": 55000.0,
                "current_range_lower": 45000.0,
                "breakout_count": 0,
            },
        }
        position = MagicMock()
        exchange = AsyncMock()

        # Price well above upper * 1.05 = 57750
        current_price = 60000.0

        with patch(
            "app.services.grid_trading_service.rebalance_grid_on_breakout",
            new_callable=AsyncMock,
            return_value={"breakout_count": 1},
        ) as mock_rebalance, patch(
            "app.strategies.grid_trading.calculate_arithmetic_levels",
            return_value=[58000, 59000, 60000, 61000, 62000],
        ):
            result = await detect_and_handle_breakout(
                bot, position, exchange, db, current_price=current_price
            )

        assert result is True
        mock_rebalance.assert_called_once()

    @pytest.mark.asyncio
    async def test_dynamic_adjustment_disabled_returns_false(self):
        """Edge case: returns False when enable_dynamic_adjustment is False."""
        db = AsyncMock()
        bot = MagicMock()
        bot.bot_config = {"enable_dynamic_adjustment": False}
        position = MagicMock()
        exchange = AsyncMock()

        result = await detect_and_handle_breakout(
            bot, position, exchange, db, current_price=100000.0
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_no_grid_state_returns_false(self):
        """Edge case: returns False when grid_state is empty."""
        db = AsyncMock()
        bot = MagicMock()
        bot.bot_config = {
            "enable_dynamic_adjustment": True,
            "grid_state": {},
        }
        position = MagicMock()
        exchange = AsyncMock()

        result = await detect_and_handle_breakout(
            bot, position, exchange, db, current_price=50000.0
        )

        assert result is False


# ---------------------------------------------------------------------------
# check_and_run_ai_optimization
# ---------------------------------------------------------------------------


class TestCheckAndRunAiOptimization:
    """Tests for check_and_run_ai_optimization()."""

    @pytest.mark.asyncio
    async def test_returns_false_when_not_due(self):
        """Edge case: returns False when ai_optimization_due is False."""
        result = await check_and_run_ai_optimization(
            bot=MagicMock(),
            position=MagicMock(),
            exchange_client=AsyncMock(),
            db=AsyncMock(),
            signal_data={"ai_optimization_due": False},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_ai_disabled(self):
        """Edge case: returns False when enable_ai_optimization is False."""
        bot = MagicMock()
        bot.strategy_config = {"enable_ai_optimization": False}

        result = await check_and_run_ai_optimization(
            bot=bot,
            position=MagicMock(),
            exchange_client=AsyncMock(),
            db=AsyncMock(),
            signal_data={"ai_optimization_due": True},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_runs_optimization_and_returns_true(self):
        """Happy path: runs AI optimization and returns True on success."""
        bot = MagicMock()
        bot.id = 1
        bot.strategy_config = {"enable_ai_optimization": True}

        with patch(
            "app.services.ai_grid_optimizer.run_ai_grid_optimization",
            new_callable=AsyncMock,
            return_value={"adjusted": True},
        ):
            result = await check_and_run_ai_optimization(
                bot=bot,
                position=MagicMock(),
                exchange_client=AsyncMock(),
                db=AsyncMock(),
                signal_data={"ai_optimization_due": True},
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        """Failure: returns False when AI optimization raises exception."""
        bot = MagicMock()
        bot.id = 2
        bot.strategy_config = {"enable_ai_optimization": True}

        with patch(
            "app.services.ai_grid_optimizer.run_ai_grid_optimization",
            new_callable=AsyncMock,
            side_effect=Exception("AI provider down"),
        ):
            result = await check_and_run_ai_optimization(
                bot=bot,
                position=MagicMock(),
                exchange_client=AsyncMock(),
                db=AsyncMock(),
                signal_data={"ai_optimization_due": True},
            )

        assert result is False


# ---------------------------------------------------------------------------
# check_and_run_rotation
# ---------------------------------------------------------------------------


class TestCheckAndRunRotation:
    """Tests for check_and_run_rotation()."""

    @pytest.mark.asyncio
    async def test_rotation_executed_returns_true(self):
        """Happy path: rotation executed successfully returns True."""
        bot = MagicMock()
        bot.id = 1

        with patch(
            "app.services.grid_rotation_service.check_and_run_rotation",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await check_and_run_rotation(
                bot=bot,
                position=MagicMock(),
                exchange_client=AsyncMock(),
                db=AsyncMock(),
                current_price=50000.0,
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_rotation_not_needed_returns_false(self):
        """Happy path: rotation not due returns False."""
        bot = MagicMock()
        bot.id = 2

        with patch(
            "app.services.grid_rotation_service.check_and_run_rotation",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await check_and_run_rotation(
                bot=bot,
                position=MagicMock(),
                exchange_client=AsyncMock(),
                db=AsyncMock(),
                current_price=50000.0,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_rotation_exception_returns_false(self):
        """Failure: exception in rotation returns False, does not propagate."""
        bot = MagicMock()
        bot.id = 3

        with patch(
            "app.services.grid_rotation_service.check_and_run_rotation",
            new_callable=AsyncMock,
            side_effect=Exception("rotation error"),
        ):
            result = await check_and_run_rotation(
                bot=bot,
                position=MagicMock(),
                exchange_client=AsyncMock(),
                db=AsyncMock(),
                current_price=50000.0,
            )

        assert result is False


# ---------------------------------------------------------------------------
# rebalance_grid_on_breakout
# ---------------------------------------------------------------------------


class TestRebalanceGridOnBreakout:
    """Tests for rebalance_grid_on_breakout()."""

    @pytest.mark.asyncio
    async def test_rebalance_cancels_old_and_places_new_orders(self):
        """Happy path: cancels old orders and initializes new grid."""
        from app.services.grid_trading_service import rebalance_grid_on_breakout

        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        bot.product_id = "BTC-USD"
        bot.bot_config = {
            "grid_mode": "neutral",
            "grid_type": "arithmetic",
            "total_investment_quote": 1000.0,
            "grid_state": {
                "current_range_upper": 55000.0,
                "current_range_lower": 45000.0,
                "breakout_count": 0,
            },
        }

        position = MagicMock()
        position.id = 10
        exchange = AsyncMock()

        new_levels = [56000.0, 58000.0, 60000.0, 62000.0, 64000.0]

        with patch(
            "app.services.grid_trading_service.cancel_grid_orders",
            new_callable=AsyncMock,
            return_value=5,
        ) as mock_cancel, patch(
            "app.services.grid_trading_service.initialize_grid",
            new_callable=AsyncMock,
            return_value={
                "total_buy_orders": 2,
                "total_sell_orders": 2,
                "current_range_upper": 64000.0,
                "current_range_lower": 56000.0,
            },
        ) as mock_init:
            result = await rebalance_grid_on_breakout(
                bot=bot,
                position=position,
                exchange_client=exchange,
                db=db,
                breakout_direction="upward",
                current_price=60000.0,
                new_levels=new_levels,
                new_upper=64000.0,
                new_lower=56000.0,
            )

        mock_cancel.assert_called_once()
        mock_init.assert_called_once()
        assert result["breakout_count"] == 1
        assert result["last_breakout_direction"] == "upward"

    @pytest.mark.asyncio
    async def test_rebalance_increments_breakout_count(self):
        """Edge case: breakout count increments from existing value."""
        from app.services.grid_trading_service import rebalance_grid_on_breakout

        db = AsyncMock()
        bot = MagicMock()
        bot.id = 2
        bot.bot_config = {
            "grid_state": {
                "current_range_upper": 55000.0,
                "current_range_lower": 45000.0,
                "breakout_count": 3,
            },
        }

        position = MagicMock()
        exchange = AsyncMock()

        with patch(
            "app.services.grid_trading_service.cancel_grid_orders",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "app.services.grid_trading_service.initialize_grid",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await rebalance_grid_on_breakout(
                bot=bot,
                position=position,
                exchange_client=exchange,
                db=db,
                breakout_direction="downward",
                current_price=40000.0,
                new_levels=[38000.0, 40000.0, 42000.0],
                new_upper=42000.0,
                new_lower=38000.0,
            )

        assert result["breakout_count"] == 4
        assert result["last_breakout_direction"] == "downward"

    @pytest.mark.asyncio
    async def test_rebalance_stores_previous_range(self):
        """Happy path: previous range values are stored in new grid state."""
        from app.services.grid_trading_service import rebalance_grid_on_breakout

        db = AsyncMock()
        bot = MagicMock()
        bot.id = 3
        bot.bot_config = {
            "grid_state": {
                "current_range_upper": 55000.0,
                "current_range_lower": 45000.0,
                "breakout_count": 0,
            },
        }

        position = MagicMock()
        exchange = AsyncMock()

        with patch(
            "app.services.grid_trading_service.cancel_grid_orders",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "app.services.grid_trading_service.initialize_grid",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await rebalance_grid_on_breakout(
                bot=bot,
                position=position,
                exchange_client=exchange,
                db=db,
                breakout_direction="upward",
                current_price=60000.0,
                new_levels=[58000.0, 60000.0, 62000.0],
                new_upper=62000.0,
                new_lower=58000.0,
            )

        assert result["previous_range_upper"] == 55000.0
        assert result["previous_range_lower"] == 45000.0


# ---------------------------------------------------------------------------
# detect_and_handle_breakout — additional edge cases
# ---------------------------------------------------------------------------


class TestDetectAndHandleBreakoutAdditional:
    """Additional tests for detect_and_handle_breakout edge cases."""

    @pytest.mark.asyncio
    async def test_downward_breakout_triggers_rebalance(self):
        """Happy path: price below lower-threshold triggers downward rebalance."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        bot.product_id = "BTC-USD"
        bot.bot_config = {
            "enable_dynamic_adjustment": True,
            "breakout_threshold_percent": 5.0,
            "grid_type": "arithmetic",
            "num_grid_levels": 5,
            "total_investment_quote": 1000.0,
            "grid_state": {
                "current_range_upper": 55000.0,
                "current_range_lower": 45000.0,
                "breakout_count": 0,
            },
        }
        position = MagicMock()
        exchange = AsyncMock()

        # Price below lower * 0.95 = 42750
        current_price = 40000.0

        with patch(
            "app.services.grid_trading_service.rebalance_grid_on_breakout",
            new_callable=AsyncMock,
            return_value={"breakout_count": 1},
        ) as mock_rebalance, patch(
            "app.strategies.grid_trading.calculate_arithmetic_levels",
            return_value=[38000, 39000, 40000, 41000, 42000],
        ):
            result = await detect_and_handle_breakout(
                bot, position, exchange, db, current_price=current_price
            )

        assert result is True
        mock_rebalance.assert_called_once()

    @pytest.mark.asyncio
    async def test_price_at_threshold_boundary_no_breakout(self):
        """Edge case: price exactly at threshold boundary does NOT trigger."""
        db = AsyncMock()
        bot = MagicMock()
        bot.bot_config = {
            "enable_dynamic_adjustment": True,
            "breakout_threshold_percent": 5.0,
            "grid_state": {
                "current_range_upper": 55000.0,
                "current_range_lower": 45000.0,
            },
        }
        position = MagicMock()
        exchange = AsyncMock()

        # upper * (1 + 0.05) = 57750 — at boundary
        result = await detect_and_handle_breakout(
            bot, position, exchange, db, current_price=57750.0
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_geometric_grid_type_uses_geometric_levels(self):
        """Edge case: geometric grid type uses calculate_geometric_levels."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        bot.product_id = "BTC-USD"
        bot.bot_config = {
            "enable_dynamic_adjustment": True,
            "breakout_threshold_percent": 5.0,
            "grid_type": "geometric",
            "num_grid_levels": 5,
            "total_investment_quote": 1000.0,
            "grid_state": {
                "current_range_upper": 55000.0,
                "current_range_lower": 45000.0,
                "breakout_count": 0,
            },
        }
        position = MagicMock()
        exchange = AsyncMock()

        with patch(
            "app.services.grid_trading_service.rebalance_grid_on_breakout",
            new_callable=AsyncMock,
            return_value={"breakout_count": 1},
        ), patch(
            "app.strategies.grid_trading.calculate_geometric_levels",
            return_value=[58000, 59000, 60000, 61000, 62000],
        ) as mock_geo:
            result = await detect_and_handle_breakout(
                bot, position, exchange, db, current_price=60000.0
            )

        assert result is True
        mock_geo.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_range_bounds_returns_false(self):
        """Edge case: grid_state with missing range bounds returns False."""
        db = AsyncMock()
        bot = MagicMock()
        bot.bot_config = {
            "enable_dynamic_adjustment": True,
            "grid_state": {
                "current_range_upper": None,
                "current_range_lower": None,
            },
        }
        position = MagicMock()
        exchange = AsyncMock()

        result = await detect_and_handle_breakout(
            bot, position, exchange, db, current_price=50000.0
        )

        assert result is False


# ---------------------------------------------------------------------------
# handle_grid_order_fill — additional edge cases
# ---------------------------------------------------------------------------


class TestHandleGridOrderFillAdditional:
    """Additional tests for handle_grid_order_fill edge cases."""

    @pytest.mark.asyncio
    async def test_buy_fill_exchange_error_returns_none(self):
        """Failure: exchange error when placing sell response returns None."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        bot.product_id = "BTC-USD"
        bot.bot_config = {
            "grid_state": {
                "grid_mode": "neutral",
                "grid_levels": [
                    {"order_type": "sell", "price": 52000, "status": "pending"},
                ],
            }
        }

        position = MagicMock()
        pending_order = MagicMock()
        pending_order.side = "BUY"
        pending_order.filled_price = 48000.0
        pending_order.filled_base_amount = 0.02

        exchange = AsyncMock()
        exchange.create_limit_order.side_effect = Exception("Exchange error")

        result = await handle_grid_order_fill(
            pending_order=pending_order,
            bot=bot,
            position=position,
            exchange_client=exchange,
            db=db,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_buy_fill_no_order_id_in_response_returns_none(self):
        """Edge case: exchange returns response without order_id."""
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        bot.product_id = "BTC-USD"
        bot.bot_config = {
            "grid_state": {
                "grid_mode": "neutral",
                "grid_levels": [
                    {"order_type": "sell", "price": 52000, "status": "pending"},
                ],
            }
        }

        position = MagicMock()
        pending_order = MagicMock()
        pending_order.side = "BUY"
        pending_order.filled_price = 48000.0
        pending_order.filled_base_amount = 0.02

        exchange = AsyncMock()
        exchange.create_limit_order.return_value = {}  # No order_id

        result = await handle_grid_order_fill(
            pending_order=pending_order,
            bot=bot,
            position=position,
            exchange_client=exchange,
            db=db,
        )

        assert result is None
