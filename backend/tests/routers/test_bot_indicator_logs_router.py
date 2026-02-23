"""
Tests for backend/app/bot_routers/bot_indicator_logs_router.py

Covers indicator log retrieval with filters and indicator log summary.
"""

import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException

from app.models import Bot, IndicatorLog, User


# =============================================================================
# Helpers
# =============================================================================


def _make_user():
    """Create a test user."""
    user = User(
        email="indicator@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=datetime.utcnow(),
    )
    return user


async def _make_bot(db_session, user, name="IndicatorBot"):
    """Create, flush, and return a test bot."""
    bot = Bot(
        user_id=user.id,
        name=name,
        strategy_type="indicator_dca",
        strategy_config={"indicators": ["rsi", "macd"]},
        product_id="ETH-BTC",
        product_ids=["ETH-BTC"],
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(bot)
    await db_session.flush()
    return bot


async def _make_indicator_log(db_session, bot, product_id="ETH-BTC",
                              phase="base_order", conditions_met=True,
                              timestamp=None, current_price=0.05):
    """Create and flush an indicator log entry."""
    log = IndicatorLog(
        bot_id=bot.id,
        product_id=product_id,
        phase=phase,
        conditions_met=conditions_met,
        conditions_detail=[
            {"type": "rsi", "operator": "<", "threshold": 30, "actual_value": 25, "result": True}
        ],
        indicators_snapshot={"rsi": 25.0, "macd": 0.001},
        current_price=current_price,
        timestamp=timestamp or datetime.utcnow(),
    )
    db_session.add(log)
    await db_session.flush()
    return log


# =============================================================================
# GET /{bot_id}/indicator-logs
# =============================================================================


class TestGetIndicatorLogs:
    """Tests for GET /{bot_id}/indicator-logs"""

    @pytest.mark.asyncio
    async def test_get_indicator_logs_success(self, db_session):
        """Happy path: returns indicator logs in reverse chronological order."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        t1 = datetime.utcnow() - timedelta(hours=2)
        t2 = datetime.utcnow()
        await _make_indicator_log(db_session, bot, phase="base_order", timestamp=t1)
        await _make_indicator_log(db_session, bot, phase="take_profit", timestamp=t2)

        result = await get_indicator_logs(
            bot_id=bot.id, limit=50, offset=0,
            db=db_session, current_user=user
        )

        assert len(result) == 2
        # Most recent first
        assert result[0].phase == "take_profit"
        assert result[1].phase == "base_order"

    @pytest.mark.asyncio
    async def test_get_indicator_logs_filter_by_product(self, db_session):
        """Edge case: product_id filter returns only matching logs."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        await _make_indicator_log(db_session, bot, product_id="ETH-BTC")
        await _make_indicator_log(db_session, bot, product_id="SOL-BTC")

        result = await get_indicator_logs(
            bot_id=bot.id, limit=50, offset=0, product_id="ETH-BTC",
            db=db_session, current_user=user
        )

        assert len(result) == 1
        assert result[0].product_id == "ETH-BTC"

    @pytest.mark.asyncio
    async def test_get_indicator_logs_filter_by_phase(self, db_session):
        """Edge case: phase filter returns only matching logs."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        await _make_indicator_log(db_session, bot, phase="base_order")
        await _make_indicator_log(db_session, bot, phase="safety_order")
        await _make_indicator_log(db_session, bot, phase="take_profit")

        result = await get_indicator_logs(
            bot_id=bot.id, limit=50, offset=0, phase="safety_order",
            db=db_session, current_user=user
        )

        assert len(result) == 1
        assert result[0].phase == "safety_order"

    @pytest.mark.asyncio
    async def test_get_indicator_logs_filter_by_conditions_met(self, db_session):
        """Edge case: conditions_met filter returns matching logs."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        await _make_indicator_log(db_session, bot, conditions_met=True)
        await _make_indicator_log(db_session, bot, conditions_met=False)

        result = await get_indicator_logs(
            bot_id=bot.id, limit=50, offset=0, conditions_met=True,
            db=db_session, current_user=user
        )

        assert len(result) == 1
        assert result[0].conditions_met is True

    @pytest.mark.asyncio
    async def test_get_indicator_logs_filter_by_since(self, db_session):
        """Edge case: since filter returns only recent logs."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        old_time = datetime.utcnow() - timedelta(hours=48)
        new_time = datetime.utcnow()
        await _make_indicator_log(db_session, bot, timestamp=old_time)
        await _make_indicator_log(db_session, bot, timestamp=new_time)

        since = datetime.utcnow() - timedelta(hours=1)
        result = await get_indicator_logs(
            bot_id=bot.id, limit=50, offset=0, since=since,
            db=db_session, current_user=user
        )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_indicator_logs_bot_not_found_raises_404(self, db_session):
        """Failure: getting logs for nonexistent bot raises 404."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_indicator_logs(
                bot_id=99999, limit=50, offset=0,
                db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_indicator_logs_empty_result(self, db_session):
        """Edge case: returns empty list when no logs exist."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        result = await get_indicator_logs(
            bot_id=bot.id, limit=50, offset=0,
            db=db_session, current_user=user
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_get_indicator_logs_respects_limit(self, db_session):
        """Edge case: limit parameter restricts results count."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        for i in range(5):
            ts = datetime.utcnow() - timedelta(minutes=i)
            await _make_indicator_log(db_session, bot, timestamp=ts)

        result = await get_indicator_logs(
            bot_id=bot.id, limit=2, offset=0,
            db=db_session, current_user=user
        )

        assert len(result) == 2


# =============================================================================
# GET /{bot_id}/indicator-logs/summary
# =============================================================================


class TestGetIndicatorLogsSummary:
    """Tests for GET /{bot_id}/indicator-logs/summary"""

    @pytest.mark.asyncio
    async def test_summary_success(self, db_session):
        """Happy path: returns aggregated summary by phase and product."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs_summary

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        now = datetime.utcnow()
        await _make_indicator_log(
            db_session, bot, phase="base_order",
            conditions_met=True, product_id="ETH-BTC",
            timestamp=now - timedelta(hours=1)
        )
        await _make_indicator_log(
            db_session, bot, phase="base_order",
            conditions_met=False, product_id="ETH-BTC",
            timestamp=now - timedelta(hours=2)
        )
        await _make_indicator_log(
            db_session, bot, phase="take_profit",
            conditions_met=True, product_id="SOL-BTC",
            timestamp=now - timedelta(hours=3)
        )

        result = await get_indicator_logs_summary(
            bot_id=bot.id, hours=24,
            db=db_session, current_user=user
        )

        assert result["total_evaluations"] == 3
        assert result["time_period_hours"] == 24

        # Check by_phase
        assert "base_order" in result["by_phase"]
        assert result["by_phase"]["base_order"]["total"] == 2
        assert result["by_phase"]["base_order"]["met"] == 1
        assert result["by_phase"]["base_order"]["not_met"] == 1

        assert "take_profit" in result["by_phase"]
        assert result["by_phase"]["take_profit"]["total"] == 1
        assert result["by_phase"]["take_profit"]["met"] == 1

        # Check by_product
        assert "ETH-BTC" in result["by_product"]
        assert result["by_product"]["ETH-BTC"]["total"] == 2
        assert "SOL-BTC" in result["by_product"]
        assert result["by_product"]["SOL-BTC"]["total"] == 1

    @pytest.mark.asyncio
    async def test_summary_excludes_old_logs(self, db_session):
        """Edge case: logs older than the hours window are excluded."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs_summary

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        old_time = datetime.utcnow() - timedelta(hours=48)
        new_time = datetime.utcnow() - timedelta(hours=1)
        await _make_indicator_log(db_session, bot, timestamp=old_time)
        await _make_indicator_log(db_session, bot, timestamp=new_time)

        result = await get_indicator_logs_summary(
            bot_id=bot.id, hours=24,
            db=db_session, current_user=user
        )

        assert result["total_evaluations"] == 1

    @pytest.mark.asyncio
    async def test_summary_empty_result(self, db_session):
        """Edge case: returns zero totals when no logs exist."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs_summary

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        result = await get_indicator_logs_summary(
            bot_id=bot.id, hours=24,
            db=db_session, current_user=user
        )

        assert result["total_evaluations"] == 0
        assert result["by_phase"] == {}
        assert result["by_product"] == {}

    @pytest.mark.asyncio
    async def test_summary_bot_not_found_raises_404(self, db_session):
        """Failure: getting summary for nonexistent bot raises 404."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs_summary

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_indicator_logs_summary(
                bot_id=99999, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_summary_with_product_filter(self, db_session):
        """Edge case: product_id filter narrows the summary."""
        from app.bot_routers.bot_indicator_logs_router import get_indicator_logs_summary

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        now = datetime.utcnow()
        await _make_indicator_log(
            db_session, bot, product_id="ETH-BTC",
            timestamp=now - timedelta(hours=1)
        )
        await _make_indicator_log(
            db_session, bot, product_id="SOL-BTC",
            timestamp=now - timedelta(hours=1)
        )

        result = await get_indicator_logs_summary(
            bot_id=bot.id, product_id="ETH-BTC", hours=24,
            db=db_session, current_user=user
        )

        assert result["total_evaluations"] == 1
        assert "ETH-BTC" in result["by_product"]
        assert "SOL-BTC" not in result["by_product"]
