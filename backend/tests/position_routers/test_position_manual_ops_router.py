"""
Tests for backend/app/position_routers/position_manual_ops_router.py

Covers endpoints:
- POST /{position_id}/add-funds
- PATCH /{position_id}/notes
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Account, Bot, Position, User


# =============================================================================
# Helpers
# =============================================================================


async def _create_user_with_account(db_session, email="manual@example.com"):
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
# POST /{position_id}/add-funds
# =============================================================================


class TestAddFundsToPosition:
    """Tests for add_funds_to_position endpoint."""

    @pytest.mark.asyncio
    @patch("app.position_routers.position_manual_ops_router.execute_buy", new_callable=AsyncMock)
    @patch("app.position_routers.position_manual_ops_router.TradingClient")
    async def test_add_funds_succeeds(self, mock_tc_cls, mock_execute_buy, db_session):
        """Happy path: adding funds to an open position executes a buy."""
        from app.position_routers.position_manual_ops_router import add_funds_to_position
        from app.position_routers.schemas import AddFundsRequest

        user, account = await _create_user_with_account(db_session, email="af_ok@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(
            db_session, account, bot=bot, status="open",
            total_quote_spent=0.01,
            max_quote_allowed=0.25,
        )

        mock_coinbase = AsyncMock()
        mock_coinbase.get_current_price = AsyncMock(return_value=0.03)

        mock_trade = MagicMock()
        mock_trade.id = 42
        mock_trade.base_amount = 0.333
        mock_execute_buy.return_value = mock_trade

        request = AddFundsRequest(btc_amount=0.005)

        result = await add_funds_to_position(
            position_id=pos.id,
            request=request,
            db=db_session,
            coinbase=mock_coinbase,
            current_user=user,
        )

        assert "Added" in result["message"]
        assert result["trade_id"] == 42
        assert result["price"] == 0.03
        assert result["base_acquired"] == 0.333
        assert result["quote_currency"] == "BTC"
        mock_execute_buy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_funds_exceeds_max_allowed_returns_400(self, db_session):
        """Failure: adding funds that exceed max_quote_allowed returns 400."""
        from app.position_routers.position_manual_ops_router import add_funds_to_position
        from app.position_routers.schemas import AddFundsRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="af_exceed@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(
            db_session, account, bot=bot, status="open",
            total_quote_spent=0.24,
            max_quote_allowed=0.25,
        )

        mock_coinbase = AsyncMock()
        request = AddFundsRequest(btc_amount=0.02)  # 0.24 + 0.02 = 0.26 > 0.25

        with pytest.raises(HTTPException) as exc_info:
            await add_funds_to_position(
                position_id=pos.id,
                request=request,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 400
        assert "exceed max allowed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_add_funds_closed_position_returns_400(self, db_session):
        """Failure: adding funds to a closed position returns 400."""
        from app.position_routers.position_manual_ops_router import add_funds_to_position
        from app.position_routers.schemas import AddFundsRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="af_closed@example.com")
        pos = await _create_position(db_session, account, status="closed")

        mock_coinbase = AsyncMock()
        request = AddFundsRequest(btc_amount=0.01)

        with pytest.raises(HTTPException) as exc_info:
            await add_funds_to_position(
                position_id=pos.id,
                request=request,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 400
        assert "not open" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_add_funds_position_not_found(self, db_session):
        """Failure: adding funds to non-existent position returns 404."""
        from app.position_routers.position_manual_ops_router import add_funds_to_position
        from app.position_routers.schemas import AddFundsRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="af_404@example.com")
        mock_coinbase = AsyncMock()
        request = AddFundsRequest(btc_amount=0.01)

        with pytest.raises(HTTPException) as exc_info:
            await add_funds_to_position(
                position_id=99999,
                request=request,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_add_funds_user_with_no_accounts_returns_404(self, db_session):
        """Edge case: user with no accounts gets 404."""
        from app.position_routers.position_manual_ops_router import add_funds_to_position
        from app.position_routers.schemas import AddFundsRequest
        from fastapi import HTTPException

        user = User(
            email="af_noaccount@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        mock_coinbase = AsyncMock()
        request = AddFundsRequest(btc_amount=0.01)

        with pytest.raises(HTTPException) as exc_info:
            await add_funds_to_position(
                position_id=1,
                request=request,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# PATCH /{position_id}/notes
# =============================================================================


class TestUpdatePositionNotes:
    """Tests for update_position_notes endpoint."""

    @pytest.mark.asyncio
    async def test_update_notes_succeeds(self, db_session):
        """Happy path: updating notes on an existing position."""
        from app.position_routers.position_manual_ops_router import update_position_notes
        from app.position_routers.schemas import UpdateNotesRequest

        user, account = await _create_user_with_account(db_session, email="notes_ok@example.com")
        pos = await _create_position(db_session, account, status="open")

        request = UpdateNotesRequest(notes="Good entry point, watching RSI")

        result = await update_position_notes(
            position_id=pos.id,
            request=request,
            db=db_session,
            current_user=user,
        )

        assert result["notes"] == "Good entry point, watching RSI"
        assert pos.notes == "Good entry point, watching RSI"

    @pytest.mark.asyncio
    async def test_update_notes_empty_string(self, db_session):
        """Edge case: clearing notes with empty string."""
        from app.position_routers.position_manual_ops_router import update_position_notes
        from app.position_routers.schemas import UpdateNotesRequest

        user, account = await _create_user_with_account(db_session, email="notes_clear@example.com")
        pos = await _create_position(db_session, account, status="open", notes="Old note")

        request = UpdateNotesRequest(notes="")

        result = await update_position_notes(
            position_id=pos.id,
            request=request,
            db=db_session,
            current_user=user,
        )

        assert result["notes"] == ""
        assert pos.notes == ""

    @pytest.mark.asyncio
    async def test_update_notes_on_closed_position(self, db_session):
        """Edge case: notes can be updated even on closed positions (no status check)."""
        from app.position_routers.position_manual_ops_router import update_position_notes
        from app.position_routers.schemas import UpdateNotesRequest

        user, account = await _create_user_with_account(db_session, email="notes_closed@example.com")
        pos = await _create_position(db_session, account, status="closed")

        request = UpdateNotesRequest(notes="Reviewed post-close")

        result = await update_position_notes(
            position_id=pos.id,
            request=request,
            db=db_session,
            current_user=user,
        )

        assert result["notes"] == "Reviewed post-close"

    @pytest.mark.asyncio
    async def test_update_notes_position_not_found(self, db_session):
        """Failure: updating notes on non-existent position returns 404."""
        from app.position_routers.position_manual_ops_router import update_position_notes
        from app.position_routers.schemas import UpdateNotesRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="notes_404@example.com")
        request = UpdateNotesRequest(notes="Won't be saved")

        with pytest.raises(HTTPException) as exc_info:
            await update_position_notes(
                position_id=99999,
                request=request,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_notes_other_users_position_returns_404(self, db_session):
        """Security: cannot update notes on another user's position."""
        from app.position_routers.position_manual_ops_router import update_position_notes
        from app.position_routers.schemas import UpdateNotesRequest
        from fastapi import HTTPException

        user1, account1 = await _create_user_with_account(db_session, email="notes_owner@example.com")
        user2, account2 = await _create_user_with_account(db_session, email="notes_other@example.com")
        pos = await _create_position(db_session, account1, status="open")

        request = UpdateNotesRequest(notes="Hacker note")

        with pytest.raises(HTTPException) as exc_info:
            await update_position_notes(
                position_id=pos.id,
                request=request,
                db=db_session,
                current_user=user2,
            )
        assert exc_info.value.status_code == 404
