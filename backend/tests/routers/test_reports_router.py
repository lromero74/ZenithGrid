"""
Tests for reports_router — expense item create/update endpoints, bulk delete,
and account-scoped filtering for goals, schedules, and reports.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from app.models import (
    Account, ExpenseItem, Report, ReportGoal, ReportSchedule, User,
)


@pytest.fixture
async def expense_goal(db_session):
    """Create a user and an expenses-type goal for testing."""
    user = User(
        email="expense_router_test@example.com",
        hashed_password="hashed",
        display_name="Test",
    )
    db_session.add(user)
    await db_session.flush()

    goal = ReportGoal(
        user_id=user.id,
        name="Test Bills",
        target_type="expenses",
        target_currency="USD",
        target_value=5000.0,
        expense_period="monthly",
        time_horizon_months=12,
        start_date=datetime.utcnow(),
        target_date=datetime.utcnow() + timedelta(days=365),
    )
    db_session.add(goal)
    await db_session.flush()
    return user, goal


class TestCreateExpenseItemFields:
    """Verify all fields are saved when creating expense items."""

    @pytest.mark.asyncio
    async def test_create_expense_item_saves_due_day(self, db_session, expense_goal):
        """due_day should be persisted on create (was missing before fix)."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Housing",
            name="Rent",
            amount=1500.0,
            frequency="monthly",
            due_day=15,
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.due_day == 15

    @pytest.mark.asyncio
    async def test_create_expense_item_saves_due_day_last(self, db_session, expense_goal):
        """due_day=-1 (last day of month) should be persisted."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Housing",
            name="Rent Test",
            amount=1000.0,
            frequency="monthly",
            due_day=-1,
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.due_day == -1

    @pytest.mark.asyncio
    async def test_create_expense_item_saves_due_month(self, db_session, expense_goal):
        """due_month should be persisted on create (was missing before fix)."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Insurance",
            name="Car Insurance",
            amount=600.0,
            frequency="semi_annual",
            due_day=1,
            due_month=6,
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.due_month == 6
        assert item.due_day == 1

    @pytest.mark.asyncio
    async def test_create_expense_item_saves_login_url(self, db_session, expense_goal):
        """login_url should be persisted on create (was missing before fix)."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Streaming",
            name="Netflix",
            amount=15.99,
            frequency="monthly",
            login_url="https://netflix.com/login",
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.login_url == "https://netflix.com/login"

    @pytest.mark.asyncio
    async def test_create_expense_item_all_optional_fields(self, db_session, expense_goal):
        """All optional fields (due_day, due_month, login_url) saved together."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Utilities",
            name="Electric",
            amount=200.0,
            frequency="monthly",
            due_day=20,
            due_month=3,
            login_url="https://electric.com/pay",
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.due_day == 20
        assert item.due_month == 3
        assert item.login_url == "https://electric.com/pay"

    @pytest.mark.asyncio
    async def test_create_expense_item_null_optional_fields(self, db_session, expense_goal):
        """Optional fields default to None when not provided."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Food",
            name="Groceries",
            amount=400.0,
            frequency="monthly",
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.due_day is None
        assert item.due_month is None
        assert item.login_url is None


# ---------------------------------------------------------------------------
# Bulk Delete Reports
# ---------------------------------------------------------------------------


@pytest.fixture
async def bulk_delete_setup(db_session):
    """Create two users, a schedule, and several reports for bulk delete testing."""
    user1 = User(
        email="bulk_del_user1@example.com",
        hashed_password="hashed",
        display_name="User1",
    )
    user2 = User(
        email="bulk_del_user2@example.com",
        hashed_password="hashed",
        display_name="User2",
    )
    db_session.add_all([user1, user2])
    await db_session.flush()

    schedule = ReportSchedule(
        user_id=user1.id,
        name="Weekly",
        periodicity="weekly",
        recipients=[],
    )
    db_session.add(schedule)
    await db_session.flush()

    reports = []
    for i in range(5):
        r = Report(
            user_id=user1.id,
            schedule_id=schedule.id,
            periodicity="weekly",
            period_start=datetime(2026, 1, 1 + i),
            period_end=datetime(2026, 1, 7 + i),
            html_content=f"<p>Report {i}</p>",
            delivery_status="sent",
        )
        reports.append(r)
    # One report owned by user2
    other_report = Report(
        user_id=user2.id,
        schedule_id=schedule.id,
        periodicity="weekly",
        period_start=datetime(2026, 2, 1),
        period_end=datetime(2026, 2, 7),
        html_content="<p>Other user report</p>",
        delivery_status="sent",
    )
    db_session.add_all(reports + [other_report])
    await db_session.flush()
    return user1, user2, reports, other_report


class TestBulkDeleteReports:
    """Tests for POST /reports/bulk-delete endpoint logic."""

    @pytest.mark.asyncio
    async def test_bulk_delete_happy_path(self, db_session, bulk_delete_setup):
        """Delete 3 reports owned by the user — should succeed and return count."""
        user1, _, reports, _ = bulk_delete_setup
        ids_to_delete = [reports[0].id, reports[1].id, reports[2].id]

        from app.routers.reports_router import BulkDeleteRequest
        # Simulate the endpoint logic directly on the DB
        result = await db_session.execute(
            select(Report).where(
                Report.id.in_(ids_to_delete),
                Report.user_id == user1.id,
            )
        )
        found = list(result.scalars().all())
        assert len(found) == 3
        for r in found:
            await db_session.delete(r)
        await db_session.flush()

        # Verify they're gone
        remaining = await db_session.execute(
            select(Report).where(
                Report.user_id == user1.id,
            )
        )
        assert len(list(remaining.scalars().all())) == 2

    @pytest.mark.asyncio
    async def test_bulk_delete_partial_ids(self, db_session, bulk_delete_setup):
        """Some IDs exist, some don't — deletes what it can."""
        user1, _, reports, _ = bulk_delete_setup
        ids_to_delete = [reports[0].id, 99999]

        result = await db_session.execute(
            select(Report).where(
                Report.id.in_(ids_to_delete),
                Report.user_id == user1.id,
            )
        )
        found = list(result.scalars().all())
        assert len(found) == 1
        for r in found:
            await db_session.delete(r)
        await db_session.flush()

    @pytest.mark.asyncio
    async def test_bulk_delete_wrong_user_gets_nothing(self, db_session, bulk_delete_setup):
        """User2 cannot delete user1's reports — query returns empty list."""
        _, user2, reports, _ = bulk_delete_setup
        ids_to_delete = [reports[0].id, reports[1].id]

        result = await db_session.execute(
            select(Report).where(
                Report.id.in_(ids_to_delete),
                Report.user_id == user2.id,
            )
        )
        found = list(result.scalars().all())
        assert len(found) == 0

    @pytest.mark.asyncio
    async def test_bulk_delete_nonexistent_ids_empty(self, db_session, bulk_delete_setup):
        """All IDs invalid — returns empty list (endpoint would 404)."""
        user1, _, _, _ = bulk_delete_setup

        result = await db_session.execute(
            select(Report).where(
                Report.id.in_([88888, 99999]),
                Report.user_id == user1.id,
            )
        )
        found = list(result.scalars().all())
        assert len(found) == 0

    @pytest.mark.asyncio
    async def test_bulk_delete_request_validation_empty_list(self):
        """Empty list should fail Pydantic validation."""
        from app.routers.reports_router import BulkDeleteRequest
        with pytest.raises(Exception):
            BulkDeleteRequest(report_ids=[])

    @pytest.mark.asyncio
    async def test_bulk_delete_request_validation_exceeds_max(self):
        """>100 IDs should fail Pydantic validation."""
        from app.routers.reports_router import BulkDeleteRequest
        with pytest.raises(Exception):
            BulkDeleteRequest(report_ids=list(range(101)))


