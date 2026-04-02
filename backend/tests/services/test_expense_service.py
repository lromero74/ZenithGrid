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


class TestComputeMonthlySavingsContribution:
    """Tests for PMT-based monthly contribution calculator."""

    def test_no_growth_no_existing_savings(self):
        """At 0% growth: contribution = target / months_remaining."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_monthly_savings_contribution
        target_date = date.today() + timedelta(days=365)  # ~12 months
        result = compute_monthly_savings_contribution(
            target_amount=1200.0,
            target_date=target_date,
            current_balance=0.0,
            annual_growth_rate_pct=0.0,
            tax_pct=0.0,
        )
        # ~$100/month (exact depends on days remaining, approx 12 months)
        assert result == pytest.approx(100.0, rel=0.1)

    def test_with_growth_reduces_required_contribution(self):
        """With positive growth, needed monthly contribution is less than flat."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_monthly_savings_contribution
        target_date = date.today() + timedelta(days=365 * 2)  # 24 months
        no_growth = compute_monthly_savings_contribution(
            target_amount=5000.0, target_date=target_date,
            current_balance=0.0, annual_growth_rate_pct=0.0, tax_pct=0.0,
        )
        with_growth = compute_monthly_savings_contribution(
            target_amount=5000.0, target_date=target_date,
            current_balance=0.0, annual_growth_rate_pct=8.0, tax_pct=0.0,
        )
        assert with_growth < no_growth

    def test_existing_balance_reduces_contribution(self):
        """A head start reduces the required monthly contribution."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_monthly_savings_contribution
        target_date = date.today() + timedelta(days=365)
        full = compute_monthly_savings_contribution(
            target_amount=1200.0, target_date=target_date,
            current_balance=0.0, annual_growth_rate_pct=0.0, tax_pct=0.0,
        )
        with_head_start = compute_monthly_savings_contribution(
            target_amount=1200.0, target_date=target_date,
            current_balance=600.0, annual_growth_rate_pct=0.0, tax_pct=0.0,
        )
        assert with_head_start == pytest.approx(full / 2, rel=0.05)

    def test_already_funded_returns_zero(self):
        """If current_balance >= target, no contribution needed."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_monthly_savings_contribution
        target_date = date.today() + timedelta(days=365)
        result = compute_monthly_savings_contribution(
            target_amount=1000.0, target_date=target_date,
            current_balance=1000.0, annual_growth_rate_pct=0.0, tax_pct=0.0,
        )
        assert result == pytest.approx(0.0, abs=0.01)

    def test_past_due_returns_zero(self):
        """If target_date is in the past, return 0 (can't contribute retroactively)."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_monthly_savings_contribution
        target_date = date.today() - timedelta(days=30)
        result = compute_monthly_savings_contribution(
            target_amount=1000.0, target_date=target_date,
            current_balance=0.0, annual_growth_rate_pct=0.0, tax_pct=0.0,
        )
        assert result == 0.0

    def test_tax_grosses_up_target(self):
        """Tax withholding increases the effective target amount."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_monthly_savings_contribution
        target_date = date.today() + timedelta(days=365)
        no_tax = compute_monthly_savings_contribution(
            target_amount=1000.0, target_date=target_date,
            current_balance=0.0, annual_growth_rate_pct=0.0, tax_pct=0.0,
        )
        with_tax = compute_monthly_savings_contribution(
            target_amount=1000.0, target_date=target_date,
            current_balance=0.0, annual_growth_rate_pct=0.0, tax_pct=25.0,
        )
        # With 25% tax, gross-up: need $1000 / (1 - 0.25) = $1333.33
        assert with_tax == pytest.approx(no_tax * (1 / 0.75), rel=0.05)

    def test_known_pmt_value(self):
        """Verify against a manually-calculated PMT value.

        Scenario: save $5,000 in 24 months at 8% annual growth, starting from $0.
        Excel PMT(8%/12, 24, 0, -5000) ≈ $191.19/month
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_monthly_savings_contribution
        # Use exactly 730 days (≈ 24 months)
        target_date = date.today() + timedelta(days=730)
        result = compute_monthly_savings_contribution(
            target_amount=5000.0, target_date=target_date,
            current_balance=0.0, annual_growth_rate_pct=8.0, tax_pct=0.0,
        )
        # PMT formula result — allow 5% tolerance for day-count rounding
        assert result == pytest.approx(191.19, rel=0.05)


class TestComputeExpenseCoverageWithSavings:
    """Tests for waterfall with mixed expense + savings_target items."""

    def test_savings_targets_separated_from_expenses(self):
        """Savings targets appear in savings_targets list, not items list."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage
        expense = _mock_item("Rent", 1500, "monthly")
        savings = _mock_savings_item(
            name="Cruise 2026",
            target_amount=5000.0,
            target_date=date.today() + timedelta(days=548),  # ~18 months
            current_balance=0.0,
            growth_rate=0.0,
        )
        result = compute_expense_coverage(
            [expense, savings], "monthly", 2000.0, 0.0
        )
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "Rent"
        assert len(result["savings_targets"]) == 1
        assert result["savings_targets"][0]["name"] == "Cruise 2026"

    def test_savings_contribution_deducted_from_surplus(self):
        """Savings contributions are deducted from income remaining after expenses."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage
        expense = _mock_item("Rent", 1500, "monthly")
        savings = _mock_savings_item(
            name="Car Fund",
            target_amount=12000.0,
            target_date=date.today() + timedelta(days=365),  # 12 months
            current_balance=0.0,
            growth_rate=0.0,
        )
        # Income = $3000, expense = $1500, savings contribution ≈ $1000/mo
        result = compute_expense_coverage(
            [expense, savings], "monthly", 3000.0, 0.0
        )
        assert result["items"][0]["status"] == "covered"
        savings_item = result["savings_targets"][0]
        assert savings_item["monthly_contribution"] == pytest.approx(1000.0, rel=0.05)
        # Should be covered: $3000 - $1500 rent = $1500 remaining >= $1000 contribution
        assert savings_item["status"] == "covered"

    def test_savings_blocked_when_expense_above_is_partial(self):
        """Savings target is blocked when a higher-priority expense is only partially covered.

        When income runs out mid-expense (partial status), the savings target that
        follows should be 'blocked' — income is exhausted by items with higher claim.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage
        expense = _mock_item("Rent", 3000, "monthly")
        savings = _mock_savings_item(
            name="Vacation",
            target_amount=6000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=0.0,
        )
        result = compute_expense_coverage(
            [expense, savings], "monthly", 2500.0, 0.0
        )
        assert result["items"][0]["status"] == "partial"
        assert result["savings_targets"][0]["status"] == "blocked"

    def test_total_claims_includes_savings(self):
        """total_claims = total_expenses + total_savings_contributions."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage
        expense = _mock_item("Rent", 1000, "monthly")
        savings = _mock_savings_item(
            name="Fund",
            target_amount=12000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=0.0,
        )
        result = compute_expense_coverage(
            [expense, savings], "monthly", 5000.0, 0.0
        )
        assert result["total_claims"] == pytest.approx(
            result["total_expenses"] + result["total_savings_contributions"], rel=0.01
        )

    def test_savings_progress_fields_present(self):
        """Each savings target item includes progress tracking fields."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage
        savings = _mock_savings_item(
            name="House DP",
            target_amount=50000.0,
            target_date=date.today() + timedelta(days=365 * 3),
            current_balance=10000.0,
            growth_rate=7.0,
        )
        result = compute_expense_coverage([savings], "monthly", 10000.0, 0.0)
        st = result["savings_targets"][0]
        assert "monthly_contribution" in st
        assert "savings_pct" in st
        assert "months_remaining" in st
        assert "savings_on_track" in st
        assert st["savings_pct"] == pytest.approx(20.0, rel=0.05)  # 10000/50000

    def test_no_savings_targets_returns_empty_list(self):
        """Result always has savings_targets key even with no savings items."""
        from app.services.expense_service import compute_expense_coverage
        items = [_mock_item("Rent", 1500, "monthly")]
        result = compute_expense_coverage(items, "monthly", 2000.0, 0.0)
        assert "savings_targets" in result
        assert result["savings_targets"] == []
        assert result["total_savings_contributions"] == 0.0
        assert result["total_claims"] == result["total_expenses"]


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
    item.item_type = "expense"
    item.savings_target_amount = None
    item.savings_target_date = None
    item.savings_is_recurring = False
    item.savings_recurrence_months = None
    item.assumed_growth_rate_pct = None
    item.savings_current_balance = 0.0
    return item


