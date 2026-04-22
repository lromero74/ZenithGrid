"""
Tests for backend/app/routers/reports_crud_router.py and services/report_access.py

Covers:
- Helpers: _resolve_report_user_id, get_accessible_goal, get_writable_goal,
  _get_accessible_report, _resolve_write_user_id, get_writable_schedule
- Goals CRUD: list_goals, update_goal, delete_goal (create_goal hit by a known
  AttributeError bug — see known-issue test)
- Schedules CRUD: list_schedules, create_schedule, update_schedule, delete_schedule
- Reports: list_reports, get_report, delete_report, bulk_delete_reports,
  download_report_pdf
- Serializers: _goal_to_dict, _schedule_to_dict, report_to_dict,
  _normalize_recipient_for_api, _parse_json_list

Multi-user isolation is tested by creating two users and asserting that
user A cannot read, update, or delete user B's goals/schedules/reports.
"""

import inspect
import json
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.auth.dependencies import Perm
from app.models import (
    Account,
    Report,
    ReportGoal,
    ReportSchedule,
    User,
)
from app.routers.reports_crud_router import (
    BulkDeleteRequest,
    GoalCreate,
    GoalUpdate,
    ScheduleCreate,
    _get_accessible_report,
    _goal_to_dict,
    _normalize_recipient_for_api,
    _parse_json_list,
    _resolve_report_user_id,
    _resolve_write_user_id,
    _schedule_to_dict,
    bulk_delete_reports,
    create_goal,
    delete_goal,
    delete_report,
    delete_schedule,
    download_report_pdf,
    get_report,
    list_goals,
    list_reports,
    list_schedules,
    update_goal,
)
from app.services.report_access import (
    get_accessible_goal,
    get_writable_goal,
    get_writable_schedule,
    report_to_dict,
)


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


async def _make_user(db, email, superuser=True):
    u = User(email=email, hashed_password="x", is_active=True, is_superuser=superuser)
    db.add(u)
    await db.flush()
    return u


async def _make_account(db, user_id, name="Acct"):
    a = Account(user_id=user_id, name=name, type="cex", exchange="coinbase", is_active=True)
    db.add(a)
    await db.flush()
    return a


async def _make_goal(
    db, user_id, account_id=None, target_type="balance", target_currency="USD",
    target_value=1000.0, time_horizon_months=12, name="My Goal",
):
    start = datetime.utcnow()
    g = ReportGoal(
        user_id=user_id,
        account_id=account_id,
        name=name,
        target_type=target_type,
        target_currency=target_currency,
        target_value=target_value,
        time_horizon_months=time_horizon_months,
        start_date=start,
        target_date=start + timedelta(days=30 * time_horizon_months),
    )
    db.add(g)
    await db.flush()
    return g


async def _make_schedule(
    db, user_id, account_id=None, name="Weekly",
    schedule_type="weekly", periodicity="Weekly",
):
    s = ReportSchedule(
        user_id=user_id,
        account_id=account_id,
        name=name,
        periodicity=periodicity,
        schedule_type=schedule_type,
        period_window="full_prior",
    )
    db.add(s)
    await db.flush()
    return s


async def _make_report(
    db, user_id, schedule_id=None, account_id=None,
    html_content=None, pdf_content=None, ai_summary=None,
):
    now = datetime.utcnow()
    r = Report(
        user_id=user_id,
        account_id=account_id,
        schedule_id=schedule_id,
        period_start=now - timedelta(days=7),
        period_end=now,
        periodicity="Weekly",
        html_content=html_content,
        pdf_content=pdf_content,
        ai_summary=ai_summary,
        delivery_status="manual",
    )
    db.add(r)
    await db.flush()
    return r


# ---------------------------------------------------------------------------
# Tests: serializer helpers (no DB needed)
# ---------------------------------------------------------------------------


