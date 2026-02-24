"""
Tests for backend/app/services/report_scheduler.py

Covers:
- compute_next_run_flexible: next-run calculation for all schedule types
- compute_period_bounds_flexible: period window computation
- _compute_full_prior_bounds: full prior period bounds
- _compute_next_run_legacy / _compute_period_bounds_legacy: legacy functions
- _normalize_recipient: email extraction from various formats
- _format_period_label: human-readable date range labels
- build_periodicity_label: schedule description strings
- _ordinal: ordinal number formatting
- _should_auto_prior: auto-switch to full prior on period-start days
- Helper functions: _parse_schedule_days, _at_run_time, etc.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.services.report_scheduler import (
    compute_next_run_flexible,
    compute_period_bounds_flexible,
    compute_next_run_at,
    compute_period_bounds,
    build_periodicity_label,
    _normalize_recipient,
    _format_period_label,
    _ordinal,
    _parse_schedule_days,
    _at_run_time,
    _last_day_of_month,
    _resolve_day_of_month,
    _compute_full_prior_bounds,
    _should_auto_prior,
    _compute_next_run_legacy,
    _compute_period_bounds_legacy,
    RUN_HOUR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_schedule(**kwargs):
    """Create a mock ReportSchedule with defaults."""
    sched = MagicMock()
    sched.schedule_type = kwargs.get("schedule_type", "weekly")
    sched.schedule_days = kwargs.get("schedule_days", None)
    sched.quarter_start_month = kwargs.get("quarter_start_month", None)
    sched.period_window = kwargs.get("period_window", "full_prior")
    sched.lookback_value = kwargs.get("lookback_value", None)
    sched.lookback_unit = kwargs.get("lookback_unit", None)
    sched.force_standard_days = kwargs.get("force_standard_days", None)
    sched.periodicity = kwargs.get("periodicity", "weekly")
    return sched


# ===========================================================================
# Tests for small helper functions
# ===========================================================================


class TestHelperFunctions:
    """Tests for small utility functions."""

    def test_at_run_time_sets_hour(self):
        """Happy path: sets hour to RUN_HOUR, zeroes minutes/seconds."""
        dt = datetime(2025, 3, 15, 14, 30, 45, 123456)
        result = _at_run_time(dt)
        assert result.hour == RUN_HOUR
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0
        assert result.day == 15

    def test_last_day_of_month_feb_leap(self):
        """Edge case: February in a leap year."""
        assert _last_day_of_month(2024, 2) == 29

    def test_last_day_of_month_feb_non_leap(self):
        """Edge case: February in a non-leap year."""
        assert _last_day_of_month(2025, 2) == 28

    def test_last_day_of_month_december(self):
        """Happy path: December has 31 days."""
        assert _last_day_of_month(2025, 12) == 31

    def test_resolve_day_of_month_last_day(self):
        """Happy path: -1 resolves to last day of month."""
        assert _resolve_day_of_month(-1, 2025, 2) == 28
        assert _resolve_day_of_month(-1, 2025, 3) == 31

    def test_resolve_day_of_month_clamps(self):
        """Edge case: day 31 clamped to actual last day."""
        assert _resolve_day_of_month(31, 2025, 4) == 30  # April has 30 days

    def test_resolve_day_of_month_normal(self):
        """Happy path: normal day within range."""
        assert _resolve_day_of_month(15, 2025, 1) == 15

    def test_parse_schedule_days_valid_json(self):
        """Happy path: parses JSON array of ints."""
        sched = _make_schedule(schedule_days='[0, 2, 4]')
        result = _parse_schedule_days(sched)
        assert result == [0, 2, 4]

    def test_parse_schedule_days_none(self):
        """Edge case: None schedule_days returns None."""
        sched = _make_schedule(schedule_days=None)
        assert _parse_schedule_days(sched) is None

    def test_parse_schedule_days_invalid_json(self):
        """Failure: invalid JSON returns None."""
        sched = _make_schedule(schedule_days='not json')
        assert _parse_schedule_days(sched) is None

    def test_parse_schedule_days_non_list(self):
        """Edge case: JSON that's not a list returns None."""
        sched = _make_schedule(schedule_days='42')
        assert _parse_schedule_days(sched) is None


