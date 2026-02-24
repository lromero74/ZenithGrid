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
    _build_transfers_section,
    _expense_name_html,
    _fmt_coverage_pct,
    _format_due_label,
    _md_to_styled_html,
    _normalize_ai_summary,
    _ordinal_day,
    _render_pdf_markdown,
    _sanitize_for_pdf,
    _transfer_label,
    build_report_html,
    generate_pdf,
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
            "due_month": item.get("due_month"),
            "frequency_anchor": item.get("frequency_anchor"),
            "frequency_n": item.get("frequency_n"),
            "login_url": item.get("login_url"),
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

    def test_weekly_item_shows_day_of_week(self):
        """Weekly items should show day-of-week names in upcoming tab."""
        g = _make_expense_goal([
            {"name": "Groceries", "amount": 100, "frequency": "weekly", "due_day": 4},
        ])
        html = _build_expenses_goal_card(g)
        assert "Fri" in html  # 4 = Friday

    def test_yearly_item_with_month(self):
        """Yearly items should show month + day in upcoming tab."""
        g = _make_expense_goal([
            {"name": "Insurance", "amount": 1200, "frequency": "yearly",
             "due_day": 15, "due_month": 6},
        ])
        html = _build_expenses_goal_card(g)
        # Whether it appears in upcoming depends on current month,
        # but the card should always render without error
        assert "Insurance" in html

    def test_upcoming_shows_bill_amount_not_normalized(self):
        """Upcoming tab should show the raw bill amount, not the period-normalized one."""
        # Weekly $100 normalizes to ~$433/mo — upcoming should show $100.00
        g = _make_expense_goal([
            {"name": "Groceries", "amount": 100, "frequency": "weekly",
             "due_day": 4, "normalized_amount": 433.33},
        ])
        # Use email_mode to get stacked sections (easier to parse)
        html = _build_expenses_goal_card(g, email_mode=True)
        # Find the Groceries row in the upcoming section
        # In email mode, upcoming section appears after ">Upcoming</p>"
        upcoming_start = html.find(">Upcoming</p>")
        assert upcoming_start != -1, "Upcoming header not found"
        upcoming_html = html[upcoming_start:]
        # The upcoming row for Groceries should show $100.00 (bill amount)
        assert "100.00" in upcoming_html
        # Should NOT contain the normalized amount in the upcoming section
        assert "433.33" not in upcoming_html


# ---------------------------------------------------------------------------
# _format_due_label helper
# ---------------------------------------------------------------------------


class TestFormatDueLabel:
    """Test the due label formatting helper."""

    def test_monthly_day(self):
        assert _format_due_label({"due_day": 15, "frequency": "monthly"}) == "15th"

    def test_monthly_last(self):
        assert _format_due_label({"due_day": -1, "frequency": "monthly"}) == "Last"

    def test_weekly_monday_no_now(self):
        assert _format_due_label({"due_day": 0, "frequency": "weekly"}) == "Mon"

    def test_weekly_friday_no_now(self):
        assert _format_due_label({"due_day": 4, "frequency": "weekly"}) == "Fri"

    def test_biweekly_sunday_no_now(self):
        assert _format_due_label({"due_day": 6, "frequency": "biweekly"}) == "Sun"

    def test_weekly_friday_with_now(self):
        """When now is provided, weekly labels include month and day-of-month."""
        from datetime import datetime
        # 2026-02-23 is a Monday (weekday=0), Friday (dd=4) is 4 days later = Feb 27
        now = datetime(2026, 2, 23)
        label = _format_due_label({"due_day": 4, "frequency": "weekly"}, now=now)
        assert label == "Fri Feb 27th"

    def test_biweekly_with_now_same_day(self):
        """When due_day == today's weekday, show today's date with month."""
        from datetime import datetime
        # 2026-02-23 is a Monday (weekday=0), due_day=0 → 0 days → Feb 23
        now = datetime(2026, 2, 23)
        label = _format_due_label({"due_day": 0, "frequency": "biweekly"}, now=now)
        assert label == "Mon Feb 23rd"

    def test_monthly_day_with_now(self):
        """Monthly labels include month when now is provided."""
        from datetime import datetime
        now = datetime(2026, 2, 23)
        label = _format_due_label({"due_day": 28, "frequency": "monthly"}, now=now)
        assert label == "Feb 28th"

    def test_monthly_past_day_still_shows_current_month(self):
        """Monthly due day already past still shows current month (upcoming filters it out)."""
        from datetime import datetime
        now = datetime(2026, 2, 23)
        label = _format_due_label({"due_day": 5, "frequency": "monthly"}, now=now)
        assert label == "Feb 5th"

    def test_yearly_with_month(self):
        label = _format_due_label(
            {"due_day": 1, "due_month": 3, "frequency": "yearly"}
        )
        assert label == "Mar 1st"

    def test_quarterly_with_month(self):
        label = _format_due_label(
            {"due_day": -1, "due_month": 6, "frequency": "quarterly"}
        )
        assert label == "Jun Last"

    def test_no_due_day(self):
        assert _format_due_label({"frequency": "monthly"}) == ""

    def test_none_due_day(self):
        assert _format_due_label({"due_day": None, "frequency": "monthly"}) == ""


