"""
Tests for backend/app/bot_routers/bot_ai_logs_router.py

Covers AI bot log creation, retrieval with filters, and unified decision logs.
"""

import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException

from app.models import AIBotLog, Bot, IndicatorLog, User


# =============================================================================
# Helpers
# =============================================================================


def _make_user():
    """Create a test user."""
    user = User(
        email="ailogs@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=datetime.utcnow(),
    )
    return user


async def _make_bot(db_session, user, name="AILogBot", strategy_type="gemini_dca"):
    """Create, flush, and return a test bot."""
    bot = Bot(
        user_id=user.id,
        name=name,
        strategy_type=strategy_type,
        strategy_config={"model": "gemini-pro"},
        product_id="ETH-BTC",
        product_ids=["ETH-BTC"],
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(bot)
    await db_session.flush()
    return bot


async def _make_ai_log(db_session, bot, thinking="AI reasoning", decision="hold",
                       confidence=75.0, current_price=0.05, timestamp=None,
                       product_id=None, position_id=None, context=None):
    """Create and flush an AI bot log entry."""
    log = AIBotLog(
        bot_id=bot.id,
        thinking=thinking,
        decision=decision,
        confidence=confidence,
        current_price=current_price,
        position_status="open",
        product_id=product_id,
        position_id=position_id,
        context=context,
        timestamp=timestamp or datetime.utcnow(),
    )
    db_session.add(log)
    await db_session.flush()
    return log


async def _make_indicator_log(db_session, bot, product_id="ETH-BTC",
                              phase="base_order", conditions_met=True,
                              timestamp=None, current_price=0.05):
    """Create and flush an indicator log entry."""
    log = IndicatorLog(
        bot_id=bot.id,
        product_id=product_id,
        phase=phase,
        conditions_met=conditions_met,
        conditions_detail=[{"type": "rsi", "result": True}],
        indicators_snapshot={"rsi": 45.0},
        current_price=current_price,
        timestamp=timestamp or datetime.utcnow(),
    )
    db_session.add(log)
    await db_session.flush()
    return log


# =============================================================================
# POST /{bot_id}/logs  (create AI log)
# =============================================================================


class TestCreateAIBotLog:
    """Tests for POST /{bot_id}/logs"""

    @pytest.mark.asyncio
    async def test_create_ai_log_success(self, db_session):
        """Happy path: creates an AI bot log entry."""
        from app.bot_routers.bot_ai_logs_router import create_ai_bot_log
        from app.bot_routers.schemas import AIBotLogCreate

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        log_data = AIBotLogCreate(
            thinking="Market is consolidating. RSI at 45.",
            decision="hold",
            confidence=70.0,
            current_price=0.05,
            position_status="open",
            context={"rsi": 45.0, "macd": "neutral"},
        )

        result = await create_ai_bot_log(
            bot_id=bot.id, log_data=log_data, db=db_session, current_user=user
        )

        assert result.bot_id == bot.id
        assert result.thinking == "Market is consolidating. RSI at 45."
        assert result.decision == "hold"
        assert result.confidence == pytest.approx(70.0)

    @pytest.mark.asyncio
    async def test_create_ai_log_minimal_fields(self, db_session):
        """Edge case: creates log with only required fields."""
        from app.bot_routers.bot_ai_logs_router import create_ai_bot_log
        from app.bot_routers.schemas import AIBotLogCreate

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        log_data = AIBotLogCreate(
            thinking="Minimal reasoning",
            decision="buy",
        )

        result = await create_ai_bot_log(
            bot_id=bot.id, log_data=log_data, db=db_session, current_user=user
        )

        assert result.bot_id == bot.id
        assert result.decision == "buy"
        assert result.confidence is None
        assert result.current_price is None

    @pytest.mark.asyncio
    async def test_create_ai_log_bot_not_found_raises_404(self, db_session):
        """Failure: creating log for nonexistent bot raises 404."""
        from app.bot_routers.bot_ai_logs_router import create_ai_bot_log
        from app.bot_routers.schemas import AIBotLogCreate

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        log_data = AIBotLogCreate(thinking="test", decision="hold")

        with pytest.raises(HTTPException) as exc_info:
            await create_ai_bot_log(
                bot_id=99999, log_data=log_data, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_ai_log_wrong_user_raises_404(self, db_session):
        """Failure: cannot create log for another user's bot."""
        from app.bot_routers.bot_ai_logs_router import create_ai_bot_log
        from app.bot_routers.schemas import AIBotLogCreate

        owner = _make_user()
        other = User(
            email="other-ai@example.com", hashed_password="hashed",
            is_active=True, created_at=datetime.utcnow(),
        )
        db_session.add_all([owner, other])
        await db_session.flush()

        bot = await _make_bot(db_session, owner)
        log_data = AIBotLogCreate(thinking="test", decision="hold")

        with pytest.raises(HTTPException) as exc_info:
            await create_ai_bot_log(
                bot_id=bot.id, log_data=log_data, db=db_session, current_user=other
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# GET /{bot_id}/logs  (list AI logs)
# =============================================================================


class TestGetAIBotLogs:
    """Tests for GET /{bot_id}/logs"""

    @pytest.mark.asyncio
    async def test_get_logs_success(self, db_session):
        """Happy path: returns AI bot logs in reverse chronological order."""
        from app.bot_routers.bot_ai_logs_router import get_ai_bot_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        old_time = datetime.utcnow() - timedelta(hours=2)
        new_time = datetime.utcnow()
        await _make_ai_log(db_session, bot, decision="buy", timestamp=old_time)
        await _make_ai_log(db_session, bot, decision="hold", timestamp=new_time)

        result = await get_ai_bot_logs(
            bot_id=bot.id, limit=50, offset=0,
            db=db_session, current_user=user
        )

        assert len(result) == 2
        # Most recent first
        assert result[0].decision == "hold"
        assert result[1].decision == "buy"

    @pytest.mark.asyncio
    async def test_get_logs_with_product_filter(self, db_session):
        """Edge case: filters logs by product_id."""
        from app.bot_routers.bot_ai_logs_router import get_ai_bot_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        await _make_ai_log(db_session, bot, product_id="ETH-BTC")
        await _make_ai_log(db_session, bot, product_id="SOL-BTC")

        result = await get_ai_bot_logs(
            bot_id=bot.id, limit=50, offset=0, product_id="ETH-BTC",
            db=db_session, current_user=user
        )

        assert len(result) == 1
        assert result[0].product_id == "ETH-BTC"

    @pytest.mark.asyncio
    async def test_get_logs_with_since_filter(self, db_session):
        """Edge case: filters logs by since timestamp."""
        from app.bot_routers.bot_ai_logs_router import get_ai_bot_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        old_time = datetime.utcnow() - timedelta(hours=48)
        new_time = datetime.utcnow()
        await _make_ai_log(db_session, bot, decision="old", timestamp=old_time)
        await _make_ai_log(db_session, bot, decision="new", timestamp=new_time)

        since = datetime.utcnow() - timedelta(hours=1)
        result = await get_ai_bot_logs(
            bot_id=bot.id, limit=50, offset=0, since=since,
            db=db_session, current_user=user
        )

        assert len(result) == 1
        assert result[0].decision == "new"

    @pytest.mark.asyncio
    async def test_get_logs_empty_result(self, db_session):
        """Edge case: returns empty list when no logs exist."""
        from app.bot_routers.bot_ai_logs_router import get_ai_bot_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        result = await get_ai_bot_logs(
            bot_id=bot.id, limit=50, offset=0,
            db=db_session, current_user=user
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_get_logs_bot_not_found_raises_404(self, db_session):
        """Failure: getting logs for nonexistent bot raises 404."""
        from app.bot_routers.bot_ai_logs_router import get_ai_bot_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_ai_bot_logs(
                bot_id=99999, limit=50, offset=0,
                db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_logs_respects_limit_and_offset(self, db_session):
        """Edge case: limit and offset pagination works correctly."""
        from app.bot_routers.bot_ai_logs_router import get_ai_bot_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        for i in range(5):
            ts = datetime.utcnow() - timedelta(minutes=i)
            await _make_ai_log(db_session, bot, decision=f"d{i}", timestamp=ts)

        result = await get_ai_bot_logs(
            bot_id=bot.id, limit=2, offset=1,
            db=db_session, current_user=user
        )

        assert len(result) == 2


# =============================================================================
# GET /{bot_id}/decision-logs  (unified AI + Indicator logs)
# =============================================================================


class TestGetUnifiedDecisionLogs:
    """Tests for GET /{bot_id}/decision-logs"""

    @pytest.mark.asyncio
    async def test_unified_logs_merges_ai_and_indicator(self, db_session):
        """Happy path: returns both AI and indicator logs merged by timestamp."""
        from app.bot_routers.bot_ai_logs_router import get_unified_decision_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        t1 = datetime.utcnow() - timedelta(minutes=10)
        t2 = datetime.utcnow() - timedelta(minutes=5)
        t3 = datetime.utcnow()

        await _make_ai_log(db_session, bot, decision="buy", timestamp=t1)
        await _make_indicator_log(db_session, bot, timestamp=t2)
        await _make_ai_log(db_session, bot, decision="hold", timestamp=t3)

        result = await get_unified_decision_logs(
            bot_id=bot.id, limit=50, offset=0,
            db=db_session, current_user=user
        )

        assert len(result) == 3
        # Most recent first
        assert result[0]["log_type"] == "ai"
        assert result[1]["log_type"] == "indicator"
        assert result[2]["log_type"] == "ai"

    @pytest.mark.asyncio
    async def test_unified_logs_bot_not_found_raises_404(self, db_session):
        """Failure: getting unified logs for nonexistent bot raises 404."""
        from app.bot_routers.bot_ai_logs_router import get_unified_decision_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_unified_decision_logs(
                bot_id=99999, limit=50, offset=0,
                db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unified_logs_empty_result(self, db_session):
        """Edge case: returns empty list when no logs exist."""
        from app.bot_routers.bot_ai_logs_router import get_unified_decision_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        result = await get_unified_decision_logs(
            bot_id=bot.id, limit=50, offset=0,
            db=db_session, current_user=user
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_unified_logs_ai_fields_populated(self, db_session):
        """Happy path: AI log entries have AI-specific fields."""
        from app.bot_routers.bot_ai_logs_router import get_unified_decision_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        await _make_ai_log(
            db_session, bot, thinking="Market analysis",
            decision="buy", confidence=85.0
        )

        result = await get_unified_decision_logs(
            bot_id=bot.id, limit=50, offset=0,
            db=db_session, current_user=user
        )

        assert len(result) == 1
        log = result[0]
        assert log["log_type"] == "ai"
        assert log["thinking"] == "Market analysis"
        assert log["decision"] == "buy"
        assert log["confidence"] == pytest.approx(85.0)

    @pytest.mark.asyncio
    async def test_unified_logs_indicator_fields_populated(self, db_session):
        """Happy path: indicator log entries have indicator-specific fields."""
        from app.bot_routers.bot_ai_logs_router import get_unified_decision_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        await _make_indicator_log(
            db_session, bot, phase="base_order", conditions_met=True
        )

        result = await get_unified_decision_logs(
            bot_id=bot.id, limit=50, offset=0,
            db=db_session, current_user=user
        )

        assert len(result) == 1
        log = result[0]
        assert log["log_type"] == "indicator"
        assert log["phase"] == "base_order"
        assert log["conditions_met"] == 1  # SQLite stores booleans as integers in UNION ALL results

    @pytest.mark.asyncio
    async def test_unified_logs_with_product_filter(self, db_session):
        """Edge case: product_id filter applies to both AI and indicator logs."""
        from app.bot_routers.bot_ai_logs_router import get_unified_decision_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        await _make_ai_log(db_session, bot, product_id="ETH-BTC")
        await _make_ai_log(db_session, bot, product_id="SOL-BTC")
        await _make_indicator_log(db_session, bot, product_id="ETH-BTC")
        await _make_indicator_log(db_session, bot, product_id="SOL-BTC")

        result = await get_unified_decision_logs(
            bot_id=bot.id, limit=50, offset=0, product_id="ETH-BTC",
            db=db_session, current_user=user
        )

        assert len(result) == 2
        for log in result:
            assert log["product_id"] == "ETH-BTC"
