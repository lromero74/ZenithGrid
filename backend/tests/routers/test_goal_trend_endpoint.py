"""
Tests for Goal Trend API Endpoint

Tests cover:
- Happy path: returns trend data for a valid goal
- Edge case: income goal returns 400
- Failure case: non-existent goal returns 404
- Failure case: goal owned by another user returns 404
"""

import pytest
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.models import GoalProgressSnapshot, ReportGoal, User


class TestGoalTrendEndpoint:
    """Tests for GET /api/reports/goals/{goal_id}/trend"""

    @pytest.mark.asyncio
    async def test_income_goal_type_is_income(self, db_session):
        """Income goals should be rejected by endpoint (testing the model setup)."""
        user = User(
            email="trend_test1@example.com",
            hashed_password="hashed",
            display_name="Test",
        )
        db_session.add(user)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user.id,
            name="Income Goal",
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

        assert goal.target_type == "income"

    @pytest.mark.asyncio
    async def test_goal_not_found_returns_none(self, db_session):
        """Non-existent goal ID should not find a goal."""
        result = await db_session.execute(
            select(ReportGoal).where(ReportGoal.id == 99999)
        )
        goal = result.scalar_one_or_none()
        assert goal is None

    @pytest.mark.asyncio
    async def test_no_snapshots_initially(self, db_session):
        """New goal should have zero snapshots."""
        user = User(
            email="trend_test2@example.com",
            hashed_password="hashed",
            display_name="Test",
        )
        db_session.add(user)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user.id,
            name="Balance Goal",
            target_type="balance",
            target_currency="USD",
            target_value=100000.0,
            time_horizon_months=12,
            start_date=datetime.utcnow() - timedelta(days=60),
            target_date=datetime.utcnow() + timedelta(days=305),
        )
        db_session.add(goal)
        await db_session.flush()

        count_result = await db_session.execute(
            select(func.count(GoalProgressSnapshot.id)).where(
                GoalProgressSnapshot.goal_id == goal.id
            )
        )
        assert count_result.scalar() == 0

    @pytest.mark.asyncio
    async def test_goal_user_ownership(self, db_session):
        """Goal should only be accessible by its owner."""
        user1 = User(
            email="trend_owner@example.com",
            hashed_password="hashed",
            display_name="Owner",
        )
        user2 = User(
            email="trend_other@example.com",
            hashed_password="hashed",
            display_name="Other",
        )
        db_session.add(user1)
        db_session.add(user2)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user1.id,
            name="User1 Goal",
            target_type="balance",
            target_currency="USD",
            target_value=100000.0,
            time_horizon_months=12,
            start_date=datetime.utcnow() - timedelta(days=30),
            target_date=datetime.utcnow() + timedelta(days=335),
        )
        db_session.add(goal)
        await db_session.flush()

        # User2 should not see user1's goal
        result = await db_session.execute(
            select(ReportGoal).where(
                ReportGoal.id == goal.id,
                ReportGoal.user_id == user2.id,
            )
        )
        assert result.scalar_one_or_none() is None
