"""
Tests for backend/app/position_routers/position_limit_orders_router.py

Covers endpoints:
- POST /{position_id}/limit-close
- GET /{position_id}/ticker
- GET /{position_id}/slippage-check
- POST /{position_id}/cancel-limit-close
- POST /{position_id}/update-limit-close
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.models import Account, Bot, PendingOrder, Position, User


# =============================================================================
# Helpers
# =============================================================================


async def _create_user_with_account(db_session, email="limit@example.com"):
    """Create a test user with an active CEX account."""
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id,
        name="Test Account",
        type="cex",
        exchange="coinbase",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    return user, account


async def _create_bot(db_session, user, account, **overrides):
    """Create a test bot."""
    defaults = dict(
        user_id=user.id,
        account_id=account.id,
        name="Test Bot",
        strategy_type="macd_dca",
        strategy_config={"base_order_fixed": 0.01},
    )
    defaults.update(overrides)
    bot = Bot(**defaults)
    db_session.add(bot)
    await db_session.flush()
    return bot


async def _create_position(db_session, account, bot=None, **overrides):
    """Create a test position with sensible defaults."""
    defaults = dict(
        bot_id=bot.id if bot else None,
        account_id=account.id,
        product_id="ETH-BTC",
        status="open",
        opened_at=datetime.utcnow(),
        initial_quote_balance=1.0,
        max_quote_allowed=0.25,
        total_quote_spent=0.01,
        total_base_acquired=0.5,
        average_buy_price=0.02,
    )
    defaults.update(overrides)
    position = Position(**defaults)
    db_session.add(position)
    await db_session.flush()
    return position


# =============================================================================
# POST /{position_id}/limit-close
# =============================================================================


class TestLimitClosePosition:
    """Tests for limit_close_position endpoint."""

    @pytest.mark.asyncio
    @patch("app.order_validation.get_product_minimums", new_callable=AsyncMock)
    async def test_limit_close_succeeds(self, mock_minimums, db_session):
        """Happy path: creating a limit close order works."""
        from app.position_routers.position_limit_orders_router import limit_close_position
        from app.position_routers.schemas import LimitCloseRequest

        mock_minimums.return_value = {"base_increment": "0.00000001"}

        user, account = await _create_user_with_account(db_session, email="lc_ok@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(
            db_session, account, bot=bot, status="open",
            total_base_acquired=1.5,
        )

        mock_coinbase = AsyncMock()
        mock_coinbase.create_limit_order = AsyncMock(return_value={
            "success_response": {"order_id": "order-abc-123"},
        })

        request = LimitCloseRequest(limit_price=0.025, time_in_force="gtc")

        result = await limit_close_position(
            position_id=pos.id,
            request=request,
            db=db_session,
            coinbase=mock_coinbase,
            current_user=user,
        )

        assert result["message"] == "Limit close order placed successfully"
        assert result["order_id"] == "order-abc-123"
        assert result["limit_price"] == 0.025
        assert pos.closing_via_limit is True
        assert pos.limit_close_order_id == "order-abc-123"

    @pytest.mark.asyncio
    @patch("app.order_validation.get_product_minimums", new_callable=AsyncMock)
    async def test_limit_close_already_closing_returns_400(self, mock_minimums, db_session):
        """Failure: position already has a pending limit close order."""
        from app.position_routers.position_limit_orders_router import limit_close_position
        from app.position_routers.schemas import LimitCloseRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="lc_dup@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(
            db_session, account, bot=bot, status="open",
            closing_via_limit=True,
        )

        mock_coinbase = AsyncMock()
        request = LimitCloseRequest(limit_price=0.025)

        with pytest.raises(HTTPException) as exc_info:
            await limit_close_position(
                position_id=pos.id,
                request=request,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 400
        assert "already has a pending limit close" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.order_validation.get_product_minimums", new_callable=AsyncMock)
    async def test_limit_close_gtd_without_end_time_returns_400(self, mock_minimums, db_session):
        """Failure: GTD order without end_time returns 400."""
        from app.position_routers.position_limit_orders_router import limit_close_position
        from app.position_routers.schemas import LimitCloseRequest
        from fastapi import HTTPException

        mock_minimums.return_value = {"base_increment": "0.00000001"}

        user, account = await _create_user_with_account(db_session, email="lc_gtd@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(db_session, account, bot=bot, status="open")

        mock_coinbase = AsyncMock()
        request = LimitCloseRequest(limit_price=0.025, time_in_force="gtd", end_time=None)

        with pytest.raises(HTTPException) as exc_info:
            await limit_close_position(
                position_id=pos.id,
                request=request,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 400
        assert "end_time is required" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.order_validation.get_product_minimums", new_callable=AsyncMock)
    async def test_limit_close_exchange_failure_returns_500(self, mock_minimums, db_session):
        """Failure: exchange returns error response for limit order creation."""
        from app.position_routers.position_limit_orders_router import limit_close_position
        from app.position_routers.schemas import LimitCloseRequest
        from fastapi import HTTPException

        mock_minimums.return_value = {"base_increment": "0.00000001"}

        user, account = await _create_user_with_account(db_session, email="lc_err@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(db_session, account, bot=bot, status="open")

        mock_coinbase = AsyncMock()
        mock_coinbase.create_limit_order = AsyncMock(return_value={
            "error_response": {
                "error": "INSUFFICIENT_FUND",
                "message": "Not enough balance",
                "error_details": "",
            },
        })

        request = LimitCloseRequest(limit_price=0.025, time_in_force="gtc")

        with pytest.raises(HTTPException) as exc_info:
            await limit_close_position(
                position_id=pos.id,
                request=request,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 500
        assert "Not enough balance" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_limit_close_not_open_returns_400(self, db_session):
        """Edge case: limit close on closed position returns 400."""
        from app.position_routers.position_limit_orders_router import limit_close_position
        from app.position_routers.schemas import LimitCloseRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="lc_closed@example.com")
        pos = await _create_position(db_session, account, status="closed")

        mock_coinbase = AsyncMock()
        request = LimitCloseRequest(limit_price=0.025)

        with pytest.raises(HTTPException) as exc_info:
            await limit_close_position(
                position_id=pos.id,
                request=request,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# GET /{position_id}/ticker
# =============================================================================


class TestGetPositionTicker:
    """Tests for get_position_ticker endpoint."""

    @pytest.mark.asyncio
    async def test_ticker_returns_prices(self, db_session):
        """Happy path: returns bid/ask/mark prices for the position."""
        from app.position_routers.position_limit_orders_router import get_position_ticker

        user, account = await _create_user_with_account(db_session, email="tick_ok@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(db_session, account, bot=bot, product_id="BTC-USD")

        mock_exchange = AsyncMock()
        mock_exchange.get_ticker = AsyncMock(return_value={
            "best_bid": "50000.00",
            "best_ask": "50100.00",
            "price": "50050.00",
        })

        with patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            return_value=mock_exchange,
        ):
            result = await get_position_ticker(
                position_id=pos.id,
                db=db_session,
                current_user=user,
            )

        assert result["product_id"] == "BTC-USD"
        assert result["best_bid"] == 50000.00
        assert result["best_ask"] == 50100.00
        assert result["mark_price"] == pytest.approx(50050.00)
        assert result["last_price"] == 50050.00

    @pytest.mark.asyncio
    async def test_ticker_position_not_found(self, db_session):
        """Failure: ticker for non-existent position returns 404."""
        from app.position_routers.position_limit_orders_router import get_position_ticker
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="tick_404@example.com")

        with pytest.raises(HTTPException) as exc_info:
            await get_position_ticker(
                position_id=99999,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_ticker_zero_bid_ask_uses_price(self, db_session):
        """Edge case: when bid/ask are zero, mark price falls back to last price."""
        from app.position_routers.position_limit_orders_router import get_position_ticker

        user, account = await _create_user_with_account(db_session, email="tick_zero@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(db_session, account, bot=bot, product_id="BTC-USD")

        mock_exchange = AsyncMock()
        mock_exchange.get_ticker = AsyncMock(return_value={
            "best_bid": "0",
            "best_ask": "0",
            "price": "49000.00",
        })

        with patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            return_value=mock_exchange,
        ):
            result = await get_position_ticker(
                position_id=pos.id,
                db=db_session,
                current_user=user,
            )

        assert result["mark_price"] == 49000.00


# =============================================================================
# GET /{position_id}/slippage-check
# =============================================================================


class TestCheckSlippage:
    """Tests for check_market_close_slippage endpoint."""

    @pytest.mark.asyncio
    async def test_slippage_check_no_warning(self, db_session):
        """Happy path: small slippage below threshold, no warning."""
        from app.position_routers.position_limit_orders_router import check_market_close_slippage

        user, account = await _create_user_with_account(db_session, email="slip_ok@example.com")
        pos = await _create_position(
            db_session, account, status="open",
            total_base_acquired=1.0,
            total_quote_spent=0.02,
            product_id="ETH-BTC",
        )

        mock_coinbase = AsyncMock()
        # Tight spread -- minimal slippage
        mock_coinbase.get_ticker = AsyncMock(return_value={
            "best_bid": "0.0300",
            "best_ask": "0.0301",
            "price": "0.0300",
        })

        result = await check_market_close_slippage(
            position_id=pos.id,
            db=db_session,
            coinbase=mock_coinbase,
            current_user=user,
        )

        assert result["show_warning"] is False
        assert result["product_id"] == "ETH-BTC"

    @pytest.mark.asyncio
    async def test_slippage_check_shows_warning(self, db_session):
        """Edge case: large spread causes >25% slippage warning."""
        from app.position_routers.position_limit_orders_router import check_market_close_slippage

        user, account = await _create_user_with_account(db_session, email="slip_warn@example.com")
        # Position barely in profit at mark but big spread eats into it
        pos = await _create_position(
            db_session, account, status="open",
            total_base_acquired=1.0,
            total_quote_spent=100.0,
            product_id="ETH-USD",
        )

        mock_coinbase = AsyncMock()
        # Mark = 101, profit at mark = 1.0
        # Bid = 100.5, profit at bid = 0.5
        # Slippage = 0.5/1.0 = 50% > 25%
        mock_coinbase.get_ticker = AsyncMock(return_value={
            "best_bid": "100.5",
            "best_ask": "101.5",
            "price": "101.0",
        })

        result = await check_market_close_slippage(
            position_id=pos.id,
            db=db_session,
            coinbase=mock_coinbase,
            current_user=user,
        )

        assert result["show_warning"] is True
        assert result["slippage_percentage"] > 25.0

    @pytest.mark.asyncio
    async def test_slippage_check_closed_position_returns_400(self, db_session):
        """Failure: slippage check on closed position returns 400."""
        from app.position_routers.position_limit_orders_router import check_market_close_slippage
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="slip_closed@example.com")
        pos = await _create_position(db_session, account, status="closed")

        mock_coinbase = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await check_market_close_slippage(
                position_id=pos.id,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_slippage_zero_expected_profit(self, db_session):
        """Edge case: when expected profit at mark is zero or negative, slippage pct stays 0."""
        from app.position_routers.position_limit_orders_router import check_market_close_slippage

        user, account = await _create_user_with_account(db_session, email="slip_zero@example.com")
        pos = await _create_position(
            db_session, account, status="open",
            total_base_acquired=1.0,
            total_quote_spent=200.0,
            product_id="ETH-USD",
        )

        mock_coinbase = AsyncMock()
        # Mark price = 100, so position is at a loss
        mock_coinbase.get_ticker = AsyncMock(return_value={
            "best_bid": "99",
            "best_ask": "101",
            "price": "100",
        })

        result = await check_market_close_slippage(
            position_id=pos.id,
            db=db_session,
            coinbase=mock_coinbase,
            current_user=user,
        )

        # Position is at a loss, so slippage_percentage stays 0
        assert result["slippage_percentage"] == 0.0
        assert result["show_warning"] is False


# =============================================================================
# POST /{position_id}/cancel-limit-close
# =============================================================================


class TestCancelLimitClose:
    """Tests for cancel_limit_close endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_limit_close_succeeds(self, db_session):
        """Happy path: cancelling a limit close order resets position flags."""
        from app.position_routers.position_limit_orders_router import cancel_limit_close

        user, account = await _create_user_with_account(db_session, email="clc_ok@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(
            db_session, account, bot=bot, status="open",
            closing_via_limit=True,
            limit_close_order_id="order-xyz-789",
        )

        # Create a matching PendingOrder so the lookup succeeds
        pending = PendingOrder(
            position_id=pos.id,
            bot_id=bot.id,
            order_id="order-xyz-789",
            product_id="ETH-BTC",
            side="SELL",
            order_type="LIMIT",
            limit_price=0.03,
            quote_amount=0.0,
            trade_type="limit_close",
            status="pending",
        )
        db_session.add(pending)
        await db_session.flush()

        mock_coinbase = AsyncMock()
        mock_coinbase.cancel_order = AsyncMock(return_value=True)

        result = await cancel_limit_close(
            position_id=pos.id,
            db=db_session,
            coinbase=mock_coinbase,
            current_user=user,
        )

        assert result["message"] == "Limit close order canceled successfully"
        assert pos.closing_via_limit is False
        assert pos.limit_close_order_id is None
        assert pending.status == "canceled"
        mock_coinbase.cancel_order.assert_awaited_once_with("order-xyz-789")

    @pytest.mark.asyncio
    async def test_cancel_limit_close_no_pending_order_returns_400(self, db_session):
        """Failure: position without a pending limit close order returns 400."""
        from app.position_routers.position_limit_orders_router import cancel_limit_close
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="clc_no@example.com")
        pos = await _create_position(
            db_session, account, status="open",
            closing_via_limit=False,
        )

        mock_coinbase = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await cancel_limit_close(
                position_id=pos.id,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 400
        assert "does not have a pending limit close" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_cancel_limit_close_position_not_found(self, db_session):
        """Failure: cancel for non-existent position returns 404."""
        from app.position_routers.position_limit_orders_router import cancel_limit_close
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="clc_404@example.com")
        mock_coinbase = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await cancel_limit_close(
                position_id=99999,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# POST /{position_id}/update-limit-close
# =============================================================================


class TestUpdateLimitClose:
    """Tests for update_limit_close endpoint."""

    @pytest.mark.asyncio
    @patch("app.product_precision.format_quote_amount_for_product", return_value="0.02500000")
    async def test_update_limit_close_succeeds(self, mock_fmt, db_session):
        """Happy path: updating limit close price works."""
        from app.position_routers.position_limit_orders_router import update_limit_close
        from app.position_routers.schemas import UpdateLimitCloseRequest

        user, account = await _create_user_with_account(db_session, email="ulc_ok@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(
            db_session, account, bot=bot, status="open",
            closing_via_limit=True,
            limit_close_order_id="order-edit-123",
            total_base_acquired=1.5,
        )

        pending = PendingOrder(
            position_id=pos.id,
            bot_id=bot.id,
            order_id="order-edit-123",
            product_id="ETH-BTC",
            side="SELL",
            order_type="LIMIT",
            limit_price=0.03,
            quote_amount=0.0,
            trade_type="limit_close",
            status="pending",
            remaining_base_amount=1.5,
        )
        db_session.add(pending)
        await db_session.flush()

        mock_coinbase = AsyncMock()
        mock_coinbase.edit_order = AsyncMock(return_value={
            "success_response": {"order_id": "order-edit-123"},
        })

        request = UpdateLimitCloseRequest(new_limit_price=0.025)

        result = await update_limit_close(
            position_id=pos.id,
            request=request,
            db=db_session,
            coinbase=mock_coinbase,
            current_user=user,
        )

        assert result["message"] == "Limit close order updated successfully"
        assert result["order_id"] == "order-edit-123"
        assert result["new_limit_price"] == 0.025
        assert pending.limit_price == 0.025

    @pytest.mark.asyncio
    async def test_update_limit_close_no_pending_order_returns_400(self, db_session):
        """Failure: position without a limit close order returns 400."""
        from app.position_routers.position_limit_orders_router import update_limit_close
        from app.position_routers.schemas import UpdateLimitCloseRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="ulc_no@example.com")
        pos = await _create_position(
            db_session, account, status="open",
            closing_via_limit=False,
        )

        mock_coinbase = AsyncMock()
        request = UpdateLimitCloseRequest(new_limit_price=0.025)

        with pytest.raises(HTTPException) as exc_info:
            await update_limit_close(
                position_id=pos.id,
                request=request,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("app.product_precision.format_quote_amount_for_product", return_value="0.02500000")
    async def test_update_limit_close_exchange_error(self, mock_fmt, db_session):
        """Failure: exchange returns error for edit order."""
        from app.position_routers.position_limit_orders_router import update_limit_close
        from app.position_routers.schemas import UpdateLimitCloseRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="ulc_err@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(
            db_session, account, bot=bot, status="open",
            closing_via_limit=True,
            limit_close_order_id="order-edit-fail",
        )

        pending = PendingOrder(
            position_id=pos.id,
            bot_id=bot.id,
            order_id="order-edit-fail",
            product_id="ETH-BTC",
            side="SELL",
            order_type="LIMIT",
            limit_price=0.03,
            quote_amount=0.0,
            trade_type="limit_close",
            status="pending",
        )
        db_session.add(pending)
        await db_session.flush()

        mock_coinbase = AsyncMock()
        mock_coinbase.edit_order = AsyncMock(return_value={
            "error_response": {
                "error": "EDIT_FAILED",
                "message": "Order cannot be edited",
            },
        })

        request = UpdateLimitCloseRequest(new_limit_price=0.025)

        with pytest.raises(HTTPException) as exc_info:
            await update_limit_close(
                position_id=pos.id,
                request=request,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 500
        assert "Order cannot be edited" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.product_precision.format_quote_amount_for_product", return_value="0.02500000")
    async def test_update_limit_close_pending_order_not_found_returns_404(self, mock_fmt, db_session):
        """Edge case: position has limit close flag but pending order record is missing."""
        from app.position_routers.position_limit_orders_router import update_limit_close
        from app.position_routers.schemas import UpdateLimitCloseRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="ulc_nopo@example.com")
        pos = await _create_position(
            db_session, account, status="open",
            closing_via_limit=True,
            limit_close_order_id="order-ghost",
        )

        mock_coinbase = AsyncMock()
        request = UpdateLimitCloseRequest(new_limit_price=0.025)

        with pytest.raises(HTTPException) as exc_info:
            await update_limit_close(
                position_id=pos.id,
                request=request,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 404
        assert "Pending order not found" in exc_info.value.detail
