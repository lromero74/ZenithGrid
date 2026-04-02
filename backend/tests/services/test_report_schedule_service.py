"""
Tests for backend/app/services/report_schedule_service.py

Covers:
- compute_next_run_for_new_schedule: datetime computation from body params
- create_schedule_record: full schedule creation with goal links
- update_schedule_record: partial update with recomputation
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import NotFoundError, ValidationError
from app.models import ReportGoal, ReportSchedule, User
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
    body.retention_count = overrides.get("retention_count", None)
    body.retention_days = overrides.get("retention_days", None)

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
            compute_next_run_for_new_schedule(body)

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
            compute_next_run_for_new_schedule(body)

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
            compute_next_run_for_new_schedule(body)

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


# =============================================================================
# apply_retention
# =============================================================================


class TestApplyRetention:
    """TDD: apply_retention deletes old reports based on retention_count
    and retention_days. Both are optional; both null = keep all.

    Logic: a report is deleted when BOTH applicable limits are exceeded.
    If only one limit is set, that limit governs alone.
    """

    def _make_schedule(self, retention_count=None, retention_days=None):
        s = MagicMock(spec=ReportSchedule)
        s.id = 1
        s.retention_count = retention_count
        s.retention_days = retention_days
        return s

    def _make_report(self, report_id, days_old):
        from datetime import timedelta
        r = MagicMock()
        r.id = report_id
        r.created_at = datetime.utcnow() - timedelta(days=days_old)
        return r

    @pytest.mark.asyncio
    async def test_no_retention_keeps_all(self):
        """Both limits null — no deletion."""
        from app.services.report_schedule_service import apply_retention
        schedule = self._make_schedule()
        db = AsyncMock()
        deleted = await apply_retention(schedule, db)
        assert deleted == 0
        db.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_count_only_keeps_last_n(self):
        """retention_count=2 with 5 reports — oldest 3 deleted."""
        from app.services.report_schedule_service import apply_retention

        schedule = self._make_schedule(retention_count=2)
        reports = [self._make_report(i, days_old=50 - i * 5) for i in range(5)]
        # reports[0] is oldest (50 days), reports[4] is newest (30 days)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = reports
        db.execute.return_value = mock_result

        deleted = await apply_retention(schedule, db)

        assert deleted == 3
        # Should have deleted the 3 oldest (indices 0,1,2)
        assert db.delete.call_count == 3

    @pytest.mark.asyncio
    async def test_count_only_no_excess(self):
        """retention_count=10 with 3 reports — nothing deleted."""
        from app.services.report_schedule_service import apply_retention

        schedule = self._make_schedule(retention_count=10)
        reports = [self._make_report(i, days_old=10 - i) for i in range(3)]

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = reports
        db.execute.return_value = mock_result

        deleted = await apply_retention(schedule, db)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_days_only_deletes_old(self):
        """retention_days=30 — reports older than 30 days deleted."""
        from app.services.report_schedule_service import apply_retention

        schedule = self._make_schedule(retention_days=30)
        reports = [
            self._make_report(1, days_old=60),   # old — delete
            self._make_report(2, days_old=45),   # old — delete
            self._make_report(3, days_old=20),   # recent — keep
            self._make_report(4, days_old=5),    # recent — keep
        ]

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = reports
        db.execute.return_value = mock_result

        deleted = await apply_retention(schedule, db)
        assert deleted == 2

    @pytest.mark.asyncio
    async def test_both_limits_and_logic(self):
        """Both limits set: delete only when BOTH are exceeded (more permissive)."""
        from app.services.report_schedule_service import apply_retention

        # retention_count=3, retention_days=10
        # Report that exceeds count but NOT age should be kept
        # Report that exceeds age but NOT count should be kept
        # Only report that exceeds both is deleted
        schedule = self._make_schedule(retention_count=3, retention_days=10)
        reports = [
            self._make_report(1, days_old=60),   # count pos 0/4: count-exceeded; age-exceeded → DELETE
            self._make_report(2, days_old=60),   # count pos 1/4: count-exceeded; age-exceeded → DELETE
            self._make_report(3, days_old=5),    # count pos 2/4: count-exceeded; NOT age-exceeded → KEEP
            self._make_report(4, days_old=3),    # count pos 3/4: within count; NOT age-exceeded → KEEP
            self._make_report(5, days_old=1),    # newest: within count; NOT age-exceeded → KEEP
        ]
        # With count=3 and 5 reports: positions 0,1 exceed count (keep last 3 = positions 2,3,4)
        # Reports 0,1 are >10 days old AND exceed count → BOTH exceeded → DELETE
        # Report 2 exceeds count but is only 5 days old → NOT both → KEEP

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = reports
        db.execute.return_value = mock_result

        deleted = await apply_retention(schedule, db)
        assert deleted == 2   # only reports[0] and reports[1]

    @pytest.mark.asyncio
    async def test_empty_reports_no_error(self):
        """Edge case: no reports at all — no crash, 0 deleted."""
        from app.services.report_schedule_service import apply_retention
        schedule = self._make_schedule(retention_count=5)
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result
        deleted = await apply_retention(schedule, db)
        assert deleted == 0