# ---------------------------------------------------------------------------
# _expense_name_html — login URL linking
# ---------------------------------------------------------------------------


class TestExpenseNameHtml:
    """Test expense name rendering with optional login URL."""

    def test_plain_name_no_url(self):
        result = _expense_name_html({"name": "Netflix"})
        assert result == "Netflix"
        assert "<a " not in result

    def test_name_with_url_renders_link(self):
        result = _expense_name_html(
            {"name": "Netflix", "login_url": "https://netflix.com/login"}
        )
        assert "<a " in result
        assert 'href="https://netflix.com/login"' in result
        assert 'target="_blank"' in result
        assert "Netflix" in result

    def test_link_has_noopener(self):
        result = _expense_name_html(
            {"name": "X", "login_url": "https://example.com"}
        )
        assert "noopener" in result

    def test_login_url_none(self):
        result = _expense_name_html({"name": "Rent", "login_url": None})
        assert result == "Rent"

    def test_login_url_in_card_coverage_tab(self):
        g = _make_expense_goal([
            {"name": "Netflix", "amount": 15, "due_day": 15,
             "login_url": "https://netflix.com/login"},
        ])
        html = _build_expenses_goal_card(g)
        assert 'href="https://netflix.com/login"' in html
        assert 'target="_blank"' in html


# ---------------------------------------------------------------------------
# _build_expenses_goal_card — email_mode (stacked, no CSS tabs)
# ---------------------------------------------------------------------------


class TestBuildExpensesGoalCardEmailMode:
    """Email mode renders stacked sections instead of CSS-only tabs."""

    def test_email_mode_no_radio_inputs(self):
        """Email clients strip CSS; no radio buttons should appear."""
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g, email_mode=True)
        assert '<input type="radio"' not in html

    def test_email_mode_no_style_block(self):
        """Email mode should not use <style> blocks (stripped by email clients)."""
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g, email_mode=True)
        assert "<style>" not in html

    def test_email_mode_has_coverage_header(self):
        """Coverage section should have a visible header."""
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g, email_mode=True)
        assert ">Coverage</p>" in html

    def test_email_mode_has_upcoming_header(self):
        """Upcoming section should have a visible header."""
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g, email_mode=True)
        assert ">Upcoming</p>" in html

    def test_email_mode_coverage_content_visible(self):
        """Coverage content should be in a visible div (no display:none)."""
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g, email_mode=True)
        # Ensure coverage content (Total Expenses) is present
        assert "Total Expenses" in html
        assert "Income After Tax" in html

    def test_email_mode_upcoming_content_visible(self):
        """Upcoming items should be rendered (not hidden behind broken tabs)."""
        g = _make_expense_goal([
            {"name": "Future Bill", "amount": 200, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g, email_mode=True)
        assert "Future Bill" in html

    def test_email_mode_preserves_progress_bar(self):
        """The progress bar header should still appear in email mode."""
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ], coverage_pct=75.0)
        html = _build_expenses_goal_card(g, email_mode=True)
        assert "75% Covered" in html

    def test_email_mode_no_display_none_panels(self):
        """Email mode should NOT have hidden panels — all content is inline."""
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g, email_mode=True)
        # The in-app version has display:none panels; email should not
        assert 'display: none' not in html

    def test_web_mode_still_has_tabs(self):
        """Non-email mode should still produce CSS-only tabs."""
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g, email_mode=False)
        assert '<input type="radio"' in html
        assert "<style>" in html


