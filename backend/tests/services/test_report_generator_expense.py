"""
Tests for biweekly and every_n_days due date helpers in report_generator_service.
"""

from datetime import datetime

from app.services.report_generator_service import (
    _next_biweekly_date,
    _next_every_n_days_date,
    _format_due_label,
)


class TestNextBiweeklyDate:
    """Tests for _next_biweekly_date helper."""

    def test_off_week_pushes_7_days(self):
        """anchor=2/20 (Thu), today=2/23 (Mon), dow=4 (Fri) → 3/6 (off-week Thu+1)."""
        # 2026-02-20 is a Friday, 2026-02-23 is a Monday
        result = _next_biweekly_date("2026-02-20", 4, datetime(2026, 2, 23))
        assert result == datetime(2026, 3, 6)

    def test_on_week_returns_this_week(self):
        """anchor=2/27 (Fri), today=2/23 (Mon), dow=4 (Fri) → 2/27 (on-week)."""
        result = _next_biweekly_date("2026-02-27", 4, datetime(2026, 2, 23))
        assert result == datetime(2026, 2, 27)

    def test_anchor_in_future_returns_anchor(self):
        """If anchor hasn't started yet, return anchor date."""
        result = _next_biweekly_date("2026-03-10", 1, datetime(2026, 2, 23))
        assert result == datetime(2026, 3, 10)

    def test_today_is_due_day_on_week(self):
        """Today IS the due day and it's an on-week → returns today."""
        # anchor=2/20 (Fri), today=3/6 (Fri) → 14 days later, on-week
        result = _next_biweekly_date("2026-02-20", 4, datetime(2026, 3, 6))
        assert result == datetime(2026, 3, 6)

    def test_today_is_due_day_off_week(self):
        """Today IS the due day but off-week → returns today+7."""
        # anchor=2/20 (Fri), today=2/27 (Fri) → 7 days later, off-week
        result = _next_biweekly_date("2026-02-20", 4, datetime(2026, 2, 27))
        assert result == datetime(2026, 3, 6)

    def test_same_day_as_anchor(self):
        """today == anchor → returns anchor (on-week, 0 weeks diff)."""
        result = _next_biweekly_date("2026-02-20", 4, datetime(2026, 2, 20))
        assert result == datetime(2026, 2, 20)


class TestNextEveryNDaysDate:
    """Tests for _next_every_n_days_date helper."""

    def test_mid_cycle(self):
        """anchor=2/15, n=10, today=2/23 → next=2/25 (10 days after anchor)."""
        result = _next_every_n_days_date("2026-02-15", 10, datetime(2026, 2, 23))
        assert result == datetime(2026, 2, 25)

    def test_exactly_on_due(self):
        """anchor=2/15, n=10, today=2/25 → returns 2/25 (exactly on due)."""
        result = _next_every_n_days_date("2026-02-15", 10, datetime(2026, 2, 25))
        assert result == datetime(2026, 2, 25)

    def test_anchor_in_future(self):
        """anchor in the future → returns anchor date."""
        result = _next_every_n_days_date("2026-03-10", 10, datetime(2026, 2, 23))
        assert result == datetime(2026, 3, 10)

    def test_daily_returns_today(self):
        """n=1 → returns today (daily)."""
        result = _next_every_n_days_date("2026-02-01", 1, datetime(2026, 2, 23))
        assert result == datetime(2026, 2, 23)

    def test_on_anchor_day(self):
        """today == anchor → returns anchor."""
        result = _next_every_n_days_date("2026-02-23", 7, datetime(2026, 2, 23))
        assert result == datetime(2026, 2, 23)

    def test_just_past_due(self):
        """anchor=2/15, n=10, today=2/26 → next=3/7 (20 days after anchor)."""
        result = _next_every_n_days_date("2026-02-15", 10, datetime(2026, 2, 26))
        assert result == datetime(2026, 3, 7)


class TestFormatDueLabelAnchored:
    """Tests for _format_due_label with anchor-based frequencies."""

    def test_biweekly_with_anchor(self):
        """biweekly with anchor computes correct date."""
        item = {
            "due_day": 4, "frequency": "biweekly",
            "frequency_anchor": "2026-02-20", "frequency_n": None,
        }
        label = _format_due_label(item, now=datetime(2026, 2, 23))
        assert label == "Fri Mar 6th"  # 3/6 is a Friday, day 6

    def test_biweekly_without_anchor_falls_back(self):
        """biweekly without anchor falls back to weekly-style calc."""
        item = {"due_day": 4, "frequency": "biweekly"}
        label = _format_due_label(item, now=datetime(2026, 2, 23))
        # Should still produce a label (fallback behavior)
        assert "Fri" in label

    def test_every_n_days_with_anchor(self):
        """every_n_days with anchor+n computes correct date."""
        item = {
            "due_day": None, "frequency": "every_n_days",
            "frequency_anchor": "2026-02-15", "frequency_n": 10,
        }
        label = _format_due_label(item, now=datetime(2026, 2, 23))
        assert label == "Feb 25th"  # Next due 2/25

    def test_every_n_days_without_anchor_returns_empty(self):
        """every_n_days without anchor returns empty string."""
        item = {"due_day": None, "frequency": "every_n_days"}
        label = _format_due_label(item, now=datetime(2026, 2, 23))
        assert label == ""
