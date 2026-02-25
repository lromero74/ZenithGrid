"""Tests for expense change tracking between reports."""

import pytest

from app.services.report_scheduler import _compute_expense_changes
from app.services.report_generator_service.expense_builder import (
    _build_expense_changes_html,
)


# ---- Helpers to build test data ----

def _make_goal(goal_id, items):
    """Build a minimal expense goal dict with coverage items."""
    return {
        "goal_id": goal_id,
        "target_type": "expenses",
        "expense_coverage": {
            "items": items,
        },
    }


def _make_item(item_id, name, normalized_amount):
    """Build a minimal expense item dict."""
    return {
        "id": item_id,
        "name": name,
        "normalized_amount": normalized_amount,
    }


class TestComputeExpenseChanges:
    """Tests for _compute_expense_changes logic."""

    def test_increased_item(self):
        """Higher normalized_amount detected with correct delta and pct."""
        report_data = {
            "goals": [_make_goal(1, [_make_item(10, "Netflix", 18.00)])],
        }
        prior_data = {
            "goals": [_make_goal(1, [_make_item(10, "Netflix", 16.00)])],
        }
        _compute_expense_changes(report_data, prior_data)
        changes = report_data["goals"][0]["expense_changes"]
        assert "increased" in changes
        assert len(changes["increased"]) == 1
        inc = changes["increased"][0]
        assert inc["name"] == "Netflix"
        assert inc["amount"] == 18.00
        assert inc["delta"] == pytest.approx(2.00)
        assert inc["pct_delta"] == pytest.approx(12.5)

    def test_decreased_item(self):
        """Lower normalized_amount detected with negative delta."""
        report_data = {
            "goals": [_make_goal(1, [_make_item(10, "Spotify", 8.00)])],
        }
        prior_data = {
            "goals": [_make_goal(1, [_make_item(10, "Spotify", 10.00)])],
        }
        _compute_expense_changes(report_data, prior_data)
        changes = report_data["goals"][0]["expense_changes"]
        assert "decreased" in changes
        assert len(changes["decreased"]) == 1
        dec = changes["decreased"][0]
        assert dec["name"] == "Spotify"
        assert dec["amount"] == 8.00
        assert dec["delta"] == pytest.approx(-2.00)
        assert dec["pct_delta"] == pytest.approx(-20.0)

    def test_unchanged_item_excluded(self):
        """Same amount does not appear in changes."""
        report_data = {
            "goals": [_make_goal(1, [_make_item(10, "Netflix", 15.99)])],
        }
        prior_data = {
            "goals": [_make_goal(1, [_make_item(10, "Netflix", 15.99)])],
        }
        _compute_expense_changes(report_data, prior_data)
        assert "expense_changes" not in report_data["goals"][0]

    def test_added_item(self):
        """Current-only item appears in added list."""
        report_data = {
            "goals": [_make_goal(1, [
                _make_item(10, "Netflix", 15.99),
                _make_item(20, "Disney+", 12.99),
            ])],
        }
        prior_data = {
            "goals": [_make_goal(1, [_make_item(10, "Netflix", 15.99)])],
        }
        _compute_expense_changes(report_data, prior_data)
        changes = report_data["goals"][0]["expense_changes"]
        assert "added" in changes
        assert len(changes["added"]) == 1
        assert changes["added"][0]["name"] == "Disney+"
        assert changes["added"][0]["amount"] == 12.99

    def test_removed_item(self):
        """Prior-only item appears in removed list."""
        report_data = {
            "goals": [_make_goal(1, [_make_item(10, "Netflix", 15.99)])],
        }
        prior_data = {
            "goals": [_make_goal(1, [
                _make_item(10, "Netflix", 15.99),
                _make_item(20, "HBO Max", 14.00),
            ])],
        }
        _compute_expense_changes(report_data, prior_data)
        changes = report_data["goals"][0]["expense_changes"]
        assert "removed" in changes
        assert len(changes["removed"]) == 1
        assert changes["removed"][0]["name"] == "HBO Max"
        assert changes["removed"][0]["amount"] == 14.00

    def test_no_prior_goal_no_changes(self):
        """No matching prior goal means no expense_changes key."""
        report_data = {
            "goals": [_make_goal(1, [_make_item(10, "Netflix", 15.99)])],
        }
        prior_data = {
            "goals": [_make_goal(999, [_make_item(10, "Netflix", 15.99)])],
        }
        _compute_expense_changes(report_data, prior_data)
        assert "expense_changes" not in report_data["goals"][0]

    def test_small_delta_ignored(self):
        """Delta < $0.01 is ignored."""
        report_data = {
            "goals": [_make_goal(1, [_make_item(10, "Netflix", 15.999)])],
        }
        prior_data = {
            "goals": [_make_goal(1, [_make_item(10, "Netflix", 15.995)])],
        }
        _compute_expense_changes(report_data, prior_data)
        # 15.999 - 15.995 = 0.004, rounds to 0.00 delta → ignored
        assert "expense_changes" not in report_data["goals"][0]

    def test_zero_prior_amount(self):
        """Zero prior amount results in 0 pct_delta (no division by zero)."""
        report_data = {
            "goals": [_make_goal(1, [_make_item(10, "Netflix", 15.99)])],
        }
        prior_data = {
            "goals": [_make_goal(1, [_make_item(10, "Netflix", 0.00)])],
        }
        _compute_expense_changes(report_data, prior_data)
        changes = report_data["goals"][0]["expense_changes"]
        assert "increased" in changes
        inc = changes["increased"][0]
        assert inc["pct_delta"] == 0

    def test_mixed_changes(self):
        """Multiple change types in the same goal."""
        report_data = {
            "goals": [_make_goal(1, [
                _make_item(10, "Netflix", 18.00),   # increased from 16
                _make_item(20, "Spotify", 8.00),    # decreased from 10
                _make_item(30, "Disney+", 12.99),   # new
            ])],
        }
        prior_data = {
            "goals": [_make_goal(1, [
                _make_item(10, "Netflix", 16.00),
                _make_item(20, "Spotify", 10.00),
                _make_item(40, "HBO Max", 14.00),   # removed
            ])],
        }
        _compute_expense_changes(report_data, prior_data)
        changes = report_data["goals"][0]["expense_changes"]
        assert len(changes["increased"]) == 1
        assert len(changes["decreased"]) == 1
        assert len(changes["added"]) == 1
        assert len(changes["removed"]) == 1

    def test_non_expense_goals_ignored(self):
        """Non-expense goals are skipped entirely."""
        report_data = {
            "goals": [{
                "goal_id": 1,
                "target_type": "balance",
                "target_value": 10000,
            }],
        }
        prior_data = {
            "goals": [{
                "goal_id": 1,
                "target_type": "balance",
                "target_value": 10000,
            }],
        }
        _compute_expense_changes(report_data, prior_data)
        assert "expense_changes" not in report_data["goals"][0]

    def test_no_goals_no_crash(self):
        """Empty goals list doesn't crash."""
        report_data = {"goals": []}
        prior_data = {"goals": []}
        _compute_expense_changes(report_data, prior_data)

    def test_items_with_no_id_skipped(self):
        """Items without an id are skipped (not matched)."""
        report_data = {
            "goals": [_make_goal(1, [
                {"id": None, "name": "Mystery", "normalized_amount": 5.00},
            ])],
        }
        prior_data = {
            "goals": [_make_goal(1, [
                {"id": None, "name": "Mystery", "normalized_amount": 5.00},
            ])],
        }
        _compute_expense_changes(report_data, prior_data)
        assert "expense_changes" not in report_data["goals"][0]