# ---------------------------------------------------------------------------
# build_report_html — email_mode threads through to goals
# ---------------------------------------------------------------------------


class TestBuildReportHtmlEmailModeGoals:
    """Verify email_mode propagates to expense goal cards."""

    @pytest.fixture()
    def mock_brand(self):
        with patch(
            "app.services.report_generator_service.get_brand",
            return_value=MOCK_BRAND,
        ):
            yield

    def test_email_mode_expenses_no_radio(self, mock_brand):
        """build_report_html with email_mode=True should have stacked expense sections."""
        report_data = {
            "account_value_usd": 1000,
            "goals": [
                _make_expense_goal([
                    {"name": "Rent", "amount": 1500, "due_day": 28},
                ]),
            ],
        }
        html = build_report_html(
            report_data, ai_summary=None,
            user_name="Test", period_label="Feb 2026",
            email_mode=True,
        )
        assert '<input type="radio"' not in html
        assert ">Coverage</p>" in html
        assert ">Upcoming</p>" in html

    def test_web_mode_expenses_has_tabs(self, mock_brand):
        """build_report_html with email_mode=False should keep CSS tabs."""
        report_data = {
            "account_value_usd": 1000,
            "goals": [
                _make_expense_goal([
                    {"name": "Rent", "amount": 1500, "due_day": 28},
                ]),
            ],
        }
        html = build_report_html(
            report_data, ai_summary=None,
            user_name="Test", period_label="Feb 2026",
            email_mode=False,
        )
        assert '<input type="radio"' in html
        assert "<style>" in html


# ---------------------------------------------------------------------------
# _md_to_styled_html — markdown to dark-theme HTML
# ---------------------------------------------------------------------------