def _mock_savings_item(name: str, target_amount: float, target_date,
                       current_balance: float = 0.0, growth_rate: float = 8.0,
                       is_recurring: bool = False, recurrence_months: int = None,
                       sort_order: int = 0):
    """Create a mock savings target item for testing."""
    item = MagicMock()
    item.name = name
    item.category = 'Savings'
    item.amount = 0.0
    item.frequency = 'monthly'
    item.frequency_n = None
    item.due_day = None
    item.due_month = None
    item.login_url = None
    item.is_active = True
    item.sort_order = sort_order
    item.amount_mode = 'fixed'
    item.percent_of_income = None
    item.percent_basis = None
    item.item_type = 'savings_target'
    item.savings_target_amount = target_amount
    item.savings_target_date = target_date
    item.savings_is_recurring = is_recurring
    item.savings_recurrence_months = recurrence_months
    item.assumed_growth_rate_pct = growth_rate
    item.savings_current_balance = current_balance
    return item


# ---------------------------------------------------------------------------
# New tests: savings waterfall with account_balance > 0
# ---------------------------------------------------------------------------

class TestComputeExpenseCoverageWithAccountBalance:
    """Tests for compute_expense_coverage when account_balance > 0.

    When account_balance is provided, savings targets reserve capital from the
    balance pool. The income earmarked for those reserved reserves is then
    subtracted from current_income before expenses are evaluated.
    """

    def test_savings_target_before_expense_reserves_from_balance(self):
        """Savings target BEFORE an expense reserves capital from account_balance.

        The reserved capital earmarks a portion of income (dynamic_reserved *
        income_rate), which reduces the income available to subsequent expenses.
        The savings target itself should be 'funded' when the balance fully
        covers capital_required.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        # account_balance = $50000, annual return = 12% (1%/mo).
        # Savings target: $10000 in ~12 months → capital_required ≈ $8874.
        # At 12% annual: income_rate = income_after_tax / account_balance.
        # income = $5000/mo (post-tax), income_rate = 5000/50000 = 0.1.
        # dynamic_reserved ≈ 8874, income_earmarked ≈ 887.
        savings = _mock_savings_item(
            name="Car Fund",
            target_amount=10000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=12.0,
            sort_order=0,
        )
        expense = _mock_item("Rent", 1000, "monthly", sort_order=1)

        result = compute_expense_coverage(
            [savings, expense],
            period="monthly",
            projected_income=5000.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=12.0,
            account_balance=50000.0,
        )

        st = result["savings_targets"][0]
        # Capital fully covered by account balance → funded
        assert st["status"] == "funded"
        assert st["dynamic_reserved"] > 0
        assert st["income_earmarked"] > 0
        # income_earmarked = dynamic_reserved * income_rate (= dynamic_reserved * 5000/50000)
        expected_earmarked = pytest.approx(st["dynamic_reserved"] * (5000.0 / 50000.0), rel=0.01)
        assert st["income_earmarked"] == expected_earmarked
        # free_balance should be reduced by dynamic_reserved
        assert result["free_balance"] == pytest.approx(50000.0 - st["dynamic_reserved"], rel=0.01)

    def test_savings_target_before_expense_reduces_available_income(self):
        """Income earmarked by a savings reservation reduces what expenses can use.

        With a tight income, the earmarked portion should leave the expense
        with less income than it would have without the savings target.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        # income = $600/mo. account_balance = $10000, annual return = 12%.
        # income_rate = 600 / 10000 = 0.06.
        # Savings target: $5000 in 12 months. capital_required ≈ 5000/(1.01)^12 ≈ 4437.
        # dynamic_reserved = 4437, income_earmarked = 4437 * 0.06 ≈ 266.
        # Remaining income for expenses = 600 - 266 = 334.
        # Expense = $400/mo → partial (334/400 = 83.5%).
        savings = _mock_savings_item(
            name="Vacation",
            target_amount=5000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=12.0,
            sort_order=0,
        )
        expense = _mock_item("Rent", 400, "monthly", sort_order=1)

        result = compute_expense_coverage(
            [savings, expense],
            period="monthly",
            projected_income=600.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=12.0,
            account_balance=10000.0,
        )

        st = result["savings_targets"][0]
        assert st["income_earmarked"] > 0
        # Expense should not be fully covered because some income is earmarked
        expense_entry = result["items"][0]
        assert expense_entry["coverage_pct"] < 100.0

    def test_savings_target_zero_balance_falls_back_to_income_coverage(self):
        """When account_balance = 0, savings target uses income-based coverage.

        The savings target must NOT set blocked=True and must NOT block
        expenses below it. Coverage falls back to income-based logic.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        savings = _mock_savings_item(
            name="Emergency Fund",
            target_amount=3000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=0.0,
            sort_order=0,
        )
        expense = _mock_item("Netflix", 15, "monthly", sort_order=1)

        result = compute_expense_coverage(
            [savings, expense],
            period="monthly",
            projected_income=5000.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=0.0,
            account_balance=0.0,
        )

        # With no account_balance, the savings target must NOT block the expense
        expense_entry = result["items"][0]
        assert expense_entry["status"] != "blocked", (
            "Expense after savings target with account_balance=0 must not be blocked"
        )
        # income_rate is 0 when account_balance=0 → no income earmarked
        st = result["savings_targets"][0]
        assert st["income_earmarked"] == 0.0

    def test_savings_target_capital_gap_blocks_items_below(self):
        """When cap_gap > 0 and account_balance > 0, items below are blocked.

        If the account balance is insufficient to cover capital_required,
        blocked=True is set and all subsequent items get status='blocked'.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        # account_balance = $1000, but savings needs ~$8874 capital.
        # dynamic_reserved = min(8874, 1000) = 1000; cap_gap = 7874 > 0 → blocked.
        savings = _mock_savings_item(
            name="House DP",
            target_amount=10000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=12.0,
            sort_order=0,
        )
        expense1 = _mock_item("Netflix", 15, "monthly", sort_order=1)
        expense2 = _mock_item("Gym", 50, "monthly", sort_order=2)

        result = compute_expense_coverage(
            [savings, expense1, expense2],
            period="monthly",
            projected_income=5000.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=12.0,
            account_balance=1000.0,
        )

        st = result["savings_targets"][0]
        assert st["capital_gap"] > 0
        # Both expenses below the underfunded savings target must be blocked
        for item in result["items"]:
            assert item["status"] == "blocked", (
                f"Expected '{item['name']}' to be blocked but got '{item['status']}'"
            )

    def test_savings_target_cap_gap_zero_does_not_block(self):
        """When cap_gap = 0, the savings target is funded and items below are NOT blocked."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        # account_balance = $100000 — more than enough to cover any reasonable PV.
        savings = _mock_savings_item(
            name="Car Fund",
            target_amount=10000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=12.0,
            sort_order=0,
        )
        expense = _mock_item("Netflix", 15, "monthly", sort_order=1)

        result = compute_expense_coverage(
            [savings, expense],
            period="monthly",
            projected_income=5000.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=12.0,
            account_balance=100000.0,
        )

        st = result["savings_targets"][0]
        assert st["capital_gap"] == 0.0
        assert st["status"] == "funded"
        # The expense below must not be blocked
        assert result["items"][0]["status"] != "blocked"


class TestComputeSavingsCapitalRequired:
    """Tests for the PV formula in compute_savings_capital_required."""

    def test_pv_formula_known_value(self):
        """PV = FV / (1+r)^n for target=$10000 in 12 months at 12% annual.

        monthly rate = 12%/12 = 1% = 0.01
        n = 12 months (approximately, using 365 days / 30.4375)
        PV = 10000 / (1.01)^12 ≈ 8874.49
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_savings_capital_required
        import math

        # Use exactly 365 days so n ≈ 365/30.4375 ≈ 11.99 months
        target_date = date.today() + timedelta(days=365)
        result = compute_savings_capital_required(
            target_amount=10000.0,
            target_date=target_date,
            annual_growth_rate_pct=12.0,
            tax_pct=0.0,
            is_recurring=False,
            current_balance=0.0,
        )
        # Expected: 10000 / (1.01)^(365/30.4375)
        _DAYS_PER_MONTH = 30.4375
        n = 365 / _DAYS_PER_MONTH
        expected = 10000.0 / math.pow(1.01, n)
        assert result == pytest.approx(expected, rel=0.001)
        # Sanity-check that it's near the textbook 8874.49 for exactly 12 months
        assert 8800.0 < result < 8950.0

    def test_pv_zero_rate_returns_gross_target(self):
        """At 0% growth rate, PV equals the gross target (no discounting)."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_savings_capital_required

        target_date = date.today() + timedelta(days=365)
        result = compute_savings_capital_required(
            target_amount=10000.0,
            target_date=target_date,
            annual_growth_rate_pct=0.0,
            tax_pct=0.0,
        )
        assert result == pytest.approx(10000.0)

    def test_pv_past_date_returns_zero(self):
        """If target_date is in the past, capital_required = 0."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_savings_capital_required

        past_date = date.today() - timedelta(days=1)
        result = compute_savings_capital_required(
            target_amount=10000.0,
            target_date=past_date,
            annual_growth_rate_pct=12.0,
        )
        assert result == 0.0

    def test_pv_extreme_rate_does_not_raise_overflow(self):
        """An astronomically large growth rate must return 0.0, not crash.

        This guards against the OverflowError that occurs when the account_balance
        denominator is incorrectly computed (e.g. summing multiple snapshots instead
        of one), yielding a daily_rate that's thousands of percent.
        math.pow(1 + r, n) would overflow float range → OverflowError.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_savings_capital_required

        target_date = date.today() + timedelta(days=365)
        # 1e30 %/year causes math.pow to overflow float range — guard must catch it
        result = compute_savings_capital_required(
            target_amount=10000.0,
            target_date=target_date,
            annual_growth_rate_pct=1e30,
        )
        assert result == 0.0, (
            f"Expected 0.0 for extreme rate (OverflowError guard), got {result}"
        )

    def test_pv_higher_rate_means_lower_capital_required(self):
        """Higher growth rate → lower capital needed today (stronger discounting)."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_savings_capital_required

        target_date = date.today() + timedelta(days=365)
        low = compute_savings_capital_required(
            target_amount=10000.0, target_date=target_date,
            annual_growth_rate_pct=1.0,
        )
        high = compute_savings_capital_required(
            target_amount=10000.0, target_date=target_date,
            annual_growth_rate_pct=20.0,
        )
        assert high < low


