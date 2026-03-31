"""
Tests for the Bot Budget Rebalancer router.

Covers:
- GET /api/bots/rebalancer?account_id=... returns bots grouped by quote currency
- PUT /api/bots/rebalancer saves group settings and writes bot.budget_percentage
- Validation: sum > max_total_pct → 400, max_total_pct > 150 → 400
- Auth: wrong account → 404/403
- Upsert: saving twice updates existing group, doesn't duplicate
"""

import pytest
from datetime import datetime
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models import Account, Bot, BotProduct, User
from app.models.trading import BotRebalancerGroup


# =============================================================================
# Helpers
# =============================================================================


async def _create_user(db_session, email="user@example.com") -> User:
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        is_superuser=True,  # superuser bypasses RBAC for simplicity in these tests
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _create_account(db_session, user: User, name="Test Account") -> Account:
    account = Account(
        user_id=user.id,
        name=name,
        type="cex",
        exchange="coinbase",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()
    return account


async def _create_bot(
    db_session,
    user: User,
    account: Account,
    name="Test Bot",
    product_ids=None,
) -> Bot:
    if product_ids is None:
        product_ids = ["ETH-USDC"]
    bot = Bot(
        user_id=user.id,
        account_id=account.id,
        name=name,
        strategy_type="macd_dca",
        strategy_config={"base_order_fixed": 0.01},
        product_id=product_ids[0],
        product_ids=product_ids,
        is_active=False,
        budget_percentage=0.0,
        bot_rebalancer_enabled=False,
        bot_rebalancer_target_pct=0.0,
    )
    db_session.add(bot)
    await db_session.flush()
    # Create BotProduct records so get_quote_currency() reads from the junction table
    for pid in product_ids:
        db_session.add(BotProduct(bot_id=bot.id, product_id=pid))
    await db_session.flush()
    await db_session.refresh(bot)
    return bot


def _build_app(db_session, current_user: User) -> FastAPI:
    """Build a minimal FastAPI app with the rebalancer router and overridden deps."""
    from app.routers.bots import router as bots_router

    app = FastAPI()
    app.include_router(bots_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return current_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


# =============================================================================
# Tests
# =============================================================================


class TestGetRebalancerState:
    @pytest.mark.asyncio
    async def test_get_rebalancer_state_returns_groups_by_currency(self, db_session):
        """GET returns bots grouped by quote currency with correct defaults."""
        user = await _create_user(db_session)
        account = await _create_account(db_session, user)
        bot1 = await _create_bot(
            db_session, user, account, name="Bot USDC 1", product_ids=["ETH-USDC"]
        )
        bot2 = await _create_bot(
            db_session, user, account, name="Bot USDC 2", product_ids=["BTC-USDC"]
        )
        bot3 = await _create_bot(
            db_session, user, account, name="Bot BTC 1", product_ids=["ETH-BTC"]
        )

        app = _build_app(db_session, user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/bots/rebalancer?account_id={account.id}"
            )

        assert response.status_code == 200
        data = response.json()
        # Should have two currency groups: BTC and USDC
        currencies = {g["base_currency"] for g in data}
        assert "USDC" in currencies
        assert "BTC" in currencies

        usdc_group = next(g for g in data if g["base_currency"] == "USDC")
        assert len(usdc_group["bots"]) == 2
        assert usdc_group["max_total_pct"] == 100.0

        btc_group = next(g for g in data if g["base_currency"] == "BTC")
        assert len(btc_group["bots"]) == 1
        _ = bot1.id, bot2.id, bot3.id  # ensure variables are used

    @pytest.mark.asyncio
    async def test_get_rebalancer_state_unknown_account_returns_404(self, db_session):
        """GET with non-existent or unowned account returns 404."""
        user = await _create_user(db_session)
        app = _build_app(db_session, user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/bots/rebalancer?account_id=99999")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_rebalancer_state_merges_existing_group_settings(
        self, db_session
    ):
        """GET merges existing BotRebalancerGroup settings for a currency."""
        user = await _create_user(db_session)
        account = await _create_account(db_session, user)
        await _create_bot(
            db_session, user, account, name="Bot USDC", product_ids=["ETH-USDC"]
        )
        # Pre-create a group
        group = BotRebalancerGroup(
            account_id=account.id,
            base_currency="USDC",
            max_total_pct=80.0,
            overweight_tolerance_pct=10.0,
            enabled=True,
        )
        db_session.add(group)
        await db_session.flush()

        app = _build_app(db_session, user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/bots/rebalancer?account_id={account.id}"
            )

        assert response.status_code == 200
        data = response.json()
        usdc_group = next(g for g in data if g["base_currency"] == "USDC")
        assert usdc_group["max_total_pct"] == 80.0
        assert usdc_group["overweight_tolerance_pct"] == 10.0


class TestSaveRebalancer:
    @pytest.mark.asyncio
    async def test_save_rebalancer_writes_budget_percentage(self, db_session):
        """PUT saves group and writes bot.budget_percentage for enabled bots."""
        user = await _create_user(db_session)
        account = await _create_account(db_session, user)
        bot = await _create_bot(
            db_session, user, account, name="Bot USDC", product_ids=["ETH-USDC"]
        )

        payload = {
            "account_id": account.id,
            "base_currency": "USDC",
            "max_total_pct": 100.0,
            "overweight_tolerance_pct": 5.0,
            "bots": [
                {"bot_id": bot.id, "enabled": True, "target_pct": 60.0}
            ],
        }

        app = _build_app(db_session, user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put("/api/bots/rebalancer", json=payload)

        assert response.status_code == 200
        assert response.json()["ok"] is True

        # Reload bot and verify
        await db_session.refresh(bot)
        assert bot.bot_rebalancer_enabled is True
        assert bot.bot_rebalancer_target_pct == 60.0
        assert bot.budget_percentage == 60.0

    @pytest.mark.asyncio
    async def test_save_rebalancer_sum_exceeds_max_returns_400(self, db_session):
        """PUT returns 400 when sum of enabled bot target_pcts > max_total_pct."""
        user = await _create_user(db_session)
        account = await _create_account(db_session, user)
        bot1 = await _create_bot(
            db_session, user, account, name="Bot A", product_ids=["ETH-USDC"]
        )
        bot2 = await _create_bot(
            db_session, user, account, name="Bot B", product_ids=["BTC-USDC"]
        )

        payload = {
            "account_id": account.id,
            "base_currency": "USDC",
            "max_total_pct": 100.0,
            "overweight_tolerance_pct": 5.0,
            "bots": [
                {"bot_id": bot1.id, "enabled": True, "target_pct": 70.0},
                {"bot_id": bot2.id, "enabled": True, "target_pct": 50.0},  # 120 > 100
            ],
        }

        app = _build_app(db_session, user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put("/api/bots/rebalancer", json=payload)

        assert response.status_code == 400
        assert "exceeds" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_save_rebalancer_invalid_max_pct_returns_400(self, db_session):
        """PUT returns 400 when max_total_pct > 150."""
        user = await _create_user(db_session)
        account = await _create_account(db_session, user)
        bot = await _create_bot(
            db_session, user, account, name="Bot USDC", product_ids=["ETH-USDC"]
        )

        payload = {
            "account_id": account.id,
            "base_currency": "USDC",
            "max_total_pct": 200.0,  # Invalid: > 150
            "overweight_tolerance_pct": 5.0,
            "bots": [{"bot_id": bot.id, "enabled": True, "target_pct": 100.0}],
        }

        app = _build_app(db_session, user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put("/api/bots/rebalancer", json=payload)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_save_rebalancer_wrong_account_returns_403(self, db_session):
        """PUT returns 403 when account_id belongs to a different user."""
        owner = await _create_user(db_session, email="owner@example.com")
        attacker = await _create_user(db_session, email="attacker@example.com")
        account = await _create_account(db_session, owner)
        bot = await _create_bot(
            db_session, owner, account, name="Bot USDC", product_ids=["ETH-USDC"]
        )

        payload = {
            "account_id": account.id,
            "base_currency": "USDC",
            "max_total_pct": 100.0,
            "overweight_tolerance_pct": 5.0,
            "bots": [{"bot_id": bot.id, "enabled": True, "target_pct": 50.0}],
        }

        # Request made as the attacker
        app = _build_app(db_session, attacker)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put("/api/bots/rebalancer", json=payload)

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_save_rebalancer_upserts_group(self, db_session):
        """Saving twice updates the existing group, does not create a duplicate."""
        user = await _create_user(db_session)
        account = await _create_account(db_session, user)
        bot = await _create_bot(
            db_session, user, account, name="Bot USDC", product_ids=["ETH-USDC"]
        )

        payload = {
            "account_id": account.id,
            "base_currency": "USDC",
            "max_total_pct": 100.0,
            "overweight_tolerance_pct": 5.0,
            "bots": [{"bot_id": bot.id, "enabled": True, "target_pct": 40.0}],
        }

        app = _build_app(db_session, user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r1 = await client.put("/api/bots/rebalancer", json=payload)
        assert r1.status_code == 200

        # Save again with different values
        payload["max_total_pct"] = 120.0
        payload["bots"][0]["target_pct"] = 80.0

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r2 = await client.put("/api/bots/rebalancer", json=payload)
        assert r2.status_code == 200

        # Verify only one group exists
        from sqlalchemy import select, func
        count_q = await db_session.execute(
            select(func.count()).where(
                BotRebalancerGroup.account_id == account.id,
                BotRebalancerGroup.base_currency == "USDC",
            )
        )
        assert count_q.scalar() == 1

        # Verify updated values
        group_q = await db_session.execute(
            select(BotRebalancerGroup).where(
                BotRebalancerGroup.account_id == account.id,
                BotRebalancerGroup.base_currency == "USDC",
            )
        )
        group = group_q.scalar_one()
        assert group.max_total_pct == 120.0

        await db_session.refresh(bot)
        assert bot.budget_percentage == 80.0

    @pytest.mark.asyncio
    async def test_save_rebalancer_disabled_bot_not_written(self, db_session):
        """Disabled bot slot: sets rebalancer_enabled=False but does not change budget_percentage."""
        user = await _create_user(db_session)
        account = await _create_account(db_session, user)
        bot = await _create_bot(
            db_session, user, account, name="Bot USDC", product_ids=["ETH-USDC"]
        )
        bot.budget_percentage = 33.0  # Pre-set budget
        await db_session.flush()

        payload = {
            "account_id": account.id,
            "base_currency": "USDC",
            "max_total_pct": 100.0,
            "overweight_tolerance_pct": 5.0,
            "bots": [{"bot_id": bot.id, "enabled": False, "target_pct": 0.0}],
        }

        app = _build_app(db_session, user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put("/api/bots/rebalancer", json=payload)

        assert response.status_code == 200
        await db_session.refresh(bot)
        assert bot.bot_rebalancer_enabled is False
        # budget_percentage should NOT be overwritten for disabled slots
        assert bot.budget_percentage == 33.0