# ===========================================================================
# Tests for _normalize_recipient
# ===========================================================================


class TestNormalizeRecipient:
    """Tests for _normalize_recipient()."""

    def test_plain_string_returned_as_is(self):
        """Happy path: plain string email."""
        assert _normalize_recipient("user@example.com") == "user@example.com"

    def test_dict_with_email_key(self):
        """Happy path: dict format extracts email."""
        result = _normalize_recipient({"email": "user@example.com", "level": "simple"})
        assert result == "user@example.com"

    def test_non_string_converted(self):
        """Edge case: non-string coerced via str()."""
        assert _normalize_recipient(42) == "42"


# ===========================================================================
# Tests for _ordinal
# ===========================================================================


class TestOrdinal:
    """Tests for _ordinal() number formatting."""

    def test_basic_ordinals(self):
        """Happy path: 1st, 2nd, 3rd, 4th."""
        assert _ordinal(1) == "1st"
        assert _ordinal(2) == "2nd"
        assert _ordinal(3) == "3rd"
        assert _ordinal(4) == "4th"

    def test_teens_all_th(self):
        """Edge case: 11th, 12th, 13th (not 11st, 12nd, 13rd)."""
        assert _ordinal(11) == "11th"
        assert _ordinal(12) == "12th"
        assert _ordinal(13) == "13th"

    def test_higher_ordinals(self):
        """21st, 22nd, 23rd, 31st."""
        assert _ordinal(21) == "21st"
        assert _ordinal(22) == "22nd"
        assert _ordinal(23) == "23rd"
        assert _ordinal(31) == "31st"


# ===========================================================================
# Tests for _format_period_label
# ===========================================================================


class TestFormatPeriodLabel:
    """Tests for _format_period_label()."""

    def test_same_year_same_month(self):
        """Happy path: both dates in same month."""
        result = _format_period_label(
            datetime(2025, 1, 1), datetime(2025, 1, 31),
        )
        assert "January 01" in result
        assert "31, 2025" in result

    def test_same_year_different_month(self):
        """Happy path: same year, different months."""
        result = _format_period_label(
            datetime(2025, 1, 1), datetime(2025, 3, 15),
        )
        assert "January 01" in result
        assert "March 15, 2025" in result

    def test_different_years(self):
        """Edge case: spans year boundary."""
        result = _format_period_label(
            datetime(2024, 12, 1), datetime(2025, 1, 31),
        )
        assert "2024" in result
        assert "2025" in result


# ===========================================================================
# Tests for compute_next_run_flexible
# ===========================================================================


