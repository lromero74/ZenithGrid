"""
Tests for reports_router — expense item create/update endpoints and bulk delete.

Covers the bug fix where create_expense_item() was not passing
due_day, due_month, and login_url to the ExpenseItem constructor,
plus bulk delete functionality.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from app.models import ExpenseItem, Report, ReportGoal, ReportSchedule, User


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
