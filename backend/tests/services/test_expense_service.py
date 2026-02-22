"""
Tests for expense_service — normalization and coverage waterfall logic.

Written BEFORE implementation (TDD).
"""

import pytest
from unittest.mock import MagicMock


class TestNormalizeToMonthly:
    """Test conversion from various frequencies to monthly amounts."""

    def test_daily_to_monthly(self):
        from app.services.expense_service import normalize_to_monthly
        # $10/day -> $10 * 30.4375 = $304.375
        assert normalize_to_monthly(10.0, "daily") == pytest.approx(304.375)

    def test_weekly_to_monthly(self):
        from app.services.expense_service import normalize_to_monthly
        # $100/week -> $100 * 52/12 = $433.33...
        assert normalize_to_monthly(100.0, "weekly") == pytest.approx(433.3333, rel=1e-3)

    def test_biweekly_to_monthly(self):
        from app.services.expense_service import normalize_to_monthly
        # $200/biweekly -> $200 * 26/12 = $433.33...
        assert normalize_to_monthly(200.0, "biweekly") == pytest.approx(433.3333, rel=1e-3)

    def test_every_n_days_to_monthly(self):
        from app.services.expense_service import normalize_to_monthly
        # $50 every 14 days -> $50 * 30.4375/14 = $108.705...
        assert normalize_to_monthly(50.0, "every_n_days", 14) == pytest.approx(108.705, rel=1e-2)

    def test_monthly_passthrough(self):
        from app.services.expense_service import normalize_to_monthly
        assert normalize_to_monthly(500.0, "monthly") == pytest.approx(500.0)

    def test_quarterly_to_monthly(self):
        from app.services.expense_service import normalize_to_monthly
        # $900/quarter -> $900/3 = $300
        assert normalize_to_monthly(900.0, "quarterly") == pytest.approx(300.0)

    def test_yearly_to_monthly(self):
        from app.services.expense_service import normalize_to_monthly
        # $1200/year -> $1200/12 = $100
        assert normalize_to_monthly(1200.0, "yearly") == pytest.approx(100.0)

    def test_semi_monthly_to_monthly(self):
        from app.services.expense_service import normalize_to_monthly
        # $500 semi-monthly (2x/month) -> $500 * 2 = $1000
        assert normalize_to_monthly(500.0, "semi_monthly") == pytest.approx(1000.0)

    def test_semi_monthly_zero_amount(self):
        from app.services.expense_service import normalize_to_monthly
        assert normalize_to_monthly(0.0, "semi_monthly") == pytest.approx(0.0)

    def test_semi_annual_to_monthly(self):
        from app.services.expense_service import normalize_to_monthly
        # $600 semi-annual (2x/year) -> $600 / 6 = $100
        assert normalize_to_monthly(600.0, "semi_annual") == pytest.approx(100.0)

    def test_semi_annual_zero_amount(self):
        from app.services.expense_service import normalize_to_monthly
        assert normalize_to_monthly(0.0, "semi_annual") == pytest.approx(0.0)

    def test_every_n_days_without_n_raises(self):
        from app.services.expense_service import normalize_to_monthly
        with pytest.raises(ValueError, match="frequency_n"):
            normalize_to_monthly(50.0, "every_n_days", None)

    def test_unknown_frequency_raises(self):
        from app.services.expense_service import normalize_to_monthly
        with pytest.raises(ValueError, match="Unknown frequency"):
            normalize_to_monthly(50.0, "hourly")


class TestNormalizeMonthlyToPeriod:
    """Test conversion from monthly amount to different goal periods."""

    def test_to_weekly(self):
        from app.services.expense_service import normalize_monthly_to_period
        # $500/month -> $500 * 12/52 = $115.384...
        assert normalize_monthly_to_period(500.0, "weekly") == pytest.approx(115.3846, rel=1e-3)

    def test_to_monthly(self):
        from app.services.expense_service import normalize_monthly_to_period
        assert normalize_monthly_to_period(500.0, "monthly") == pytest.approx(500.0)

    def test_to_quarterly(self):
        from app.services.expense_service import normalize_monthly_to_period
        # $500/month -> $500 * 3 = $1500
        assert normalize_monthly_to_period(500.0, "quarterly") == pytest.approx(1500.0)

    def test_to_yearly(self):
        from app.services.expense_service import normalize_monthly_to_period
        # $500/month -> $500 * 12 = $6000
        assert normalize_monthly_to_period(500.0, "yearly") == pytest.approx(6000.0)