class TestComputeNextRunFlexible:
    """Tests for compute_next_run_flexible()."""

    def test_daily_next_day(self):
        """Happy path: daily schedule returns next day at RUN_HOUR."""
        sched = _make_schedule(schedule_type="daily")
        after = datetime(2025, 3, 15, 10, 0, 0)
        result = compute_next_run_flexible(sched, after)
        assert result == datetime(2025, 3, 16, RUN_HOUR, 0, 0)

    def test_weekly_next_matching_day(self):
        """Happy path: weekly picks next matching weekday."""
        # 2025-03-15 is Saturday (weekday=5), schedule days = [0] (Monday)
        sched = _make_schedule(schedule_type="weekly", schedule_days='[0]')
        after = datetime(2025, 3, 15, 10, 0, 0)
        result = compute_next_run_flexible(sched, after)
        # Next Monday is 2025-03-17
        assert result.weekday() == 0
        assert result.date() == datetime(2025, 3, 17).date()
        assert result.hour == RUN_HOUR

    def test_weekly_multiple_days(self):
        """Happy path: weekly with Mon+Wed picks next match."""
        # 2025-03-17 is Monday, after Mon => next match is Wed (day 2)
        sched = _make_schedule(schedule_type="weekly", schedule_days='[0, 2]')
        after = datetime(2025, 3, 17, 10, 0, 0)
        result = compute_next_run_flexible(sched, after)
        assert result.weekday() == 2  # Wednesday
        assert result.date() == datetime(2025, 3, 19).date()

    def test_weekly_default_monday(self):
        """Edge case: no schedule_days defaults to Monday."""
        sched = _make_schedule(schedule_type="weekly", schedule_days=None)
        # 2025-03-18 is Tuesday
        after = datetime(2025, 3, 18, 10, 0, 0)
        result = compute_next_run_flexible(sched, after)
        assert result.weekday() == 0  # Monday
        assert result.date() == datetime(2025, 3, 24).date()

    def test_monthly_next_day_of_month(self):
        """Happy path: monthly on 15th, after the 10th => same month 15th."""
        sched = _make_schedule(schedule_type="monthly", schedule_days='[15]')
        after = datetime(2025, 3, 10, 10, 0, 0)
        result = compute_next_run_flexible(sched, after)
        assert result.day == 15
        assert result.month == 3
        assert result.hour == RUN_HOUR

    def test_monthly_wraps_to_next_month(self):
        """Edge case: past the day this month, wraps to next month."""
        sched = _make_schedule(schedule_type="monthly", schedule_days='[5]')
        after = datetime(2025, 3, 10, 10, 0, 0)
        result = compute_next_run_flexible(sched, after)
        assert result.day == 5
        assert result.month == 4

    def test_monthly_last_day(self):
        """Edge case: day -1 resolves to last day of month."""
        sched = _make_schedule(schedule_type="monthly", schedule_days='[-1]')
        after = datetime(2025, 2, 1, 10, 0, 0)
        result = compute_next_run_flexible(sched, after)
        assert result.day == 28  # Feb 2025 (non-leap)
        assert result.month == 2

    def test_quarterly_next_quarter(self):
        """Happy path: quarterly from Jan, day 1."""
        sched = _make_schedule(
            schedule_type="quarterly",
            schedule_days='[1]',
            quarter_start_month=1,
        )
        after = datetime(2025, 1, 15, 10, 0, 0)
        result = compute_next_run_flexible(sched, after)
        # Q months: 1, 4, 7, 10 — next after Jan 15 is Apr 1
        assert result.month == 4
        assert result.day == 1
        assert result.hour == RUN_HOUR

    def test_yearly_next_year(self):
        """Happy path: yearly on Jun 15, after Jun 15 => next year."""
        sched = _make_schedule(
            schedule_type="yearly", schedule_days='[6, 15]',
        )
        after = datetime(2025, 6, 15, 10, 0, 0)
        result = compute_next_run_flexible(sched, after)
        assert result.year == 2026
        assert result.month == 6
        assert result.day == 15

    def test_yearly_same_year(self):
        """Happy path: yearly on Jun 15, before Jun 15 => same year."""
        sched = _make_schedule(
            schedule_type="yearly", schedule_days='[6, 15]',
        )
        after = datetime(2025, 3, 1, 10, 0, 0)
        result = compute_next_run_flexible(sched, after)
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 15

    def test_unknown_type_fallback(self):
        """Failure: unknown schedule type falls back to 7-day offset."""
        sched = _make_schedule(schedule_type="bogus")
        after = datetime(2025, 3, 15, 10, 0, 0)
        result = compute_next_run_flexible(sched, after)
        assert result == _at_run_time(after + timedelta(days=7))


# ===========================================================================
# Tests for compute_period_bounds_flexible
# ===========================================================================