class TestComputeGrossTarget:
    """Tests for _compute_gross_target — recurring savings with tax."""

    def test_recurring_with_tax_adds_balance(self):
        """Recurring target with tax: gross = target/(1-tax) + current_balance.

        target=$1000, tax=10%, current_balance=$500
        gross = 1000/(1-0.1) + 500 = 1111.11 + 500 = 1611.11
        """
        from app.services.expense_service import _compute_gross_target

        result = _compute_gross_target(
            target_amount=1000.0,
            tax_pct=10.0,
            is_recurring=True,
            current_balance=500.0,
        )
        assert result == pytest.approx(1611.11, rel=0.001)

    def test_non_recurring_with_tax_no_balance_added(self):
        """Non-recurring with tax: gross = target/(1-tax), balance ignored."""
        from app.services.expense_service import _compute_gross_target

        result = _compute_gross_target(
            target_amount=1000.0,
            tax_pct=10.0,
            is_recurring=False,
            current_balance=500.0,
        )
        # Should NOT add current_balance
        assert result == pytest.approx(1111.11, rel=0.001)
        assert result < 1500.0

    def test_recurring_no_tax_adds_balance(self):
        """Recurring with no tax: gross = target + current_balance."""
        from app.services.expense_service import _compute_gross_target

        result = _compute_gross_target(
            target_amount=1000.0,
            tax_pct=0.0,
            is_recurring=True,
            current_balance=500.0,
        )
        assert result == pytest.approx(1500.0)

    def test_non_recurring_no_tax_returns_target(self):
        """Non-recurring, no tax: gross = target_amount exactly."""
        from app.services.expense_service import _compute_gross_target

        result = _compute_gross_target(
            target_amount=1000.0,
            tax_pct=0.0,
            is_recurring=False,
            current_balance=500.0,
        )
        assert result == pytest.approx(1000.0)

    def test_zero_balance_recurring_with_tax(self):
        """Recurring with tax and zero balance: gross = target/(1-tax)."""
        from app.services.expense_service import _compute_gross_target

        result = _compute_gross_target(
            target_amount=1000.0,
            tax_pct=25.0,
            is_recurring=True,
            current_balance=0.0,
        )
        # 1000 / (1 - 0.25) = 1333.33
        assert result == pytest.approx(1333.33, rel=0.001)