class TestSerializerHelpers:
    """Pure functions — test without a DB session."""

    def test_normalize_recipient_from_object(self):
        d = _normalize_recipient_for_api({"email": "a@b.com", "color_scheme": "clean"})
        assert d == {"email": "a@b.com", "color_scheme": "clean"}

    def test_normalize_recipient_default_color(self):
        """Edge: legacy objects without color_scheme default to dark."""
        d = _normalize_recipient_for_api({"email": "a@b.com"})
        assert d == {"email": "a@b.com", "color_scheme": "dark"}

    def test_normalize_recipient_from_string(self):
        """Edge: oldest legacy — plain email string."""
        d = _normalize_recipient_for_api("legacy@b.com")
        assert d == {"email": "legacy@b.com", "color_scheme": "dark"}

    def test_parse_json_list_valid(self):
        assert _parse_json_list('[1, 2, 3]') == [1, 2, 3]

    def test_parse_json_list_none(self):
        assert _parse_json_list(None) is None
        assert _parse_json_list("") is None

    def test_parse_json_list_invalid_returns_none(self):
        """Failure: malformed JSON yields None, not an exception."""
        assert _parse_json_list("not-json-at-all") is None


class TestGoalToDict:
    """Tests for _goal_to_dict serializer."""

    @pytest.mark.asyncio
    async def test_serializes_balance_goal(self, db_session):
        user = await _make_user(db_session, "g@example.com")
        goal = await _make_goal(db_session, user.id, name="My Balance Goal")
        d = _goal_to_dict(goal)
        assert d["id"] == goal.id
        assert d["name"] == "My Balance Goal"
        assert d["target_type"] == "balance"
        assert d["expense_item_count"] == 0
        assert d["savings_target_count"] == 0


class TestScheduleToDict:
    """Tests for _schedule_to_dict."""

    @pytest.mark.asyncio
    async def test_serializes_basic_schedule(self, db_session):
        from sqlalchemy.orm import selectinload
        from sqlalchemy import select as sa_select

        user = await _make_user(db_session, "s@example.com")
        schedule = await _make_schedule(db_session, user.id)
        # Refresh with goal_links eager-loaded
        res = await db_session.execute(
            sa_select(ReportSchedule)
            .where(ReportSchedule.id == schedule.id)
            .options(selectinload(ReportSchedule.goal_links))
        )
        schedule = res.scalar_one()

        d = _schedule_to_dict(schedule)
        assert d["id"] == schedule.id
        assert d["schedule_type"] == "weekly"
        assert d["goal_ids"] == []
        assert d["period_window"] == "full_prior"
        assert d["generate_ai_summary"] is True
        assert d["recipients"] == []


class TestReportToDict:
    """Tests for report_to_dict."""

    @pytest.mark.asyncio
    async def test_serializes_report_without_html_by_default(self, db_session):
        user = await _make_user(db_session, "rpt@example.com")
        report = await _make_report(db_session, user.id, html_content="<html></html>")

        d = report_to_dict(report)
        assert d["id"] == report.id
        assert "html_content" not in d  # excluded unless include_html=True
        assert d["has_pdf"] is False

    @pytest.mark.asyncio
    async def test_include_html_returns_content(self, db_session):
        user = await _make_user(db_session, "rpt2@example.com")
        report = await _make_report(db_session, user.id, html_content="<b>body</b>")
        d = report_to_dict(report, include_html=True)
        assert d["html_content"] == "<b>body</b>"

    @pytest.mark.asyncio
    async def test_ai_summary_parsed_when_tiered_json(self, db_session):
        """Edge: AI summary stored as JSON dict (tiered) → returned as dict."""
        user = await _make_user(db_session, "rpt3@example.com")
        tiered = json.dumps({"simple": "easy", "comfortable": "med", "technical": "deep"})
        report = await _make_report(db_session, user.id, ai_summary=tiered)
        d = report_to_dict(report)
        assert isinstance(d["ai_summary"], dict)
        assert d["ai_summary"]["simple"] == "easy"

    @pytest.mark.asyncio
    async def test_ai_summary_kept_as_string_when_plain_text(self, db_session):
        """Edge: plain text summary stays as a string."""
        user = await _make_user(db_session, "rpt4@example.com")
        report = await _make_report(db_session, user.id, ai_summary="Plain text.")
        d = report_to_dict(report)
        assert d["ai_summary"] == "Plain text."

    @pytest.mark.asyncio
    async def test_has_pdf_true_when_pdf_bytes_present(self, db_session):
        user = await _make_user(db_session, "rpt5@example.com")
        report = await _make_report(db_session, user.id, pdf_content=b"%PDF-1.4...")
        d = report_to_dict(report)
        assert d["has_pdf"] is True