class TestComputePeriodBoundsFlexible:
    """Tests for compute_period_bounds_flexible()."""

    def test_full_prior_weekly(self):
        """Happy path: full_prior weekly returns last Mon-Sun."""
        sched = _make_schedule(
            schedule_type="weekly", period_window="full_prior",
        )
        # 2025-03-17 is Monday
        run_at = datetime(2025, 3, 17, 10, 0, 0)
        start, end = compute_period_bounds_flexible(sched, run_at)
        # Prior week: Mon 3/10 to Sun 3/16 (midnight)
        assert start == datetime(2025, 3, 10, 0, 0, 0)
        assert end == datetime(2025, 3, 17, 0, 0, 0)

    def test_full_prior_monthly(self):
        """Happy path: full_prior monthly returns prior calendar month."""
        sched = _make_schedule(
            schedule_type="monthly", period_window="full_prior",
        )
        run_at = datetime(2025, 3, 1, 10, 0, 0)
        start, end = compute_period_bounds_flexible(sched, run_at)
        assert start == datetime(2025, 2, 1, 0, 0, 0)
        assert end == datetime(2025, 3, 1, 0, 0, 0)

    def test_wtd_window(self):
        """Happy path: week-to-date from Monday to run_at."""
        sched = _make_schedule(
            schedule_type="weekly", period_window="wtd",
        )
        # 2025-03-19 is Wednesday (weekday=2)
        run_at = datetime(2025, 3, 19, 10, 0, 0)
        start, end = compute_period_bounds_flexible(sched, run_at)
        assert start == datetime(2025, 3, 17, 0, 0, 0)  # Monday
        assert end == datetime(2025, 3, 19, 0, 0, 0)

    def test_mtd_window(self):
        """Happy path: month-to-date from 1st to run_at."""
        sched = _make_schedule(
            schedule_type="monthly", period_window="mtd",
        )
        run_at = datetime(2025, 3, 15, 10, 0, 0)
        start, end = compute_period_bounds_flexible(sched, run_at)
        assert start == datetime(2025, 3, 1, 0, 0, 0)
        assert end == datetime(2025, 3, 15, 0, 0, 0)

    def test_ytd_window(self):
        """Happy path: year-to-date from Jan 1 to run_at."""
        sched = _make_schedule(
            schedule_type="monthly", period_window="ytd",
        )
        run_at = datetime(2025, 6, 15, 10, 0, 0)
        start, end = compute_period_bounds_flexible(sched, run_at)
        assert start == datetime(2025, 1, 1, 0, 0, 0)
        assert end == datetime(2025, 6, 15, 0, 0, 0)

    def test_trailing_days(self):
        """Happy path: trailing 7 days."""
        sched = _make_schedule(
            schedule_type="weekly", period_window="trailing",
            lookback_value=7, lookback_unit="days",
        )
        run_at = datetime(2025, 3, 15, 10, 0, 0)
        start, end = compute_period_bounds_flexible(sched, run_at)
        assert end == datetime(2025, 3, 15, 0, 0, 0)
        assert start == datetime(2025, 3, 8, 0, 0, 0)

    def test_trailing_months(self):
        """Happy path: trailing 3 months."""
        sched = _make_schedule(
            schedule_type="monthly", period_window="trailing",
            lookback_value=3, lookback_unit="months",
        )
        run_at = datetime(2025, 6, 15, 10, 0, 0)
        start, end = compute_period_bounds_flexible(sched, run_at)
        assert end == datetime(2025, 6, 15, 0, 0, 0)
        assert start == datetime(2025, 3, 15, 0, 0, 0)

    def test_qtd_window(self):
        """Happy path: quarter-to-date."""
        sched = _make_schedule(
            schedule_type="quarterly", period_window="qtd",
            quarter_start_month=1,
        )
        run_at = datetime(2025, 5, 15, 10, 0, 0)
        start, end = compute_period_bounds_flexible(sched, run_at)
        # Q starts: 1, 4, 7, 10 — most recent <= May is April
        assert start == datetime(2025, 4, 1, 0, 0, 0)
        assert end == datetime(2025, 5, 15, 0, 0, 0)

    def test_full_prior_daily(self):
        """Happy path: full_prior daily = yesterday."""
        sched = _make_schedule(
            schedule_type="daily", period_window="full_prior",
        )
        run_at = datetime(2025, 3, 15, 10, 0, 0)
        start, end = compute_period_bounds_flexible(sched, run_at)
        assert start == datetime(2025, 3, 14, 0, 0, 0)
        assert end == datetime(2025, 3, 15, 0, 0, 0)

    def test_full_prior_yearly(self):
        """Happy path: full_prior yearly = prior calendar year."""
        sched = _make_schedule(
            schedule_type="yearly", period_window="full_prior",
        )
        run_at = datetime(2025, 3, 15, 10, 0, 0)
        start, end = compute_period_bounds_flexible(sched, run_at)
        assert start == datetime(2024, 1, 1, 0, 0, 0)
        assert end == datetime(2025, 1, 1, 0, 0, 0)


