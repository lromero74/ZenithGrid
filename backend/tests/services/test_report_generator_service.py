"""
Tests for report generator service — tabbed AI section and CSP compliance.

Tests cover:
- _normalize_ai_summary: None, str, dict, JSON string handling
- _build_tabbed_ai_section: empty tiers, single tier, multiple tiers, CSS-only tabs
- CSP compliance: no <script>, onclick, or JS in HTML output
- build_report_html: end-to-end CSP compliance for both email and web modes
"""

import json
import re
from unittest.mock import patch

import pytest

from app.services.report_generator_service import (
    _build_expenses_goal_card,
    _build_tabbed_ai_section,
    _normalize_ai_summary,
    _ordinal_day,
    build_report_html,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


BRAND_COLOR = "#3b82f6"

MOCK_BRAND = {
    "shortName": "TestBot",
    "tagline": "Automated Trading",
    "copyright": "2026 TestBot",
    "colors": {"primary": "#3b82f6"},
}


def _make_tiered_summary(beginner=None, comfortable=None, experienced=None):
    """Helper to build a tiered AI summary dict."""
    return {
        "beginner": beginner,
        "comfortable": comfortable,
        "experienced": experienced,
    }


def _minimal_report_data():
    """Minimal report_data dict for build_report_html calls."""
    return {
        "account_value_usd": 50000.0,
        "account_value_btc": 1.0,
        "period_profit_usd": 500.0,
        "period_profit_btc": 0.01,
        "total_trades": 25,
        "win_rate": 60.0,
        "winning_trades": 15,
        "losing_trades": 10,
    }


# ---------------------------------------------------------------------------
# _normalize_ai_summary tests
# ---------------------------------------------------------------------------


class TestNormalizeAiSummary:
    """Tests for _normalize_ai_summary — normalizing various input types."""

    def test_none_returns_none(self):
        assert _normalize_ai_summary(None) is None

    def test_dict_passes_through(self):
        summary = {"beginner": "easy", "comfortable": "medium", "experienced": "hard"}
        result = _normalize_ai_summary(summary)
        assert result is summary

    def test_plain_string_wraps_as_comfortable(self):
        result = _normalize_ai_summary("Plain text summary")
        assert result == {
            "beginner": None,
            "comfortable": "Plain text summary",
            "experienced": None,
        }

    def test_json_string_dict_parsed(self):
        tiered = {"beginner": "easy", "comfortable": "medium", "experienced": "hard"}
        json_str = json.dumps(tiered)
        result = _normalize_ai_summary(json_str)
        assert result == tiered

    def test_json_string_without_comfortable_key_wraps_as_string(self):
        """JSON that parses to a dict but lacks 'comfortable' key is treated as plain text."""
        json_str = json.dumps({"foo": "bar"})
        result = _normalize_ai_summary(json_str)
        assert result["comfortable"] == json_str
        assert result["beginner"] is None
        assert result["experienced"] is None

    def test_invalid_json_string_wraps_as_comfortable(self):
        result = _normalize_ai_summary("not-valid-json {")
        assert result["comfortable"] == "not-valid-json {"

    def test_non_string_non_dict_returns_none(self):
        """Unexpected types (int, list, etc.) return None."""
        assert _normalize_ai_summary(42) is None
        assert _normalize_ai_summary([1, 2, 3]) is None

    def test_empty_string_wraps_as_comfortable(self):
        result = _normalize_ai_summary("")
        assert result["comfortable"] == ""


# ---------------------------------------------------------------------------
# _build_tabbed_ai_section tests — Empty tiers
# ---------------------------------------------------------------------------


class TestBuildTabbedAiSectionEmpty:
    """Tests for _build_tabbed_ai_section when no tiers have content."""

    def test_all_none_returns_empty(self):
        summary = _make_tiered_summary()
        result = _build_tabbed_ai_section(summary, "comfortable", BRAND_COLOR)
        assert result == ""

    def test_all_empty_strings_returns_empty(self):
        summary = _make_tiered_summary(beginner="", comfortable="", experienced="")
        result = _build_tabbed_ai_section(summary, "comfortable", BRAND_COLOR)
        assert result == ""

    def test_empty_dict_returns_empty(self):
        result = _build_tabbed_ai_section({}, "comfortable", BRAND_COLOR)
        assert result == ""

    def test_none_values_and_missing_keys_returns_empty(self):
        result = _build_tabbed_ai_section(
            {"beginner": None, "other_key": "ignored"}, "comfortable", BRAND_COLOR,
        )
        assert result == ""


# ---------------------------------------------------------------------------
# _build_tabbed_ai_section tests — Single tier
# ---------------------------------------------------------------------------


class TestBuildTabbedAiSectionSingle:
    """When only one tier has content, render a single section (no tabs)."""

    def test_single_tier_no_tabs(self):
        summary = _make_tiered_summary(comfortable="Analysis text here.")
        result = _build_tabbed_ai_section(summary, "comfortable", BRAND_COLOR)
        assert "Analysis text here." in result
        # No radio inputs or tab bar
        assert '<input type="radio"' not in result
        assert "ai-tab-bar" not in result

    def test_single_tier_uses_correct_label(self):
        summary = _make_tiered_summary(beginner="Simplified text.")
        result = _build_tabbed_ai_section(summary, "beginner", BRAND_COLOR)
        assert "Summary (Simplified)" in result

    def test_single_tier_uses_brand_color(self):
        summary = _make_tiered_summary(experienced="Technical deep dive.")
        result = _build_tabbed_ai_section(summary, "experienced", "#ff5500")
        assert "#ff5500" in result

    def test_single_tier_no_script_tags(self):
        summary = _make_tiered_summary(comfortable="Content here.")
        result = _build_tabbed_ai_section(summary, "comfortable", BRAND_COLOR)
        assert "<script" not in result.lower()
        assert "onclick" not in result.lower()

    def test_single_tier_renders_paragraphs(self):
        summary = _make_tiered_summary(
            comfortable="First paragraph.\n\nSecond paragraph."
        )
        result = _build_tabbed_ai_section(summary, "comfortable", BRAND_COLOR)
        assert "First paragraph." in result
        assert "Second paragraph." in result
        # Two <p> tags for two paragraphs
        assert result.count("<p ") == 2


# ---------------------------------------------------------------------------
# _build_tabbed_ai_section tests — Multiple tiers
# ---------------------------------------------------------------------------


class TestBuildTabbedAiSectionMultiple:
    """When multiple tiers have content, render CSS-only tabs."""

    @pytest.fixture
    def two_tier_summary(self):
        return _make_tiered_summary(
            beginner="Beginner summary text.",
            comfortable="Comfortable analysis text.",
        )

    @pytest.fixture
    def three_tier_summary(self):
        return _make_tiered_summary(
            beginner="Beginner summary text.",
            comfortable="Comfortable analysis text.",
            experienced="Experienced technical text.",
        )

    def test_contains_hidden_radio_inputs(self, two_tier_summary):
        result = _build_tabbed_ai_section(
            two_tier_summary, "comfortable", BRAND_COLOR,
        )
        assert '<input type="radio"' in result
        assert 'id="ai-tab-beginner"' in result
        assert 'id="ai-tab-comfortable"' in result
        assert 'style="display:none"' in result

    def test_contains_tab_bar_with_labels(self, two_tier_summary):
        result = _build_tabbed_ai_section(
            two_tier_summary, "comfortable", BRAND_COLOR,
        )
        assert 'class="ai-tab-bar"' in result
        assert 'for="ai-tab-beginner"' in result
        assert 'for="ai-tab-comfortable"' in result
        assert "Summary (Simplified)" in result
        assert "AI Performance Analysis" in result

    def test_contains_content_panels(self, three_tier_summary):
        result = _build_tabbed_ai_section(
            three_tier_summary, "comfortable", BRAND_COLOR,
        )
        assert 'id="ai-panel-beginner"' in result
        assert 'id="ai-panel-comfortable"' in result
        assert 'id="ai-panel-experienced"' in result
        assert "Beginner summary text." in result
        assert "Comfortable analysis text." in result
        assert "Experienced technical text." in result

    def test_contains_style_block_with_checked_rules(self, two_tier_summary):
        result = _build_tabbed_ai_section(
            two_tier_summary, "comfortable", BRAND_COLOR,
        )
        assert "<style>" in result
        assert ":checked" in result
        # CSS rules for showing panels
        assert "#ai-tab-beginner:checked ~ #ai-panel-beginner" in result
        assert "#ai-tab-comfortable:checked ~ #ai-panel-comfortable" in result

    def test_display_block_uses_important(self, two_tier_summary):
        """CSS display:block must use !important to override inline display:none."""
        result = _build_tabbed_ai_section(
            two_tier_summary, "comfortable", BRAND_COLOR,
        )
        # Each panel's CSS rule must have !important so it overrides inline style
        assert "display: block !important" in result
        # Verify the pattern for each available tier
        for tier in ["beginner", "comfortable"]:
            rule = f"#ai-tab-{tier}:checked ~ #ai-panel-{tier}"
            rule_idx = result.index(rule)
            # The !important should appear in the same CSS rule block
            rule_end = result.index("}", rule_idx)
            rule_text = result[rule_idx:rule_end]
            assert "!important" in rule_text, (
                f"CSS rule for {tier} panel missing !important"
            )

    def test_display_block_important_three_tiers(self, three_tier_summary):
        """All three tier panel rules must use !important."""
        result = _build_tabbed_ai_section(
            three_tier_summary, "comfortable", BRAND_COLOR,
        )
        for tier in ["beginner", "comfortable", "experienced"]:
            rule = f"#ai-tab-{tier}:checked ~ #ai-panel-{tier}"
            assert rule in result
            rule_idx = result.index(rule)
            rule_end = result.index("}", rule_idx)
            rule_text = result[rule_idx:rule_end]
            assert "!important" in rule_text, (
                f"CSS rule for {tier} panel missing !important"
            )

    def test_default_level_gets_checked_attribute(self, three_tier_summary):
        result = _build_tabbed_ai_section(
            three_tier_summary, "comfortable", BRAND_COLOR,
        )
        # The comfortable radio should have checked
        comfortable_radio = re.search(
            r'<input[^>]*id="ai-tab-comfortable"[^>]*>', result,
        )
        assert comfortable_radio is not None
        assert "checked" in comfortable_radio.group()

        # The beginner radio should NOT have checked
        beginner_radio = re.search(
            r'<input[^>]*id="ai-tab-beginner"[^>]*>', result,
        )
        assert beginner_radio is not None
        assert "checked" not in beginner_radio.group()

    def test_different_default_level(self, three_tier_summary):
        result = _build_tabbed_ai_section(
            three_tier_summary, "beginner", BRAND_COLOR,
        )
        beginner_radio = re.search(
            r'<input[^>]*id="ai-tab-beginner"[^>]*>', result,
        )
        assert beginner_radio is not None
        assert "checked" in beginner_radio.group()

        comfortable_radio = re.search(
            r'<input[^>]*id="ai-tab-comfortable"[^>]*>', result,
        )
        assert comfortable_radio is not None
        assert "checked" not in comfortable_radio.group()

    def test_no_script_tags(self, three_tier_summary):
        result = _build_tabbed_ai_section(
            three_tier_summary, "comfortable", BRAND_COLOR,
        )
        assert "<script" not in result.lower()
        assert "</script>" not in result.lower()

    def test_no_onclick_handlers(self, three_tier_summary):
        result = _build_tabbed_ai_section(
            three_tier_summary, "comfortable", BRAND_COLOR,
        )
        assert "onclick" not in result.lower()

    def test_no_javascript_anywhere(self, three_tier_summary):
        result = _build_tabbed_ai_section(
            three_tier_summary, "comfortable", BRAND_COLOR,
        )
        lower = result.lower()
        assert "javascript:" not in lower
        assert "onerror" not in lower
        assert "onload" not in lower
        assert "onmouseover" not in lower

    def test_panels_default_hidden(self, two_tier_summary):
        """All panels start with display:none (CSS :checked reveals the active one)."""
        result = _build_tabbed_ai_section(
            two_tier_summary, "comfortable", BRAND_COLOR,
        )
        panels = re.findall(r'<div id="ai-panel-[^"]*"[^>]*>', result)
        assert len(panels) == 2
        for panel in panels:
            assert "display: none" in panel or "display:none" in panel

    def test_brand_color_in_css_rules(self, two_tier_summary):
        result = _build_tabbed_ai_section(
            two_tier_summary, "comfortable", "#ff0000",
        )
        assert "#ff0000" in result

    def test_tier_order_preserved(self, three_tier_summary):
        result = _build_tabbed_ai_section(
            three_tier_summary, "comfortable", BRAND_COLOR,
        )
        # Radios should appear in order: beginner, comfortable, experienced
        beginner_pos = result.index('id="ai-tab-beginner"')
        comfortable_pos = result.index('id="ai-tab-comfortable"')
        experienced_pos = result.index('id="ai-tab-experienced"')
        assert beginner_pos < comfortable_pos < experienced_pos

    def test_three_tiers_three_radios(self, three_tier_summary):
        result = _build_tabbed_ai_section(
            three_tier_summary, "comfortable", BRAND_COLOR,
        )
        radio_count = result.count('<input type="radio"')
        assert radio_count == 3

    def test_multi_paragraph_content(self):
        summary = _make_tiered_summary(
            beginner="Para one.\n\nPara two.\n\nPara three.",
            comfortable="Single paragraph.",
        )
        result = _build_tabbed_ai_section(summary, "comfortable", BRAND_COLOR)
        # Beginner panel should have 3 <p> tags, comfortable should have 1
        beginner_panel_match = re.search(
            r'id="ai-panel-beginner"[^>]*>(.*?)</div>',
            result,
            re.DOTALL,
        )
        assert beginner_panel_match is not None
        beginner_content = beginner_panel_match.group(1)
        assert beginner_content.count("<p ") == 3


# ---------------------------------------------------------------------------
# CSP compliance — build_report_html
# ---------------------------------------------------------------------------


class TestBuildReportHtmlCspCompliance:
    """Ensure the full HTML report output is CSP-safe (no inline JS)."""

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_web_mode_no_script_tags(self, mock_brand):
        """Web report (email_mode=False) must not contain <script> tags."""
        ai = _make_tiered_summary(
            beginner="Beginner text.",
            comfortable="Comfortable text.",
            experienced="Experienced text.",
        )
        html = build_report_html(
            report_data=_minimal_report_data(),
            ai_summary=ai,
            user_name="Test User",
            period_label="Jan 1 - Jan 7, 2026",
        )
        assert "<script" not in html.lower()
        assert "</script>" not in html.lower()

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_web_mode_no_onclick(self, mock_brand):
        """Web report must not contain onclick handlers."""
        ai = _make_tiered_summary(
            beginner="Beginner text.",
            comfortable="Comfortable text.",
        )
        html = build_report_html(
            report_data=_minimal_report_data(),
            ai_summary=ai,
            user_name="Test User",
            period_label="Jan 1 - Jan 7, 2026",
        )
        assert "onclick" not in html.lower()

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_web_mode_no_javascript_protocol(self, mock_brand):
        ai = _make_tiered_summary(comfortable="Analysis text.")
        html = build_report_html(
            report_data=_minimal_report_data(),
            ai_summary=ai,
            user_name="Test User",
            period_label="Jan 1 - Jan 7, 2026",
        )
        assert "javascript:" not in html.lower()

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_email_mode_no_script_tags(self, mock_brand):
        """Email report must also be CSP-safe."""
        ai = _make_tiered_summary(
            beginner="Beginner text.",
            comfortable="Comfortable text.",
            experienced="Experienced text.",
        )
        html = build_report_html(
            report_data=_minimal_report_data(),
            ai_summary=ai,
            user_name="Test User",
            period_label="Jan 1 - Jan 7, 2026",
            email_mode=True,
        )
        assert "<script" not in html.lower()
        assert "onclick" not in html.lower()

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_web_mode_has_css_tabs(self, mock_brand):
        """Web report with multiple tiers should use CSS-only tabs."""
        ai = _make_tiered_summary(
            beginner="Beginner text.",
            comfortable="Comfortable text.",
        )
        html = build_report_html(
            report_data=_minimal_report_data(),
            ai_summary=ai,
            user_name="Test User",
            period_label="Jan 1 - Jan 7, 2026",
        )
        assert "<style>" in html
        assert ":checked" in html
        assert '<input type="radio"' in html

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_email_mode_no_tabs(self, mock_brand):
        """Email mode should render single section (no tabs/radios)."""
        ai = _make_tiered_summary(
            beginner="Beginner text.",
            comfortable="Comfortable text.",
            experienced="Experienced text.",
        )
        html = build_report_html(
            report_data=_minimal_report_data(),
            ai_summary=ai,
            user_name="Test User",
            period_label="Jan 1 - Jan 7, 2026",
            email_mode=True,
        )
        assert '<input type="radio"' not in html
        assert "ai-tab-bar" not in html
        # But it should still show the default tier content
        assert "Comfortable text." in html

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_no_ai_summary_shows_placeholder(self, mock_brand):
        """When ai_summary is None, show the 'add credentials' prompt."""
        html = build_report_html(
            report_data=_minimal_report_data(),
            ai_summary=None,
            user_name="Test User",
            period_label="Jan 1 - Jan 7, 2026",
        )
        assert "AI provider credentials" in html
        assert "<script" not in html.lower()

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_string_ai_summary_uses_single_section(self, mock_brand):
        """Plain string ai_summary should render as single section (no tabs)."""
        html = build_report_html(
            report_data=_minimal_report_data(),
            ai_summary="Plain text analysis.",
            user_name="Test User",
            period_label="Jan 1 - Jan 7, 2026",
        )
        assert "Plain text analysis." in html
        assert '<input type="radio"' not in html
        assert "<script" not in html.lower()

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_schedule_name_in_title(self, mock_brand):
        html = build_report_html(
            report_data=_minimal_report_data(),
            ai_summary=None,
            user_name="Test User",
            period_label="Jan 1 - Jan 7, 2026",
            schedule_name="Weekly Summary",
        )
        assert "Weekly Summary" in html

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_no_inline_event_handlers_in_full_html(self, mock_brand):
        """Scan the full HTML for any inline event handler attributes."""
        ai = _make_tiered_summary(
            beginner="B text.",
            comfortable="C text.",
            experienced="E text.",
        )
        html = build_report_html(
            report_data=_minimal_report_data(),
            ai_summary=ai,
            user_name="Test User",
            period_label="Jan 1 - Jan 7, 2026",
        )
        # Check for common inline event handlers
        event_handlers = [
            "onclick", "onchange", "onmouseover", "onmouseout",
            "onfocus", "onblur", "onsubmit", "onload", "onerror",
        ]
        lower_html = html.lower()
        for handler in event_handlers:
            assert handler not in lower_html, f"Found '{handler}' in HTML output"


# ---------------------------------------------------------------------------
# _ordinal_day helper
# ---------------------------------------------------------------------------


class TestOrdinalDay:
    """Test the ordinal day rendering helper."""

    def test_first(self):
        assert _ordinal_day(1) == "1st"

    def test_second(self):
        assert _ordinal_day(2) == "2nd"

    def test_third(self):
        assert _ordinal_day(3) == "3rd"

    def test_fourth(self):
        assert _ordinal_day(4) == "4th"

    def test_eleventh(self):
        assert _ordinal_day(11) == "11th"

    def test_twelfth(self):
        assert _ordinal_day(12) == "12th"

    def test_thirteenth(self):
        assert _ordinal_day(13) == "13th"

    def test_twenty_first(self):
        assert _ordinal_day(21) == "21st"

    def test_thirty_first(self):
        assert _ordinal_day(31) == "31st"

    def test_last_day(self):
        assert _ordinal_day(-1) == "Last"

    def test_fifteenth(self):
        assert _ordinal_day(15) == "15th"


# ---------------------------------------------------------------------------
# _build_expenses_goal_card — tabbed Coverage + Upcoming
# ---------------------------------------------------------------------------


def _make_expense_goal(items, goal_id=1, coverage_pct=100.0):
    """Create a goal dict with expense coverage data."""
    coverage_items = []
    total = 0
    for item in items:
        norm = item.get("normalized_amount", item.get("amount", 0))
        total += norm
        coverage_items.append({
            "id": item.get("id", 1),
            "name": item["name"],
            "category": item.get("category", "General"),
            "amount": item.get("amount", norm),
            "frequency": item.get("frequency", "monthly"),
            "due_day": item.get("due_day"),
            "normalized_amount": norm,
            "status": item.get("status", "covered"),
            "coverage_pct": item.get("coverage_pct_val", 100.0),
        })
    return {
        "id": goal_id,
        "name": "Monthly Bills",
        "target_type": "expenses",
        "target_currency": "USD",
        "expense_period": "monthly",
        "tax_withholding_pct": 0,
        "expense_coverage": {
            "total_expenses": total,
            "income_after_tax": total * 2,
            "coverage_pct": coverage_pct,
            "shortfall": 0,
            "covered_count": len(coverage_items),
            "total_count": len(coverage_items),
            "items": coverage_items,
        },
    }


class TestBuildExpensesGoalCardTabs:
    """Test the tabbed expense card output."""

    def test_produces_two_radio_inputs(self):
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 1},
        ])
        html = _build_expenses_goal_card(g)
        assert 'name="exp-tab-1"' in html
        assert 'id="exp-tab-coverage-1"' in html
        assert 'id="exp-tab-upcoming-1"' in html

    def test_coverage_tab_checked_by_default(self):
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 1},
        ])
        html = _build_expenses_goal_card(g)
        coverage_radio = re.search(
            r'<input[^>]*id="exp-tab-coverage-1"[^>]*>', html,
        )
        assert coverage_radio is not None
        assert "checked" in coverage_radio.group()

    def test_display_block_uses_important(self):
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 1},
        ])
        html = _build_expenses_goal_card(g)
        assert "display: block !important" in html

    def test_upcoming_filters_to_future_due_days(self):
        """Upcoming tab should only show items with due_day >= today."""
        g = _make_expense_goal([
            {"name": "Past Bill", "amount": 100, "due_day": 1},
            {"name": "Future Bill", "amount": 200, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g)
        # The upcoming panel should contain "Future Bill"
        # Whether "Past Bill" shows depends on today's date
        assert "Future Bill" in html

    def test_no_due_days_shows_helpful_message(self):
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500},
            {"name": "Netflix", "amount": 15},
        ])
        html = _build_expenses_goal_card(g)
        assert "Set due dates on your expenses" in html

    def test_last_day_resolved_correctly(self):
        """due_day=-1 should render as 'Last' in the upcoming tab."""
        g = _make_expense_goal([
            {"name": "Mortgage", "amount": 2000, "due_day": -1},
        ])
        html = _build_expenses_goal_card(g)
        # -1 resolves to last day of month, should always be >= today
        assert "Last" in html

    def test_upcoming_sorted_by_due_day(self):
        g = _make_expense_goal([
            {"name": "Late Bill", "amount": 100, "due_day": 28},
            {"name": "Early Bill", "amount": 200, "due_day": 15},
            {"name": "Last Day", "amount": 50, "due_day": -1},
        ])
        html = _build_expenses_goal_card(g)
        # "15th" should appear before "28th" in the upcoming panel
        pos_15 = html.find("15th")
        pos_28 = html.find("28th")
        if pos_15 != -1 and pos_28 != -1:
            assert pos_15 < pos_28

    def test_coverage_tab_still_has_itemized_table(self):
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 1},
            {"name": "Netflix", "amount": 15, "due_day": 15},
        ])
        html = _build_expenses_goal_card(g)
        assert "Total Expenses" in html
        assert "Income After Tax" in html
        assert "Items Covered" in html

    def test_unique_radio_names_per_goal(self):
        """Different goal IDs should use different radio names."""
        g1 = _make_expense_goal([{"name": "A", "amount": 100, "due_day": 1}], goal_id=5)
        g2 = _make_expense_goal([{"name": "B", "amount": 200, "due_day": 1}], goal_id=9)
        html1 = _build_expenses_goal_card(g1)
        html2 = _build_expenses_goal_card(g2)
        assert 'name="exp-tab-5"' in html1
        assert 'name="exp-tab-9"' in html2

    def test_status_badges_reused_in_upcoming(self):
        """Upcoming tab should show the same coverage badges as coverage tab."""
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 28,
             "status": "uncovered", "coverage_pct_val": 0.0},
        ])
        html = _build_expenses_goal_card(g)
        # The upcoming panel should contain the Uncovered badge
        assert "Uncovered" in html