# ---------------------------------------------------------------------------
# Tests: access helpers
# ---------------------------------------------------------------------------


class TestResolveReportUserId:
    """_resolve_report_user_id routes queries to the account OWNER."""

    @pytest.mark.asyncio
    async def test_returns_current_user_when_no_account(self, db_session):
        user = await _make_user(db_session, "solo@example.com")
        uid = await _resolve_report_user_id(db_session, user.id, None)
        assert uid == user.id

    @pytest.mark.asyncio
    async def test_returns_owner_for_own_account(self, db_session):
        user = await _make_user(db_session, "own@example.com")
        acct = await _make_account(db_session, user.id)
        uid = await _resolve_report_user_id(db_session, user.id, acct.id)
        assert uid == user.id

    @pytest.mark.asyncio
    async def test_raises_404_for_inaccessible_account(self, db_session):
        """Failure: account does not exist / no membership → 404."""
        u1 = await _make_user(db_session, "u1@example.com")
        u2 = await _make_user(db_session, "u2@example.com")
        acct = await _make_account(db_session, u2.id)  # owned by u2

        with pytest.raises(HTTPException) as exc:
            await _resolve_report_user_id(db_session, u1.id, acct.id)
        assert exc.value.status_code == 404


class TestGetAccessibleGoal:
    """get_accessible_goal enforces multi-user isolation."""

    @pytest.mark.asyncio
    async def test_owner_can_read_own_goal(self, db_session):
        user = await _make_user(db_session, "own@example.com")
        goal = await _make_goal(db_session, user.id)
        result = await get_accessible_goal(db_session, goal.id, user.id)
        assert result.id == goal.id

    @pytest.mark.asyncio
    async def test_other_user_cannot_read_goal(self, db_session):
        """Failure: different user → 404."""
        u1 = await _make_user(db_session, "uu1@example.com")
        u2 = await _make_user(db_session, "uu2@example.com")
        goal = await _make_goal(db_session, u1.id)

        with pytest.raises(HTTPException) as exc:
            await get_accessible_goal(db_session, goal.id, u2.id)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_goal_raises_404(self, db_session):
        user = await _make_user(db_session, "nope@example.com")
        with pytest.raises(HTTPException) as exc:
            await get_accessible_goal(db_session, 99999, user.id)
        assert exc.value.status_code == 404


class TestGetWritableGoal:
    """get_writable_goal — owner can write; non-owner with no manager role → 403."""

    @pytest.mark.asyncio
    async def test_owner_can_write(self, db_session):
        user = await _make_user(db_session, "w@example.com")
        goal = await _make_goal(db_session, user.id)
        result = await get_writable_goal(db_session, goal.id, user)
        assert result.id == goal.id

    @pytest.mark.asyncio
    async def test_non_owner_gets_404(self, db_session):
        """Non-owner sees 404 (not readable at all)."""
        u1 = await _make_user(db_session, "w1@example.com")
        u2 = await _make_user(db_session, "w2@example.com")
        goal = await _make_goal(db_session, u1.id)
        with pytest.raises(HTTPException) as exc:
            await get_writable_goal(db_session, goal.id, u2)
        assert exc.value.status_code == 404


class TestGetAccessibleReport:
    @pytest.mark.asyncio
    async def test_owner_can_read_own_report(self, db_session):
        user = await _make_user(db_session, "rr@example.com")
        report = await _make_report(db_session, user.id)
        result = await _get_accessible_report(db_session, report.id, user.id)
        assert result.id == report.id

    @pytest.mark.asyncio
    async def test_other_user_blocked_404(self, db_session):
        u1 = await _make_user(db_session, "r1@example.com")
        u2 = await _make_user(db_session, "r2@example.com")
        report = await _make_report(db_session, u1.id)
        with pytest.raises(HTTPException) as exc:
            await _get_accessible_report(db_session, report.id, u2.id)
        assert exc.value.status_code == 404