# ===========================================================================
# Tests for _should_auto_prior
# ===========================================================================


class TestShouldAutoPrior:
    """Tests for _should_auto_prior() auto-switch logic."""

    def test_mtd_on_first_of_month_auto_switches(self):
        """Happy path: MTD on day 1 => auto-prior."""
        sched = _make_schedule(
            schedule_type="monthly", period_window="mtd",
            force_standard_days=None,
        )
        period_end = datetime(2025, 3, 1, 0, 0, 0)
        assert _should_auto_prior(sched, "mtd", period_end) is True

    def test_mtd_on_mid_month_no_switch(self):
        """Edge case: MTD on day 15 => no auto-prior."""
        sched = _make_schedule(schedule_type="monthly")
        period_end = datetime(2025, 3, 15, 0, 0, 0)
        assert _should_auto_prior(sched, "mtd", period_end) is False

    def test_wtd_on_monday_auto_switches(self):
        """Happy path: WTD on Monday => auto-prior."""
        sched = _make_schedule(
            schedule_type="weekly", period_window="wtd",
            force_standard_days=None,
        )
        # 2025-03-17 is Monday
        period_end = datetime(2025, 3, 17, 0, 0, 0)
        assert _should_auto_prior(sched, "wtd", period_end) is True

    def test_force_standard_overrides_auto_prior(self):
        """Edge case: force_standard_days prevents auto-prior."""
        sched = _make_schedule(
            schedule_type="monthly", period_window="mtd",
            force_standard_days='[1]',
        )
        period_end = datetime(2025, 3, 1, 0, 0, 0)
        assert _should_auto_prior(sched, "mtd", period_end) is False

    def test_non_period_start_window(self):
        """Edge case: full_prior window doesn't trigger auto-prior."""
        sched = _make_schedule(schedule_type="monthly")
        period_end = datetime(2025, 3, 1, 0, 0, 0)
        assert _should_auto_prior(sched, "full_prior", period_end) is False


# ===========================================================================
# Tests for _compute_full_prior_bounds
# ===========================================================================


class TestComputeFullPriorBounds:
    """Tests for _compute_full_prior_bounds()."""

    def test_quarterly_bounds(self):
        """Happy path: full prior quarter."""
        sched = _make_schedule(quarter_start_month=1)
        # Run in April => prior quarter is Jan 1 - Apr 1
        period_end = datetime(2025, 4, 15, 0, 0, 0)
        start, end = _compute_full_prior_bounds("quarterly", period_end, sched)
        assert start == datetime(2025, 1, 1, 0, 0, 0)
        assert end == datetime(2025, 4, 1, 0, 0, 0)

    def test_unknown_type_fallback(self):
        """Failure: unknown type falls back to 7-day window."""
        sched = _make_schedule()
        period_end = datetime(2025, 3, 15, 0, 0, 0)
        start, end = _compute_full_prior_bounds("bogus", period_end, sched)
        assert start == datetime(2025, 3, 8, 0, 0, 0)
        assert end == datetime(2025, 3, 15, 0, 0, 0)


# ===========================================================================
# Tests for legacy functions
# ===========================================================================


