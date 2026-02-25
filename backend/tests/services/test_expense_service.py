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

    def test_due_month_included_in_output(self):
        from app.services.expense_service import compute_expense_coverage
        items = [_mock_item("Insurance", 600, "quarterly", due_day=15, due_month=3)]
        result = compute_expense_coverage(items, "monthly", 1000.0, 0.0)
        assert result["items"][0]["due_month"] == 3

    def test_due_month_none_when_not_set(self):
        from app.services.expense_service import compute_expense_coverage
        items = [_mock_item("Rent", 1500, "monthly", due_day=1)]
        result = compute_expense_coverage(items, "monthly", 2000.0, 0.0)
        assert result["items"][0]["due_month"] is None

    def test_login_url_included_in_output(self):
        from app.services.expense_service import compute_expense_coverage
        items = [_mock_item("Netflix", 15, "monthly", login_url="https://netflix.com/login")]
        result = compute_expense_coverage(items, "monthly", 100.0, 0.0)
        assert result["items"][0]["login_url"] == "https://netflix.com/login"

    def test_login_url_none_when_not_set(self):
        from app.services.expense_service import compute_expense_coverage
        items = [_mock_item("Rent", 1500, "monthly")]
        result = compute_expense_coverage(items, "monthly", 2000.0, 0.0)
        assert result["items"][0]["login_url"] is None


class TestCoverageSortModes:
    """Test the sort_mode parameter for coverage waterfall ordering."""

    def test_coverage_amount_asc_is_default(self):
        """Default sort puts smallest expenses first."""
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Rent", 1500, "monthly"),
            _mock_item("Netflix", 15, "monthly"),
            _mock_item("Gym", 50, "monthly"),
        ]
        result = compute_expense_coverage(items, "monthly", 5000.0, 0.0)
        names = [i["name"] for i in result["items"]]
        assert names == ["Netflix", "Gym", "Rent"]

    def test_coverage_amount_desc_reverses_order(self):
        """amount_desc puts largest expenses first."""
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Netflix", 15, "monthly"),
            _mock_item("Gym", 50, "monthly"),
            _mock_item("Rent", 1500, "monthly"),
        ]
        result = compute_expense_coverage(
            items, "monthly", 5000.0, 0.0, sort_mode="amount_desc"
        )
        names = [i["name"] for i in result["items"]]
        assert names == ["Rent", "Gym", "Netflix"]

    def test_coverage_amount_desc_partial_coverage(self):
        """With desc sort and limited income, the largest item gets covered first."""
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Netflix", 15, "monthly"),
            _mock_item("Gym", 50, "monthly"),
            _mock_item("Rent", 1500, "monthly"),
        ]
        # $1540 covers Rent (1500) + partial Gym (50), Netflix uncovered
        result = compute_expense_coverage(
            items, "monthly", 1540.0, 0.0, sort_mode="amount_desc"
        )
        rent = result["items"][0]
        gym = result["items"][1]
        netflix = result["items"][2]
        assert rent["status"] == "covered"
        assert gym["status"] == "partial"
        assert gym["coverage_pct"] == pytest.approx(80.0)  # 40/50
        assert netflix["status"] == "uncovered"

    def test_coverage_custom_uses_sort_order(self):
        """Custom mode sorts by sort_order field."""
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Rent", 1500, "monthly", sort_order=2),
            _mock_item("Netflix", 15, "monthly", sort_order=0),
            _mock_item("Gym", 50, "monthly", sort_order=1),
        ]
        result = compute_expense_coverage(
            items, "monthly", 5000.0, 0.0, sort_mode="custom"
        )
        names = [i["name"] for i in result["items"]]
        assert names == ["Netflix", "Gym", "Rent"]

    def test_coverage_custom_partial_respects_order(self):
        """Custom order determines which items get covered first."""
        from app.services.expense_service import compute_expense_coverage
        # Custom order: Rent first, then Netflix, then Gym
        items = [
            _mock_item("Rent", 1500, "monthly", sort_order=0),
            _mock_item("Netflix", 15, "monthly", sort_order=1),
            _mock_item("Gym", 50, "monthly", sort_order=2),
        ]
        # $1520 covers Rent + Netflix, partial Gym
        result = compute_expense_coverage(
            items, "monthly", 1520.0, 0.0, sort_mode="custom"
        )
        rent = result["items"][0]
        netflix = result["items"][1]
        gym = result["items"][2]
        assert rent["name"] == "Rent"
        assert rent["status"] == "covered"
        assert netflix["name"] == "Netflix"
        assert netflix["status"] == "covered"
        assert gym["name"] == "Gym"
        assert gym["status"] == "partial"

    def test_sort_order_included_in_output(self):
        """sort_order field should be in the output items."""
        from app.services.expense_service import compute_expense_coverage
        items = [_mock_item("Netflix", 15, "monthly", sort_order=5)]
        result = compute_expense_coverage(items, "monthly", 100.0, 0.0)
        assert result["items"][0]["sort_order"] == 5


