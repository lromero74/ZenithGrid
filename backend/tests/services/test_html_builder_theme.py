"""
Tests for HTML builder color scheme (dark vs clean theme).

Tests cover:
- Happy path: dark theme produces dark background colors
- Happy path: clean theme produces white/light background colors
- Edge case: unknown color_scheme defaults to dark (no crash)
- Clean theme does not break HTML structure
"""

from app.services.report_generator_service.html_builder import (
    _apply_clean_theme,
    build_report_html,
)


# Minimal report data for building HTML
_MINIMAL_DATA = {
    "account_value_usd": 1000.0,
    "account_value_btc": 0.01,
    "period_profit_usd": 50.0,
    "period_profit_btc": 0.0005,
    "total_trades": 10,
    "winning_trades": 7,
    "losing_trades": 3,
    "win_rate": 70.0,
    "goals": [],
}


class TestApplyCleanTheme:
    """Tests for the _apply_clean_theme post-processor."""

    def test_replaces_dark_body_bg_with_white(self):
        html = '<body style="background-color: #0f172a">'
        result = _apply_clean_theme(html)
        assert "background-color: #ffffff" in result
        assert "#0f172a" not in result

    def test_replaces_card_bg(self):
        html = '<td style="background-color: #1e293b">'
        result = _apply_clean_theme(html)
        assert "background-color: #f8fafc" in result

    def test_replaces_dark_text_with_dark_on_light(self):
        html = '<p style="color: #f1f5f9">Hello</p>'
        result = _apply_clean_theme(html)
        assert "color: #111827" in result

    def test_replaces_border_colors(self):
        html = '<div style="border: 1px solid #334155">'
        result = _apply_clean_theme(html)
        assert "border: 1px solid #e2e8f0" in result

    def test_preserves_profit_green(self):
        """Clean theme uses a slightly darker green, but still green."""
        html = '<span style="color: #10b981">+$50</span>'
        result = _apply_clean_theme(html)
        assert "color: #059669" in result

    def test_preserves_loss_red(self):
        html = '<span style="color: #ef4444">-$20</span>'
        result = _apply_clean_theme(html)
        assert "color: #dc2626" in result


class TestBuildReportHtmlColorScheme:
    """Tests for build_report_html with color_scheme parameter."""

    def test_dark_scheme_has_dark_background(self):
        html = build_report_html(
            _MINIMAL_DATA, None, "Test User", "Jan 1-7",
            color_scheme="dark",
        )
        assert "background-color: #0f172a" in html

    def test_clean_scheme_has_white_background(self):
        html = build_report_html(
            _MINIMAL_DATA, None, "Test User", "Jan 1-7",
            color_scheme="clean",
        )
        assert "background-color: #ffffff" in html
        assert "#0f172a" not in html

    def test_clean_scheme_has_dark_text(self):
        html = build_report_html(
            _MINIMAL_DATA, None, "Test User", "Jan 1-7",
            color_scheme="clean",
        )
        # Primary text should be dark
        assert "color: #111827" in html

    def test_default_is_dark(self):
        """No color_scheme param should default to dark."""
        html = build_report_html(
            _MINIMAL_DATA, None, "Test User", "Jan 1-7",
        )
        assert "background-color: #0f172a" in html

    def test_unknown_scheme_stays_dark(self):
        """Unknown color_scheme should just return dark (no replacement)."""
        html = build_report_html(
            _MINIMAL_DATA, None, "Test User", "Jan 1-7",
            color_scheme="neon",
        )
        assert "background-color: #0f172a" in html

    def test_clean_html_still_valid(self):
        """Clean theme should produce valid HTML structure."""
        html = build_report_html(
            _MINIMAL_DATA, None, "Test User", "Jan 1-7",
            color_scheme="clean",
        )
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "<body" in html