class TestLegacyComputeNextRun:
    """Tests for _compute_next_run_legacy()."""

    def test_daily(self):
        """Happy path: daily advances by 1 day."""
        last = datetime(2025, 3, 15, 6, 0, 0)
        result = _compute_next_run_legacy("daily", last)
        assert result == datetime(2025, 3, 16, 6, 0, 0)

    def test_weekly(self):
        """Happy path: weekly advances to next Monday."""
        # 2025-03-15 is Saturday (weekday=5)
        last = datetime(2025, 3, 15, 6, 0, 0)
        result = _compute_next_run_legacy("weekly", last)
        assert result.weekday() == 0  # Monday
        assert result >= last

    def test_monthly_wraps_year(self):
        """Edge case: monthly from December wraps to next year Jan."""
        last = datetime(2025, 12, 15, 6, 0, 0)
        result = _compute_next_run_legacy("monthly", last)
        assert result == datetime(2026, 1, 1, 6, 0, 0)

    def test_monthly_normal(self):
        """Happy path: monthly from March to April."""
        last = datetime(2025, 3, 15, 6, 0, 0)
        result = _compute_next_run_legacy("monthly", last)
        assert result == datetime(2025, 4, 1, 6, 0, 0)

    def test_quarterly(self):
        """Happy path: quarterly from Feb => April."""
        last = datetime(2025, 2, 15, 6, 0, 0)
        result = _compute_next_run_legacy("quarterly", last)
        assert result == datetime(2025, 4, 1, 6, 0, 0)

    def test_quarterly_wraps_year(self):
        """Edge case: quarterly from Nov => next year Jan."""
        last = datetime(2025, 11, 15, 6, 0, 0)
        result = _compute_next_run_legacy("quarterly", last)
        assert result == datetime(2026, 1, 1, 6, 0, 0)

    def test_yearly(self):
        """Happy path: yearly advances to next Jan 1."""
        last = datetime(2025, 6, 15, 6, 0, 0)
        result = _compute_next_run_legacy("yearly", last)
        assert result == datetime(2026, 1, 1, 6, 0, 0)

    def test_biweekly(self):
        """Happy path: biweekly advances by ~14 days."""
        last = datetime(2025, 3, 1, 6, 0, 0)
        result = _compute_next_run_legacy("biweekly", last)
        assert result >= last + timedelta(days=7)
        assert result.hour == 6

    def test_unknown_fallback(self):
        """Failure: unknown periodicity falls back to 7 days."""
        last = datetime(2025, 3, 15, 6, 0, 0)
        result = _compute_next_run_legacy("bogus", last)
        assert result == last + timedelta(days=7)


class TestLegacyComputePeriodBounds:
    """Tests for _compute_period_bounds_legacy()."""

    def test_daily_period(self):
        """Happy path: daily = yesterday to today."""
        run_at = datetime(2025, 3, 15, 10, 0, 0)
        start, end = _compute_period_bounds_legacy("daily", run_at)
        assert start == datetime(2025, 3, 14, 0, 0, 0)
        assert end == datetime(2025, 3, 15, 0, 0, 0)

    def test_weekly_period(self):
        """Happy path: weekly = 7-day lookback."""
        run_at = datetime(2025, 3, 15, 10, 0, 0)
        start, end = _compute_period_bounds_legacy("weekly", run_at)
        assert (end - start).days == 7

    def test_monthly_period(self):
        """Happy path: monthly = prior calendar month."""
        run_at = datetime(2025, 3, 15, 10, 0, 0)
        start, end = _compute_period_bounds_legacy("monthly", run_at)
        assert start == datetime(2025, 2, 1, 0, 0, 0)
        assert end == datetime(2025, 3, 1, 0, 0, 0)

    def test_quarterly_period(self):
        """Happy path: quarterly = 3-month lookback from month start."""
        run_at = datetime(2025, 6, 15, 10, 0, 0)
        start, end = _compute_period_bounds_legacy("quarterly", run_at)
        assert end == datetime(2025, 6, 1, 0, 0, 0)
        assert start == datetime(2025, 3, 1, 0, 0, 0)

    def test_quarterly_wraps_year(self):
        """Edge case: quarterly from Jan-Mar wraps to prior year."""
        run_at = datetime(2025, 2, 15, 10, 0, 0)
        start, end = _compute_period_bounds_legacy("quarterly", run_at)
        assert end == datetime(2025, 2, 1, 0, 0, 0)
        assert start.year == 2024

    def test_yearly_period(self):
        """Happy path: yearly = prior calendar year."""
        run_at = datetime(2025, 6, 15, 10, 0, 0)
        start, end = _compute_period_bounds_legacy("yearly", run_at)
        assert start == datetime(2024, 1, 1, 0, 0, 0)
        assert end == datetime(2025, 1, 1, 0, 0, 0)

    def test_unknown_fallback(self):
        """Failure: unknown periodicity = 7-day lookback from run_at."""
        run_at = datetime(2025, 3, 15, 10, 0, 0)
        start, end = _compute_period_bounds_legacy("bogus", run_at)
        assert end == run_at
        assert start == run_at - timedelta(days=7)