class TestResolveWriteUserId:
    @pytest.mark.asyncio
    async def test_returns_current_user_when_no_account(self, db_session):
        user = await _make_user(db_session, "rw@example.com")
        uid = await _resolve_write_user_id(db_session, user, None)
        assert uid == user.id

    @pytest.mark.asyncio
    async def test_returns_owner_for_own_account(self, db_session):
        user = await _make_user(db_session, "rw2@example.com")
        acct = await _make_account(db_session, user.id)
        uid = await _resolve_write_user_id(db_session, user, acct.id)
        assert uid == user.id

    @pytest.mark.asyncio
    async def test_raises_403_for_non_manager_other_account(self, db_session):
        """Failure: user is not owner/manager → 403."""
        u1 = await _make_user(db_session, "rw3@example.com")
        u2 = await _make_user(db_session, "rw4@example.com")
        acct = await _make_account(db_session, u2.id)
        with pytest.raises(HTTPException) as exc:
            await _resolve_write_user_id(db_session, u1, acct.id)
        assert exc.value.status_code == 403


class TestGetWritableSchedule:
    @pytest.mark.asyncio
    async def test_owner_can_write_schedule(self, db_session):
        user = await _make_user(db_session, "ws@example.com")
        schedule = await _make_schedule(db_session, user.id)
        sched, uid = await get_writable_schedule(db_session, schedule.id, user)
        assert sched.id == schedule.id
        assert uid == user.id

    @pytest.mark.asyncio
    async def test_nonexistent_schedule_404(self, db_session):
        user = await _make_user(db_session, "ws2@example.com")
        with pytest.raises(HTTPException) as exc:
            await get_writable_schedule(db_session, 99999, user)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_other_user_schedule_403(self, db_session):
        u1 = await _make_user(db_session, "ws3@example.com")
        u2 = await _make_user(db_session, "ws4@example.com")
        schedule = await _make_schedule(db_session, u1.id)
        with pytest.raises(HTTPException) as exc:
            await get_writable_schedule(db_session, schedule.id, u2)
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Tests: Goals CRUD (list, update, delete)
# ---------------------------------------------------------------------------


class TestListGoals:
    @pytest.mark.asyncio
    async def test_returns_only_current_user_goals(self, db_session):
        """Multi-user isolation: user A cannot see user B's goals."""
        u1 = await _make_user(db_session, "lg1@example.com")
        u2 = await _make_user(db_session, "lg2@example.com")
        await _make_goal(db_session, u1.id, name="A's goal")
        await _make_goal(db_session, u2.id, name="B's goal")

        result = await list_goals(account_id=None, db=db_session, current_user=u1)
        names = [g["name"] for g in result]
        assert names == ["A's goal"]

    @pytest.mark.asyncio
    async def test_empty_when_no_goals(self, db_session):
        user = await _make_user(db_session, "empty@example.com")
        result = await list_goals(account_id=None, db=db_session, current_user=user)
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_by_account_id(self, db_session):
        """Edge: account_id filter restricts goals to that account only."""
        user = await _make_user(db_session, "acctf@example.com")
        a1 = await _make_account(db_session, user.id, name="A1")
        a2 = await _make_account(db_session, user.id, name="A2")
        await _make_goal(db_session, user.id, account_id=a1.id, name="Goal on A1")
        await _make_goal(db_session, user.id, account_id=a2.id, name="Goal on A2")

        result = await list_goals(account_id=a1.id, db=db_session, current_user=user)
        assert len(result) == 1
        assert result[0]["name"] == "Goal on A1"


