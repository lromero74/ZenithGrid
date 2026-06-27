"""Tests for asynchronous manual report generation.

Covers the pending-row lifecycle added so ``POST /api/reports/generate`` returns
immediately instead of blocking on the slow AI+PDF render:
- the orphan reaper that self-heals reports stuck in ``pending`` after a crash,
- the fast path that creates a ``pending`` row + schedules background work,
- the background worker flipping the row to ``failed`` on error,
- ``generate_report_for_schedule`` filling an existing row in place (no dup row).
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Report, ReportSchedule, User
from app.services import report_scheduler as rs
from app.utils.timeutil import utcnow


async def _mk_user(db, email):
    user = User(email=email, hashed_password="x", is_active=True, created_at=utcnow())
    db.add(user)
    await db.flush()
    return user


async def _mk_schedule(db, user_id, **kw):
    defaults = dict(
        user_id=user_id, name="Weekly", periodicity="Weekly",
        schedule_type="weekly", is_enabled=True, next_run_at=datetime(2026, 6, 1),
        account_id=None, generate_ai_summary=False,
    )
    defaults.update(kw)
    sched = ReportSchedule(**defaults)
    db.add(sched)
    await db.flush()
    return sched


async def _mk_report(db, user_id, status="pending", created_at=None, **kw):
    rpt = Report(
        user_id=user_id, account_id=None,
        period_start=datetime(2026, 6, 1), period_end=datetime(2026, 6, 7),
        periodicity="Weekly", generation_status=status,
        created_at=created_at or utcnow(), **kw,
    )
    db.add(rpt)
    await db.flush()
    return rpt


class TestReapOrphanedPending:
    @pytest.mark.asyncio
    async def test_old_pending_marked_failed(self, db_session):
        user = await _mk_user(db_session, "reap_old@test.com")
        old = await _mk_report(
            db_session, user.id, status="pending",
            created_at=utcnow() - timedelta(minutes=30),
        )
        n = await rs._reap_orphaned_pending_reports(db_session, older_than_minutes=15)
        await db_session.refresh(old)
        assert n == 1
        assert old.generation_status == "failed"
        assert "restart" in (old.generation_error or "").lower()

    @pytest.mark.asyncio
    async def test_recent_pending_untouched(self, db_session):
        user = await _mk_user(db_session, "reap_recent@test.com")
        recent = await _mk_report(
            db_session, user.id, status="pending",
            created_at=utcnow() - timedelta(minutes=2),
        )
        n = await rs._reap_orphaned_pending_reports(db_session, older_than_minutes=15)
        await db_session.refresh(recent)
        assert n == 0
        assert recent.generation_status == "pending"

    @pytest.mark.asyncio
    async def test_complete_never_reaped(self, db_session):
        user = await _mk_user(db_session, "reap_done@test.com")
        done = await _mk_report(
            db_session, user.id, status="complete",
            created_at=utcnow() - timedelta(minutes=30),
        )
        n = await rs._reap_orphaned_pending_reports(db_session, older_than_minutes=15)
        await db_session.refresh(done)
        assert n == 0
        assert done.generation_status == "complete"


class TestStartManualGeneration:
    @pytest.mark.asyncio
    async def test_creates_pending_row_and_schedules_bg(self, db_session):
        user = await _mk_user(db_session, "start@test.com")
        sched = await _mk_schedule(db_session, user.id)
        await db_session.commit()

        def _close(coro):  # avoid "coroutine never awaited" warning
            coro.close()

        with patch.object(rs, "_spawn_bg", side_effect=_close) as spawn:
            report = await rs.start_manual_report_generation(
                db_session, sched, user, send_email=False,
            )

        assert report.id is not None
        assert report.generation_status == "pending"
        assert report.html_content is None
        assert report.generation_error is None
        spawn.assert_called_once()

        fetched = await db_session.get(Report, report.id)
        assert fetched.generation_status == "pending"


class TestManualGenerationBgFailure:
    @pytest.mark.asyncio
    async def test_failure_marks_report_failed(self, async_engine, db_session):
        maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        user = await _mk_user(db_session, "bgfail@test.com")
        sched = await _mk_schedule(db_session, user.id)
        pending = await _mk_report(db_session, user.id, status="pending", schedule_id=sched.id)
        await db_session.commit()

        boom = AsyncMock(side_effect=RuntimeError("boom while rendering"))
        with patch.object(rs, "generate_report_for_schedule", new=boom):
            await rs._run_manual_generation_bg(
                pending.id, sched.id, user.id, False, session_maker=maker,
            )

        async with maker() as check:
            row = await check.get(Report, pending.id)
            assert row.generation_status == "failed"
            assert "boom" in (row.generation_error or "")


class TestGenerateFillsExistingRow:
    @pytest.mark.asyncio
    async def test_existing_pending_row_filled_and_completed(self, db_session):
        user = await _mk_user(db_session, "fill@test.com")
        sched = await _mk_schedule(db_session, user.id, generate_ai_summary=False)
        pending = await _mk_report(db_session, user.id, status="pending", schedule_id=sched.id)
        await db_session.flush()
        before = (await db_session.execute(select(func.count(Report.id)))).scalar()

        with patch.object(
            rs, "_compute_report_period",
            return_value=(datetime(2026, 6, 1), datetime(2026, 6, 7), "Jun 1-7"),
        ), patch.object(rs, "_fetch_schedule_goals", new=AsyncMock(return_value=[])), \
                patch.object(rs, "_attach_goal_trend_data", new=AsyncMock()), \
                patch.object(rs, "_fetch_account_name", new=AsyncMock(return_value=None)), \
                patch("app.services.report_data_service.gather_report_data",
                      new=AsyncMock(return_value={"x": 1})), \
                patch("app.services.report_data_service.get_prior_period_data",
                      new=AsyncMock(return_value=None)), \
                patch("app.services.report_generator_service.build_report_html",
                      new=MagicMock(return_value="<html>ok</html>")), \
                patch("app.services.report_generator_service.generate_pdf",
                      new=MagicMock(return_value=b"PDF")):
            result = await rs.generate_report_for_schedule(
                db_session, sched, user, save=True, send_email=False,
                advance_schedule=False, report=pending,
            )

        assert result.id == pending.id
        assert result.generation_status == "complete"
        assert result.html_content == "<html>ok</html>"
        assert result.pdf_content == b"PDF"

        after = (await db_session.execute(select(func.count(Report.id)))).scalar()
        assert after == before  # filled in place — no duplicate row