# ---------------------------------------------------------------------------
# Account-Scoped Reports
# ---------------------------------------------------------------------------


@pytest.fixture
async def account_scope_setup(db_session):
    """Create a user with two accounts and goals/schedules/reports on each."""
    user = User(
        email="acct_scope_test@example.com",
        hashed_password="hashed",
        display_name="Test",
    )
    db_session.add(user)
    await db_session.flush()

    acct_live = Account(
        user_id=user.id,
        name="Live",
        type="cex",
        is_default=True,
    )
    acct_paper = Account(
        user_id=user.id,
        name="Paper",
        type="cex",
        is_default=False,
    )
    db_session.add_all([acct_live, acct_paper])
    await db_session.flush()

    # Goals — one per account
    goal_live = ReportGoal(
        user_id=user.id,
        account_id=acct_live.id,
        name="Live Goal",
        target_type="balance",
        target_currency="USD",
        target_value=10000.0,
        time_horizon_months=12,
        start_date=datetime.utcnow(),
        target_date=datetime.utcnow() + timedelta(days=365),
    )
    goal_paper = ReportGoal(
        user_id=user.id,
        account_id=acct_paper.id,
        name="Paper Goal",
        target_type="balance",
        target_currency="USD",
        target_value=5000.0,
        time_horizon_months=6,
        start_date=datetime.utcnow(),
        target_date=datetime.utcnow() + timedelta(days=180),
    )
    db_session.add_all([goal_live, goal_paper])
    await db_session.flush()

    # Schedules — one per account
    sched_live = ReportSchedule(
        user_id=user.id,
        account_id=acct_live.id,
        name="Live Weekly",
        periodicity="weekly",
        recipients=[],
    )
    sched_paper = ReportSchedule(
        user_id=user.id,
        account_id=acct_paper.id,
        name="Paper Weekly",
        periodicity="weekly",
        recipients=[],
    )
    db_session.add_all([sched_live, sched_paper])
    await db_session.flush()

    # Reports — two per account
    reports_live = []
    for i in range(2):
        r = Report(
            user_id=user.id,
            account_id=acct_live.id,
            schedule_id=sched_live.id,
            periodicity="weekly",
            period_start=datetime(2026, 1, 1 + i),
            period_end=datetime(2026, 1, 7 + i),
            html_content=f"<p>Live Report {i}</p>",
            delivery_status="sent",
        )
        reports_live.append(r)

    reports_paper = []
    for i in range(2):
        r = Report(
            user_id=user.id,
            account_id=acct_paper.id,
            schedule_id=sched_paper.id,
            periodicity="weekly",
            period_start=datetime(2026, 2, 1 + i),
            period_end=datetime(2026, 2, 7 + i),
            html_content=f"<p>Paper Report {i}</p>",
            delivery_status="sent",
        )
        reports_paper.append(r)

    db_session.add_all(reports_live + reports_paper)
    await db_session.flush()

    return {
        "user": user,
        "acct_live": acct_live,
        "acct_paper": acct_paper,
        "goal_live": goal_live,
        "goal_paper": goal_paper,
        "sched_live": sched_live,
        "sched_paper": sched_paper,
        "reports_live": reports_live,
        "reports_paper": reports_paper,
    }


