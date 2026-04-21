"""Tests for the get_prior_ai_signals tool.

Returns the user's last N AI decisions for the current product plus outcome
backfill columns (win/loss/breakeven + realized_pnl_pct) where available.

Covers:
- Happy path — rows returned newest-first with outcome columns
- Filter — only this user + this product
- Filter — days window clips older rows
- Edge — no prior signals returns empty list
- Validation — clamp days (1..90) and limit (1..20)
- Registry — tool is registered under its name
"""

from datetime import datetime, timedelta

from app.indicators.ai_tools import REGISTRY, ToolContext, execute
from app.models import AIOpinionLog, User


async def _make_user(db, email="p@p.com"):
    user = User(email=email, hashed_password="x")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_opinion(
    db, user, *,
    product_id="ETH-USD",
    signal="buy",
    confidence=70,
    created_days_ago=1,
    outcome=None,
    realized_pnl_pct=None,
    is_sell_check=False,
    ai_model="claude",
    reasoning="test reason",
    tool_calls=None,
):
    row = AIOpinionLog(
        user_id=user.id,
        product_id=product_id,
        signal=signal,
        confidence=confidence,
        reasoning=reasoning,
        ai_model=ai_model,
        tool_calls=tool_calls,
        is_sell_check=is_sell_check,
        created_at=datetime.utcnow() - timedelta(days=created_days_ago),
        outcome=outcome,
        realized_pnl_pct=realized_pnl_pct,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


class TestGetPriorAISignals:
    async def test_happy_path_newest_first(self, db_session):
        user = await _make_user(db_session)
        await _make_opinion(
            db_session, user, signal="buy", confidence=55, created_days_ago=5,
            outcome="loss", realized_pnl_pct=-1.2,
        )
        await _make_opinion(
            db_session, user, signal="hold", confidence=60, created_days_ago=3,
        )
        await _make_opinion(
            db_session, user, signal="buy", confidence=80, created_days_ago=1,
            outcome="win", realized_pnl_pct=2.5,
        )

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_prior_ai_signals", {"days": 14, "limit": 10}, ctx,
        )

        signals = result["signals"]
        assert len(signals) == 3
        # Newest first
        confidences = [s["confidence"] for s in signals]
        assert confidences == [80, 60, 55]
        # Outcome columns surfaced when present
        newest = signals[0]
        assert newest["signal"] == "buy"
        assert newest["outcome"] == "win"
        assert newest["realized_pnl_pct"] == 2.5
        # Middle row has no outcome yet
        assert signals[1]["outcome"] is None

    async def test_filters_other_products(self, db_session):
        user = await _make_user(db_session)
        await _make_opinion(db_session, user, product_id="ETH-USD")
        await _make_opinion(db_session, user, product_id="BTC-USD")

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_prior_ai_signals", {"days": 14, "limit": 10}, ctx,
        )
        assert len(result["signals"]) == 1
        assert result["signals"][0]["product_id"] == "ETH-USD"

    async def test_filters_other_users(self, db_session):
        owner = await _make_user(db_session, email="owner@p.com")
        other = await _make_user(db_session, email="other@p.com")
        await _make_opinion(db_session, owner)
        await _make_opinion(db_session, other)

        ctx = ToolContext(
            db=db_session, user_id=owner.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_prior_ai_signals", {"days": 14, "limit": 10}, ctx,
        )
        assert len(result["signals"]) == 1

    async def test_days_window_clips_old_rows(self, db_session):
        user = await _make_user(db_session)
        await _make_opinion(db_session, user, created_days_ago=30)
        await _make_opinion(db_session, user, created_days_ago=1)

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_prior_ai_signals", {"days": 7, "limit": 10}, ctx,
        )
        assert len(result["signals"]) == 1

    async def test_empty_returns_empty_list(self, db_session):
        user = await _make_user(db_session)
        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_prior_ai_signals", {"days": 14, "limit": 10}, ctx,
        )
        assert result["signals"] == []

    async def test_limit_clamped(self, db_session):
        user = await _make_user(db_session)
        for i in range(25):
            await _make_opinion(db_session, user, created_days_ago=(i % 6) + 1)

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_prior_ai_signals", {"days": 30, "limit": 999}, ctx,
        )
        assert len(result["signals"]) <= 20

    async def test_days_clamped_to_max(self, db_session):
        """days > 90 must be clamped to the 90-day retention horizon."""
        user = await _make_user(db_session)
        # Row outside 90-day window — should never be returned.
        await _make_opinion(db_session, user, created_days_ago=120)
        await _make_opinion(db_session, user, created_days_ago=1)

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_prior_ai_signals", {"days": 999, "limit": 20}, ctx,
        )
        assert len(result["signals"]) == 1


class TestRegistry:
    def test_tool_is_registered(self):
        assert "get_prior_ai_signals" in REGISTRY