class TestCustomSortSavingsTargetPlacement:
    """Tests for custom sort_mode: savings target position affects blocking direction.

    Blocking only flows FORWARD (downward) from a savings target. Expenses
    that appear BEFORE the savings target in sort order are evaluated before
    blocked is ever set — so they must NOT be blocked.
    """

    def test_savings_target_after_expenses_does_not_block_those_expenses(self):
        """Expenses sorted BEFORE an underfunded savings target are not blocked.

        With custom sort: expense at sort_order=0, savings at sort_order=1.
        The expense runs through the waterfall first. Even if the savings target
        later sets blocked=True, the expense has already been evaluated and
        should retain its actual coverage status.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        # account_balance = $500 — insufficient to cover capital_required for $10000 target.
        expense = _mock_item("Rent", 500, "monthly", sort_order=0)
        savings = _mock_savings_item(
            name="House DP",
            target_amount=10000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=12.0,
            sort_order=1,
        )

        result = compute_expense_coverage(
            [expense, savings],
            period="monthly",
            projected_income=2000.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=12.0,
            account_balance=500.0,
        )

        st = result["savings_targets"][0]
        assert st["capital_gap"] > 0, "Savings target should have a capital gap"

        # The expense came BEFORE the savings target; it must not be blocked
        expense_entry = result["items"][0]
        assert expense_entry["status"] != "blocked", (
            f"Expense at sort_order=0 must not be blocked by savings at sort_order=1; "
            f"got status='{expense_entry['status']}'"
        )
        assert expense_entry["status"] == "covered"

    def test_savings_target_before_expense_blocks_items_below_when_underfunded(self):
        """With custom sort, savings at sort_order=0 BEFORE expense at sort_order=1
        blocks the expense when the savings target is underfunded.

        This is the mirror of the previous test — position determines blocking.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        savings = _mock_savings_item(
            name="House DP",
            target_amount=10000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=12.0,
            sort_order=0,
        )
        expense = _mock_item("Rent", 500, "monthly", sort_order=1)

        result = compute_expense_coverage(
            [expense, savings],
            period="monthly",
            projected_income=2000.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=12.0,
            account_balance=500.0,
        )

        st = result["savings_targets"][0]
        assert st["capital_gap"] > 0

        expense_entry = result["items"][0]
        assert expense_entry["status"] == "blocked"

    def test_savings_target_after_multiple_expenses_does_not_block_any_of_them(self):
        """Multiple expenses placed before the savings target are all unaffected."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        expense1 = _mock_item("Netflix", 15, "monthly", sort_order=0)
        expense2 = _mock_item("Gym", 50, "monthly", sort_order=1)
        savings = _mock_savings_item(
            name="House DP",
            target_amount=50000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=12.0,
            sort_order=2,
        )

        result = compute_expense_coverage(
            [expense1, expense2, savings],
            period="monthly",
            projected_income=5000.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=12.0,
            account_balance=1000.0,  # Insufficient for $50k target
        )

        st = result["savings_targets"][0]
        assert st["capital_gap"] > 0

        for item in result["items"]:
            assert item["status"] != "blocked", (
                f"'{item['name']}' (before the savings target) must not be blocked"
            )


# ---------------------------------------------------------------------------
# New tests: savings target blocked by uncovered expenses above it
# ---------------------------------------------------------------------------

class TestSavingsTargetBlockedByUncoveredExpenses:
    """Savings targets must not reserve capital when higher-priority expenses
    cannot be fully covered by income.

    Rule: if any expense ranked above the savings target in sort order is
    'partial' or 'uncovered', the savings target gets status='blocked' and
    dynamic_reserved=0 — income has been exhausted by items with higher claim.
    """

    def test_savings_target_blocked_when_expense_above_is_uncovered(self):
        """A savings target after an uncovered expense must be blocked.

        Income: $0. Expense: $500 (uncovered — no income at all). Savings: after.
        The savings target should NOT reserve capital — income is exhausted.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        expense = _mock_item("Alimony", 500, "monthly", sort_order=0)
        savings = _mock_savings_item(
            name="Vacation",
            target_amount=5000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=8.0,
            sort_order=1,
        )

        result = compute_expense_coverage(
            [expense, savings],
            period="monthly",
            projected_income=0.0,  # zero income → expense is "uncovered"
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=8.0,
            account_balance=50000.0,  # plenty of balance — but expense is uncovered
        )

        expense_entry = result["items"][0]
        assert expense_entry["status"] == "uncovered"

        st = result["savings_targets"][0]
        assert st["status"] == "blocked", (
            f"Savings target after uncovered expense must be 'blocked', got '{st['status']}'"
        )
        assert st["dynamic_reserved"] == 0.0, (
            "Savings target must not reserve capital when expenses above are uncovered"
        )

    def test_savings_target_blocked_when_expense_above_is_partial(self):
        """A savings target after a partially-covered expense must be blocked.

        Income: $200. Expense: $500 (partial — income runs out). Savings: after.
        After the partial expense current_income=0, savings must not reserve.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        expense = _mock_item("Rent", 500, "monthly", sort_order=0)
        savings = _mock_savings_item(
            name="Car Fund",
            target_amount=10000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=8.0,
            sort_order=1,
        )

        result = compute_expense_coverage(
            [expense, savings],
            period="monthly",
            projected_income=200.0,  # only partially covers $500 expense
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=8.0,
            account_balance=50000.0,
        )

        expense_entry = result["items"][0]
        assert expense_entry["status"] == "partial"

        st = result["savings_targets"][0]
        assert st["status"] == "blocked", (
            f"Savings target after partial expense must be 'blocked', got '{st['status']}'"
        )
        assert st["dynamic_reserved"] == 0.0

    def test_savings_target_not_blocked_when_all_expenses_above_covered(self):
        """Savings target is NOT blocked when all higher-priority expenses are fully covered.

        Income: $2000. Expenses above: $500 (covered). Savings: after.
        Income not exhausted, so savings target can reserve from balance normally.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        expense = _mock_item("Rent", 500, "monthly", sort_order=0)
        savings = _mock_savings_item(
            name="Vacation",
            target_amount=5000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=8.0,
            sort_order=1,
        )

        result = compute_expense_coverage(
            [expense, savings],
            period="monthly",
            projected_income=2000.0,  # plenty of income
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=8.0,
            account_balance=50000.0,
        )

        expense_entry = result["items"][0]
        assert expense_entry["status"] == "covered"

        st = result["savings_targets"][0]
        assert st["status"] != "blocked", (
            f"Savings target must not be blocked when all expenses above are covered; "
            f"got '{st['status']}'"
        )
        assert st["dynamic_reserved"] > 0.0

    def test_multiple_uncovered_expenses_all_block_savings_target(self):
        """Multiple uncovered expenses above all block the savings target.

        Mirrors the user's real scenario: many uncovered expenses, then a savings target.
        None of the unspent income (zero) should roll forward to fund savings.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        # Income just barely covers item 0; items 1 and 2 are uncovered
        exp0 = _mock_item("Tithes", 5, "monthly", sort_order=0)
        exp1 = _mock_item("Alimony", 500, "monthly", sort_order=1)
        exp2 = _mock_item("Student Loan", 680, "monthly", sort_order=2)
        savings = _mock_savings_item(
            name="Tickets to Opposite Coast",
            target_amount=3000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=619.0,
            growth_rate=8.0,
            sort_order=3,
        )

        result = compute_expense_coverage(
            [exp0, exp1, exp2, savings],
            period="monthly",
            projected_income=5.0,  # exactly covers Tithes ($5); Alimony+Loan are uncovered
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=8.0,
            account_balance=10000.0,
        )

        assert result["items"][0]["status"] == "covered"   # Tithes ($5 = income)
        assert result["items"][1]["status"] == "uncovered"  # Alimony (income=0 now)
        assert result["items"][2]["status"] == "uncovered"  # Student Loan

        st = result["savings_targets"][0]
        assert st["status"] == "blocked"
        assert st["dynamic_reserved"] == 0.0

    def test_savings_target_blocked_propagates_to_savings_targets_below(self):
        """When a savings target is blocked by uncovered expenses, subsequent
        savings targets are also blocked (income still exhausted).
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        expense = _mock_item("Big Expense", 9999, "monthly", sort_order=0)
        st1 = _mock_savings_item(
            name="Vacation", target_amount=2000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0, growth_rate=8.0, sort_order=1,
        )
        st2 = _mock_savings_item(
            name="Car Fund", target_amount=5000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0, growth_rate=8.0, sort_order=2,
        )

        result = compute_expense_coverage(
            [expense, st1, st2],
            period="monthly",
            projected_income=100.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=8.0,
            account_balance=50000.0,
        )

        assert result["items"][0]["status"] == "partial"  # only partial from $100 income
        for st in result["savings_targets"]:
            assert st["status"] == "blocked", (
                f"'{st['name']}' must be blocked when expenses above are uncovered"
            )
            assert st["dynamic_reserved"] == 0.0