class TestComputeExpenseCoverage:
    """Test the coverage waterfall computation."""

    def test_all_covered(self):
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Rent", 1500, "monthly"),
            _mock_item("Netflix", 15, "monthly"),
            _mock_item("Gym", 50, "monthly"),
        ]
        result = compute_expense_coverage(items, "monthly", 2000.0, 0.0)
        assert result["coverage_pct"] == pytest.approx(100.0)
        assert result["total_expenses"] == pytest.approx(1565.0)
        assert result["income_after_tax"] == pytest.approx(2000.0)
        # All items should be "covered"
        for item in result["items"]:
            assert item["status"] == "covered"

    def test_none_covered(self):
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Rent", 1500, "monthly"),
            _mock_item("Netflix", 15, "monthly"),
        ]
        result = compute_expense_coverage(items, "monthly", 0.0, 0.0)
        assert result["coverage_pct"] == pytest.approx(0.0)
        for item in result["items"]:
            assert item["status"] == "uncovered"

    def test_partial_coverage(self):
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Netflix", 15, "monthly"),
            _mock_item("Gym", 50, "monthly"),
            _mock_item("Rent", 1500, "monthly"),
        ]
        # Income = $100 covers Netflix ($15) + Gym ($50) fully, partial on Rent
        # Remaining after Netflix+Gym: $100-$15-$50 = $35
        result = compute_expense_coverage(items, "monthly", 100.0, 0.0)
        total = 1565.0
        assert result["total_expenses"] == pytest.approx(total)
        # Sorted ascending: Netflix(15), Gym(50), Rent(1500)
        netflix = result["items"][0]
        gym = result["items"][1]
        rent = result["items"][2]
        assert netflix["status"] == "covered"
        assert gym["status"] == "covered"
        assert rent["status"] == "partial"
        assert rent["coverage_pct"] == pytest.approx(2.3, rel=0.1)  # 35/1500

    def test_tax_withholding(self):
        from app.services.expense_service import compute_expense_coverage
        items = [_mock_item("Rent", 1000, "monthly")]
        # Income = $2000, tax = 50% -> $1000 after tax = exactly covers rent
        result = compute_expense_coverage(items, "monthly", 2000.0, 50.0)
        assert result["income_after_tax"] == pytest.approx(1000.0)
        assert result["coverage_pct"] == pytest.approx(100.0)

    def test_empty_items(self):
        from app.services.expense_service import compute_expense_coverage
        result = compute_expense_coverage([], "monthly", 1000.0, 0.0)
        assert result["total_expenses"] == pytest.approx(0.0)
        assert result["coverage_pct"] == pytest.approx(100.0)
        assert result["items"] == []

    def test_sorted_ascending(self):
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Rent", 1500, "monthly"),
            _mock_item("Netflix", 15, "monthly"),
            _mock_item("Gym", 50, "monthly"),
        ]
        result = compute_expense_coverage(items, "monthly", 5000.0, 0.0)
        amounts = [i["normalized_amount"] for i in result["items"]]
        assert amounts == sorted(amounts)

    def test_mixed_frequencies(self):
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Daily Coffee", 5, "daily"),   # ~152.19/mo
            _mock_item("Rent", 1500, "monthly"),       # 1500/mo
            _mock_item("Insurance", 600, "quarterly"),  # 200/mo
        ]
        result = compute_expense_coverage(items, "monthly", 2000.0, 0.0)
        # Total monthly ~= 152.19 + 1500 + 200 = 1852.19
        assert result["total_expenses"] == pytest.approx(1852.19, rel=1e-2)
        assert result["coverage_pct"] == pytest.approx(100.0)

    def test_deposit_needed(self):
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Rent", 1000, "monthly"),
            _mock_item("Netflix", 15, "monthly"),
        ]
        # Income = $500, tax = 0
        result = compute_expense_coverage(items, "monthly", 500.0, 0.0)
        # Shortfall = 1015 - 500 = 515
        assert result["shortfall"] == pytest.approx(515.0)

    def test_partial_item_tracking(self):
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Netflix", 15, "monthly"),
            _mock_item("Gym", 50, "monthly"),
            _mock_item("Rent", 1500, "monthly"),
        ]
        # $100 covers Netflix + Gym, partial on Rent
        result = compute_expense_coverage(items, "monthly", 100.0, 0.0)
        assert result["partial_item_name"] == "Rent"
        assert result["partial_item_shortfall"] == pytest.approx(1465.0)
        assert "next_uncovered_name" not in result  # Rent is the last item

    def test_partial_with_next_uncovered(self):
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Netflix", 15, "monthly"),
            _mock_item("Gym", 50, "monthly"),
            _mock_item("Insurance", 200, "monthly"),
            _mock_item("Rent", 1500, "monthly"),
        ]
        # $100 covers Netflix + Gym, partial on Insurance, Rent uncovered
        result = compute_expense_coverage(items, "monthly", 100.0, 0.0)
        assert result["partial_item_name"] == "Insurance"
        assert result["partial_item_shortfall"] == pytest.approx(165.0)
        assert result["next_uncovered_name"] == "Rent"
        assert result["next_uncovered_amount"] == pytest.approx(1500.0)

    def test_no_partial_first_uncovered_tracked(self):
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Netflix", 15, "monthly"),
            _mock_item("Rent", 1500, "monthly"),
        ]
        # $15 exactly covers Netflix, Rent is fully uncovered (no partial)
        result = compute_expense_coverage(items, "monthly", 15.0, 0.0)
        assert "partial_item_name" not in result
        assert result["next_uncovered_name"] == "Rent"
        assert result["next_uncovered_amount"] == pytest.approx(1500.0)

    def test_all_covered_no_partial_or_next(self):
        from app.services.expense_service import compute_expense_coverage
        items = [_mock_item("Netflix", 15, "monthly")]
        result = compute_expense_coverage(items, "monthly", 100.0, 0.0)
        assert "partial_item_name" not in result
        assert "next_uncovered_name" not in result


