"""
Tests for backend/app/services/report_schedule_service.py

Covers:
- compute_next_run_for_new_schedule: datetime computation from body params
- create_schedule_record: full schedule creation with goal links
- update_schedule_record: partial update with recomputation
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import NotFoundError, ValidationError
from app.models import ReportGoal, ReportSchedule, ReportScheduleGoal, User
from app.services.report_schedule_service import (
    compute_next_run_for_new_schedule,
    create_schedule_record,
    update_schedule_record,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_body(**overrides):
    """Create a mock schedule request body with sensible defaults."""
    body = MagicMock()
    body.schedule_type = overrides.get("schedule_type", "weekly")
    body.schedule_days = overrides.get("schedule_days", [1])  # Monday
    body.quarter_start_month = overrides.get("quarter_start_month", None)
    body.period_window = overrides.get("period_window", "full_prior")
    body.lookback_value = overrides.get("lookback_value", None)
    body.lookback_unit = overrides.get("lookback_unit", None)
    body.name = overrides.get("name", "Weekly Report")
    body.account_id = overrides.get("account_id", None)
    body.is_enabled = overrides.get("is_enabled", True)
    body.show_expense_lookahead = overrides.get("show_expense_lookahead", True)
    body.ai_provider = overrides.get("ai_provider", None)
    body.generate_ai_summary = overrides.get("generate_ai_summary", True)
    body.goal_ids = overrides.get("goal_ids", [])
    body.periodicity = overrides.get("periodicity", None)
    body.force_standard_days = overrides.get("force_standard_days", None)
    body.chart_horizon = overrides.get("chart_horizon", "auto")
    body.chart_lookahead_multiplier = overrides.get("chart_lookahead_multiplier", 1.0)
    body.show_minimap = overrides.get("show_minimap", True)

    # Recipients
    r1 = MagicMock()
    r1.email = "user@example.com"
    r1.color_scheme = "dark"
    body.recipients = overrides.get("recipients", [r1])

    return body


# =============================================================================
# compute_next_run_for_new_schedule
# =============================================================================


class TestComputeNextRunForNewSchedule:
    """Tests for compute_next_run_for_new_schedule()."""

    def test_returns_datetime(self):
        """Happy path: returns a datetime from body params."""
        body = _make_body(schedule_type="daily", schedule_days=None)

        with patch(
            "app.services.report_schedule_service.compute_next_run_flexible",
            return_value=datetime(2026, 3, 1, 8, 0, 0),
        ):
            result = compute_next_run_for_new_schedule(body)

        assert isinstance(result, datetime)
        assert result == datetime(2026, 3, 1, 8, 0, 0)

    def test_weekly_schedule_with_days(self):
        """Happy path: weekly schedule with specific days."""
        body = _make_body(schedule_type="weekly", schedule_days=[0, 4])  # Mon, Fri

        with patch(
            "app.services.report_schedule_service.compute_next_run_flexible",
            return_value=datetime(2026, 3, 2, 0, 0, 0),
        ) as mock_compute:
            result = compute_next_run_for_new_schedule(body)

        assert mock_compute.called
        # The sched object should have schedule_type="weekly"
        call_args = mock_compute.call_args
        sched = call_args[0][0]
        assert sched.schedule_type == "weekly"

    def test_quarterly_schedule(self):
        """Edge case: quarterly schedule passes quarter_start_month."""
        body = _make_body(
            schedule_type="quarterly",
            quarter_start_month=1,
            schedule_days=None,
        )

        with patch(
            "app.services.report_schedule_service.compute_next_run_flexible",
            return_value=datetime(2026, 4, 1, 0, 0, 0),
        ) as mock_compute:
            result = compute_next_run_for_new_schedule(body)

        sched = mock_compute.call_args[0][0]
        assert sched.quarter_start_month == 1

    def test_trailing_lookback_schedule(self):
        """Edge case: trailing schedule with lookback value/unit."""
        body = _make_body(
            schedule_type="daily",
            period_window="trailing",
            lookback_value=7,
            lookback_unit="days",
            schedule_days=None,
        )

        with patch(
            "app.services.report_schedule_service.compute_next_run_flexible",
            return_value=datetime(2026, 3, 1, 0, 0, 0),
        ) as mock_compute:
            result = compute_next_run_for_new_schedule(body)

        sched = mock_compute.call_args[0][0]
        assert sched.lookback_value == 7
        assert sched.lookback_unit == "days"


# =============================================================================
# create_schedule_record
# =============================================================================


class TestCreateScheduleRecord:
    """Tests for create_schedule_record()."""

    @pytest.mark.asyncio
    async def test_creates_schedule_with_goals(self, db_session):
        """Happy path: creates schedule with goal links."""
        # Create a user and goal
        user = User(
            email="sched@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        goal = ReportGoal(
            user_id=user.id,
            name="Target 1 BTC",
            target_type="balance",
            target_value=1.0,
            target_currency="BTC",
            time_horizon_months=12,
            target_date=datetime(2027, 2, 28),
        )
        db_session.add(goal)
        await db_session.flush()

        body = _make_body(goal_ids=[goal.id])

        with patch(
            "app.services.report_schedule_service.compute_next_run_flexible",
            return_value=datetime(2026, 3, 5, 0, 0, 0),
        ), patch(
            "app.services.report_schedule_service.build_periodicity_label",
            return_value="Weekly on Mon",
        ):
            result = await create_schedule_record(db_session, user.id, body)

        assert result.id is not None
        assert result.user_id == user.id
        assert result.name == "Weekly Report"
        assert result.is_enabled is True
        assert len(result.goal_links) == 1

    @pytest.mark.asyncio
    async def test_invalid_goal_id_raises(self, db_session):
        """Failure: non-existent goal ID raises ValidationError."""
        user = User(
            email="sched_bad@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        body = _make_body(goal_ids=[99999])

        with patch(
            "app.services.report_schedule_service.compute_next_run_flexible",
            return_value=datetime(2026, 3, 5, 0, 0, 0),
        ), patch(
            "app.services.report_schedule_service.build_periodicity_label",
            return_value="Weekly",
        ):
            with pytest.raises(ValidationError, match="Invalid goal IDs"):
                await create_schedule_record(db_session, user.id, body)

    @pytest.mark.asyncio
    async def test_creates_schedule_without_goals(self, db_session):
        """Edge case: schedule with no goals still creates successfully."""
        user = User(
            email="sched_nogoals@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        body = _make_body(goal_ids=[])

        with patch(
            "app.services.report_schedule_service.compute_next_run_flexible",
            return_value=datetime(2026, 3, 5, 0, 0, 0),
        ), patch(
            "app.services.report_schedule_service.build_periodicity_label",
            return_value="Daily",
        ):
            result = await create_schedule_record(db_session, user.id, body)

        assert result.id is not None
        assert len(result.goal_links) == 0

    @pytest.mark.asyncio
    async def test_uses_provided_periodicity(self, db_session):
        """Edge case: when body.periodicity is set, uses it instead of computing."""
        user = User(
            email="sched_period@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        body = _make_body(goal_ids=[], periodicity="Custom Label")

        with patch(
            "app.services.report_schedule_service.compute_next_run_flexible",
            return_value=datetime(2026, 3, 5, 0, 0, 0),
        ), patch(
            "app.services.report_schedule_service.build_periodicity_label",
            return_value="Should Not Use This",
        ):
            result = await create_schedule_record(db_session, user.id, body)

        assert result.periodicity == "Custom Label"

    @pytest.mark.asyncio
    async def test_recipients_serialized_correctly(self, db_session):
        """Happy path: recipients are serialized with email + color_scheme."""
        user = User(
            email="sched_recip@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        r1 = MagicMock()
        r1.email = "a@test.com"
        r1.color_scheme = "light"
        r2 = MagicMock()
        r2.email = "b@test.com"
        r2.color_scheme = "dark"
        body = _make_body(goal_ids=[], recipients=[r1, r2])

        with patch(
            "app.services.report_schedule_service.compute_next_run_flexible",
            return_value=datetime(2026, 3, 5, 0, 0, 0),
        ), patch(
            "app.services.report_schedule_service.build_periodicity_label",
            return_value="Daily",
        ):
            result = await create_schedule_record(db_session, user.id, body)

        assert len(result.recipients) == 2
        assert result.recipients[0]["email"] == "a@test.com"
        assert result.recipients[1]["color_scheme"] == "dark"


# =============================================================================
# update_schedule_record
# =============================================================================


class TestUpdateScheduleRecord:
    """Tests for update_schedule_record()."""

    @pytest.mark.asyncio
    async def test_updates_name(self, db_session):
        """Happy path: updating name field works."""
        user = User(
            email="update_sched@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        schedule = ReportSchedule(
            user_id=user.id,
            name="Old Name",
            periodicity="Daily",
            schedule_type="daily",
            is_enabled=True,
            next_run_at=datetime(2026, 3, 1),
        )
        db_session.add(schedule)
        await db_session.flush()

        body = MagicMock()
        body.model_dump.return_value = {"name": "New Name"}

        result = await update_schedule_record(db_session, user.id, schedule.id, body)

        assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_schedule_not_found_raises(self, db_session):
        """Failure: non-existent schedule raises NotFoundError."""
        user = User(
            email="update_404@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        body = MagicMock()
        body.model_dump.return_value = {"name": "Anything"}

        with pytest.raises(NotFoundError, match="Schedule not found"):
            await update_schedule_record(db_session, user.id, 99999, body)

    @pytest.mark.asyncio
    async def test_schedule_config_change_recomputes_next_run(self, db_session):
        """Happy path: changing schedule_type recomputes next_run_at and periodicity."""
        user = User(
            email="update_recomp@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        schedule = ReportSchedule(
            user_id=user.id,
            name="Test Schedule",
            periodicity="Daily",
            schedule_type="daily",
            is_enabled=True,
            next_run_at=datetime(2026, 3, 1),
        )
        db_session.add(schedule)
        await db_session.flush()

        body = MagicMock()
        body.model_dump.return_value = {"schedule_type": "weekly"}

        with patch(
            "app.services.report_schedule_service.build_periodicity_label",
            return_value="Weekly on Mon",
        ), patch(
            "app.services.report_schedule_service.compute_next_run_flexible",
            return_value=datetime(2026, 3, 8, 0, 0, 0),
        ):
            result = await update_schedule_record(db_session, user.id, schedule.id, body)

        assert result.schedule_type == "weekly"
        assert result.periodicity == "Weekly on Mon"

    @pytest.mark.asyncio
    async def test_update_goal_ids_invalid_raises(self, db_session):
        """Failure: updating with invalid goal IDs raises ValidationError."""
        user = User(
            email="update_goals@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        schedule = ReportSchedule(
            user_id=user.id,
            name="Goal Test",
            periodicity="Daily",
            schedule_type="daily",
            is_enabled=True,
            next_run_at=datetime(2026, 3, 1),
        )
        db_session.add(schedule)
        await db_session.flush()

        body = MagicMock()
        body.model_dump.return_value = {"goal_ids": [99999]}

        with pytest.raises(ValidationError, match="Invalid goal IDs"):
            await update_schedule_record(db_session, user.id, schedule.id, body)

    @pytest.mark.asyncio
    async def test_periodicity_stripped_from_update(self, db_session):
        """Edge case: user-supplied periodicity is ignored (auto-generated)."""
        user = User(
            email="update_strip@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        schedule = ReportSchedule(
            user_id=user.id,
            name="Strip Test",
            periodicity="Daily",
            schedule_type="daily",
            is_enabled=True,
            next_run_at=datetime(2026, 3, 1),
        )
        db_session.add(schedule)
        await db_session.flush()

        body = MagicMock()
        body.model_dump.return_value = {
            "name": "Updated",
            "periodicity": "User Override Attempt",
        }

        result = await update_schedule_record(db_session, user.id, schedule.id, body)

        # Periodicity should NOT be the user-supplied value
        assert result.periodicity == "Daily"  # Original unchanged (no schedule fields changed)