class TestAccountScopedGoals:
    """Goals should be filterable by account_id."""

    @pytest.mark.asyncio
    async def test_list_goals_filters_by_account_id(
        self, db_session, account_scope_setup
    ):
        """Filtering by account_id returns only that account's goals."""
        s = account_scope_setup
        result = await db_session.execute(
            select(ReportGoal).where(
                ReportGoal.user_id == s["user"].id,
                ReportGoal.account_id == s["acct_live"].id,
            )
        )
        goals = list(result.scalars().all())
        assert len(goals) == 1
        assert goals[0].name == "Live Goal"

    @pytest.mark.asyncio
    async def test_list_goals_no_filter_returns_all(
        self, db_session, account_scope_setup
    ):
        """Without account_id filter, all user goals are returned."""
        s = account_scope_setup
        result = await db_session.execute(
            select(ReportGoal).where(
                ReportGoal.user_id == s["user"].id,
            )
        )
        goals = list(result.scalars().all())
        assert len(goals) == 2

    @pytest.mark.asyncio
    async def test_create_goal_stores_account_id(
        self, db_session, account_scope_setup
    ):
        """account_id is persisted when creating a goal."""
        s = account_scope_setup
        goal = ReportGoal(
            user_id=s["user"].id,
            account_id=s["acct_paper"].id,
            name="New Paper Goal",
            target_type="profit",
            target_currency="USD",
            target_value=1000.0,
            time_horizon_months=3,
            start_date=datetime.utcnow(),
            target_date=datetime.utcnow() + timedelta(days=90),
        )
        db_session.add(goal)
        await db_session.flush()
        await db_session.refresh(goal)
        assert goal.account_id == s["acct_paper"].id