class TestDefaultExpenseCategories:
    """Verify the default category list."""

    def test_defaults_exist(self):
        from app.services.expense_service import DEFAULT_EXPENSE_CATEGORIES
        assert "Housing" in DEFAULT_EXPENSE_CATEGORIES
        assert "Utilities" in DEFAULT_EXPENSE_CATEGORIES
        assert "Subscriptions" in DEFAULT_EXPENSE_CATEGORIES
        assert "Donations" in DEFAULT_EXPENSE_CATEGORIES
        assert len(DEFAULT_EXPENSE_CATEGORIES) == 13


class TestPercentOfIncomeDonations:
    """Test percent-of-income donation items in the coverage waterfall."""

    def test_pre_tax_basic(self):
        """10% pre-tax of $1000 income = $100."""
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Tithe", 0, "monthly", category="Donations",
                       amount_mode="percent_of_income",
                       percent_of_income=10.0, percent_basis="pre_tax"),
        ]
        result = compute_expense_coverage(items, "monthly", 1000.0, 0.0)
        assert result["items"][0]["normalized_amount"] == pytest.approx(100.0)
        assert result["items"][0]["amount_mode"] == "percent_of_income"
        assert result["items"][0]["percent_of_income"] == 10.0
        assert result["items"][0]["percent_basis"] == "pre_tax"

    def test_post_tax_basic(self):
        """10% post-tax of $1000 with 20% tax = 10% of $800 = $80."""
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Tithe", 0, "monthly", category="Donations",
                       amount_mode="percent_of_income",
                       percent_of_income=10.0, percent_basis="post_tax"),
        ]
        result = compute_expense_coverage(items, "monthly", 1000.0, 20.0)
        assert result["items"][0]["normalized_amount"] == pytest.approx(80.0)

    def test_mixed_percent_and_fixed(self):
        """Percent and fixed items coexist in the waterfall."""
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Rent", 1500, "monthly"),
            _mock_item("Tithe", 0, "monthly", category="Donations",
                       amount_mode="percent_of_income",
                       percent_of_income=10.0, percent_basis="pre_tax"),
        ]
        # Income $2000, tax 0%. Tithe = 10% of $2000 = $200
        # Total expenses = 1500 + 200 = 1700
        result = compute_expense_coverage(items, "monthly", 2000.0, 0.0)
        assert result["total_expenses"] == pytest.approx(1700.0)
        # Sorted ascending: Tithe ($200) then Rent ($1500)
        assert result["items"][0]["name"] == "Tithe"
        assert result["items"][0]["normalized_amount"] == pytest.approx(200.0)
        assert result["items"][1]["name"] == "Rent"

    def test_zero_income_yields_zero_donation(self):
        """With zero income, percent donation = $0."""
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Tithe", 0, "monthly", category="Donations",
                       amount_mode="percent_of_income",
                       percent_of_income=10.0, percent_basis="pre_tax"),
        ]
        result = compute_expense_coverage(items, "monthly", 0.0, 0.0)
        assert result["items"][0]["normalized_amount"] == pytest.approx(0.0)

    def test_fixed_items_default_amount_mode(self):
        """Existing fixed items have amount_mode='fixed' in output."""
        from app.services.expense_service import compute_expense_coverage
        items = [_mock_item("Netflix", 15, "monthly")]
        result = compute_expense_coverage(items, "monthly", 100.0, 0.0)
        assert result["items"][0]["amount_mode"] == "fixed"
        assert "percent_of_income" not in result["items"][0]

    def test_percent_item_no_frequency_normalization(self):
        """Percent items compute from income, not from frequency normalization."""
        from app.services.expense_service import compute_expense_coverage
        # Even though amount=0 and frequency=monthly, the normalized amount
        # should come from percent_of_income calculation, not normalize_item_to_period
        items = [
            _mock_item("Tithe", 0, "monthly", category="Donations",
                       amount_mode="percent_of_income",
                       percent_of_income=5.0, percent_basis="pre_tax"),
        ]
        result = compute_expense_coverage(items, "monthly", 2000.0, 0.0)
        assert result["items"][0]["normalized_amount"] == pytest.approx(100.0)

    def test_percent_with_quarterly_period(self):
        """Percent-of-income is based on period income, not monthly."""
        from app.services.expense_service import compute_expense_coverage
        items = [
            _mock_item("Tithe", 0, "monthly", category="Donations",
                       amount_mode="percent_of_income",
                       percent_of_income=10.0, percent_basis="pre_tax"),
        ]
        # projected_income for quarterly period = $3000
        result = compute_expense_coverage(items, "quarterly", 3000.0, 0.0)
        assert result["items"][0]["normalized_amount"] == pytest.approx(300.0)


# ----- Helpers -----

def _mock_item(name: str, amount: float, frequency: str,
               frequency_n: int = None, due_day: int = None,
               due_month: int = None, login_url: str = None,
               sort_order: int = 0, category: str = "General",
               amount_mode: str = "fixed",
               percent_of_income: float = None,
               percent_basis: str = None):
    """Create a mock expense item for testing."""
    item = MagicMock()
    item.name = name
    item.category = category
    item.amount = amount
    item.frequency = frequency
    item.frequency_n = frequency_n
    item.due_day = due_day
    item.due_month = due_month
    item.login_url = login_url
    item.is_active = True
    item.sort_order = sort_order
    item.amount_mode = amount_mode
    item.percent_of_income = percent_of_income
    item.percent_basis = percent_basis
    return item