class TestDynamicReservedPVNotFullBalance:
    """Tests that dynamic_reserved = capital_required (PV), not the full account balance.

    The on-track check is PV-based: if the account holds enough today to compound
    to the target, the savings target is 'funded' and only the PV is reserved.
    Excess balance rolls forward to items lower in the priority list.
    """

    def test_only_pv_reserved_not_full_account_balance(self):
        """dynamic_reserved equals capital_required (PV), not account_balance.

        If the account has $2000 but only $905 (PV) is needed today to compound
        to $1000 in 12 months at 10%/yr, exactly $905 should be reserved —
        leaving $1095 of free balance for items below.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage, compute_savings_capital_required

        target_date = date.today() + timedelta(days=365)
        savings = _mock_savings_item(
            name="Vacation Fund",
            target_amount=1000.0,
            target_date=target_date,
            current_balance=0.0,
            growth_rate=10.0,
            sort_order=0,
        )

        pv = compute_savings_capital_required(
            target_amount=1000.0,
            target_date=target_date,
            annual_growth_rate_pct=10.0,
        )
        # PV should be noticeably less than $1000
        assert pv < 1000.0

        result = compute_expense_coverage(
            [savings],
            period="monthly",
            projected_income=200.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=10.0,
            account_balance=2000.0,  # Much more than PV needed
        )

        st = result["savings_targets"][0]
        # dynamic_reserved = min(capital_required, remaining_balance) = capital_required
        assert st["dynamic_reserved"] == pytest.approx(st["capital_required"], rel=1e-5)
        assert st["dynamic_reserved"] < 2000.0  # Not the full balance
        assert st["capital_gap"] == 0.0
        assert st["status"] == "funded"
        # Remaining free balance = $2000 - PV
        assert result["free_balance"] == pytest.approx(2000.0 - pv, rel=1e-3)

    def test_excess_balance_available_to_items_below(self):
        """After a funded savings target, remaining balance/income flows to items below.

        A savings target that reserves only its PV leaves the excess income
        available for expenses below it — the ✓ case does NOT gate items below.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        savings = _mock_savings_item(
            name="Car Fund",
            target_amount=5000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=12.0,
            sort_order=0,
        )
        # Large expense that can only be covered if income isn't fully consumed
        expense = _mock_item("Rent", 1000.0, "monthly", sort_order=1)

        result = compute_expense_coverage(
            [savings, expense],
            period="monthly",
            projected_income=1500.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=12.0,
            account_balance=50000.0,  # Far more than PV — savings target will be funded
        )

        st = result["savings_targets"][0]
        assert st["capital_gap"] == 0.0
        assert st["status"] == "funded"
        # Expense below a funded savings target is NOT blocked and has income available
        exp = result["items"][0]
        assert exp["status"] != "blocked"
        assert exp["status"] in ("covered", "partial")

    def test_account_balance_just_enough_for_pv_is_on_track(self):
        """If account_balance >= capital_required (PV), savings target is on track.

        The '45% funded' raw metric (current_balance / gross_target) is irrelevant
        to on-track status — only whether the PV is covered matters.
        """
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage, compute_savings_capital_required

        target_date = date.today() + timedelta(days=180)  # 6 months out
        pv = compute_savings_capital_required(
            target_amount=1000.0,
            target_date=target_date,
            annual_growth_rate_pct=24.0,  # 2%/month
        )
        # Set account balance to exactly the PV — should be "just enough"
        account_balance = round(pv, 2)

        savings = _mock_savings_item(
            name="Ticket",
            target_amount=1000.0,
            target_date=target_date,
            current_balance=0.0,
            growth_rate=24.0,
            sort_order=0,
        )

        result = compute_expense_coverage(
            [savings],
            period="monthly",
            projected_income=0.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=24.0,
            account_balance=account_balance,
        )

        st = result["savings_targets"][0]
        assert st["capital_gap"] == pytest.approx(0.0, abs=0.01)
        assert st["status"] == "funded"
        assert st["dynamic_reserved"] == pytest.approx(pv, rel=1e-3)