class TestUpdateGoal:
    @pytest.mark.asyncio
    async def test_updates_name(self, db_session):
        user = await _make_user(db_session, "upd@example.com")
        goal = await _make_goal(db_session, user.id, name="Old")

        body = GoalUpdate(name="New")
        result = await update_goal(
            goal_id=goal.id, body=body, db=db_session, current_user=user,
        )
        assert result["name"] == "New"

    @pytest.mark.asyncio
    async def test_rejects_past_target_date(self, db_session):
        """Failure: target_date in the past returns 400."""
        user = await _make_user(db_session, "updp@example.com")
        goal = await _make_goal(db_session, user.id)
        past_date = datetime.utcnow() - timedelta(days=10)

        body = GoalUpdate(target_date=past_date)
        with pytest.raises(HTTPException) as exc:
            await update_goal(
                goal_id=goal.id, body=body, db=db_session, current_user=user,
            )
        assert exc.value.status_code == 400
        assert "must be in the future" in exc.value.detail

    @pytest.mark.asyncio
    async def test_other_user_cannot_update(self, db_session):
        """Multi-user isolation on PUT."""
        u1 = await _make_user(db_session, "up1@example.com")
        u2 = await _make_user(db_session, "up2@example.com")
        goal = await _make_goal(db_session, u1.id)

        with pytest.raises(HTTPException) as exc:
            await update_goal(
                goal_id=goal.id, body=GoalUpdate(name="hacked"),
                db=db_session, current_user=u2,
            )
        assert exc.value.status_code == 404


class TestDeleteGoal:
    @pytest.mark.asyncio
    async def test_deletes_own_goal(self, db_session):
        user = await _make_user(db_session, "dg@example.com")
        goal = await _make_goal(db_session, user.id)

        result = await delete_goal(
            goal_id=goal.id, db=db_session, current_user=user,
        )
        assert result == {"detail": "Goal deleted"}

    @pytest.mark.asyncio
    async def test_other_user_cannot_delete(self, db_session):
        u1 = await _make_user(db_session, "dg1@example.com")
        u2 = await _make_user(db_session, "dg2@example.com")
        goal = await _make_goal(db_session, u1.id)

        with pytest.raises(HTTPException) as exc:
            await delete_goal(goal_id=goal.id, db=db_session, current_user=u2)
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Schedules CRUD (list, create, delete)
# ---------------------------------------------------------------------------


class TestListSchedules:
    @pytest.mark.asyncio
    async def test_returns_only_current_user(self, db_session):
        u1 = await _make_user(db_session, "ls1@example.com")
        u2 = await _make_user(db_session, "ls2@example.com")
        await _make_schedule(db_session, u1.id, name="Mine")
        await _make_schedule(db_session, u2.id, name="Yours")

        result = await list_schedules(account_id=None, db=db_session, current_user=u1)
        names = [s["name"] for s in result]
        assert names == ["Mine"]


class TestCreateSchedule:
    @pytest.mark.asyncio
    async def test_creates_schedule_with_valid_body(self, db_session):
        """Happy path: creates a weekly schedule."""
        from app.routers.reports_crud_router import create_schedule

        user = await _make_user(db_session, "cs@example.com")

        body = ScheduleCreate(
            name="Weekly Test",
            schedule_type="weekly",
            schedule_days=[0, 3],  # Mon, Thu
            period_window="full_prior",
        )
        result = await create_schedule(
            body=body, db=db_session, current_user=user,
        )
        assert result["name"] == "Weekly Test"
        assert result["schedule_type"] == "weekly"
        assert result["schedule_days"] == [0, 3]

    @pytest.mark.asyncio
    async def test_create_schedule_with_invalid_goal_id_raises(self, db_session):
        """Failure: goal_ids that don't belong to user → ValidationError."""
        from app.routers.reports_crud_router import create_schedule

        user = await _make_user(db_session, "csg@example.com")
        body = ScheduleCreate(
            name="Weekly",
            schedule_type="weekly",
            schedule_days=[0],
            period_window="full_prior",
            goal_ids=[999999],
        )
        # create_schedule_record raises ValidationError from the service layer
        with pytest.raises(Exception) as exc:
            await create_schedule(body=body, db=db_session, current_user=user)
        # ValidationError message includes "Invalid goal IDs"
        assert "Invalid goal IDs" in str(exc.value) or "not found" in str(exc.value).lower()

    def test_schedule_create_rejects_trailing_without_lookback_value(self):
        """Failure: Pydantic validator rejects trailing without lookback_value."""
        with pytest.raises(Exception) as exc:
            ScheduleCreate(
                name="x", schedule_type="weekly",
                period_window="trailing",
            )
        assert "lookback_value is required" in str(exc.value)

    def test_schedule_create_auto_sets_lookback_unit_for_trailing(self):
        """Edge: lookback_unit defaults to 'days' when trailing + lookback_value set."""
        s = ScheduleCreate(
            name="x", schedule_type="weekly",
            period_window="trailing", lookback_value=30,
        )
        assert s.lookback_unit == "days"


