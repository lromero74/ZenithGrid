"""
Tests for backend/app/services/indicator_log_service.py

Tests logging indicator evaluations, retrieving logs with filters,
and cleaning up old logs.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import Bot, IndicatorLog, User, Account
from app.services.indicator_log_service import (
    log_indicator_evaluation,
    get_indicator_logs,
    cleanup_old_indicator_logs,
)


async def _create_bot(db_session, name="TestBot"):
    """Helper to create a User + Account + Bot for FK constraints."""
    user = User(email=f"{name}@test.com", hashed_password="hash", is_active=True)
    db_session.add(user)
    await db_session.flush()

    account = Account(user_id=user.id, name="TestAccount", type="cex", is_active=True)
    db_session.add(account)
    await db_session.flush()

    bot = Bot(
        user_id=user.id,
        account_id=account.id,
        name=name,
        strategy_type="macd_dca",
        strategy_config={},
        is_active=True,
    )
    db_session.add(bot)
    await db_session.flush()
    return bot


class TestLogIndicatorEvaluation:
    """Tests for log_indicator_evaluation()."""

    @pytest.mark.asyncio
    async def test_happy_path_creates_log(self, db_session):
        """Happy path: creates and returns an IndicatorLog record."""
        bot = await _create_bot(db_session)

        conditions = [
            {"type": "RSI", "timeframe": "1h", "operator": "<", "threshold": 30, "actual_value": 25, "result": True}
        ]

        result = await log_indicator_evaluation(
            db=db_session,
            bot_id=bot.id,
            product_id="ETH-BTC",
            phase="base_order",
            conditions_met=True,
            conditions_detail=conditions,
            indicators_snapshot={"rsi_1h": 25.0},
            current_price=0.05,
        )

        assert result is not None
        assert result.bot_id == bot.id
        assert result.product_id == "ETH-BTC"
        assert result.phase == "base_order"
        assert result.conditions_met is True
        assert result.current_price == 0.05

    @pytest.mark.asyncio
    async def test_empty_conditions_returns_none(self, db_session):
        """Edge case: empty conditions_detail skips logging."""
        bot = await _create_bot(db_session, name="EmptyBot")

        result = await log_indicator_evaluation(
            db=db_session,
            bot_id=bot.id,
            product_id="BTC-USD",
            phase="base_order",
            conditions_met=False,
            conditions_detail=[],
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_optional_fields_can_be_none(self, db_session):
        """Edge case: indicators_snapshot and current_price can be None."""
        bot = await _create_bot(db_session, name="OptionalBot")

        conditions = [{"type": "MACD", "result": True}]

        result = await log_indicator_evaluation(
            db=db_session,
            bot_id=bot.id,
            product_id="SOL-USD",
            phase="take_profit",
            conditions_met=True,
            conditions_detail=conditions,
            indicators_snapshot=None,
            current_price=None,
        )

        assert result is not None
        assert result.indicators_snapshot is None
        assert result.current_price is None

    @pytest.mark.asyncio
    async def test_db_error_returns_none(self, db_session):
        """Failure: database error returns None instead of raising."""
        # Use invalid bot_id that will fail the FK constraint
        # But the function catches all exceptions
        with patch("app.services.indicator_log_service.IndicatorLog") as MockLog:
            MockLog.side_effect = Exception("DB exploded")

            result = await log_indicator_evaluation(
                db=db_session,
                bot_id=99999,
                product_id="ETH-USD",
                phase="base_order",
                conditions_met=False,
                conditions_detail=[{"type": "RSI", "result": False}],
            )

            assert result is None


class TestGetIndicatorLogs:
    """Tests for get_indicator_logs()."""

    @pytest.mark.asyncio
    async def test_returns_logs_for_bot(self, db_session):
        """Happy path: returns logs for specified bot."""
        bot = await _create_bot(db_session, name="LogBot")

        # Create some logs directly
        for i in range(3):
            log = IndicatorLog(
                bot_id=bot.id,
                product_id="ETH-BTC",
                phase="base_order",
                conditions_met=True,
                conditions_detail=[{"type": "RSI"}],
                timestamp=datetime.utcnow() - timedelta(minutes=i),
            )
            db_session.add(log)
        await db_session.commit()

        logs = await get_indicator_logs(db_session, bot_id=bot.id)
        assert len(logs) == 3

    @pytest.mark.asyncio
    async def test_filter_by_product_id(self, db_session):
        """Happy path: filter logs by product_id."""
        bot = await _create_bot(db_session, name="FilterBot")

        log1 = IndicatorLog(
            bot_id=bot.id, product_id="ETH-BTC", phase="base_order",
            conditions_met=True, conditions_detail=[{"type": "RSI"}],
        )
        log2 = IndicatorLog(
            bot_id=bot.id, product_id="SOL-USD", phase="base_order",
            conditions_met=True, conditions_detail=[{"type": "MACD"}],
        )
        db_session.add_all([log1, log2])
        await db_session.commit()

        logs = await get_indicator_logs(db_session, bot_id=bot.id, product_id="ETH-BTC")
        assert len(logs) == 1
        assert logs[0].product_id == "ETH-BTC"

    @pytest.mark.asyncio
    async def test_filter_by_phase(self, db_session):
        """Happy path: filter logs by phase."""
        bot = await _create_bot(db_session, name="PhaseBot")

        log1 = IndicatorLog(
            bot_id=bot.id, product_id="ETH-BTC", phase="base_order",
            conditions_met=True, conditions_detail=[{"type": "RSI"}],
        )
        log2 = IndicatorLog(
            bot_id=bot.id, product_id="ETH-BTC", phase="take_profit",
            conditions_met=False, conditions_detail=[{"type": "MACD"}],
        )
        db_session.add_all([log1, log2])
        await db_session.commit()

        logs = await get_indicator_logs(db_session, bot_id=bot.id, phase="take_profit")
        assert len(logs) == 1
        assert logs[0].phase == "take_profit"

    @pytest.mark.asyncio
    async def test_limit_and_offset(self, db_session):
        """Edge case: limit and offset pagination works."""
        bot = await _create_bot(db_session, name="PaginateBot")

        for i in range(5):
            log = IndicatorLog(
                bot_id=bot.id, product_id="ETH-BTC", phase="base_order",
                conditions_met=True, conditions_detail=[{"idx": i}],
                timestamp=datetime.utcnow() - timedelta(minutes=i),
            )
            db_session.add(log)
        await db_session.commit()

        logs = await get_indicator_logs(db_session, bot_id=bot.id, limit=2, offset=1)
        assert len(logs) == 2

    @pytest.mark.asyncio
    async def test_empty_results(self, db_session):
        """Edge case: no matching logs returns empty list."""
        bot = await _create_bot(db_session, name="EmptyLogBot")
        logs = await get_indicator_logs(db_session, bot_id=bot.id)
        assert logs == []


class TestCleanupOldIndicatorLogs:
    """Tests for cleanup_old_indicator_logs()."""

    @pytest.mark.asyncio
    async def test_deletes_old_logs_keeps_recent(self, db_session):
        """Happy path: keeps recent logs, deletes older ones."""
        bot = await _create_bot(db_session, name="CleanupBot")

        # Create 10 logs with well-spaced timestamps to ensure clear ordering
        for i in range(10):
            log = IndicatorLog(
                bot_id=bot.id, product_id="ETH-BTC", phase="base_order",
                conditions_met=True, conditions_detail=[{"idx": i}],
                timestamp=datetime.utcnow() - timedelta(hours=i * 2),
            )
            db_session.add(log)
        await db_session.commit()

        deleted = await cleanup_old_indicator_logs(db_session, bot_id=bot.id, keep_count=3)
        # The function finds the timestamp of the 4th most recent log via offset(3),
        # then deletes everything strictly before that timestamp.
        # With 10 logs at distinct times, logs at indices 4-9 (6 logs) are before
        # the cutoff timestamp (log at index 3).
        assert deleted == 6

        remaining = await get_indicator_logs(db_session, bot_id=bot.id)
        assert len(remaining) == 4  # keep_count(3) + the cutoff row itself

    @pytest.mark.asyncio
    async def test_no_cleanup_when_under_limit(self, db_session):
        """Edge case: fewer logs than keep_count means nothing deleted."""
        bot = await _create_bot(db_session, name="UnderLimitBot")

        log = IndicatorLog(
            bot_id=bot.id, product_id="ETH-BTC", phase="base_order",
            conditions_met=True, conditions_detail=[{"test": True}],
        )
        db_session.add(log)
        await db_session.commit()

        deleted = await cleanup_old_indicator_logs(db_session, bot_id=bot.id, keep_count=100)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_no_logs_returns_zero(self, db_session):
        """Edge case: no logs at all returns 0."""
        bot = await _create_bot(db_session, name="NoLogsBot")
        deleted = await cleanup_old_indicator_logs(db_session, bot_id=bot.id)
        assert deleted == 0
