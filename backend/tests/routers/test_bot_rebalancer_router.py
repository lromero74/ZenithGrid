"""
Tests for backend/app/bot_routers/bot_rebalancer_router.py

Covers the bot budget rebalancer save endpoint, especially the max_total_pct
validation boundary and account-scoped access checks.
"""

import pytest
from fastapi import HTTPException

from app.bot_routers.bot_rebalancer_router import save_rebalancer
from app.bot_routers.schemas import BotRebalancerSaveRequest
from app.models import Account, Bot, User
from app.utils.timeutil import utcnow


def _make_user(db_session, email="rebalancer@example.com"):
    """Create and flush a test user."""
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=utcnow(),
    )
    db_session.add(user)
    return user


async def _make_account(db_session, user, name="Test Account"):
    """Create and flush a test account owned by user."""
    account = Account(
        user_id=user.id,
        name=name,
        type="paper",
        is_active=True,
        created_at=utcnow(),
    )
    db_session.add(account)
    await db_session.flush()
    return account


async def _make_bot(db_session, user, account_id, name="TestBot", product_id="BTC-USD"):
    """Create, flush, and return a test bot."""
    bot = Bot(
        user_id=user.id,
        account_id=account_id,
        name=name,
        strategy_type="grid_trading",
        strategy_config={"upper_price": 100_000, "lower_price": 90_000, "grid_levels": 5},
        product_id=product_id,
        product_ids=[product_id],
        is_active=False,
        budget_percentage=5.0,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db_session.add(bot)
    await db_session.flush()
    return bot


class TestSaveRebalancerValidation:
    """Tests for PUT /api/bots/rebalancer validation rules."""

    @pytest.mark.asyncio
    async def test_save_accepts_200_percent_max_total(self, db_session):
        """Happy path: max_total_pct up to 200 is accepted."""
        user = _make_user(db_session)
        await db_session.flush()
        account = await _make_account(db_session, user)
        bot1 = await _make_bot(db_session, user, account.id, name="Bot1", product_id="BTC-USD")
        bot2 = await _make_bot(db_session, user, account.id, name="Bot2", product_id="ETH-USD")

        payload = BotRebalancerSaveRequest(
            account_id=account.id,
            base_currency="USD",
            max_total_pct=200.0,
            overweight_tolerance_pct=5.0,
            bots=[
                {"bot_id": bot1.id, "enabled": True, "target_pct": 120.0},
                {"bot_id": bot2.id, "enabled": True, "target_pct": 80.0},
            ],
        )

        result = await save_rebalancer(payload=payload, db=db_session, current_user=user)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_save_rejects_201_percent_max_total(self, db_session):
        """Failure: max_total_pct above 200 is rejected."""
        user = _make_user(db_session)
        await db_session.flush()
        account = await _make_account(db_session, user)
        bot1 = await _make_bot(db_session, user, account.id, name="Bot1", product_id="BTC-USD")

        payload = BotRebalancerSaveRequest(
            account_id=account.id,
            base_currency="USD",
            max_total_pct=201.0,
            overweight_tolerance_pct=5.0,
            bots=[
                {"bot_id": bot1.id, "enabled": True, "target_pct": 100.0},
            ],
        )

        with pytest.raises(HTTPException) as exc_info:
            await save_rebalancer(payload=payload, db=db_session, current_user=user)
        assert exc_info.value.status_code == 400
        assert "between 1 and 200" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_save_rejects_total_exceeding_max(self, db_session):
        """Failure: enabled-bot total cannot exceed max_total_pct."""
        user = _make_user(db_session)
        await db_session.flush()
        account = await _make_account(db_session, user)
        bot1 = await _make_bot(db_session, user, account.id, name="Bot1", product_id="BTC-USD")
        bot2 = await _make_bot(db_session, user, account.id, name="Bot2", product_id="ETH-USD")

        payload = BotRebalancerSaveRequest(
            account_id=account.id,
            base_currency="USD",
            max_total_pct=150.0,
            overweight_tolerance_pct=5.0,
            bots=[
                {"bot_id": bot1.id, "enabled": True, "target_pct": 100.0},
                {"bot_id": bot2.id, "enabled": True, "target_pct": 60.0},
            ],
        )

        with pytest.raises(HTTPException) as exc_info:
            await save_rebalancer(payload=payload, db=db_session, current_user=user)
        assert exc_info.value.status_code == 400
        assert "exceeds max_total_pct" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_save_rejects_other_users_account(self, db_session):
        """Security: a user cannot save rebalancer settings for another user's account."""
        owner = _make_user(db_session, email="owner@example.com")
        attacker = _make_user(db_session, email="attacker@example.com")
        await db_session.flush()
        account = await _make_account(db_session, owner, name="Owner Account")
        bot = await _make_bot(db_session, owner, account.id, name="OwnerBot", product_id="BTC-USD")

        payload = BotRebalancerSaveRequest(
            account_id=account.id,
            base_currency="USD",
            max_total_pct=100.0,
            overweight_tolerance_pct=5.0,
            bots=[
                {"bot_id": bot.id, "enabled": True, "target_pct": 100.0},
            ],
        )

        with pytest.raises(HTTPException) as exc_info:
            await save_rebalancer(payload=payload, db=db_session, current_user=attacker)
        assert exc_info.value.status_code == 403
