"""
Tests for Goal Snapshot Service

Tests cover:
- Happy path: capturing snapshots for active balance/profit goals
- Edge case: no active goals returns 0
- Edge case: income goals are skipped
- Failure case: goal with zero target value
- Trend data: returns correct structure with ideal values
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.models import (
    GoalProgressSnapshot,
    ReportGoal,
    User,
)
from app.services.goal_snapshot_service import (
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