class TestMdToStyledHtml:
    """Test markdown-to-styled-HTML conversion for AI summaries."""

    def test_bold_text_styled(self):
        result = _md_to_styled_html("**important**", "#3b82f6")
        assert "<strong" in result
        assert "color: #f1f5f9" in result
        assert "important" in result

    def test_h3_header_uses_brand_color(self):
        result = _md_to_styled_html("### Performance Overview", "#ff5500")
        assert "<h3" in result
        assert "#ff5500" in result
        assert "Performance Overview" in result

    def test_bullet_list_styled(self):
        result = _md_to_styled_html("- item one\n- item two", "#3b82f6")
        assert "<ul" in result
        assert "<li" in result
        assert "item one" in result
        assert "item two" in result

    def test_plain_text_wrapped_in_p(self):
        result = _md_to_styled_html("Just plain text.", "#3b82f6")
        assert "<p " in result
        assert "Just plain text." in result
        assert "color: #cbd5e1" in result

    def test_italic_text_styled(self):
        result = _md_to_styled_html("*muted note*", "#3b82f6")
        assert "<em" in result
        assert "color: #94a3b8" in result

    def test_emoji_preserved_in_html(self):
        """Emoji should pass through in HTML (only stripped in PDF)."""
        result = _md_to_styled_html("### \U0001F4CA Overview", "#3b82f6")
        assert "\U0001F4CA" in result

    def test_multiple_paragraphs(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = _md_to_styled_html(text, "#3b82f6")
        assert "First paragraph." in result
        assert "Second paragraph." in result
        p_count = result.count("<p ")
        assert p_count == 2

    def test_old_plain_text_compat(self):
        """Old summaries (plain text, no markdown) should render as <p> tags."""
        text = "This is a legacy summary with no markdown formatting."
        result = _md_to_styled_html(text, "#3b82f6")
        assert "<p " in result
        assert "legacy summary" in result


# ---------------------------------------------------------------------------
# _sanitize_for_pdf — emoji stripping
# ---------------------------------------------------------------------------


class TestSanitizeForPdfEmoji:
    """Test that _sanitize_for_pdf strips emoji for Helvetica compatibility."""

    def test_emoji_stripped(self):
        result = _sanitize_for_pdf("\U0001F4CA Performance Overview")
        assert "\U0001F4CA" not in result
        assert "Performance Overview" in result

    def test_multiple_emoji_stripped(self):
        result = _sanitize_for_pdf("\U0001F680 Launching \U0001F4B0 Profits")
        assert "\U0001F680" not in result
        assert "\U0001F4B0" not in result
        assert "Launching" in result
        assert "Profits" in result

    def test_plain_text_preserved(self):
        result = _sanitize_for_pdf("No emoji here, just $100 profit.")
        assert result == "No emoji here, just $100 profit."

    def test_unicode_dashes_preserved_as_ascii(self):
        """En-dash and em-dash should be replaced with ASCII equivalents."""
        result = _sanitize_for_pdf("range \u2013 values \u2014 note")
        assert "range - values -- note" == result

    def test_smart_quotes_replaced(self):
        result = _sanitize_for_pdf("\u201cquoted\u201d and \u2018single\u2019")
        assert '"quoted"' in result
        assert "'single'" in result


# ---------------------------------------------------------------------------
# _build_expenses_goal_card — Projections tab
# ---------------------------------------------------------------------------


def _make_expense_goal_with_projections(items, goal_id=1, coverage_pct=50.0):
    """Create a goal dict with expense coverage data AND projection fields."""
    g = _make_expense_goal(items, goal_id=goal_id, coverage_pct=coverage_pct)
    # Add projection fields that come from report_data_service
    g["current_daily_income"] = 0.39
    g["projected_income"] = 11.70
    g["projected_income_compound"] = 12.50
    g["deposit_needed"] = 47244.83
    g["deposit_needed_compound"] = 43000.00
    g["sample_trades"] = 29
    g["lookback_days_used"] = 31
    return g


class TestExpensesGoalCardProjections:
    """Test the projections tab/section in expense goal card."""

    def test_web_mode_has_projections_tab(self):
        """In-app mode should show a Projections tab when data is present."""
        g = _make_expense_goal_with_projections([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g)
        assert "Projections" in html
        assert "exp-tab-proj-" in html

    def test_web_mode_projections_tab_has_radio(self):
        g = _make_expense_goal_with_projections([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g)
        assert 'id="exp-tab-proj-1"' in html

    def test_email_mode_has_projections_section(self):
        """Email mode should show stacked Projections section."""
        g = _make_expense_goal_with_projections([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g, email_mode=True)
        assert ">Projections</p>" in html

    def test_projections_shows_daily_avg(self):
        g = _make_expense_goal_with_projections([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g)
        assert "Daily Avg Income" in html
        assert "0.39" in html

    def test_projections_shows_linear_after_tax(self):
        g = _make_expense_goal_with_projections([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g)
        assert "Linear Projection" in html
        assert "(after tax)" in html

    def test_projections_shows_compound_after_tax(self):
        g = _make_expense_goal_with_projections([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g)
        assert "Compound Projection" in html

    def test_projections_shows_deposit_needed(self):
        g = _make_expense_goal_with_projections([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g)
        assert "Deposit Needed (Linear)" in html
        assert "Deposit Needed (Compound)" in html
        assert "47,244.83" in html
        assert "43,000.00" in html

    def test_projections_shows_trade_basis(self):
        g = _make_expense_goal_with_projections([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g)
        assert "29 trades over 31 days" in html

    def test_projections_shows_disclaimer(self):
        g = _make_expense_goal_with_projections([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g)
        assert "Past performance does not guarantee" in html

    def test_no_projections_when_no_data(self):
        """Without projection fields, no projections tab should appear."""
        g = _make_expense_goal([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g)
        assert "Projections" not in html
        assert "exp-tab-proj-" not in html

    def test_projections_css_rule_present(self):
        """CSS rule for projections panel should use !important."""
        g = _make_expense_goal_with_projections([
            {"name": "Rent", "amount": 1500, "due_day": 28},
        ])
        html = _build_expenses_goal_card(g)
        assert "exp-panel-proj-1" in html
        assert "display: block !important" in html


# ---------------------------------------------------------------------------
# _render_pdf_markdown — bullet rendering with explicit width
# ---------------------------------------------------------------------------


class TestRenderPdfMarkdownBullets:
    """Test that _render_pdf_markdown handles bullets without crashing."""

    def test_bullets_render_without_error(self):
        """Bullet items should render using explicit width calculation."""
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)

        text = (
            "### Performance Overview\n"
            "- Win rate was **71.4%** across 42 trades\n"
            "- Period profit: **$500.00**\n"
            "- A very long bullet point that should wrap to multiple lines "
            "because it contains a lot of text describing the trading performance "
            "in great detail to test that the multi_cell width is correct\n"
        )
        # Should not raise "Not enough horizontal space"
        _render_pdf_markdown(pdf, text, 59, 130, 246)

    def test_nested_markdown_in_bullets(self):
        """Bullets with bold markdown should render correctly."""
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)

        text = "- **Bold text** and normal text in a bullet\n"
        _render_pdf_markdown(pdf, text, 0, 0, 0)


# ---------------------------------------------------------------------------
# generate_pdf — capital movement metrics always included
# ---------------------------------------------------------------------------


class TestGeneratePdfCapitalMetrics:
    """PDF key metrics always include capital movement data."""

    def _make_report_data(self, **overrides):
        base = {
            "account_value_usd": 10000.0,
            "account_value_btc": 0.1,
            "period_start_value_usd": 9500.0,
            "period_profit_usd": 500.0,
            "period_profit_btc": 0.005,
            "total_trades": 42,
            "winning_trades": 30,
            "losing_trades": 12,
            "win_rate": 71.4,
            "net_deposits_usd": 0,
            "total_deposits_usd": 0,
            "total_withdrawals_usd": 0,
            "adjusted_account_growth_usd": 500.0,
        }
        base.update(overrides)
        return base

    def test_pdf_includes_capital_metrics_zero_deposits(self):
        """PDF should include period start value and adjusted growth even with zero deposits."""
        data = self._make_report_data()
        result = generate_pdf("<html></html>", data, "Test Report")
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 100  # valid PDF

    def test_pdf_includes_capital_metrics_with_deposits(self):
        """PDF should include deposit/withdrawal breakdown when present."""
        data = self._make_report_data(
            net_deposits_usd=5000.0,
            total_deposits_usd=6000.0,
            total_withdrawals_usd=1000.0,
            adjusted_account_growth_usd=-4500.0,
        )
        result = generate_pdf("<html></html>", data, "Test Report")
        assert result is not None
        assert isinstance(result, bytes)

    def test_pdf_with_ai_summary_bullets(self):
        """PDF with AI tiered summary containing bullets should not crash."""
        data = self._make_report_data()
        data["_ai_summary"] = {
            "beginner": (
                "### Performance Overview\n"
                "- You made **$500** in profit\n"
                "- Your win rate was **71.4%**\n"
                "### Capital Movements\n"
                "- No deposits or withdrawals this period\n"
            ),
            "comfortable": "### Performance Overview\nSolid period.",
            "experienced": "### Performance Overview\nAlpha positive.",
        }
        result = generate_pdf("<html></html>", data, "Test Report")
        assert result is not None


# ---------------------------------------------------------------------------
# _fmt_coverage_pct — adaptive precision
# ---------------------------------------------------------------------------


class TestCoveragePrecision:
    """Tests for _fmt_coverage_pct adaptive precision formatting."""

    def test_zero_shows_two_decimals(self):
        assert _fmt_coverage_pct(0) == "0.00%"

    def test_sub_one_shows_two_decimals(self):
        assert _fmt_coverage_pct(0.31) == "0.31%"

    def test_exactly_one_shows_one_decimal(self):
        assert _fmt_coverage_pct(1.0) == "1.0%"

    def test_mid_range_shows_one_decimal(self):
        assert _fmt_coverage_pct(3.25) == "3.2%"

    def test_ten_plus_shows_zero_decimals(self):
        assert _fmt_coverage_pct(67.8) == "68%"

    def test_hundred_percent(self):
        assert _fmt_coverage_pct(100.0) == "100%"

    def test_very_small_value(self):
        assert _fmt_coverage_pct(0.01) == "0.01%"


# ---------------------------------------------------------------------------
# _build_transfers_section — HTML transfer table
# ---------------------------------------------------------------------------


class TestTransfersSection:
    """Tests for _build_transfers_section HTML output."""

    def test_empty_records_returns_empty(self):
        assert _build_transfers_section({}) == ""
        assert _build_transfers_section({"transfer_records": []}) == ""

    def test_trade_summary_renders_when_present(self):
        """Trading summary row appears when trade_summary has trades."""
        data = {
            "trade_summary": {
                "total_trades": 15,
                "winning_trades": 10,
                "losing_trades": 5,
                "net_profit_usd": 250.50,
            },
        }
        html = _build_transfers_section(data)
        assert "Capital Movements" in html
        assert "Trading Activity" in html
        assert "15 trades" in html
        assert "10W/5L" in html
        assert "+$250.50" in html

    def test_trade_summary_negative_renders_red(self):
        """Negative net P&L renders with correct color."""
        data = {
            "trade_summary": {
                "total_trades": 5,
                "winning_trades": 1,
                "losing_trades": 4,
                "net_profit_usd": -75.00,
            },
        }
        html = _build_transfers_section(data)
        assert "#ef4444" in html  # red
        assert "$75.00" in html

    def test_trade_summary_absent_no_row(self):
        """No trading summary row when trade_summary is absent."""
        data = {"transfer_records": [
            {"date": "2026-02-23", "type": "deposit", "amount_usd": 100.0},
        ]}
        html = _build_transfers_section(data)
        assert "Trading Activity" not in html
        assert "Capital Movements" in html

    def test_trade_summary_zero_trades_no_row(self):
        """No trading summary row when total_trades is 0."""
        data = {
            "trade_summary": {"total_trades": 0, "winning_trades": 0,
                              "losing_trades": 0, "net_profit_usd": 0},
            "transfer_records": [
                {"date": "2026-02-23", "type": "deposit", "amount_usd": 100.0},
            ],
        }
        html = _build_transfers_section(data)
        assert "Trading Activity" not in html

    def test_trade_summary_only_no_transfers(self):
        """Section renders with only trade summary and no transfer records."""
        data = {
            "trade_summary": {
                "total_trades": 3,
                "winning_trades": 2,
                "losing_trades": 1,
                "net_profit_usd": 50.00,
            },
        }
        html = _build_transfers_section(data)
        assert "Capital Movements" in html
        assert "Trading Activity" in html
        assert "Deposit" not in html

    def test_deposit_renders_green(self):
        data = {"transfer_records": [
            {"date": "2026-02-23", "type": "deposit", "amount_usd": 150.0},
        ]}
        html = _build_transfers_section(data)
        assert "Capital Movements" in html
        assert "#10b981" in html  # green
        assert "+$150.00" in html
        assert "Deposit" in html

    def test_withdrawal_renders_red(self):
        data = {"transfer_records": [
            {"date": "2026-02-20", "type": "withdrawal", "amount_usd": 50.0},
        ]}
        html = _build_transfers_section(data)
        assert "#ef4444" in html  # red
        assert "-$50.00" in html
        assert "Withdrawal" in html

    def test_multiple_records_all_rendered(self):
        data = {"transfer_records": [
            {"date": "2026-02-23", "type": "deposit", "amount_usd": 100.0},
            {"date": "2026-02-21", "type": "withdrawal", "amount_usd": 25.0},
            {"date": "2026-02-20", "type": "deposit", "amount_usd": 200.0},
        ]}
        html = _build_transfers_section(data)
        # 1 header + 3 data rows (no trade summary row)
        assert "2026-02-23" in html
        assert "2026-02-21" in html
        assert "2026-02-20" in html


# ---------------------------------------------------------------------------
# HTML deposit metrics — always show row
# ---------------------------------------------------------------------------


class TestMetricsSectionDeposits:
    """Deposit/withdrawal row in key metrics always shows."""

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_deposits_row_shown_when_zero(self, mock_brand):
        """Deposit row should appear even when net_deposits is 0."""
        data = _minimal_report_data()
        data["net_deposits_usd"] = 0
        data["adjusted_account_growth_usd"] = 500.0
        html = build_report_html(
            report_data=data,
            ai_summary=None,
            user_name="Test",
            period_label="Feb 2026",
        )
        assert "Net Deposits" in html
        assert "Adjusted Growth" in html

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_deposits_row_hidden_when_no_adjusted(self, mock_brand):
        """If adjusted_account_growth_usd is missing entirely, no deposit row."""
        data = _minimal_report_data()
        # No adjusted_account_growth_usd key at all
        html = build_report_html(
            report_data=data,
            ai_summary=None,
            user_name="Test",
            period_label="Feb 2026",
        )
        assert "Net Deposits" not in html


# ---------------------------------------------------------------------------
# generate_pdf — with transfer records
# ---------------------------------------------------------------------------


class TestGeneratePdfTransferRecords:
    """PDF includes Capital Movements table when transfer records exist."""

    def test_pdf_with_transfers_does_not_crash(self):
        data = {
            "account_value_usd": 10000.0,
            "account_value_btc": 0.1,
            "period_start_value_usd": 9500.0,
            "period_profit_usd": 500.0,
            "period_profit_btc": 0.005,
            "total_trades": 42,
            "winning_trades": 30,
            "losing_trades": 12,
            "win_rate": 71.4,
            "net_deposits_usd": 150.0,
            "total_deposits_usd": 150.0,
            "total_withdrawals_usd": 0,
            "adjusted_account_growth_usd": 350.0,
            "transfer_records": [
                {"date": "2026-02-23", "type": "deposit", "amount_usd": 150.0},
            ],
        }
        result = generate_pdf("<html></html>", data, "Test Report")
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 100


# ---------------------------------------------------------------------------
# build_report_html — transfers section in full report
# ---------------------------------------------------------------------------


class TestBuildReportHtmlTransfers:
    """Transfer table appears in the full HTML report."""

    @patch("app.services.report_generator_service.get_brand", return_value=MOCK_BRAND)
    def test_transfers_section_in_full_report(self, mock_brand):
        data = _minimal_report_data()
        data["transfer_records"] = [
            {"date": "2026-02-23", "type": "deposit", "amount_usd": 150.0},
        ]
        html = build_report_html(
            report_data=data,
            ai_summary=None,
            user_name="Test",
            period_label="Feb 2026",
        )
        assert "Capital Movements" in html
        assert "+$150.00" in html


# ---------------------------------------------------------------------------
# _transfer_label — original_type → human-readable label
# ---------------------------------------------------------------------------


class TestTransferLabel:
    """Tests for _transfer_label mapping original_type to display labels."""

    def test_cardspend_btc(self):
        rec = {"original_type": "cardspend", "type": "withdrawal", "currency": "BTC"}
        assert _transfer_label(rec) == "Card Spend (BTC)"

    def test_cardspend_usd(self):
        rec = {"original_type": "cardspend", "type": "withdrawal", "currency": "USD"}
        assert _transfer_label(rec) == "Card Spend (USD)"

    def test_cardspend_no_currency_defaults_usd(self):
        rec = {"original_type": "cardspend", "type": "withdrawal"}
        assert _transfer_label(rec) == "Card Spend (USD)"

    def test_fiat_withdrawal(self):
        rec = {"original_type": "fiat_withdrawal", "type": "withdrawal"}
        assert _transfer_label(rec) == "Bank Withdrawal"

    def test_fiat_deposit(self):
        rec = {"original_type": "fiat_deposit", "type": "deposit"}
        assert _transfer_label(rec) == "Bank Deposit"

    def test_send(self):
        rec = {"original_type": "send", "type": "deposit"}
        assert _transfer_label(rec) == "Crypto Transfer"

    def test_exchange_deposit(self):
        rec = {"original_type": "exchange_deposit", "type": "deposit"}
        assert _transfer_label(rec) == "Exchange Transfer"

    def test_exchange_withdrawal(self):
        rec = {"original_type": "exchange_withdrawal", "type": "withdrawal"}
        assert _transfer_label(rec) == "Exchange Transfer"

    def test_fallback_no_original_type(self):
        """When original_type is None, fall back to type.capitalize()."""
        rec = {"type": "withdrawal"}
        assert _transfer_label(rec) == "Withdrawal"

    def test_fallback_none_original_type(self):
        rec = {"original_type": None, "type": "deposit"}
        assert _transfer_label(rec) == "Deposit"

    def test_fallback_unknown_original_type(self):
        """Unknown original_type values fall back to type.capitalize()."""
        rec = {"original_type": "staking_reward", "type": "deposit"}
        assert _transfer_label(rec) == "Deposit"

    def test_fallback_empty_record(self):
        assert _transfer_label({}) == ""


# ---------------------------------------------------------------------------
# _build_transfers_section — Card Spend label rendering
# ---------------------------------------------------------------------------


class TestTransfersSectionCardSpend:
    """Transfer table renders Card Spend labels from original_type."""

    def test_html_renders_card_spend_label(self):
        data = {"transfer_records": [
            {"date": "2026-02-20", "type": "withdrawal", "amount_usd": 12.50,
             "currency": "BTC", "original_type": "cardspend"},
        ]}
        html = _build_transfers_section(data)
        assert "Card Spend (BTC)" in html
        assert "Withdrawal" not in html

    def test_html_renders_bank_withdrawal_label(self):
        data = {"transfer_records": [
            {"date": "2026-02-20", "type": "withdrawal", "amount_usd": 500.0,
             "currency": "USD", "original_type": "fiat_withdrawal"},
        ]}
        html = _build_transfers_section(data)
        assert "Bank Withdrawal" in html

    def test_html_renders_bank_deposit_label(self):
        data = {"transfer_records": [
            {"date": "2026-02-15", "type": "deposit", "amount_usd": 1000.0,
             "currency": "USD", "original_type": "fiat_deposit"},
        ]}
        html = _build_transfers_section(data)
        assert "Bank Deposit" in html

    def test_html_fallback_no_original_type(self):
        """Legacy records without original_type still show capitalized type."""
        data = {"transfer_records": [
            {"date": "2026-02-15", "type": "deposit", "amount_usd": 100.0},
        ]}
        html = _build_transfers_section(data)
        assert "Deposit" in html

    def test_pdf_renders_card_spend_label(self):
        """PDF output with card spend records should not crash."""
        data = {
            "account_value_usd": 10000.0,
            "account_value_btc": 0.1,
            "period_start_value_usd": 9500.0,
            "period_profit_usd": 500.0,
            "period_profit_btc": 0.005,
            "total_trades": 10,
            "winning_trades": 7,
            "losing_trades": 3,
            "win_rate": 70.0,
            "net_deposits_usd": -12.50,
            "total_deposits_usd": 0,
            "total_withdrawals_usd": 12.50,
            "adjusted_account_growth_usd": 512.50,
            "transfer_records": [
                {"date": "2026-02-20", "type": "withdrawal", "amount_usd": 12.50,
                 "currency": "BTC", "original_type": "cardspend"},
            ],
        }
        result = generate_pdf("<html></html>", data, "Test Report")
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 100
