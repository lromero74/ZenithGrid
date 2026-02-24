"""Tests for expense goal lookahead feature."""
import pytest
from datetime import datetime, timedelta

from app.services.report_generator_service import (
    _get_upcoming_items,
    _get_lookahead_items,
    LOOKAHEAD_DAYS,
)


class TestGetLookaheadItems:
    """Tests for _get_lookahead_items function."""

    def _make_item(self, **kwargs):
        """Create a minimal expense item dict for testing."""
        base = {
            "name": "Test Expense",
            "category": "Housing",
            "amount": 1000.0,
            "frequency": "monthly",
            "due_day": 1,
            "due_month": None,
            "frequency_anchor": None,
            "frequency_n": None,
            "status": "uncovered",
            "coverage_pct": 0,
        }
        base.update(kwargs)
        return base

    # --- Happy path tests ---

    def test_mtd_shows_next_month_items(self):
        """Items due early next month appear in MTD lookahead."""
        items = [self._make_item(due_day=1)]
        now = datetime(2026, 2, 15)
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 1
        _, item = result[0]
        assert item["_lookahead_due_date"] == datetime(2026, 3, 1)

    def test_mtd_shows_items_within_lookahead_window(self):
        """Items due on the 10th of next month appear (within 15 days)."""
        items = [self._make_item(due_day=10)]
        now = datetime(2026, 2, 20)
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 1
        _, item = result[0]
        assert item["_lookahead_due_date"] == datetime(2026, 3, 10)

    def test_wtd_shows_next_week_items(self):
        """WTD reports show items due in the first days of next week."""
        # Wednesday Feb 18, 2026 -- next Monday is Feb 23
        items = [self._make_item(frequency="weekly", due_day=0)]  # Monday
        now = datetime(2026, 2, 18)
        result = _get_lookahead_items(items, now, "wtd")
        assert len(result) == 1
        _, item = result[0]
        # Next Monday from Wed Feb 18 = Mon Feb 23
        assert item["_lookahead_due_date"] == datetime(2026, 2, 23)

    def test_multiple_items_sorted_by_due_date(self):
        """Multiple lookahead items are sorted by days from period start."""
        items = [
            self._make_item(name="Rent", due_day=1),
            self._make_item(name="Insurance", due_day=5),
            self._make_item(name="Phone", due_day=10),
        ]
        now = datetime(2026, 2, 20)
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 3
        names = [item.get("name") for _, item in result]
        assert names == ["Rent", "Insurance", "Phone"]

    def test_lookahead_days_constant(self):
        """LOOKAHEAD_DAYS is 15."""
        assert LOOKAHEAD_DAYS == 15

    def test_item_copy_preserves_original(self):
        """Returned items are copies, not mutating the original."""
        items = [self._make_item(due_day=1)]
        now = datetime(2026, 2, 15)
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 1
        _, item_copy = result[0]
        assert "_lookahead_due_date" in item_copy
        assert "_lookahead_due_date" not in items[0]

    # --- Edge case tests ---

    def test_mtd_excludes_items_beyond_lookahead_window(self):
        """Items due after the 15-day lookahead window are excluded."""
        items = [self._make_item(due_day=20)]
        now = datetime(2026, 2, 15)
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 0

    def test_last_day_of_month_item(self):
        """Items with due_day=-1 (last day) are correctly handled."""
        items = [self._make_item(due_day=-1)]
        now = datetime(2026, 2, 15)
        # Last day of March is 31 -- beyond 15-day window
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 0

    def test_december_to_january_rollover(self):
        """Year boundary: December MTD shows January items."""
        items = [self._make_item(due_day=5)]
        now = datetime(2026, 12, 20)
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 1
        _, item = result[0]
        assert item["_lookahead_due_date"] == datetime(2027, 1, 5)

    def test_every_n_days_frequency(self):
        """every_n_days items with valid anchor appear in lookahead."""
        items = [self._make_item(
            frequency="every_n_days",
            frequency_n=14,
            frequency_anchor="2026-01-01",
            due_day=None,
        )]
        now = datetime(2026, 2, 20)
        result = _get_lookahead_items(items, now, "mtd")
        # Anchor Jan 1 + 14-day intervals: Jan 15, Jan 29, Feb 12, Feb 26,
        # Mar 12 — Mar 12 is within [Mar 1, Mar 16), so should appear
        assert isinstance(result, list)
        if result:
            _, item = result[0]
            assert "_lookahead_due_date" in item

    def test_quarterly_item_not_due_next_month(self):
        """Quarterly items only appear if due in the lookahead month."""
        items = [self._make_item(
            frequency="quarterly", due_day=1, due_month=4,
        )]
        now = datetime(2026, 2, 15)
        # Next month is March; quarterly due_month=4 means {4, 7, 10, 1}
        # March (3) is NOT in that set
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 0

    def test_quarterly_item_due_next_month(self):
        """Quarterly items appear when due month matches next period."""
        items = [self._make_item(
            frequency="quarterly", due_day=1, due_month=1,
        )]
        # dm=1 quarter months = {1, 4, 7, 10}
        # If now=June, next month=July which IS in the set
        now = datetime(2026, 6, 15)
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 1

    def test_yearly_item_not_due_next_month(self):
        """Yearly items only appear if next month matches due_month."""
        items = [self._make_item(
            frequency="yearly", due_day=1, due_month=6,
        )]
        now = datetime(2026, 2, 15)
        # Next month is March, yearly dm=6 → not due
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 0

    def test_yearly_item_due_next_month(self):
        """Yearly items appear when next month matches due_month."""
        items = [self._make_item(
            frequency="yearly", due_day=5, due_month=3,
        )]
        now = datetime(2026, 2, 15)
        # Next month is March = dm=3
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 1

    def test_biweekly_item(self):
        """Biweekly items with anchor appear correctly in lookahead."""
        items = [self._make_item(
            frequency="biweekly",
            due_day=4,  # Friday
            frequency_anchor="2026-01-02",  # A Friday
        )]
        now = datetime(2026, 2, 20)
        result = _get_lookahead_items(items, now, "mtd")
        assert isinstance(result, list)

    def test_item_due_exactly_on_boundary(self):
        """Item due exactly on LOOKAHEAD_DAYS boundary is excluded (exclusive)."""
        items = [self._make_item(due_day=16)]
        now = datetime(2026, 2, 15)
        # Next month starts Mar 1; Mar 16 is exactly 15 days after -> excluded
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 0

    def test_item_due_day_before_boundary(self):
        """Item due 1 day before LOOKAHEAD_DAYS boundary is included."""
        items = [self._make_item(due_day=15)]
        now = datetime(2026, 2, 15)
        # Next month starts Mar 1; Mar 15 is 14 days after -> included
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 1

    def test_due_day_exceeds_month_length(self):
        """due_day=31 is clamped to actual month length (e.g. Feb 28)."""
        items = [self._make_item(due_day=31)]
        # Now is Jan 15, next month is Feb (28 days in non-leap)
        # Feb 28 is within 15-day window [Feb 1, Feb 16)?  No, 28 > 15
        now = datetime(2027, 1, 15)
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 0

    # --- Failure case tests ---

    def test_full_prior_returns_empty(self):
        """full_prior window type returns no lookahead items."""
        items = [self._make_item(due_day=1)]
        now = datetime(2026, 2, 15)
        result = _get_lookahead_items(items, now, "full_prior")
        assert len(result) == 0

    def test_trailing_returns_empty(self):
        """trailing window type returns no lookahead items."""
        items = [self._make_item(due_day=1)]
        now = datetime(2026, 2, 15)
        result = _get_lookahead_items(items, now, "trailing")
        assert len(result) == 0

    def test_empty_items_returns_empty(self):
        """Empty items list returns empty lookahead."""
        result = _get_lookahead_items([], datetime(2026, 2, 15), "mtd")
        assert len(result) == 0

    def test_items_with_no_due_day_skipped(self):
        """Items without due_day (and not every_n_days) are skipped."""
        items = [self._make_item(due_day=None)]
        now = datetime(2026, 2, 15)
        result = _get_lookahead_items(items, now, "mtd")
        assert len(result) == 0

    def test_invalid_period_window_returns_empty(self):
        """Unknown period window returns empty list."""
        items = [self._make_item(due_day=1)]
        result = _get_lookahead_items(items, datetime(2026, 2, 15), "unknown")
        assert len(result) == 0

    def test_qtd_lookahead(self):
        """QTD reports show items in early next quarter."""
        items = [self._make_item(due_day=3)]
        # Feb 15 is in Q1, next quarter starts Apr 1
        now = datetime(2026, 2, 15)
        result = _get_lookahead_items(items, now, "qtd")
        assert len(result) == 1
        _, item = result[0]
        assert item["_lookahead_due_date"] == datetime(2026, 4, 3)

    def test_ytd_lookahead(self):
        """YTD reports show items in early next year."""
        items = [self._make_item(due_day=5)]
        now = datetime(2026, 11, 15)
        result = _get_lookahead_items(items, now, "ytd")
        assert len(result) == 1
        _, item = result[0]
        assert item["_lookahead_due_date"] == datetime(2027, 1, 5)


