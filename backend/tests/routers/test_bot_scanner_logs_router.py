"""
Tests for backend/app/bot_routers/bot_scanner_logs_router.py

Covers scanner log creation, retrieval with filters, and log deletion.
"""

import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException

from app.models import Bot, ScannerLog, User


# =============================================================================
# Helpers
# =============================================================================


def _make_user():
    """Create a test user."""
    user = User(
        email="scanner@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=datetime.utcnow(),
    )
    return user


async def _make_bot(db_session, user, name="ScannerBot"):
    """Create, flush, and return a test bot."""
    bot = Bot(
        user_id=user.id,
        name=name,
        strategy_type="bull_flag",
        strategy_config={"volume_threshold": 2.0},
        product_id="BTC-USD",
        product_ids=["BTC-USD"],
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(bot)
    await db_session.flush()
    return bot


async def _make_scanner_log(db_session, bot, product_id="BTC-USD",
                            scan_type="volume_check", decision="passed",
                            reason="Volume above threshold",
                            current_price=50000.0, volume_ratio=2.5,
                            timestamp=None, pattern_data=None):
    """Create and flush a scanner log entry."""
    log = ScannerLog(
        bot_id=bot.id,
        product_id=product_id,
        scan_type=scan_type,
        decision=decision,
        reason=reason,
        current_price=current_price,
        volume_ratio=volume_ratio,
        pattern_data=pattern_data,
        timestamp=timestamp or datetime.utcnow(),
    )
    db_session.add(log)
    await db_session.flush()
    return log


# =============================================================================
# POST /{bot_id}/scanner-logs  (create)
# =============================================================================


class TestCreateScannerLog:
    """Tests for POST /{bot_id}/scanner-logs"""

    @pytest.mark.asyncio
    async def test_create_scanner_log_success(self, db_session):
        """Happy path: creates a scanner log entry."""
        from app.bot_routers.bot_scanner_logs_router import create_scanner_log
        from app.bot_routers.schemas import ScannerLogCreate

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        log_data = ScannerLogCreate(
            product_id="BTC-USD",
            scan_type="volume_check",
            decision="passed",
            reason="Volume 2.5x above average",
            current_price=50000.0,
            volume_ratio=2.5,
            pattern_data={"pattern": "bull_flag", "confidence": 0.85},
        )

        result = await create_scanner_log(
            bot_id=bot.id, log_data=log_data, db=db_session, current_user=user
        )

        assert result.bot_id == bot.id
        assert result.product_id == "BTC-USD"
        assert result.scan_type == "volume_check"
        assert result.decision == "passed"
        assert result.volume_ratio == pytest.approx(2.5)

    @pytest.mark.asyncio
    async def test_create_scanner_log_minimal_fields(self, db_session):
        """Edge case: creates log with only required fields."""
        from app.bot_routers.bot_scanner_logs_router import create_scanner_log
        from app.bot_routers.schemas import ScannerLogCreate

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        log_data = ScannerLogCreate(
            product_id="ETH-USD",
            scan_type="pattern_check",
            decision="rejected",
            reason="No pattern detected",
        )

        result = await create_scanner_log(
            bot_id=bot.id, log_data=log_data, db=db_session, current_user=user
        )

        assert result.bot_id == bot.id
        assert result.current_price is None
        assert result.volume_ratio is None
        assert result.pattern_data is None

    @pytest.mark.asyncio
    async def test_create_scanner_log_bot_not_found_raises_404(self, db_session):
        """Failure: creating log for nonexistent bot raises 404."""
        from app.bot_routers.bot_scanner_logs_router import create_scanner_log
        from app.bot_routers.schemas import ScannerLogCreate

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        log_data = ScannerLogCreate(
            product_id="BTC-USD",
            scan_type="volume_check",
            decision="passed",
            reason="Volume ok",
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_scanner_log(
                bot_id=99999, log_data=log_data, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_scanner_log_wrong_user_raises_404(self, db_session):
        """Failure: cannot create log for another user's bot."""
        from app.bot_routers.bot_scanner_logs_router import create_scanner_log
        from app.bot_routers.schemas import ScannerLogCreate

        owner = _make_user()
        other = User(
            email="other-scanner@example.com", hashed_password="hashed",
            is_active=True, created_at=datetime.utcnow(),
        )
        db_session.add_all([owner, other])
        await db_session.flush()

        bot = await _make_bot(db_session, owner)
        log_data = ScannerLogCreate(
            product_id="BTC-USD",
            scan_type="volume_check",
            decision="passed",
            reason="test",
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_scanner_log(
                bot_id=bot.id, log_data=log_data, db=db_session, current_user=other
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# GET /{bot_id}/scanner-logs  (list)
# =============================================================================


class TestGetScannerLogs:
    """Tests for GET /{bot_id}/scanner-logs"""

    @pytest.mark.asyncio
    async def test_get_scanner_logs_success(self, db_session):
        """Happy path: returns scanner logs in reverse chronological order."""
        from app.bot_routers.bot_scanner_logs_router import get_scanner_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        t1 = datetime.utcnow() - timedelta(hours=2)
        t2 = datetime.utcnow()
        await _make_scanner_log(db_session, bot, decision="rejected", timestamp=t1)
        await _make_scanner_log(db_session, bot, decision="passed", timestamp=t2)

        result = await get_scanner_logs(
            bot_id=bot.id, limit=100, offset=0,
            db=db_session, current_user=user
        )

        assert len(result) == 2
        # Most recent first
        assert result[0].decision == "passed"
        assert result[1].decision == "rejected"

    @pytest.mark.asyncio
    async def test_get_scanner_logs_filter_by_product(self, db_session):
        """Edge case: product_id filter returns only matching logs."""
        from app.bot_routers.bot_scanner_logs_router import get_scanner_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        await _make_scanner_log(db_session, bot, product_id="BTC-USD")
        await _make_scanner_log(db_session, bot, product_id="ETH-USD")

        result = await get_scanner_logs(
            bot_id=bot.id, limit=100, offset=0, product_id="BTC-USD",
            db=db_session, current_user=user
        )

        assert len(result) == 1
        assert result[0].product_id == "BTC-USD"

    @pytest.mark.asyncio
    async def test_get_scanner_logs_filter_by_scan_type(self, db_session):
        """Edge case: scan_type filter returns only matching logs."""
        from app.bot_routers.bot_scanner_logs_router import get_scanner_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        await _make_scanner_log(db_session, bot, scan_type="volume_check")
        await _make_scanner_log(db_session, bot, scan_type="pattern_check")

        result = await get_scanner_logs(
            bot_id=bot.id, limit=100, offset=0, scan_type="pattern_check",
            db=db_session, current_user=user
        )

        assert len(result) == 1
        assert result[0].scan_type == "pattern_check"

    @pytest.mark.asyncio
    async def test_get_scanner_logs_filter_by_decision(self, db_session):
        """Edge case: decision filter returns only matching logs."""
        from app.bot_routers.bot_scanner_logs_router import get_scanner_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        await _make_scanner_log(db_session, bot, decision="passed")
        await _make_scanner_log(db_session, bot, decision="rejected")
        await _make_scanner_log(db_session, bot, decision="triggered")

        result = await get_scanner_logs(
            bot_id=bot.id, limit=100, offset=0, decision="triggered",
            db=db_session, current_user=user
        )

        assert len(result) == 1
        assert result[0].decision == "triggered"

    @pytest.mark.asyncio
    async def test_get_scanner_logs_filter_by_since(self, db_session):
        """Edge case: since filter returns only recent logs."""
        from app.bot_routers.bot_scanner_logs_router import get_scanner_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        old_time = datetime.utcnow() - timedelta(hours=48)
        new_time = datetime.utcnow()
        await _make_scanner_log(db_session, bot, timestamp=old_time)
        await _make_scanner_log(db_session, bot, timestamp=new_time)

        since = datetime.utcnow() - timedelta(hours=1)
        result = await get_scanner_logs(
            bot_id=bot.id, limit=100, offset=0, since=since,
            db=db_session, current_user=user
        )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_scanner_logs_bot_not_found_raises_404(self, db_session):
        """Failure: getting logs for nonexistent bot raises 404."""
        from app.bot_routers.bot_scanner_logs_router import get_scanner_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_scanner_logs(
                bot_id=99999, limit=100, offset=0,
                db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_scanner_logs_empty_result(self, db_session):
        """Edge case: returns empty list when no logs exist."""
        from app.bot_routers.bot_scanner_logs_router import get_scanner_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        result = await get_scanner_logs(
            bot_id=bot.id, limit=100, offset=0,
            db=db_session, current_user=user
        )

        assert result == []


# =============================================================================
# DELETE /{bot_id}/scanner-logs  (clear)
# =============================================================================


class TestClearScannerLogs:
    """Tests for DELETE /{bot_id}/scanner-logs"""

    @pytest.mark.asyncio
    async def test_clear_all_scanner_logs_success(self, db_session):
        """Happy path: deletes all scanner logs for a bot."""
        from app.bot_routers.bot_scanner_logs_router import clear_scanner_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        await _make_scanner_log(db_session, bot)
        await _make_scanner_log(db_session, bot)
        await _make_scanner_log(db_session, bot)

        result = await clear_scanner_logs(
            bot_id=bot.id, db=db_session, current_user=user
        )

        assert result["deleted"] == 3

    @pytest.mark.asyncio
    async def test_clear_scanner_logs_older_than(self, db_session):
        """Edge case: only deletes logs older than specified hours."""
        from app.bot_routers.bot_scanner_logs_router import clear_scanner_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)
        old_time = datetime.utcnow() - timedelta(hours=48)
        new_time = datetime.utcnow()
        await _make_scanner_log(db_session, bot, timestamp=old_time)
        await _make_scanner_log(db_session, bot, timestamp=old_time)
        await _make_scanner_log(db_session, bot, timestamp=new_time)

        result = await clear_scanner_logs(
            bot_id=bot.id, older_than_hours=24,
            db=db_session, current_user=user
        )

        assert result["deleted"] == 2

    @pytest.mark.asyncio
    async def test_clear_scanner_logs_none_to_delete(self, db_session):
        """Edge case: returns deleted=0 when no logs exist."""
        from app.bot_routers.bot_scanner_logs_router import clear_scanner_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        result = await clear_scanner_logs(
            bot_id=bot.id, db=db_session, current_user=user
        )

        assert result["deleted"] == 0

    @pytest.mark.asyncio
    async def test_clear_scanner_logs_bot_not_found_raises_404(self, db_session):
        """Failure: clearing logs for nonexistent bot raises 404."""
        from app.bot_routers.bot_scanner_logs_router import clear_scanner_logs

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await clear_scanner_logs(
                bot_id=99999, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_clear_scanner_logs_wrong_user_raises_404(self, db_session):
        """Failure: cannot clear another user's bot logs."""
        from app.bot_routers.bot_scanner_logs_router import clear_scanner_logs

        owner = _make_user()
        other = User(
            email="other-clear@example.com", hashed_password="hashed",
            is_active=True, created_at=datetime.utcnow(),
        )
        db_session.add_all([owner, other])
        await db_session.flush()

        bot = await _make_bot(db_session, owner)
        await _make_scanner_log(db_session, bot)

        with pytest.raises(HTTPException) as exc_info:
            await clear_scanner_logs(
                bot_id=bot.id, db=db_session, current_user=other
            )
        assert exc_info.value.status_code == 404