class TestDepositCoachingFields:
    """compute_expense_coverage emits savings-gap deposit coaching fields
    when a savings target with cap_gap > 0 is blocking expenses below it."""

    def test_savings_gap_coaching_fields_populated(self):
        """first_gap_savings_* and first_blocked_after_savings_* are set when
        a savings target is underfunded and blocks expenses below it."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        savings = _mock_savings_item(
            name="Vacation Fund",
            target_amount=2000.0,
            target_date=date.today() + timedelta(days=90),
            current_balance=0.0,
            growth_rate=12.0,
            sort_order=0,
        )
        expense = _mock_item("Rent", 500.0, "monthly", sort_order=1)

        result = compute_expense_coverage(
            [savings, expense],
            period="monthly",
            projected_income=200.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=12.0,
            account_balance=300.0,  # Less than PV → savings target underfunded
        )

        # Savings target should have a gap (300 < PV of 2000 in 3 months)
        st = result["savings_targets"][0]
        assert st["capital_gap"] > 0
        assert st["status"] in ("partial", "uncovered")

        # Coaching fields should be populated
        assert result.get("first_gap_savings_name") == "Vacation Fund"
        assert result.get("first_gap_savings_cap_gap") == pytest.approx(st["capital_gap"], rel=1e-5)
        assert result.get("first_blocked_after_savings_name") == "Rent"
        assert result.get("first_blocked_after_savings_amount") == pytest.approx(500.0, rel=1e-5)

    def test_savings_gap_coaching_fields_absent_when_funded(self):
        """No coaching fields when savings target is fully funded."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        savings = _mock_savings_item(
            name="Car Fund",
            target_amount=500.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=10.0,
            sort_order=0,
        )

        result = compute_expense_coverage(
            [savings],
            period="monthly",
            projected_income=0.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=10.0,
            account_balance=50000.0,  # Far more than PV → funded
        )

        st = result["savings_targets"][0]
        assert st["capital_gap"] == 0.0
        assert st["status"] == "funded"

        # No savings-gap coaching needed
        assert result.get("first_gap_savings_name") is None
        assert result.get("first_gap_savings_cap_gap") is None

    def test_first_blocked_after_savings_is_first_expense_only(self):
        """first_blocked_after_savings_name is the FIRST blocked expense,
        not subsequent ones."""
        from datetime import date, timedelta
        from app.services.expense_service import compute_expense_coverage

        savings = _mock_savings_item(
            name="Trip",
            target_amount=3000.0,
            target_date=date.today() + timedelta(days=60),
            current_balance=0.0,
            growth_rate=12.0,
            sort_order=0,
        )
        exp1 = _mock_item("Zoho Mail", 2.08, "monthly", sort_order=1)
        exp2 = _mock_item("OSGLI", 8.70, "monthly", sort_order=2)

        result = compute_expense_coverage(
            [savings, exp1, exp2],
            period="monthly",
            projected_income=100.0,
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=12.0,
            account_balance=100.0,  # Less than PV → gap
        )

        assert result.get("first_gap_savings_name") == "Trip"
        # first blocked = Zoho Mail (first expense below the savings gap)
        assert result.get("first_blocked_after_savings_name") == "Zoho Mail"
        # NOT OSGLI (that's the second blocked)

    def test_expense_path_coaching_unaffected_when_no_savings_gap(self):
        """When there is no savings target, classic partial-item coaching works."""
        from app.services.expense_service import compute_expense_coverage

        exp1 = _mock_item("Rent", 500.0, "monthly", sort_order=0)
        exp2 = _mock_item("Food", 300.0, "monthly", sort_order=1)

        result = compute_expense_coverage(
            [exp1, exp2],
            period="monthly",
            projected_income=600.0,   # Covers Rent ($500) but only $100 left for Food
            tax_pct=0.0,
            sort_mode="custom",
            account_annual_return_pct=10.0,
            account_balance=5000.0,
        )

        # Savings coaching fields absent — no savings target
        assert result.get("first_gap_savings_name") is None
        assert result.get("first_blocked_after_savings_name") is None

        # Classic expense path coaching is set
        assert result.get("partial_item_name") == "Food"
        assert (result.get("partial_item_shortfall") or 0) > 0


# ---------------------------------------------------------------------------
# Tests: gross_target exposure in _build_savings_target_entry
# ---------------------------------------------------------------------------

class TestBuildSavingsTargetEntryGrossTarget:
    """Tests verifying that _build_savings_target_entry exposes gross_target
    so callers can show both the spend target and the total-to-accumulate.

    Written TDD — these fail until gross_target is added to the return dict.
    """

    def test_no_tax_no_recurrence_gross_equals_target(self):
        """Without tax or recurrence gross_target == savings_target_amount."""
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Vacation",
            target_amount=2000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=8.0,
            is_recurring=False,
        )
        result = _build_savings_target_entry(
            item, period="monthly", income_after_tax=3000.0, tax_pct=0.0
        )
        assert "gross_target" in result, "gross_target must be present in result"
        assert result["gross_target"] == pytest.approx(2000.0, abs=0.01)

    def test_with_tax_gross_target_inflated(self):
        """With 20% tax: gross_target = target_amount / 0.8."""
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Car",
            target_amount=10000.0,
            target_date=date.today() + timedelta(days=730),
            current_balance=0.0,
            growth_rate=8.0,
            is_recurring=False,
        )
        result = _build_savings_target_entry(
            item, period="monthly", income_after_tax=5000.0, tax_pct=20.0
        )
        assert "gross_target" in result
        # gross_withdrawal = 10000 / (1 - 0.20) = 12500
        assert result["gross_target"] == pytest.approx(12500.0, abs=0.01)

    def test_recurring_no_tax_gross_includes_self_sustaining_hold(self):
        """Recurring with no tax: gross_target = target_amount + max(balance, self_sustaining_hold)."""
        import math
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Annual trip",
            target_amount=3000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=1000.0,
            growth_rate=8.0,
            is_recurring=True,
            recurrence_months=12,
        )
        result = _build_savings_target_entry(
            item, period="monthly", income_after_tax=4000.0, tax_pct=0.0
        )
        assert "gross_target" in result
        # self_sustaining_hold = 3000 / ((1.00667)^12 - 1) ≈ 36148 >> balance=1000
        r = 8.0 / 100.0 / 12.0
        expected_hold = 3000.0 / (math.pow(1 + r, 12) - 1)
        assert result["gross_target"] == pytest.approx(3000.0 + expected_hold, rel=0.001)

    def test_recurring_with_tax_gross_target_combines_both(self):
        """Recurring + tax: gross_target = gross_withdrawal + max(balance, self_sustaining_hold)."""
        import math
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Annual bonus spend",
            target_amount=5000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=500.0,
            growth_rate=8.0,
            is_recurring=True,
            recurrence_months=12,
        )
        result = _build_savings_target_entry(
            item, period="monthly", income_after_tax=6000.0, tax_pct=25.0
        )
        assert "gross_target" in result
        # gross_withdrawal = 5000 / 0.75 = 6666.67
        # self_sustaining_hold = 6666.67 / ((1.00667)^12 - 1) >> balance=500
        r = 8.0 / 100.0 / 12.0
        gross_w = 5000.0 / 0.75
        expected_hold = gross_w / (math.pow(1 + r, 12) - 1)
        assert result["gross_target"] == pytest.approx(gross_w + expected_hold, rel=0.001)


