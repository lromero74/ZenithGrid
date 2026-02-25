"""
Tests for Goal Snapshot Service

Tests cover:
- Happy path: capturing snapshots for active balance/profit goals
- Edge case: no active goals returns 0
- Edge case: income goals are skipped
- Failure case: goal with zero target value
- Trend data: returns correct structure with ideal values
- Expense goal snapshots: capture, backfill, and trend data
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.models import (
    ExpenseItem,
    GoalProgressSnapshot,
    Position,
    ReportGoal,
    User,
)
from app.services.goal_snapshot_service import (
    _backfill_expense_goal_snapshots,
    _get_expense_snapshot_values,
    capture_goal_snapshots,
    get_goal_trend_data,
    _get_current_value_for_goal,
    _get_target_for_goal,
)


# ---- Unit tests for helper functions ----

class TestGetCurrentValueForGoal:
    """Tests for _get_current_value_for_goal helper."""

    def test_balance_goal_usd(self):
        goal = MagicMock(target_type="balance", target_currency="USD")
        result = _get_current_value_for_goal(goal, 50000.0, 1.5, 5000.0, 0.1)
        assert result == 50000.0

    def test_balance_goal_btc(self):
        goal = MagicMock(target_type="balance", target_currency="BTC")
        result = _get_current_value_for_goal(goal, 50000.0, 1.5, 5000.0, 0.1)
        assert result == 1.5

    def test_profit_goal_usd(self):
        goal = MagicMock(target_type="profit", target_currency="USD")
        result = _get_current_value_for_goal(goal, 50000.0, 1.5, 5000.0, 0.1)
        assert result == 5000.0

    def test_profit_goal_btc(self):
        goal = MagicMock(target_type="profit", target_currency="BTC")
        result = _get_current_value_for_goal(goal, 50000.0, 1.5, 5000.0, 0.1)
        assert result == 0.1

    def test_both_goal_uses_balance(self):
        goal = MagicMock(target_type="both", target_currency="USD")
        result = _get_current_value_for_goal(goal, 50000.0, 1.5, 5000.0, 0.1)
        assert result == 50000.0


class TestGetTargetForGoal:
    """Tests for _get_target_for_goal helper."""

    def test_balance_goal(self):
        goal = MagicMock(target_type="balance", target_value=100000.0)
        assert _get_target_for_goal(goal) == 100000.0

    def test_profit_goal(self):
        goal = MagicMock(target_type="profit", target_value=10000.0)
        assert _get_target_for_goal(goal) == 10000.0

    def test_both_goal_uses_balance_value(self):
        goal = MagicMock(
            target_type="both",
            target_value=50000.0,
            target_balance_value=75000.0,
        )
        assert _get_target_for_goal(goal) == 75000.0

    def test_both_goal_fallback_to_target_value(self):
        goal = MagicMock(
            target_type="both",
            target_value=50000.0,
            target_balance_value=None,
        )
        assert _get_target_for_goal(goal) == 50000.0


# ---- Integration tests using db_session ----

class TestCaptureGoalSnapshots:
    """Tests for capture_goal_snapshots."""

    @pytest.mark.asyncio
    async def test_no_active_goals_returns_zero(self, db_session):
        """No active goals should return 0 snapshots."""
        user = User(
            email="test_snap1@example.com",
            hashed_password="hashed",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        count = await capture_goal_snapshots(
            db_session, user.id, 50000.0, 1.5
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_income_goals_skipped(self, db_session):
        """Income goals should not generate snapshots."""
        user = User(
            email="test_snap2@example.com",
            hashed_password="hashed",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user.id,
            name="Monthly Income",
            target_type="income",
            target_currency="USD",
            target_value=1000.0,
            income_period="monthly",
            time_horizon_months=12,
            start_date=datetime.utcnow() - timedelta(days=30),
            target_date=datetime.utcnow() + timedelta(days=335),
        )
        db_session.add(goal)
        await db_session.flush()

        count = await capture_goal_snapshots(
            db_session, user.id, 50000.0, 1.5
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_balance_goal_creates_snapshot(self, db_session):
        """Active balance goal should create a snapshot."""
        user = User(
            email="test_snap3@example.com",
            hashed_password="hashed",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user.id,
            name="Reach 100K",
            target_type="balance",
            target_currency="USD",
            target_value=100000.0,
            time_horizon_months=12,
            start_date=datetime.utcnow() - timedelta(days=30),
            target_date=datetime.utcnow() + timedelta(days=335),
        )
        db_session.add(goal)
        await db_session.flush()

        count = await capture_goal_snapshots(
            db_session, user.id, 50000.0, 1.5
        )
        assert count == 1

    @pytest.mark.asyncio
    async def test_zero_target_value_handles_gracefully(self, db_session):
        """Goal with zero target should not crash (progress_pct = 0)."""
        user = User(
            email="test_snap4@example.com",
            hashed_password="hashed",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user.id,
            name="Zero Target",
            target_type="balance",
            target_currency="USD",
            target_value=0.0,  # Edge case
            time_horizon_months=6,
            start_date=datetime.utcnow() - timedelta(days=30),
            target_date=datetime.utcnow() + timedelta(days=150),
        )
        db_session.add(goal)
        await db_session.flush()

        # Should not crash even with zero target
        count = await capture_goal_snapshots(
            db_session, user.id, 50000.0, 1.5
        )
        assert count == 1


class TestGetGoalTrendData:
    """Tests for get_goal_trend_data."""

    @pytest.mark.asyncio
    async def test_empty_snapshots_returns_empty(self, db_session):
        """Goal with no snapshots returns empty data_points."""
        user = User(
            email="test_trend1@example.com",
            hashed_password="hashed",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user.id,
            name="Test Goal",
            target_type="balance",
            target_currency="USD",
            target_value=100000.0,
            time_horizon_months=12,
            start_date=datetime.utcnow() - timedelta(days=30),
            target_date=datetime.utcnow() + timedelta(days=335),
        )
        db_session.add(goal)
        await db_session.flush()

        result = await get_goal_trend_data(db_session, goal)
        assert result["data_points"] == []
        assert result["goal"]["id"] == goal.id

    @pytest.mark.asyncio
    async def test_trend_data_includes_ideal_values(self, db_session):
        """Trend data should include computed ideal values."""
        user = User(
            email="test_trend2@example.com",
            hashed_password="hashed",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        start = datetime.utcnow() - timedelta(days=60)
        target_date = start + timedelta(days=365)

        goal = ReportGoal(
            user_id=user.id,
            name="Balance Goal",
            target_type="balance",
            target_currency="USD",
            target_value=100000.0,
            time_horizon_months=12,
            start_date=start,
            target_date=target_date,
        )
        db_session.add(goal)
        await db_session.flush()

        # Add some snapshots
        for i in range(5):
            snap_date = start + timedelta(days=i * 10)
            snap = GoalProgressSnapshot(
                goal_id=goal.id,
                user_id=user.id,
                snapshot_date=snap_date,
                current_value=40000.0 + i * 2000,
                target_value=100000.0,
                progress_pct=40.0 + i * 2,
                on_track=True,
            )
            db_session.add(snap)
        await db_session.flush()

        result = await get_goal_trend_data(db_session, goal)
        assert len(result["data_points"]) == 5
        assert result["goal"]["target_value"] == 100000.0
        first_point = result["data_points"][0]
        assert "ideal_value" in first_point
        assert "current_value" in first_point
        assert "date" in first_point

    @pytest.mark.asyncio
    async def test_profit_goal_ideal_starts_at_zero(self, db_session):
        """Profit goals should have ideal_start_value of 0."""
        user = User(
            email="test_trend3@example.com",
            hashed_password="hashed",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user.id,
            name="Profit Goal",
            target_type="profit",
            target_currency="USD",
            target_value=10000.0,
            time_horizon_months=6,
            start_date=datetime.utcnow() - timedelta(days=30),
            target_date=datetime.utcnow() + timedelta(days=150),
        )
        db_session.add(goal)
        await db_session.flush()

        result = await get_goal_trend_data(db_session, goal)
        assert result["ideal_start_value"] == 0.0


# ---- Expense goal snapshot tests ----

async def _create_expense_goal_fixtures(db_session):
    """Helper to create user, expense goal, and expense items."""
    user = User(
        email="test_expense_snap@example.com",
        hashed_password="hashed",
        display_name="Test User",
    )
    db_session.add(user)
    await db_session.flush()

    start = datetime.utcnow() - timedelta(days=30)
    target_date = start + timedelta(days=365)

    goal = ReportGoal(
        user_id=user.id,
        name="Cover Expenses",
        target_type="expenses",
        target_currency="USD",
        target_value=0,  # Not used for expenses
        expense_period="monthly",
        tax_withholding_pct=10,
        time_horizon_months=12,
        start_date=start,
        target_date=target_date,
    )
    db_session.add(goal)
    await db_session.flush()

    # Add expense items: $500 rent + $100 utilities = $600/month total
    rent = ExpenseItem(
        goal_id=goal.id,
        user_id=user.id,
        category="Housing",
        name="Rent",
        amount=500.0,
        frequency="monthly",
        is_active=True,
        sort_order=0,
    )
    utils = ExpenseItem(
        goal_id=goal.id,
        user_id=user.id,
        category="Utilities",
        name="Electric",
        amount=100.0,
        frequency="monthly",
        is_active=True,
        sort_order=1,
    )
    db_session.add_all([rent, utils])
    await db_session.flush()

    return user, goal


class TestGetExpenseSnapshotValues:
    """Tests for _get_expense_snapshot_values helper."""

    @pytest.mark.asyncio
    async def test_happy_path_computes_coverage(self, db_session):
        """Should compute income_after_tax and total_expenses from positions."""
        user, goal = await _create_expense_goal_fixtures(db_session)

        # Add closed positions totaling $900 profit over 30 days
        # daily_income = $30, projected_monthly = $900
        # income_after_tax = $900 * 0.9 = $810
        pos = Position(
            user_id=user.id,
            product_id="BTC-USD",
            status="closed",
            profit_usd=900.0,
            closed_at=datetime.utcnow() - timedelta(days=5),
        )
        db_session.add(pos)
        await db_session.flush()

        income_at, total_exp = await _get_expense_snapshot_values(
            db_session, goal,
        )

        assert total_exp == 600.0  # $500 + $100
        assert income_at == pytest.approx(810.0, abs=5.0)

    @pytest.mark.asyncio
    async def test_no_positions_returns_zero_income(self, db_session):
        """No closed positions should yield zero income_after_tax."""
        user, goal = await _create_expense_goal_fixtures(db_session)

        income_at, total_exp = await _get_expense_snapshot_values(
            db_session, goal,
        )

        assert total_exp == 600.0
        assert income_at == 0.0

    @pytest.mark.asyncio
    async def test_no_expense_items_returns_zero_total(self, db_session):
        """Goal with no expense items should return total_expenses=0."""
        user = User(
            email="test_noitems@example.com",
            hashed_password="hashed",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user.id,
            name="Empty Expenses",
            target_type="expenses",
            target_currency="USD",
            target_value=0,
            expense_period="monthly",
            tax_withholding_pct=0,
            time_horizon_months=12,
            start_date=datetime.utcnow() - timedelta(days=30),
            target_date=datetime.utcnow() + timedelta(days=335),
        )
        db_session.add(goal)
        await db_session.flush()

        income_at, total_exp = await _get_expense_snapshot_values(
            db_session, goal,
        )
        assert total_exp == 0.0


class TestCaptureExpenseGoalSnapshots:
    """Tests for expense goals in capture_goal_snapshots."""

    @pytest.mark.asyncio
    async def test_expense_goal_creates_snapshot(self, db_session):
        """Expense goals should now create snapshots."""
        user, goal = await _create_expense_goal_fixtures(db_session)

        count = await capture_goal_snapshots(
            db_session, user.id, 50000.0, 1.5,
        )
        assert count == 1


class TestBackfillExpenseGoalSnapshots:
    """Tests for _backfill_expense_goal_snapshots."""

    @pytest.mark.asyncio
    async def test_happy_path_creates_snapshots(self, db_session):
        """Should create one snapshot per day from start to today."""
        user, goal = await _create_expense_goal_fixtures(db_session)

        # Add a closed position
        pos = Position(
            user_id=user.id,
            product_id="BTC-USD",
            status="closed",
            profit_usd=600.0,
            closed_at=goal.start_date + timedelta(days=5),
        )
        db_session.add(pos)
        await db_session.flush()

        count = await _backfill_expense_goal_snapshots(db_session, goal)

        # Should create ~30 snapshots (one per day)
        assert count >= 28
        assert count <= 32

    @pytest.mark.asyncio
    async def test_skips_existing_snapshots(self, db_session):
        """Should not duplicate existing snapshots."""
        user, goal = await _create_expense_goal_fixtures(db_session)

        # Create an existing snapshot
        snap_date = goal.start_date.replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        snap = GoalProgressSnapshot(
            goal_id=goal.id,
            user_id=user.id,
            snapshot_date=snap_date,
            current_value=0.0,
            target_value=600.0,
            progress_pct=0.0,
            on_track=False,
        )
        db_session.add(snap)
        await db_session.flush()

        count = await _backfill_expense_goal_snapshots(db_session, goal)

        # Should skip the existing date
        expected_days = (
            datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            - snap_date
        ).days
        assert count == expected_days  # one less than total days

    @pytest.mark.asyncio
    async def test_no_expense_items_returns_zero(self, db_session):
        """No expense items should skip backfill."""
        user = User(
            email="test_backfill_empty@example.com",
            hashed_password="hashed",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user.id,
            name="No Items",
            target_type="expenses",
            target_currency="USD",
            target_value=0,
            expense_period="monthly",
            tax_withholding_pct=0,
            time_horizon_months=12,
            start_date=datetime.utcnow() - timedelta(days=10),
            target_date=datetime.utcnow() + timedelta(days=355),
        )
        db_session.add(goal)
        await db_session.flush()

        count = await _backfill_expense_goal_snapshots(db_session, goal)
        assert count == 0

    @pytest.mark.asyncio
    async def test_future_start_date_returns_zero(self, db_session):
        """Goal starting in the future should return zero snapshots."""
        user, _ = await _create_expense_goal_fixtures(db_session)

        future_goal = ReportGoal(
            user_id=user.id,
            name="Future Goal",
            target_type="expenses",
            target_currency="USD",
            target_value=0,
            expense_period="monthly",
            tax_withholding_pct=0,
            time_horizon_months=12,
            start_date=datetime.utcnow() + timedelta(days=30),
            target_date=datetime.utcnow() + timedelta(days=395),
        )
        db_session.add(future_goal)
        await db_session.flush()

        # Need to add expense items to the new goal
        item = ExpenseItem(
            goal_id=future_goal.id,
            user_id=user.id,
            category="Test",
            name="Test Item",
            amount=100.0,
            frequency="monthly",
            is_active=True,
            sort_order=0,
        )
        db_session.add(item)
        await db_session.flush()

        count = await _backfill_expense_goal_snapshots(
            db_session, future_goal,
        )
        assert count == 0


class TestExpenseGoalTrendData:
    """Tests for expense goals in get_goal_trend_data."""

    @pytest.mark.asyncio
    async def test_expense_goal_ideal_starts_at_zero(self, db_session):
        """Expense goals should have ideal_start_value of 0."""
        user = User(
            email="test_exp_trend@example.com",
            hashed_password="hashed",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user.id,
            name="Expense Goal",
            target_type="expenses",
            target_currency="USD",
            target_value=600.0,
            expense_period="monthly",
            tax_withholding_pct=10,
            time_horizon_months=6,
            start_date=datetime.utcnow() - timedelta(days=30),
            target_date=datetime.utcnow() + timedelta(days=150),
        )
        db_session.add(goal)
        await db_session.flush()

        result = await get_goal_trend_data(db_session, goal)
        assert result["ideal_start_value"] == 0.0

    @pytest.mark.asyncio
    async def test_expense_trend_with_snapshots(self, db_session):
        """Expense goals should return proper trend data from snapshots."""
        user = User(
            email="test_exp_trend2@example.com",
            hashed_password="hashed",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        start = datetime.utcnow() - timedelta(days=60)
        target_date = start + timedelta(days=365)

        goal = ReportGoal(
            user_id=user.id,
            name="Expense Trend",
            target_type="expenses",
            target_currency="USD",
            target_value=600.0,
            expense_period="monthly",
            tax_withholding_pct=10,
            time_horizon_months=12,
            start_date=start,
            target_date=target_date,
        )
        db_session.add(goal)
        await db_session.flush()

        # Add snapshots
        for i in range(5):
            snap_date = start + timedelta(days=i * 10)
            snap = GoalProgressSnapshot(
                goal_id=goal.id,
                user_id=user.id,
                snapshot_date=snap_date,
                current_value=100.0 + i * 50,
                target_value=600.0,
                progress_pct=min((100.0 + i * 50) / 600 * 100, 100),
                on_track=True,
            )
            db_session.add(snap)
        await db_session.flush()

        result = await get_goal_trend_data(db_session, goal)
        assert len(result["data_points"]) == 5
        assert result["ideal_start_value"] == 0.0
        assert result["ideal_end_value"] == 600.0
        # First point ideal should be near 0 (small fraction elapsed)
        first = result["data_points"][0]
        assert first["ideal_value"] < 20.0