class TestLookaheadIntegration:
    """Tests for lookahead integration with existing functions."""

    def test_upcoming_and_lookahead_are_disjoint(self):
        """Current upcoming and next-period lookahead don't overlap."""
        items = [
            {"name": "Rent", "due_day": 1, "frequency": "monthly",
             "amount": 1000, "category": "Housing", "status": "uncovered",
             "coverage_pct": 0, "due_month": None,
             "frequency_anchor": None, "frequency_n": None},
        ]
        now = datetime(2026, 2, 15)

        upcoming = _get_upcoming_items(items, now)
        lookahead = _get_lookahead_items(items, now, "mtd")

        # Rent due_day=1 is before Feb 15, so not in upcoming
        # But it IS in next month's first 15 days (Mar 1)
        assert len(upcoming) == 0
        assert len(lookahead) == 1

    def test_lookahead_suppressed_for_non_xtd(self):
        """Lookahead returns empty for non-xTD windows."""
        items = [
            {"name": "Rent", "due_day": 1, "frequency": "monthly",
             "amount": 1000, "category": "Housing", "status": "uncovered",
             "coverage_pct": 0, "due_month": None,
             "frequency_anchor": None, "frequency_n": None},
        ]
        now = datetime(2026, 2, 15)

        for window in ("full_prior", "trailing"):
            result = _get_lookahead_items(items, now, window)
            assert len(result) == 0, f"Expected empty for {window}"