class TestSavingsTargetEntryBreakdownFields:
    """TDD: _build_savings_target_entry must expose tax_amount and recurrence_hold
    so the report can render a breakdown like:
      Spend: $25 · Tax: $3 · Hold: $12 → accumulate: $40
    """

    def test_no_tax_no_recurrence_both_zero(self):
        """Happy path: no tax, not recurring — both breakdown fields are 0."""
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Vacation",
            target_amount=1000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=8.0,
            is_recurring=False,
        )
        result = _build_savings_target_entry(item, period="monthly", income_after_tax=3000.0, tax_pct=0.0)
        assert result["tax_amount"] == pytest.approx(0.0, abs=0.01)
        assert result["recurrence_hold"] == pytest.approx(0.0, abs=0.01)

    def test_with_tax_no_recurrence(self):
        """Edge case: 20% tax adds to gross_target; recurrence_hold stays 0."""
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Laptop",
            target_amount=2000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=8.0,
            is_recurring=False,
        )
        result = _build_savings_target_entry(item, period="monthly", income_after_tax=3000.0, tax_pct=20.0)
        # gross_withdrawal = 2000 / 0.80 = 2500; tax = 500
        assert result["tax_amount"] == pytest.approx(500.0, abs=0.01)
        assert result["recurrence_hold"] == pytest.approx(0.0, abs=0.01)

    def test_recurring_no_tax(self):
        """Edge case: recurring with no tax — hold = self-sustaining seed (> balance), tax = 0."""
        import math
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Annual sub",
            target_amount=500.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=200.0,
            growth_rate=8.0,
            is_recurring=True,
            recurrence_months=12,
        )
        result = _build_savings_target_entry(item, period="monthly", income_after_tax=2000.0, tax_pct=0.0)
        # self_sustaining_hold = 500 / ((1.00667)^12 - 1) ≈ 6025; dominates over balance=200
        r = 8.0 / 100.0 / 12.0
        expected_hold = 500.0 / (math.pow(1 + r, 12) - 1)
        assert result["tax_amount"] == pytest.approx(0.0, abs=0.01)
        assert result["recurrence_hold"] == pytest.approx(expected_hold, rel=0.001)

    def test_recurring_with_tax(self):
        """Happy path: recurring + tax — self-sustaining hold dominates over current_balance."""
        import math
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Zoho Mail",
            target_amount=25.0,
            target_date=date.today() + timedelta(days=270),
            current_balance=12.0,
            growth_rate=35.9,
            is_recurring=True,
            recurrence_months=12,
        )
        result = _build_savings_target_entry(item, period="monthly", income_after_tax=3000.0, tax_pct=25.0)
        # gross_withdrawal = 25 / 0.75 = 33.33; tax = 8.33
        # self_sustaining_hold = 33.33 / ((1 + 35.9/1200)^12 - 1) ≈ 78.6; dominates over 12.0
        gross_w = 25.0 / 0.75
        r = 35.9 / 100.0 / 12.0
        expected_hold = gross_w / (math.pow(1 + r, 12) - 1)
        assert result["tax_amount"] == pytest.approx(gross_w - 25.0, abs=0.01)
        assert result["recurrence_hold"] == pytest.approx(expected_hold, rel=0.001)
        assert result["gross_target"] == pytest.approx(gross_w + expected_hold, rel=0.001)


class TestSavingsReadyStatus:
    """TDD: _build_savings_target_entry must expose is_ready=True when
    current_balance >= gross_target (fully accumulated, can spend now).

    'On Track' = on pace to accumulate by deadline.
    'Ready'    = already holds the full gross_target; no more growth needed.
    """

    def test_not_ready_when_balance_below_gross_target(self):
        """Happy path: balance below gross_target — not ready."""
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Car repair",
            target_amount=1000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=500.0,
            growth_rate=8.0,
            is_recurring=False,
        )
        result = _build_savings_target_entry(item, period="monthly", income_after_tax=3000.0, tax_pct=0.0)
        assert result["is_ready"] is False

    def test_ready_when_balance_meets_gross_target(self):
        """Happy path: balance == gross_target — is_ready=True."""
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Phone upgrade",
            target_amount=800.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=800.0,  # exact match
            growth_rate=8.0,
            is_recurring=False,
        )
        result = _build_savings_target_entry(item, period="monthly", income_after_tax=3000.0, tax_pct=0.0)
        assert result["is_ready"] is True

    def test_ready_when_balance_exceeds_gross_target(self):
        """Edge case: balance > gross_target — still ready."""
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Emergency fund",
            target_amount=1000.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=1200.0,
            growth_rate=8.0,
            is_recurring=False,
        )
        result = _build_savings_target_entry(item, period="monthly", income_after_tax=3000.0, tax_pct=0.0)
        assert result["is_ready"] is True

    def test_on_track_but_not_ready(self):
        """Edge case: capital_gap <= 0 (on track) but balance < gross_target — not ready."""
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        # Low rate + short horizon so current_balance barely covers PV but not gross
        item = _mock_savings_item(
            name="Slow saver",
            target_amount=1000.0,
            target_date=date.today() + timedelta(days=30),
            current_balance=990.0,  # close but below gross_target of 1000
            growth_rate=0.0,        # no growth so PV = FV; 990 < 1000 means not on track
            is_recurring=False,
        )
        result = _build_savings_target_entry(item, period="monthly", income_after_tax=3000.0, tax_pct=0.0)
        assert result["is_ready"] is False

    def test_ready_with_tax_and_recurrence_fully_funded(self):
        """Happy path: recurring + tax, balance >= gross_target — is_ready=True."""
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        target = 25.0
        tax_pct = 25.0
        balance = 500.0  # well above gross_target
        item = _mock_savings_item(
            name="Zoho Mail",
            target_amount=target,
            target_date=date.today() + timedelta(days=270),
            current_balance=balance,
            growth_rate=35.9,
            is_recurring=True,
            recurrence_months=12,
        )
        result = _build_savings_target_entry(item, period="monthly", income_after_tax=3000.0, tax_pct=tax_pct)
        # gross_target = 25/0.75 + max(500, self_sustaining_hold) — balance=500 dominates
        assert result["is_ready"] is True


