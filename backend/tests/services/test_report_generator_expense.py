"""
Tests for biweekly and every_n_days due date helpers in report_generator_service.
"""

from datetime import datetime

from app.services.report_generator_service import (
    _get_upcoming_items,
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


class TestGetUpcomingItems:
    """Tests for _get_upcoming_items shared helper."""

    def test_weekly_this_month_only(self):
        """Weekly item whose next occurrence is next month should be excluded."""
        # Feb 28, 2026 is a Saturday. Sunday (dow=6) is March 1 → excluded.
        items = [{"due_day": 6, "frequency": "weekly"}]
        result = _get_upcoming_items(items, datetime(2026, 2, 28))
        assert len(result) == 0

    def test_weekly_still_in_month(self):
        """Weekly item whose next occurrence is still this month → included."""
        # Feb 23, 2026 is Monday. Friday (dow=4) is Feb 27 → included.
        items = [{"due_day": 4, "frequency": "weekly", "name": "Groceries"}]
        result = _get_upcoming_items(items, datetime(2026, 2, 23))
        assert len(result) == 1
        assert result[0][1]["name"] == "Groceries"

    def test_biweekly_next_month_excluded(self):
        """Biweekly item landing in next month should be excluded."""
        # anchor=2/20, dow=4 (Fri), today=2/23 → next biweekly = 3/6 → excluded
        items = [{
            "due_day": 4, "frequency": "biweekly",
            "frequency_anchor": "2026-02-20",
        }]
        result = _get_upcoming_items(items, datetime(2026, 2, 23))
        assert len(result) == 0

    def test_biweekly_this_month_included(self):
        """Biweekly item landing this month → included."""
        # anchor=2/27, dow=4 (Fri), today=2/23 → next = 2/27 → included
        items = [{
            "due_day": 4, "frequency": "biweekly",
            "frequency_anchor": "2026-02-27", "name": "Paycheck",
        }]
        result = _get_upcoming_items(items, datetime(2026, 2, 23))
        assert len(result) == 1

    def test_every_n_days_next_month_excluded(self):
        """every_n_days item landing in next month should be excluded."""
        # anchor=2/15, n=10, today=2/26 → next=3/7 → excluded
        items = [{
            "due_day": None, "frequency": "every_n_days",
            "frequency_anchor": "2026-02-15", "frequency_n": 10,
        }]
        result = _get_upcoming_items(items, datetime(2026, 2, 26))
        assert len(result) == 0

    def test_every_n_days_this_month_included(self):
        """every_n_days item landing this month → included."""
        # anchor=2/15, n=10, today=2/23 → next=2/25 → included
        items = [{
            "due_day": None, "frequency": "every_n_days",
            "frequency_anchor": "2026-02-15", "frequency_n": 10,
            "name": "Custom",
        }]
        result = _get_upcoming_items(items, datetime(2026, 2, 23))
        assert len(result) == 1

    def test_monthly_past_day_excluded(self):
        """Monthly item whose due day already passed → excluded."""
        items = [{"due_day": 5, "frequency": "monthly"}]
        result = _get_upcoming_items(items, datetime(2026, 2, 23))
        assert len(result) == 0

    def test_monthly_future_day_included(self):
        """Monthly item with due day still ahead → included."""
        items = [{"due_day": 28, "frequency": "monthly", "name": "Rent"}]
        result = _get_upcoming_items(items, datetime(2026, 2, 23))
        assert len(result) == 1

    def test_sorted_by_sort_key(self):
        """Results should be sorted by days-until / resolved day."""
        items = [
            {"due_day": 28, "frequency": "monthly", "name": "Late"},
            {"due_day": 25, "frequency": "monthly", "name": "Early"},
        ]
        result = _get_upcoming_items(items, datetime(2026, 2, 23))
        names = [item["name"] for _, item in result]
        assert names == ["Early", "Late"]