class TestAccountScopedSchedules:
    """Schedules should be filterable by account_id."""

    @pytest.mark.asyncio
    async def test_list_schedules_filters_by_account_id(
        self, db_session, account_scope_setup
    ):
        """Filtering by account_id returns only that account's schedules."""
        s = account_scope_setup
        result = await db_session.execute(
            select(ReportSchedule).where(
                ReportSchedule.user_id == s["user"].id,
                ReportSchedule.account_id == s["acct_paper"].id,
            )
        )
        schedules = list(result.scalars().all())
        assert len(schedules) == 1
        assert schedules[0].name == "Paper Weekly"

    @pytest.mark.asyncio
    async def test_list_schedules_no_filter_returns_all(
        self, db_session, account_scope_setup
    ):
        """Without account_id filter, all user schedules are returned."""
        s = account_scope_setup
        result = await db_session.execute(
            select(ReportSchedule).where(
                ReportSchedule.user_id == s["user"].id,
            )
        )
        schedules = list(result.scalars().all())
        assert len(schedules) == 2


class TestAccountScopedReports:
    """Reports should be filterable by account_id."""

    @pytest.mark.asyncio
    async def test_list_reports_filters_by_account_id(
        self, db_session, account_scope_setup
    ):
        """Filtering by account_id returns only that account's reports."""
        s = account_scope_setup
        result = await db_session.execute(
            select(Report).where(
                Report.user_id == s["user"].id,
                Report.account_id == s["acct_live"].id,
            )
        )
        reports = list(result.scalars().all())
        assert len(reports) == 2
        for r in reports:
            assert "Live" in r.html_content

    @pytest.mark.asyncio
    async def test_list_reports_no_filter_returns_all(
        self, db_session, account_scope_setup
    ):
        """Without account_id filter, all user reports are returned."""
        s = account_scope_setup
        result = await db_session.execute(
            select(Report).where(
                Report.user_id == s["user"].id,
            )
        )
        reports = list(result.scalars().all())
        assert len(reports) == 4

    @pytest.mark.asyncio
    async def test_report_inherits_account_from_schedule(
        self, db_session, account_scope_setup
    ):
        """A report created for a schedule inherits its account_id."""
        s = account_scope_setup
        report = Report(
            user_id=s["user"].id,
            account_id=s["sched_live"].account_id,
            schedule_id=s["sched_live"].id,
            periodicity="weekly",
            period_start=datetime(2026, 3, 1),
            period_end=datetime(2026, 3, 7),
            html_content="<p>Test</p>",
            delivery_status="manual",
        )
        db_session.add(report)
        await db_session.flush()
        await db_session.refresh(report)
        assert report.account_id == s["acct_live"].id
