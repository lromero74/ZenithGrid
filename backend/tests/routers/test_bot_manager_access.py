"""
Tests for manager write access on bot endpoints.

Covers L3: account members with 'manager' role can perform write operations
(start/stop/force-run, update, delete, clone) on bots linked to a shared account.
Account members with 'observer' role are denied (404 — they don't appear in
manager_account_ids).

Affected routers:
  backend/app/bot_routers/bot_control_router.py
  backend/app/bot_routers/bot_crud_router.py
"""

import pytest
from datetime import datetime

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


async def _make_bot(
    db,
    owner: User,
    account: Account,
    name: str = "TestBot",
    is_active: bool = False,
) -> Bot:
    bot = Bot(
        user_id=owner.id,
        account_id=account.id,
        name=name,
        product_id="ETH-BTC",
        product_ids=["ETH-BTC"],
        strategy_type="macd_dca",
        strategy_config={"base_order_percentage": 5.0},
        is_active=is_active,
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
# Bot Control — start/stop/force-run (observer denied, manager allowed)
# =============================================================================


class TestBotControlManagerAccess:
    """Tests for start/stop/force-run with account member roles."""

    @pytest.mark.asyncio
    async def test_observer_cannot_start_bot(self, db_session):
        """Security: observer of account gets 404 on start (not in manager_account_ids)."""
        from app.bot_routers.bot_control_router import start_bot

        owner = await _make_user(db_session, "ctrl_owner1@example.com")
        observer = await _make_user(db_session, "ctrl_observer1@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account, is_active=False)
        await _make_membership(db_session, account, observer, role="observer")

        with pytest.raises(HTTPException) as exc_info:
            await start_bot(bot_id=bot.id, db=db_session, current_user=observer)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_manager_can_start_bot(self, db_session):
        """Happy path: manager of account can start a bot on that account."""
        from app.bot_routers.bot_control_router import start_bot

        owner = await _make_user(db_session, "ctrl_owner2@example.com")
        manager = await _make_user(db_session, "ctrl_manager2@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account, is_active=False)
        await _make_membership(db_session, account, manager, role="manager")

        result = await start_bot(bot_id=bot.id, db=db_session, current_user=manager)

        assert "started successfully" in result["message"]
        assert bot.is_active is True

    @pytest.mark.asyncio
    async def test_observer_cannot_stop_bot(self, db_session):
        """Security: observer of account gets 404 on stop."""
        from app.bot_routers.bot_control_router import stop_bot

        owner = await _make_user(db_session, "ctrl_owner3@example.com")
        observer = await _make_user(db_session, "ctrl_observer3@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account, is_active=True)
        await _make_membership(db_session, account, observer, role="observer")

        with pytest.raises(HTTPException) as exc_info:
            await stop_bot(bot_id=bot.id, db=db_session, current_user=observer)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_manager_can_stop_bot(self, db_session):
        """Happy path: manager of account can stop a bot."""
        from app.bot_routers.bot_control_router import stop_bot

        owner = await _make_user(db_session, "ctrl_owner4@example.com")
        manager = await _make_user(db_session, "ctrl_manager4@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account, is_active=True)
        await _make_membership(db_session, account, manager, role="manager")

        result = await stop_bot(bot_id=bot.id, db=db_session, current_user=manager)

        assert "stopped successfully" in result["message"]
        assert bot.is_active is False

    @pytest.mark.asyncio
    async def test_observer_cannot_force_run_bot(self, db_session):
        """Security: observer of account gets 404 on force-run."""
        from app.bot_routers.bot_control_router import force_run_bot

        owner = await _make_user(db_session, "ctrl_owner5@example.com")
        observer = await _make_user(db_session, "ctrl_observer5@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account, is_active=True)
        await _make_membership(db_session, account, observer, role="observer")

        with pytest.raises(HTTPException) as exc_info:
            await force_run_bot(bot_id=bot.id, db=db_session, current_user=observer)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_manager_can_force_run_bot(self, db_session):
        """Happy path: manager of account can force-run an active bot."""
        from app.bot_routers.bot_control_router import force_run_bot

        owner = await _make_user(db_session, "ctrl_owner6@example.com")
        manager = await _make_user(db_session, "ctrl_manager6@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account, is_active=True)
        await _make_membership(db_session, account, manager, role="manager")

        result = await force_run_bot(bot_id=bot.id, db=db_session, current_user=manager)

        assert "next monitor cycle" in result["message"]


# =============================================================================
# Bot CRUD — update / delete / clone (observer denied, manager allowed)
# =============================================================================


class TestBotCrudManagerAccess:
    """Tests for update/delete/clone with account member roles."""

    @pytest.mark.asyncio
    async def test_observer_cannot_update_bot_config(self, db_session):
        """Security: observer gets 404 when trying to update a bot's config."""
        from app.bot_routers.bot_crud_router import update_bot
        from app.bot_routers.schemas import BotUpdate

        owner = await _make_user(db_session, "crud_owner1@example.com")
        observer = await _make_user(db_session, "crud_observer1@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        await _make_membership(db_session, account, observer, role="observer")

        update = BotUpdate(description="hacked description")

        with pytest.raises(HTTPException) as exc_info:
            await update_bot(bot_id=bot.id, bot_update=update, db=db_session, current_user=observer)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_manager_can_update_bot_config(self, db_session):
        """Happy path: manager can update a bot's description."""
        from app.bot_routers.bot_crud_router import update_bot
        from app.bot_routers.schemas import BotUpdate

        owner = await _make_user(db_session, "crud_owner2@example.com")
        manager = await _make_user(db_session, "crud_manager2@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        await _make_membership(db_session, account, manager, role="manager")

        update = BotUpdate(description="manager description")

        result = await update_bot(bot_id=bot.id, bot_update=update, db=db_session, current_user=manager)

        assert result.description == "manager description"

    @pytest.mark.asyncio
    async def test_observer_cannot_delete_bot(self, db_session):
        """Security: observer gets 404 when attempting to delete a bot."""
        from app.bot_routers.bot_crud_router import delete_bot

        owner = await _make_user(db_session, "crud_owner3@example.com")
        observer = await _make_user(db_session, "crud_observer3@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        await _make_membership(db_session, account, observer, role="observer")

        with pytest.raises(HTTPException) as exc_info:
            await delete_bot(bot_id=bot.id, db=db_session, current_user=observer)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_manager_can_delete_bot_with_no_open_positions(self, db_session):
        """Happy path: manager can delete a bot that has no open positions."""
        from app.bot_routers.bot_crud_router import delete_bot

        owner = await _make_user(db_session, "crud_owner4@example.com")
        manager = await _make_user(db_session, "crud_manager4@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        await _make_membership(db_session, account, manager, role="manager")

        result = await delete_bot(bot_id=bot.id, db=db_session, current_user=manager)

        assert "deleted successfully" in result["message"]

    @pytest.mark.asyncio
    async def test_manager_cannot_delete_bot_with_open_positions(self, db_session):
        """Edge case: manager is blocked from deleting bot with open positions (400)."""
        from app.bot_routers.bot_crud_router import delete_bot

        owner = await _make_user(db_session, "crud_owner5@example.com")
        manager = await _make_user(db_session, "crud_manager5@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        await _make_membership(db_session, account, manager, role="manager")

        # Add an open position
        pos = Position(
            bot_id=bot.id,
            user_id=owner.id,
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
        db_session.add(pos)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await delete_bot(bot_id=bot.id, db=db_session, current_user=manager)

        assert exc_info.value.status_code == 400
        assert "open positions" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_observer_cannot_clone_bot(self, db_session):
        """Security: observer gets 404 when trying to clone a bot."""
        from app.bot_routers.bot_crud_router import clone_bot

        owner = await _make_user(db_session, "crud_owner6@example.com")
        observer = await _make_user(db_session, "crud_observer6@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account)
        await _make_membership(db_session, account, observer, role="observer")

        with pytest.raises(HTTPException) as exc_info:
            await clone_bot(bot_id=bot.id, db=db_session, current_user=observer)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_manager_can_clone_bot(self, db_session):
        """Happy path: manager can clone a bot on a shared account."""
        from app.bot_routers.bot_crud_router import clone_bot

        owner = await _make_user(db_session, "crud_owner7@example.com")
        manager = await _make_user(db_session, "crud_manager7@example.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, owner, account, name="OriginalBot")
        await _make_membership(db_session, account, manager, role="manager")

        result = await clone_bot(bot_id=bot.id, db=db_session, current_user=manager)

        assert "OriginalBot" in result.name
        assert "Copy" in result.name
        assert result.is_active is False


# =============================================================================
# Bot Create — observer gets 403 when specifying account_id
# =============================================================================


class TestBotCreateAccountAccess:
    """Tests for create_bot account_id access control."""

    @pytest.mark.asyncio
    async def test_observer_cannot_create_bot_on_shared_account(self, db_session):
        """Security: observer specifying account_id gets 403 (not manager).

        The access control check occurs after strategy validation, so we mock
        the StrategyRegistry to focus this test purely on access control.
        """
        from app.bot_routers.bot_crud_router import create_bot
        from app.bot_routers.schemas import BotCreate

        owner = await _make_user(db_session, "create_owner1@example.com")
        observer = await _make_user(db_session, "create_observer1@example.com")
        account = await _make_account(db_session, owner)
        await _make_membership(db_session, account, observer, role="observer")

        bot_data = BotCreate(
            name="ObserverAttemptBot",
            strategy_type="indicator_based",
            strategy_config={"base_order_percentage": 5.0},
            product_id="ETH-BTC",
            product_ids=["ETH-BTC"],
            account_id=account.id,
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_bot(bot_data=bot_data, db=db_session, current_user=observer)

        assert exc_info.value.status_code == 403
        assert "Manager access required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_manager_can_create_bot_on_shared_account(self, db_session):
        """Happy path: manager can create a bot on the shared account."""
        from app.bot_routers.bot_crud_router import create_bot
        from app.bot_routers.schemas import BotCreate

        owner = await _make_user(db_session, "create_owner2@example.com")
        manager = await _make_user(db_session, "create_manager2@example.com")
        account = await _make_account(db_session, owner)
        await _make_membership(db_session, account, manager, role="manager")

        bot_data = BotCreate(
            name="ManagerCreatedBot",
            strategy_type="indicator_based",
            strategy_config={"base_order_percentage": 5.0},
            product_id="ETH-BTC",
            product_ids=["ETH-BTC"],
            account_id=account.id,
        )

        result = await create_bot(bot_data=bot_data, db=db_session, current_user=manager)

        assert result.name == "ManagerCreatedBot"
        assert result.account_id == account.id
        assert result.is_active is False