# ---------------------------------------------------------------------------
# Self-sustaining hold for recurring savings targets
# ---------------------------------------------------------------------------

class TestSelfSustainingHold:
    """TDD: _compute_self_sustaining_hold returns the minimum seed to keep
    after a recurring withdrawal so it compounds back to (gross_withdrawal + hold)
    by the next cycle — making the savings permanently self-sustaining.

    Derived from: hold × (1+r)^n = gross_withdrawal + hold
                  hold = gross_withdrawal / ((1+r)^n − 1)
    """

    def test_compounding_property(self):
        """After keeping hold, it must compound back to gross_withdrawal + hold."""
        import math
        from app.services.expense_service import _compute_self_sustaining_hold

        gross_w = 100.0
        rate_pct = 12.0   # 1%/month
        months = 12
        hold = _compute_self_sustaining_hold(gross_w, rate_pct, months)
        r = rate_pct / 100.0 / 12.0
        # hold × (1+r)^n must equal gross_withdrawal + hold
        assert hold * math.pow(1 + r, months) == pytest.approx(gross_w + hold, rel=0.001)

    def test_zero_rate_returns_zero(self):
        """Cannot be self-sustaining with 0% growth — hold is 0."""
        from app.services.expense_service import _compute_self_sustaining_hold
        assert _compute_self_sustaining_hold(100.0, 0.0, 12) == pytest.approx(0.0)

    def test_zero_months_returns_zero(self):
        """No recurrence period — no hold needed."""
        from app.services.expense_service import _compute_self_sustaining_hold
        assert _compute_self_sustaining_hold(100.0, 12.0, 0) == pytest.approx(0.0)

    def test_none_months_returns_zero(self):
        """None recurrence months — treated as non-recurring, no hold."""
        from app.services.expense_service import _compute_self_sustaining_hold
        assert _compute_self_sustaining_hold(100.0, 12.0, None) == pytest.approx(0.0)

    def test_very_high_rate_hold_is_small(self):
        """At 240% annual, the self-sustaining hold on $100 is tiny (<$20)."""
        from app.services.expense_service import _compute_self_sustaining_hold
        hold = _compute_self_sustaining_hold(100.0, 240.0, 12)
        assert 0 < hold < 20.0

    def test_low_rate_large_hold(self):
        """At 8% annual, $500/yr withdrawal requires large perpetuity-like seed."""
        from app.services.expense_service import _compute_self_sustaining_hold
        # hold ≈ 500 / ((1.00667)^12 - 1) ≈ 6025
        hold = _compute_self_sustaining_hold(500.0, 8.0, 12)
        assert hold == pytest.approx(6025.0, rel=0.01)


class TestRecurringSelfSustainingGrossTarget:
    """TDD: _compute_gross_target for recurring items uses max(current_balance,
    self_sustaining_hold) as the hold component."""

    def test_zero_balance_uses_self_sustaining_hold(self):
        """With zero balance and positive rate, hold = self-sustaining seed."""
        from app.services.expense_service import _compute_gross_target
        gross_target = _compute_gross_target(
            target_amount=100.0,
            tax_pct=0.0,
            is_recurring=True,
            current_balance=0.0,
            annual_growth_rate_pct=12.0,
            recurrence_months=12,
        )
        # self_sustaining_hold ≈ 100 / ((1.01)^12 - 1) ≈ 788
        # gross_target = 100 + ~788 = ~888
        assert gross_target > 100.0

    def test_higher_balance_preserved(self):
        """When current_balance > self_sustaining_hold, balance is used."""
        from app.services.expense_service import _compute_gross_target
        # $10000 >> any sensible hold for $100/yr at 12%
        gross_target = _compute_gross_target(
            target_amount=100.0,
            tax_pct=0.0,
            is_recurring=True,
            current_balance=10000.0,
            annual_growth_rate_pct=12.0,
            recurrence_months=12,
        )
        assert gross_target == pytest.approx(10100.0, rel=0.001)

    def test_non_recurring_unaffected(self):
        """Non-recurring targets ignore hold entirely."""
        from app.services.expense_service import _compute_gross_target
        gross_target = _compute_gross_target(
            target_amount=100.0,
            tax_pct=0.0,
            is_recurring=False,
            current_balance=0.0,
            annual_growth_rate_pct=12.0,
            recurrence_months=12,
        )
        assert gross_target == pytest.approx(100.0)

    def test_zero_rate_falls_back_to_balance(self):
        """With zero rate, self-sustaining hold = 0; falls back to current_balance."""
        from app.services.expense_service import _compute_gross_target
        gross_target = _compute_gross_target(
            target_amount=100.0,
            tax_pct=0.0,
            is_recurring=True,
            current_balance=50.0,
            annual_growth_rate_pct=0.0,
            recurrence_months=12,
        )
        assert gross_target == pytest.approx(150.0)


class TestRecurringSelfSustainingHoldInEntry:
    """TDD: _build_savings_target_entry uses self-sustaining hold for
    recurrence_hold when growth rate is positive."""

    def test_zero_balance_recurring_with_rate_shows_positive_hold(self):
        """Zero balance + growth rate → recurrence_hold reflects self-sustaining seed."""
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Yearly Sub",
            target_amount=100.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=12.0,
            is_recurring=True,
            recurrence_months=12,
        )
        result = _build_savings_target_entry(
            item, period="monthly", income_after_tax=3000.0, tax_pct=0.0
        )
        # self_sustaining_hold ≈ 100 / ((1.01)^12 - 1) ≈ 788
        assert result["recurrence_hold"] > 0.0
        assert result["gross_target"] > 100.0

    def test_zero_rate_zero_balance_no_hold(self):
        """Without growth rate, hold stays 0 (cannot self-sustain from nothing)."""
        from datetime import date, timedelta
        from app.services.expense_service import _build_savings_target_entry

        item = _mock_savings_item(
            name="Monthly Fee",
            target_amount=25.0,
            target_date=date.today() + timedelta(days=365),
            current_balance=0.0,
            growth_rate=0.0,
            is_recurring=True,
            recurrence_months=12,
        )
        result = _build_savings_target_entry(
            item, period="monthly", income_after_tax=3000.0, tax_pct=0.0
        )
        assert result["recurrence_hold"] == pytest.approx(0.0, abs=0.01)
        assert result["gross_target"] == pytest.approx(25.0, abs=0.01)