class TestDeleteSchedule:
    @pytest.mark.asyncio
    async def test_deletes_own_schedule(self, db_session):
        user = await _make_user(db_session, "ds@example.com")
        schedule = await _make_schedule(db_session, user.id)
        result = await delete_schedule(
            schedule_id=schedule.id, db=db_session, current_user=user,
        )
        assert result == {"detail": "Schedule deleted"}

    @pytest.mark.asyncio
    async def test_other_user_gets_403(self, db_session):
        """get_writable_schedule raises 403 for non-owner non-manager."""
        u1 = await _make_user(db_session, "ds1@example.com")
        u2 = await _make_user(db_session, "ds2@example.com")
        schedule = await _make_schedule(db_session, u1.id)
        with pytest.raises(HTTPException) as exc:
            await delete_schedule(
                schedule_id=schedule.id, db=db_session, current_user=u2,
            )
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Tests: Reports (list, get, delete, bulk_delete, pdf)
# ---------------------------------------------------------------------------


class TestListReports:
    @pytest.mark.asyncio
    async def test_empty_returns_zero_total(self, db_session):
        user = await _make_user(db_session, "lrempty@example.com")
        result = await list_reports(
            limit=20, offset=0, schedule_id=None, account_id=None,
            db=db_session, current_user=user,
        )
        assert result["total"] == 0
        assert result["reports"] == []

    @pytest.mark.asyncio
    async def test_lists_current_user_reports(self, db_session):
        user = await _make_user(db_session, "lr1@example.com")
        other = await _make_user(db_session, "lr2@example.com")
        await _make_report(db_session, user.id)
        await _make_report(db_session, user.id)
        await _make_report(db_session, other.id)

        result = await list_reports(
            limit=20, offset=0, schedule_id=None, account_id=None,
            db=db_session, current_user=user,
        )
        assert result["total"] == 2
        assert len(result["reports"]) == 2

    @pytest.mark.asyncio
    async def test_pagination_limits_and_offset(self, db_session):
        user = await _make_user(db_session, "lrpg@example.com")
        for _ in range(5):
            await _make_report(db_session, user.id)

        first = await list_reports(
            limit=2, offset=0, schedule_id=None, account_id=None,
            db=db_session, current_user=user,
        )
        assert len(first["reports"]) == 2
        assert first["total"] == 5

        third_page = await list_reports(
            limit=2, offset=4, schedule_id=None, account_id=None,
            db=db_session, current_user=user,
        )
        assert len(third_page["reports"]) == 1


class TestGetReport:
    @pytest.mark.asyncio
    async def test_returns_report_with_html(self, db_session):
        user = await _make_user(db_session, "gr1@example.com")
        report = await _make_report(db_session, user.id, html_content="<html/>")

        result = await get_report(report_id=report.id, db=db_session, current_user=user)
        assert result["id"] == report.id
        assert result["html_content"] == "<html/>"

    @pytest.mark.asyncio
    async def test_other_user_blocked(self, db_session):
        u1 = await _make_user(db_session, "gr2@example.com")
        u2 = await _make_user(db_session, "gr3@example.com")
        report = await _make_report(db_session, u1.id)
        with pytest.raises(HTTPException) as exc:
            await get_report(report_id=report.id, db=db_session, current_user=u2)
        assert exc.value.status_code == 404