class TestComputeExpenseCoverageDueDay:
    """Test that due_day is carried through the coverage waterfall."""

    def test_due_day_included_in_output(self):
        from app.services.expense_service import compute_expense_coverage
        items = [_mock_item("Rent", 1500, "monthly", due_day=1)]
        result = compute_expense_coverage(items, "monthly", 2000.0, 0.0)
        assert result["items"][0]["due_day"] == 1

    def test_due_day_none_when_not_set(self):
        from app.services.expense_service import compute_expense_coverage
        items = [_mock_item("Netflix", 15, "monthly")]
        result = compute_expense_coverage(items, "monthly", 100.0, 0.0)
        assert result["items"][0]["due_day"] is None

    def test_mixed_due_day_values(self):
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Rent", 1500, "monthly", due_day=1),
            _mock_item("Netflix", 15, "monthly"),
            _mock_item("Insurance", 200, "monthly", due_day=-1),
        ]
        result = compute_expense_coverage(items, "monthly", 5000.0, 0.0)
        due_days = {i["name"]: i["due_day"] for i in result["items"]}
        assert due_days["Rent"] == 1
        assert due_days["Netflix"] is None
        assert due_days["Insurance"] == -1

    def test_due_day_does_not_affect_sort_order(self):
        """Items should still be sorted by normalized_amount, not due_day."""
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Rent", 1500, "monthly", due_day=28),
            _mock_item("Netflix", 15, "monthly", due_day=1),
        ]
        result = compute_expense_coverage(items, "monthly", 5000.0, 0.0)
        # Netflix (15) should come before Rent (1500)
        assert result["items"][0]["name"] == "Netflix"
        assert result["items"][1]["name"] == "Rent"


class TestDefaultExpenseCategories:
    """Verify the default category list."""

    def test_defaults_exist(self):
        from app.services.expense_service import DEFAULT_EXPENSE_CATEGORIES
        assert "Housing" in DEFAULT_EXPENSE_CATEGORIES
        assert "Utilities" in DEFAULT_EXPENSE_CATEGORIES
        assert "Subscriptions" in DEFAULT_EXPENSE_CATEGORIES
        assert len(DEFAULT_EXPENSE_CATEGORIES) == 12


# ----- Helpers -----

def _mock_item(name: str, amount: float, frequency: str,
               frequency_n: int = None, due_day: int = None):
    """Create a mock expense item for testing."""
    item = MagicMock()
    item.name = name
    item.category = "General"
    item.amount = amount
    item.frequency = frequency
    item.frequency_n = frequency_n
    item.due_day = due_day
    item.is_active = True
    return item
