"""
Tests for manager write access on position action endpoints.

Covers L3: account members with 'manager' role can perform write operations
(cancel, force-close, update settings) on positions linked to a shared account.
Account members with 'observer' role are denied (404 — they don't appear in
manager_account_ids).

Affected router:
  backend/app/position_routers/position_actions_router.py
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import Account, Bot, BotProduct, Position, User
from app.models.sharing import AccountMembership


# =============================================================================
# Helpers
# =============================================================================


async def _make_user(db, email: str) -> User:
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_account(db, owner: User, name: str = "SharedAccount") -> Account:
    account = Account(
        user_id=owner.id,
        name=name,
        type="cex",
        exchange="coinbase",
        is_active=True,
        is_default=True,
    )
    db.add(account)
    await db.flush()
    return account


async def _make_bot(db, owner: User, account: Account, name: str = "TestBot") -> Bot:
    bot = Bot(
        user_id=owner.id,
        account_id=account.id,
        name=name,
        product_id="ETH-BTC",
        product_ids=["ETH-BTC"],
        strategy_type="macd_dca",
        strategy_config={"base_order_percentage": 5.0},
        is_active=True,
        check_interval_seconds=300,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(bot)
    await db.flush()
    bp = BotProduct(bot_id=bot.id, product_id="ETH-BTC")
    db.add(bp)
    await db.flush()
    return bot


async def _make_position(db, owner: User, account: Account, bot: Bot, status: str = "open") -> Position:
    pos = Position(
        bot_id=bot.id,
        user_id=owner.id,
        account_id=account.id,
        product_id="ETH-BTC",
        status=status,
        opened_at=datetime.utcnow(),
        initial_quote_balance=1.0,
        max_quote_allowed=0.25,
        total_quote_spent=0.01,
        total_base_acquired=0.5,
        average_buy_price=0.02,
        strategy_config_snapshot={
            "take_profit_percentage": 2.0,
            "max_safety_orders": 3,
            "base_order_percentage": 5.0,
        },
    )
    db.add(pos)
    await db.flush()
    return pos


async def _make_membership(db, account: Account, user: User, role: str) -> AccountMembership:
    m = AccountMembership(
        account_id=account.id,
        user_id=user.id,
        role=role,
        invited_by_user_id=account.user_id,
        expires_at=None,
    )
    db.add(m)
    await db.flush()
    return m


# =============================================================================
# cancel_position — observer denied, manager allowed
# =============================================================================


class TestCancelPositionManagerAccess:
    """Tests for POST /{position_id}/cancel with account member roles."""

    @pytest.mark.asyncio
    async def test_observer_cannot_cancel_position(self, db_session):
        """Security: observer of account gets 404 on cancel (not in manager_account_ids)."""
        from app.position_routers.position_actions_router import cancel_position

        owner = await _make_user(db_session, "pos_owner1@example.com")
        observer = await _make_user(db_session, "pos_observer1@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        position = await _make_position(db_session, owner, account, bot)
        await _make_membership(db_session, account, observer, role="observer")

        with pytest.raises(HTTPException) as exc_info:
            await cancel_position(position_id=position.id, db=db_session, current_user=observer)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_manager_can_cancel_position(self, db_session):
        """Happy path: manager of account can cancel an open position."""
        from app.position_routers.position_actions_router import cancel_position

        owner = await _make_user(db_session, "pos_owner2@example.com")
        manager = await _make_user(db_session, "pos_manager2@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        position = await _make_position(db_session, owner, account, bot)
        await _make_membership(db_session, account, manager, role="manager")

        result = await cancel_position(position_id=position.id, db=db_session, current_user=manager)

        assert "cancelled successfully" in result["message"]
        assert position.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_position_returns_400(self, db_session):
        """Edge case: manager gets 400 when trying to cancel a non-open position."""
        from app.position_routers.position_actions_router import cancel_position

        owner = await _make_user(db_session, "pos_owner3@example.com")
        manager = await _make_user(db_session, "pos_manager3@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        position = await _make_position(db_session, owner, account, bot, status="cancelled")
        await _make_membership(db_session, account, manager, role="manager")

        with pytest.raises(HTTPException) as exc_info:
            await cancel_position(position_id=position.id, db=db_session, current_user=manager)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_observer_gets_404_not_403_on_cancel(self, db_session):
        """Security: the 404 response does not leak that the position exists."""
        from app.position_routers.position_actions_router import cancel_position

        owner = await _make_user(db_session, "pos_owner4@example.com")
        observer = await _make_user(db_session, "pos_observer4@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        position = await _make_position(db_session, owner, account, bot)
        await _make_membership(db_session, account, observer, role="observer")

        with pytest.raises(HTTPException) as exc_info:
            await cancel_position(position_id=position.id, db=db_session, current_user=observer)

        # Must be 404, not 403 — don't confirm the resource exists to unauthorized callers
        assert exc_info.value.status_code == 404


# =============================================================================
# force_close_position — observer denied, manager allowed
# =============================================================================


class TestForceClosePositionManagerAccess:
    """Tests for POST /{position_id}/force-close with account member roles."""

    @pytest.mark.asyncio
    async def test_observer_cannot_force_close_position(self, db_session):
        """Security: observer of account gets 404 on force-close."""
        from app.position_routers.position_actions_router import force_close_position

        owner = await _make_user(db_session, "fc_owner1@example.com")
        observer = await _make_user(db_session, "fc_observer1@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        position = await _make_position(db_session, owner, account, bot)
        await _make_membership(db_session, account, observer, role="observer")

        with pytest.raises(HTTPException) as exc_info:
            await force_close_position(
                position_id=position.id,
                skip_slippage_guard=False,
                db=db_session,
                current_user=observer,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_manager_can_force_close_position(self, db_session):
        """Happy path: manager of account can force-close an open position."""
        from app.position_routers.position_actions_router import force_close_position

        owner = await _make_user(db_session, "fc_owner2@example.com")
        manager = await _make_user(db_session, "fc_manager2@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        position = await _make_position(db_session, owner, account, bot)
        await _make_membership(db_session, account, manager, role="manager")

        mock_exchange = MagicMock()
        mock_exchange.get_current_price = AsyncMock(return_value=0.05)

        mock_strategy = MagicMock()

        mock_engine = MagicMock()
        mock_engine.execute_sell = AsyncMock(return_value=(MagicMock(), 0.002, 5.0))

        with patch(
            "app.position_routers.position_actions_router.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_exchange,
        ), patch(
            "app.strategies.StrategyRegistry.get_strategy",
            return_value=mock_strategy,
        ), patch(
            "app.position_routers.position_actions_router.StrategyTradingEngine",
            return_value=mock_engine,
        ):
            result = await force_close_position(
                position_id=position.id,
                skip_slippage_guard=True,
                db=db_session,
                current_user=manager,
            )

        assert "closed successfully" in result["message"]
        assert "profit_quote" in result


# =============================================================================
# update_position_settings — observer denied, manager allowed
# =============================================================================


class TestUpdatePositionSettingsManagerAccess:
    """Tests for PATCH /{position_id}/settings with account member roles."""

    @pytest.mark.asyncio
    async def test_observer_cannot_update_position_settings(self, db_session):
        """Security: observer of account gets 404 on settings update."""
        from app.position_routers.position_actions_router import update_position_settings
        from app.schemas.position import UpdatePositionSettingsRequest

        owner = await _make_user(db_session, "upd_owner1@example.com")
        observer = await _make_user(db_session, "upd_observer1@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        position = await _make_position(db_session, owner, account, bot)
        await _make_membership(db_session, account, observer, role="observer")

        settings = UpdatePositionSettingsRequest(take_profit_percentage=3.0)

        with pytest.raises(HTTPException) as exc_info:
            await update_position_settings(
                position_id=position.id,
                settings=settings,
                db=db_session,
                current_user=observer,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_manager_can_update_position_settings(self, db_session):
        """Happy path: manager can update take_profit_percentage on a position."""
        from app.position_routers.position_actions_router import update_position_settings
        from app.schemas.position import UpdatePositionSettingsRequest

        owner = await _make_user(db_session, "upd_owner2@example.com")
        manager = await _make_user(db_session, "upd_manager2@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        position = await _make_position(db_session, owner, account, bot)
        await _make_membership(db_session, account, manager, role="manager")

        settings = UpdatePositionSettingsRequest(take_profit_percentage=4.5)

        result = await update_position_settings(
            position_id=position.id,
            settings=settings,
            db=db_session,
            current_user=manager,
        )

        assert "updated successfully" in result["message"]
        assert result["new_config"]["take_profit_percentage"] == 4.5

    @pytest.mark.asyncio
    async def test_manager_update_settings_no_fields_returns_400(self, db_session):
        """Edge case: manager providing no fields gets 400."""
        from app.position_routers.position_actions_router import update_position_settings
        from app.schemas.position import UpdatePositionSettingsRequest

        owner = await _make_user(db_session, "upd_owner3@example.com")
        manager = await _make_user(db_session, "upd_manager3@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        position = await _make_position(db_session, owner, account, bot)
        await _make_membership(db_session, account, manager, role="manager")

        settings = UpdatePositionSettingsRequest()  # all fields None

        with pytest.raises(HTTPException) as exc_info:
            await update_position_settings(
                position_id=position.id,
                settings=settings,
                db=db_session,
                current_user=manager,
            )

        assert exc_info.value.status_code == 400
        assert "No settings provided" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_manager_update_settings_on_non_open_position_returns_400(self, db_session):
        """Edge case: manager cannot update settings on a closed position."""
        from app.position_routers.position_actions_router import update_position_settings
        from app.schemas.position import UpdatePositionSettingsRequest

        owner = await _make_user(db_session, "upd_owner4@example.com")
        manager = await _make_user(db_session, "upd_manager4@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        position = await _make_position(db_session, owner, account, bot, status="closed")
        await _make_membership(db_session, account, manager, role="manager")

        settings = UpdatePositionSettingsRequest(take_profit_percentage=3.0)

        with pytest.raises(HTTPException) as exc_info:
            await update_position_settings(
                position_id=position.id,
                settings=settings,
                db=db_session,
                current_user=manager,
            )

        assert exc_info.value.status_code == 400