class TestDeleteReport:
    @pytest.mark.asyncio
    async def test_deletes_own_report(self, db_session):
        user = await _make_user(db_session, "dr1@example.com")
        report = await _make_report(db_session, user.id)
        result = await delete_report(
            report_id=report.id, db=db_session, current_user=user,
        )
        assert result == {"detail": "Report deleted"}

    @pytest.mark.asyncio
    async def test_nonexistent_404(self, db_session):
        user = await _make_user(db_session, "drnf@example.com")
        with pytest.raises(HTTPException) as exc:
            await delete_report(
                report_id=999999, db=db_session, current_user=user,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_other_user_blocked(self, db_session):
        """Multi-user isolation: cannot delete another user's report (→ 404)."""
        u1 = await _make_user(db_session, "dr2@example.com")
        u2 = await _make_user(db_session, "dr3@example.com")
        report = await _make_report(db_session, u1.id)
        with pytest.raises(HTTPException) as exc:
            await delete_report(
                report_id=report.id, db=db_session, current_user=u2,
            )
        assert exc.value.status_code == 404


class TestBulkDeleteReports:
    @pytest.mark.asyncio
    async def test_deletes_multiple(self, db_session):
        user = await _make_user(db_session, "bd1@example.com")
        r1 = await _make_report(db_session, user.id)
        r2 = await _make_report(db_session, user.id)
        await _make_report(db_session, user.id)  # Extra one that should remain

        body = BulkDeleteRequest(report_ids=[r1.id, r2.id])
        result = await bulk_delete_reports(
            body=body, db=db_session, current_user=user,
        )
        assert result["deleted"] == 2

    @pytest.mark.asyncio
    async def test_no_matches_raises_404(self, db_session):
        user = await _make_user(db_session, "bd2@example.com")
        body = BulkDeleteRequest(report_ids=[999998, 999999])
        with pytest.raises(HTTPException) as exc:
            await bulk_delete_reports(
                body=body, db=db_session, current_user=user,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_delete_other_users_reports(self, db_session):
        """Only OUR reports get deleted even if other_user IDs are in the list."""
        u1 = await _make_user(db_session, "bd3@example.com")
        u2 = await _make_user(db_session, "bd4@example.com")
        mine = await _make_report(db_session, u1.id)
        theirs = await _make_report(db_session, u2.id)

        body = BulkDeleteRequest(report_ids=[mine.id, theirs.id])
        result = await bulk_delete_reports(
            body=body, db=db_session, current_user=u1,
        )
        # Only 1 deleted — theirs is untouched
        assert result["deleted"] == 1

        # Verify theirs still exists
        from sqlalchemy import select as sa_select
        exists = await db_session.execute(
            sa_select(Report).where(Report.id == theirs.id)
        )
        assert exists.scalar_one_or_none() is not None


class TestDownloadReportPdf:
    @pytest.mark.asyncio
    async def test_returns_pdf_bytes(self, db_session):
        user = await _make_user(db_session, "pdf1@example.com")
        report = await _make_report(
            db_session, user.id, pdf_content=b"%PDF-1.4 fake",
        )
        # Set periodicity + period_end to build filename
        response = await download_report_pdf(
            report_id=report.id, db=db_session, current_user=user,
        )
        assert response.media_type == "application/pdf"
        assert response.body == b"%PDF-1.4 fake"
        assert "attachment; filename=" in response.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_404_when_pdf_missing(self, db_session):
        """Failure: report exists but pdf_content is None → 404."""
        user = await _make_user(db_session, "pdf2@example.com")
        report = await _make_report(db_session, user.id, pdf_content=None)
        with pytest.raises(HTTPException) as exc:
            await download_report_pdf(
                report_id=report.id, db=db_session, current_user=user,
            )
        assert exc.value.status_code == 404
        assert "PDF not available" in exc.value.detail

    @pytest.mark.asyncio
    async def test_404_when_report_not_owned(self, db_session):
        u1 = await _make_user(db_session, "pdf3@example.com")
        u2 = await _make_user(db_session, "pdf4@example.com")
        report = await _make_report(
            db_session, u1.id, pdf_content=b"%PDF...",
        )
        with pytest.raises(HTTPException) as exc:
            await download_report_pdf(
                report_id=report.id, db=db_session, current_user=u2,
            )
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# create_goal happy path (sweep v2.160.4: schema previously missed
# minimap_threshold_days, causing AttributeError on every real POST /goals).
# ---------------------------------------------------------------------------


class TestCreateGoal:
    """Tests for create_goal endpoint — ensures schema and persistence work."""

    def test_goal_create_schema_includes_minimap_threshold_days(self):
        """Schema must declare minimap_threshold_days so create_goal can read it."""
        fields = set(GoalCreate.model_fields.keys())
        assert "minimap_threshold_days" in fields

    @pytest.mark.asyncio
    async def test_create_goal_persists_all_fields(self, db_session):
        """Happy path: POST /goals creates a ReportGoal with all fields populated."""
        user = await _make_user(db_session, "create_goal@example.com")
        account = await _make_account(db_session, user.id)

        body = GoalCreate(
            name="Retirement",
            target_type="balance",
            target_currency="USD",
            target_value=100000.0,
            time_horizon_months=24,
            account_id=account.id,
            chart_horizon="auto",
            show_minimap=True,
            minimap_threshold_days=45,
        )

        result = await create_goal(body=body, db=db_session, current_user=user)

        assert result["name"] == "Retirement"
        assert result["minimap_threshold_days"] == 45
        assert result["target_value"] == 100000.0
        assert result["account_id"] == account.id

    @pytest.mark.asyncio
    async def test_create_goal_defaults_minimap_threshold_days(self, db_session):
        """Edge case: when minimap_threshold_days is omitted it defaults to 90."""
        user = await _make_user(db_session, "create_goal_default@example.com")

        body = GoalCreate(
            name="Income",
            target_type="income",
            target_currency="USD",
            target_value=5000.0,
            income_period="monthly",
            time_horizon_months=12,
        )

        result = await create_goal(body=body, db=db_session, current_user=user)
        assert result["minimap_threshold_days"] == 90

    def test_goal_create_rejects_missing_income_period_for_income_target(self):
        """Failure case: income target_type without income_period is rejected."""
        with pytest.raises(ValueError):
            GoalCreate(
                name="Bad Income",
                target_type="income",
                target_currency="USD",
                target_value=1000.0,
                time_horizon_months=12,
            )


# ---------------------------------------------------------------------------
# RBAC annotation checks
# ---------------------------------------------------------------------------


class TestRBACAnnotations:
    """Verify mutation endpoints use require_permission with correct scopes."""

    def _get_inner(self, fn):
        sig = inspect.signature(fn)
        dep = sig.parameters["current_user"].default
        return dep.dependency

    def _get_perms(self, inner):
        closure_vars = inspect.getclosurevars(inner)
        perms = closure_vars.nonlocals.get("permissions")
        return [str(p) for p in perms]

    def test_update_goal_requires_reports_write(self):
        inner = self._get_inner(update_goal)
        assert "require_permission" in inner.__qualname__
        assert str(Perm.REPORTS_WRITE) in self._get_perms(inner)

    def test_delete_goal_requires_reports_delete(self):
        inner = self._get_inner(delete_goal)
        assert "require_permission" in inner.__qualname__
        assert str(Perm.REPORTS_DELETE) in self._get_perms(inner)

    def test_delete_schedule_requires_reports_delete(self):
        inner = self._get_inner(delete_schedule)
        assert "require_permission" in inner.__qualname__
        assert str(Perm.REPORTS_DELETE) in self._get_perms(inner)

    def test_delete_report_requires_reports_delete(self):
        inner = self._get_inner(delete_report)
        assert "require_permission" in inner.__qualname__
        assert str(Perm.REPORTS_DELETE) in self._get_perms(inner)

    def test_bulk_delete_requires_reports_delete(self):
        inner = self._get_inner(bulk_delete_reports)
        assert "require_permission" in inner.__qualname__
        assert str(Perm.REPORTS_DELETE) in self._get_perms(inner)

    def test_get_report_uses_get_current_user(self):
        """Read endpoints should NOT require require_permission."""
        inner = self._get_inner(get_report)
        assert "require_permission" not in inner.__qualname__

    def test_list_goals_uses_get_current_user(self):
        inner = self._get_inner(list_goals)
        assert "require_permission" not in inner.__qualname__