class TestBuildExpenseChangesHtml:
    """Tests for _build_expense_changes_html rendering."""

    def test_empty_returns_empty(self):
        """None or empty dict returns empty string."""
        assert _build_expense_changes_html(None, "$", ",.2f") == ""
        assert _build_expense_changes_html({}, "$", ",.2f") == ""

    def test_increased_renders_red(self):
        """Increased items render with red color and +$ format."""
        changes = {
            "increased": [{
                "name": "Netflix",
                "amount": 18.00,
                "delta": 2.00,
                "pct_delta": 12.5,
            }],
        }
        html = _build_expense_changes_html(changes, "$", ",.2f")
        assert "#ef4444" in html
        assert "Netflix" in html
        assert "+$2.00" in html
        assert "+12.5%" in html
        assert "$18.00" in html
        assert "Changes from Prior Report" in html

    def test_decreased_renders_green(self):
        """Decreased items render with green color and -$ format."""
        changes = {
            "decreased": [{
                "name": "Spotify",
                "amount": 8.00,
                "delta": -2.00,
                "pct_delta": -20.0,
            }],
        }
        html = _build_expense_changes_html(changes, "$", ",.2f")
        assert "#10b981" in html
        assert "Spotify" in html
        assert "-$2.00" in html
        assert "-20.0%" in html

    def test_added_renders_new(self):
        """Added items render with (new) suffix."""
        changes = {
            "added": [{
                "name": "Disney+",
                "amount": 12.99,
            }],
        }
        html = _build_expense_changes_html(changes, "$", ",.2f")
        assert "(new)" in html
        assert "Disney+" in html
        assert "$12.99" in html
        assert "#f59e0b" in html

    def test_removed_renders_removed(self):
        """Removed items render with (removed) suffix and negative prefix."""
        changes = {
            "removed": [{
                "name": "HBO Max",
                "amount": 14.00,
            }],
        }
        html = _build_expense_changes_html(changes, "$", ",.2f")
        assert "(removed)" in html
        assert "HBO Max" in html
        assert "-$14.00" in html

    def test_all_sections_present(self):
        """All four section labels appear when all change types exist."""
        changes = {
            "increased": [{"name": "A", "amount": 10, "delta": 1, "pct_delta": 10}],
            "decreased": [{"name": "B", "amount": 8, "delta": -1, "pct_delta": -10}],
            "added": [{"name": "C", "amount": 5}],
            "removed": [{"name": "D", "amount": 3}],
        }
        html = _build_expense_changes_html(changes, "$", ",.2f")
        assert "Increased" in html
        assert "Decreased" in html
        assert "Added" in html
        assert "Removed" in html

    def test_btc_format(self):
        """BTC formatting uses correct prefix and decimals."""
        changes = {
            "increased": [{
                "name": "Savings",
                "amount": 0.005,
                "delta": 0.001,
                "pct_delta": 25.0,
            }],
        }
        html = _build_expense_changes_html(changes, "", ".8f")
        assert "0.00500000" in html
        assert "+0.00100000" in html