# ===========================================================================
# Tests for public aliases
# ===========================================================================


class TestPublicAliases:
    """Tests for compute_next_run_at and compute_period_bounds aliases."""

    def test_compute_next_run_at_delegates(self):
        """Verify public alias delegates to legacy."""
        last = datetime(2025, 3, 15, 6, 0, 0)
        result = compute_next_run_at("daily", last)
        expected = _compute_next_run_legacy("daily", last)
        assert result == expected

    def test_compute_period_bounds_delegates(self):
        """Verify public alias delegates to legacy."""
        run_at = datetime(2025, 3, 15, 10, 0, 0)
        result = compute_period_bounds("weekly", run_at)
        expected = _compute_period_bounds_legacy("weekly", run_at)
        assert result == expected


# ===========================================================================
# Tests for build_periodicity_label
# ===========================================================================


class TestBuildPeriodicityLabel:
    """Tests for build_periodicity_label()."""

    def test_daily_full_prior(self):
        """Happy path: daily schedule with full_prior window."""
        result = build_periodicity_label(
            "daily", None, None, "full_prior", None, None,
        )
        assert result == "Daily - full prior period"

    def test_weekly_with_days(self):
        """Happy path: weekly with specific weekdays."""
        result = build_periodicity_label(
            "weekly", '[0, 2, 4]', None, "full_prior", None, None,
        )
        assert "Mon" in result
        assert "Wed" in result
        assert "Fri" in result

    def test_monthly_with_ordinal_days(self):
        """Happy path: monthly on 1st and 15th."""
        result = build_periodicity_label(
            "monthly", '[1, 15]', None, "mtd", None, None,
        )
        assert "1st" in result
        assert "15th" in result

    def test_monthly_with_last_day(self):
        """Edge case: monthly on last day of month."""
        result = build_periodicity_label(
            "monthly", '[-1]', None, "full_prior", None, None,
        )
        assert "last" in result

    def test_quarterly_label(self):
        """Happy path: quarterly from Feb."""
        result = build_periodicity_label(
            "quarterly", '[1]', 2, "full_prior", None, None,
        )
        assert "Quarterly" in result
        assert "Feb" in result

    def test_yearly_label(self):
        """Happy path: yearly on Jun 15."""
        result = build_periodicity_label(
            "yearly", '[6, 15]', None, "full_prior", None, None,
        )
        assert "Jun" in result
        assert "15" in result

    def test_trailing_window(self):
        """Happy path: trailing 30 days."""
        result = build_periodicity_label(
            "daily", None, None, "trailing", 30, "days",
        )
        assert "trailing 30d" in result

    def test_trailing_months(self):
        """Happy path: trailing 3 months."""
        result = build_periodicity_label(
            "monthly", '[1]', None, "trailing", 3, "months",
        )
        assert "trailing 3mo" in result

    def test_wrap_up_annotation_mtd_day1(self):
        """Edge case: MTD monthly on 1st gets (wrap-up) annotation."""
        result = build_periodicity_label(
            "monthly", '[1, 15]', None, "mtd", None, None,
        )
        assert "(wrap-up)" in result

    def test_force_standard_prevents_wrap_up(self):
        """Edge case: force_standard_days suppresses wrap-up label."""
        result = build_periodicity_label(
            "monthly", '[1, 15]', None, "mtd", None, None,
            force_standard_days='[1]',
        )
        assert "(wrap-up)" not in result

    def test_unknown_schedule_type(self):
        """Failure: unknown type is capitalized."""
        result = build_periodicity_label(
            "custom_thing", None, None, "full_prior", None, None,
        )
        assert "Custom_thing" in result

    def test_no_schedule_type(self):
        """Failure: None schedule type shows 'Custom'."""
        result = build_periodicity_label(
            None, None, None, "full_prior", None, None,
        )
        assert "Custom" in result
