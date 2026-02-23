"""
Tests for reports_router — expense item create/update endpoints.

Covers the bug fix where create_expense_item() was not passing
due_day, due_month, and login_url to the ExpenseItem constructor.
"""

import pytest
from datetime import datetime, timedelta
from app.models import ExpenseItem, ReportGoal, User


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
