"""
Tests for backend/app/position_routers/position_actions_router.py

Covers endpoints:
- POST /{position_id}/cancel
- POST /{position_id}/force-close
- PATCH /{position_id}/settings
- POST /{position_id}/resize-budget
- POST /resize-all-budgets
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Account, Bot, Position, User


# =============================================================================
# Helpers
# =============================================================================


async def _create_user_with_account(db_session, email="actions@example.com"):
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
        strategy_config={"base_order_fixed": 0.01, "take_profit_percentage": 1.5},
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
# POST /{position_id}/cancel
# =============================================================================


class TestCancelPosition:
    """Tests for cancel_position endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_open_position_succeeds(self, db_session):
        """Happy path: cancelling an open position marks it as cancelled."""
        from app.position_routers.position_actions_router import cancel_position

        user, account = await _create_user_with_account(db_session)
        pos = await _create_position(db_session, account, status="open")

        result = await cancel_position(
            position_id=pos.id,
            db=db_session,
            current_user=user,
        )

        assert result["message"] == f"Position {pos.id} cancelled successfully"
        assert pos.status == "cancelled"
        assert pos.closed_at is not None

    @pytest.mark.asyncio
    async def test_cancel_position_not_found(self, db_session):
        """Failure: cancelling a non-existent position returns 404."""
        from app.position_routers.position_actions_router import cancel_position
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="cancel404@example.com")

        with pytest.raises(HTTPException) as exc_info:
            await cancel_position(
                position_id=99999,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_closed_position_returns_400(self, db_session):
        """Edge case: cancelling a non-open position returns 400."""
        from app.position_routers.position_actions_router import cancel_position
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="cancel400@example.com")
        pos = await _create_position(db_session, account, status="closed")

        with pytest.raises(HTTPException) as exc_info:
            await cancel_position(
                position_id=pos.id,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 400
        assert "not open" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_cancel_position_owned_by_other_user_returns_404(self, db_session):
        """Security: cannot cancel another user's position."""
        from app.position_routers.position_actions_router import cancel_position
        from fastapi import HTTPException

        user1, account1 = await _create_user_with_account(db_session, email="owner@example.com")
        user2, account2 = await _create_user_with_account(db_session, email="other@example.com")
        pos = await _create_position(db_session, account1, status="open")

        with pytest.raises(HTTPException) as exc_info:
            await cancel_position(
                position_id=pos.id,
                db=db_session,
                current_user=user2,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_user_with_no_accounts_returns_404(self, db_session):
        """Edge case: user with no accounts gets 404."""
        from app.position_routers.position_actions_router import cancel_position
        from fastapi import HTTPException

        user = User(
            email="noaccount@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await cancel_position(
                position_id=1,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# POST /{position_id}/force-close
# =============================================================================


class TestForceClosePosition:
    """Tests for force_close_position endpoint."""

    @pytest.mark.asyncio
    @patch("app.position_routers.position_actions_router.StrategyTradingEngine")
    @patch("app.strategies.StrategyRegistry")
    async def test_force_close_succeeds(self, mock_registry, mock_engine_cls, db_session):
        """Happy path: force closing an open position executes sell and returns profit."""
        from app.position_routers.position_actions_router import force_close_position

        user, account = await _create_user_with_account(db_session, email="fc_ok@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(db_session, account, bot=bot, status="open")

        mock_coinbase = AsyncMock()
        mock_coinbase.get_current_price = AsyncMock(return_value=0.03)

        mock_strategy = MagicMock()
        mock_registry.get_strategy.return_value = mock_strategy

        mock_engine_instance = AsyncMock()
        mock_engine_instance.execute_sell = AsyncMock(return_value=(MagicMock(), 0.005, 2.5))
        mock_engine_cls.return_value = mock_engine_instance

        result = await force_close_position(
            position_id=pos.id,
            db=db_session,
            coinbase=mock_coinbase,
            current_user=user,
        )

        assert result["message"] == f"Position {pos.id} closed successfully"
        assert result["profit_quote"] == 0.005
        assert result["profit_percentage"] == 2.5
        mock_coinbase.get_current_price.assert_awaited_once_with("ETH-BTC")

    @pytest.mark.asyncio
    async def test_force_close_position_not_found(self, db_session):
        """Failure: force closing non-existent position returns 404."""
        from app.position_routers.position_actions_router import force_close_position
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="fc_404@example.com")
        mock_coinbase = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await force_close_position(
                position_id=99999,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_force_close_closed_position_returns_400(self, db_session):
        """Edge case: force closing an already-closed position returns 400."""
        from app.position_routers.position_actions_router import force_close_position
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="fc_closed@example.com")
        pos = await _create_position(db_session, account, status="closed")
        mock_coinbase = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await force_close_position(
                position_id=pos.id,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_force_close_position_no_bot_returns_404(self, db_session):
        """Edge case: position with no associated bot returns 404."""
        from app.position_routers.position_actions_router import force_close_position
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="fc_nobot@example.com")
        pos = await _create_position(db_session, account, bot=None, status="open")
        mock_coinbase = AsyncMock()
        mock_coinbase.get_current_price = AsyncMock(return_value=0.03)

        with pytest.raises(HTTPException) as exc_info:
            await force_close_position(
                position_id=pos.id,
                db=db_session,
                coinbase=mock_coinbase,
                current_user=user,
            )
        assert exc_info.value.status_code == 404
        assert "Bot not found" in exc_info.value.detail


# =============================================================================
# PATCH /{position_id}/settings
# =============================================================================


class TestUpdatePositionSettings:
    """Tests for update_position_settings endpoint."""

    @pytest.mark.asyncio
    async def test_update_take_profit_succeeds(self, db_session):
        """Happy path: updating take_profit_percentage works."""
        from app.position_routers.position_actions_router import update_position_settings
        from app.schemas.position import UpdatePositionSettingsRequest

        user, account = await _create_user_with_account(db_session, email="settings_ok@example.com")
        pos = await _create_position(
            db_session, account, status="open",
            strategy_config_snapshot={"take_profit_percentage": 1.5},
        )

        settings = UpdatePositionSettingsRequest(take_profit_percentage=3.0)
        result = await update_position_settings(
            position_id=pos.id,
            settings=settings,
            db=db_session,
            current_user=user,
        )

        assert "updated successfully" in result["message"]
        assert len(result["updated_fields"]) == 1
        assert result["new_config"]["take_profit_percentage"] == 3.0

    @pytest.mark.asyncio
    async def test_update_multiple_settings(self, db_session):
        """Happy path: updating multiple settings at once."""
        from app.position_routers.position_actions_router import update_position_settings
        from app.schemas.position import UpdatePositionSettingsRequest

        user, account = await _create_user_with_account(db_session, email="settings_multi@example.com")
        pos = await _create_position(
            db_session, account, status="open",
            strategy_config_snapshot={},
        )

        settings = UpdatePositionSettingsRequest(
            take_profit_percentage=5.0,
            max_safety_orders=8,
            stop_loss_enabled=True,
            stop_loss_percentage=10.0,
        )
        result = await update_position_settings(
            position_id=pos.id,
            settings=settings,
            db=db_session,
            current_user=user,
        )

        assert len(result["updated_fields"]) == 4
        assert result["new_config"]["take_profit_percentage"] == 5.0
        assert result["new_config"]["max_safety_orders"] == 8
        assert result["new_config"]["stop_loss_enabled"] is True
        assert result["new_config"]["stop_loss_percentage"] == 10.0

    @pytest.mark.asyncio
    async def test_update_no_settings_provided_returns_400(self, db_session):
        """Failure: providing no settings returns 400."""
        from app.position_routers.position_actions_router import update_position_settings
        from app.schemas.position import UpdatePositionSettingsRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="settings_empty@example.com")
        pos = await _create_position(db_session, account, status="open")

        settings = UpdatePositionSettingsRequest()  # All None
        with pytest.raises(HTTPException) as exc_info:
            await update_position_settings(
                position_id=pos.id,
                settings=settings,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 400
        assert "No settings provided" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_update_settings_closed_position_returns_400(self, db_session):
        """Edge case: updating settings on a closed position returns 400."""
        from app.position_routers.position_actions_router import update_position_settings
        from app.schemas.position import UpdatePositionSettingsRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="settings_closed@example.com")
        pos = await _create_position(db_session, account, status="closed")

        settings = UpdatePositionSettingsRequest(take_profit_percentage=5.0)
        with pytest.raises(HTTPException) as exc_info:
            await update_position_settings(
                position_id=pos.id,
                settings=settings,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 400
        assert "open positions" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_update_settings_null_config_snapshot(self, db_session):
        """Edge case: position with no existing config snapshot gets one created."""
        from app.position_routers.position_actions_router import update_position_settings
        from app.schemas.position import UpdatePositionSettingsRequest

        user, account = await _create_user_with_account(db_session, email="settings_null@example.com")
        pos = await _create_position(
            db_session, account, status="open",
            strategy_config_snapshot=None,
        )

        settings = UpdatePositionSettingsRequest(take_profit_percentage=2.0)
        result = await update_position_settings(
            position_id=pos.id,
            settings=settings,
            db=db_session,
            current_user=user,
        )

        assert result["new_config"]["take_profit_percentage"] == 2.0


# =============================================================================
# POST /{position_id}/resize-budget
# =============================================================================


class TestResizePositionBudget:
    """Tests for resize_position_budget endpoint."""

    @pytest.mark.asyncio
    @patch("app.position_routers.position_actions_router.compute_resize_budget", return_value=0.05)
    async def test_resize_budget_succeeds(self, mock_resize, db_session):
        """Happy path: resizing budget updates max_quote_allowed."""
        from app.position_routers.position_actions_router import resize_position_budget

        user, account = await _create_user_with_account(db_session, email="resize_ok@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(
            db_session, account, bot=bot, status="open",
            product_id="ETH-BTC",
            max_quote_allowed=0.01,
        )

        result = await resize_position_budget(
            position_id=pos.id,
            db=db_session,
            current_user=user,
        )

        assert result["message"] == f"Position {pos.id} budget resized"
        assert result["old_max"] == 0.01
        assert result["new_max"] == 0.05
        assert result["quote_currency"] == "BTC"
        assert pos.max_quote_allowed == 0.05

    @pytest.mark.asyncio
    @patch("app.position_routers.position_actions_router.compute_resize_budget", return_value=0.0)
    async def test_resize_budget_zero_returns_400(self, mock_resize, db_session):
        """Failure: compute returning 0 means we can't determine base order size."""
        from app.position_routers.position_actions_router import resize_position_budget
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="resize_zero@example.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(db_session, account, bot=bot, status="open")

        with pytest.raises(HTTPException) as exc_info:
            await resize_position_budget(
                position_id=pos.id,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 400
        assert "base order size" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_resize_budget_closed_position_returns_400(self, db_session):
        """Edge case: resizing a closed position returns 400."""
        from app.position_routers.position_actions_router import resize_position_budget
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="resize_closed@example.com")
        pos = await _create_position(db_session, account, status="closed")

        with pytest.raises(HTTPException) as exc_info:
            await resize_position_budget(
                position_id=pos.id,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("app.position_routers.position_actions_router.compute_resize_budget", return_value=0.10)
    async def test_resize_budget_usd_pair_quote_currency(self, mock_resize, db_session):
        """Edge case: USD pair returns USD as quote currency."""
        from app.position_routers.position_actions_router import resize_position_budget

        user, account = await _create_user_with_account(db_session, email="resize_usd@example.com")
        pos = await _create_position(
            db_session, account, status="open",
            product_id="SOL-USD",
            max_quote_allowed=50.0,
        )

        result = await resize_position_budget(
            position_id=pos.id,
            db=db_session,
            current_user=user,
        )

        assert result["quote_currency"] == "USD"


# =============================================================================
# POST /resize-all-budgets
# =============================================================================


class TestResizeAllBudgets:
    """Tests for resize_all_budgets endpoint."""

    @pytest.mark.asyncio
    @patch("app.position_routers.position_actions_router.compute_resize_budget", return_value=0.05)
    async def test_resize_all_budgets_updates_positions(self, mock_resize, db_session):
        """Happy path: resizes all open positions for the user."""
        from app.position_routers.position_actions_router import resize_all_budgets

        user, account = await _create_user_with_account(db_session, email="resize_all@example.com")
        bot = await _create_bot(db_session, user, account)
        await _create_position(
            db_session, account, bot=bot, status="open",
            max_quote_allowed=0.01,
        )
        await _create_position(
            db_session, account, bot=bot, status="open",
            max_quote_allowed=0.02,
            product_id="SOL-BTC",
        )

        result = await resize_all_budgets(
            db=db_session,
            current_user=user,
        )

        assert result["updated_count"] == 2
        assert result["total_count"] == 2
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    @patch("app.position_routers.position_actions_router.compute_resize_budget", return_value=0.0)
    async def test_resize_all_budgets_skips_when_compute_returns_zero(self, mock_resize, db_session):
        """Edge case: positions where budget cannot be computed are skipped."""
        from app.position_routers.position_actions_router import resize_all_budgets

        user, account = await _create_user_with_account(db_session, email="resize_all_skip@example.com")
        await _create_position(db_session, account, status="open", max_quote_allowed=0.01)

        result = await resize_all_budgets(
            db=db_session,
            current_user=user,
        )

        assert result["updated_count"] == 0
        assert result["total_count"] == 1
        assert result["results"][0].get("skipped") is not None

    @pytest.mark.asyncio
    @patch("app.position_routers.position_actions_router.compute_resize_budget", return_value=0.05)
    async def test_resize_all_budgets_skips_unchanged(self, mock_resize, db_session):
        """Edge case: positions with budget already at target are skipped."""
        from app.position_routers.position_actions_router import resize_all_budgets

        user, account = await _create_user_with_account(db_session, email="resize_all_same@example.com")
        # max_quote_allowed already matches the mocked resize value
        await _create_position(
            db_session, account, status="open",
            max_quote_allowed=0.05,
        )

        result = await resize_all_budgets(
            db=db_session,
            current_user=user,
        )

        # The budget difference is < 0.000000015, so it should be skipped
        assert result["updated_count"] == 0

    @pytest.mark.asyncio
    async def test_resize_all_budgets_no_open_positions(self, db_session):
        """Edge case: user with no open positions returns empty results."""
        from app.position_routers.position_actions_router import resize_all_budgets

        user, account = await _create_user_with_account(db_session, email="resize_all_empty@example.com")
        # Only closed positions
        await _create_position(db_session, account, status="closed")

        result = await resize_all_budgets(
            db=db_session,
            current_user=user,
        )

        assert result["total_count"] == 0
        assert result["updated_count"] == 0
        assert "already have correct budgets" in result["message"]
