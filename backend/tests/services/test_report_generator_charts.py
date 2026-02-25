"""
Tests for report generator chart functions (SVG, PNG, and PDF trend charts).
"""

from PIL import Image
import io

from app.services.report_generator_service import (
    _build_standard_goal_card,
    _build_trend_chart_svg,
    _format_chart_value,
    _render_trend_chart_png,
)


# ---- _format_chart_value tests ----


class TestFormatChartValue:
    """Tests for Y-axis value formatting."""

    def test_usd_large_value_millions(self):
        assert _format_chart_value(2_500_000, "USD") == "$2.5M"

    def test_usd_large_value_thousands(self):
        assert _format_chart_value(50_000, "USD") == "$50K"

    def test_usd_medium_value(self):
        assert _format_chart_value(1_500, "USD") == "$1.5K"

    def test_usd_small_value(self):
        assert _format_chart_value(500, "USD") == "$500"

    def test_usd_zero(self):
        assert _format_chart_value(0, "USD") == "$0"

    def test_btc_whole_value(self):
        assert _format_chart_value(1.5, "BTC") == "1.50"

    def test_btc_small_value(self):
        assert _format_chart_value(0.0523, "BTC") == "0.0523"

    def test_btc_zero(self):
        assert _format_chart_value(0, "BTC") == "0.0000"


# ---- _build_trend_chart_svg tests ----


class TestBuildTrendChartSvg:
    """Tests for SVG trend chart generation."""

    def _make_trend_data(self, n_points=10, on_track=True):
        """Helper to build mock trend data."""
        points = []
        for i in range(n_points):
            points.append({
                "date": f"2026-01-{i + 1:02d}",
                "current_value": 1000 + i * 100 + (50 if on_track else -50),
                "ideal_value": 1000 + i * 100,
                "progress_pct": 10 * (i + 1),
                "on_track": on_track,
            })
        return {"data_points": points}

    def test_empty_data_returns_empty(self):
        result = _build_trend_chart_svg(
            {"data_points": []}, "#3b82f6", "USD"
        )
        assert result == ""

    def test_single_point_returns_empty(self):
        result = _build_trend_chart_svg(
            {"data_points": [{"date": "2026-01-01", "current_value": 100,
                              "ideal_value": 100, "progress_pct": 50,
                              "on_track": True}]},
            "#3b82f6", "USD",
        )
        assert result == ""

    def test_valid_data_returns_svg(self):
        trend = self._make_trend_data()
        result = _build_trend_chart_svg(trend, "#3b82f6", "USD")
        assert "<svg" in result
        assert "viewBox" in result
        assert "</svg>" in result

    def test_svg_contains_polylines(self):
        trend = self._make_trend_data()
        result = _build_trend_chart_svg(trend, "#3b82f6", "USD")
        assert "<polyline" in result

    def test_svg_contains_legend(self):
        trend = self._make_trend_data()
        result = _build_trend_chart_svg(trend, "#3b82f6", "USD")
        assert "Actual" in result
        assert "Ideal" in result

    def test_svg_contains_date_labels(self):
        trend = self._make_trend_data(n_points=5)
        result = _build_trend_chart_svg(trend, "#3b82f6", "USD")
        assert "2026-01-01" in result
        assert "2026-01-05" in result

    def test_on_track_uses_green(self):
        trend = self._make_trend_data(on_track=True)
        result = _build_trend_chart_svg(trend, "#3b82f6", "USD")
        assert "#10b981" in result  # green

    def test_behind_uses_amber(self):
        trend = self._make_trend_data(on_track=False)
        result = _build_trend_chart_svg(trend, "#3b82f6", "USD")
        assert "#f59e0b" in result  # amber

    def test_brand_color_used_for_ideal(self):
        trend = self._make_trend_data()
        result = _build_trend_chart_svg(trend, "#ff0000", "USD")
        assert "#ff0000" in result

    def test_flat_values_no_crash(self):
        """All values the same should not cause division by zero."""
        points = [
            {"date": f"2026-01-{i + 1:02d}", "current_value": 500,
             "ideal_value": 500, "progress_pct": 50, "on_track": True}
            for i in range(5)
        ]
        result = _build_trend_chart_svg(
            {"data_points": points}, "#3b82f6", "USD"
        )
        assert "<svg" in result

    def test_btc_currency_formatting(self):
        points = [
            {"date": f"2026-01-{i + 1:02d}",
             "current_value": 0.05 + i * 0.01,
             "ideal_value": 0.05 + i * 0.008,
             "progress_pct": 10 * (i + 1), "on_track": True}
            for i in range(5)
        ]
        result = _build_trend_chart_svg(
            {"data_points": points}, "#3b82f6", "BTC"
        )
        assert "<svg" in result


# ---- _render_trend_chart_png tests ----


class TestRenderTrendChartPng:
    """Tests for PNG trend chart generation (email-compatible)."""

    def _make_trend_data(self, n_points=10, on_track=True):
        points = []
        for i in range(n_points):
            points.append({
                "date": f"2026-01-{i + 1:02d}",
                "current_value": 1000 + i * 100 + (50 if on_track else -50),
                "ideal_value": 1000 + i * 100,
                "progress_pct": 10 * (i + 1),
                "on_track": on_track,
            })
        return {"data_points": points}

    def test_empty_data_returns_empty_bytes(self):
        result = _render_trend_chart_png({"data_points": []}, "#3b82f6", "USD")
        assert result == b""

    def test_single_point_returns_empty_bytes(self):
        result = _render_trend_chart_png(
            {"data_points": [{"date": "2026-01-01", "current_value": 100,
                              "ideal_value": 100, "progress_pct": 50,
                              "on_track": True}]},
            "#3b82f6", "USD",
        )
        assert result == b""

    def test_valid_data_returns_png_bytes(self):
        trend = self._make_trend_data()
        result = _render_trend_chart_png(trend, "#3b82f6", "USD")
        assert isinstance(result, bytes)
        assert len(result) > 100
        # Verify it's a valid PNG (magic bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_png_dimensions_are_retina(self):
        """PNG should be 1320x400 (2x of 660x200)."""
        trend = self._make_trend_data()
        png_bytes = _render_trend_chart_png(trend, "#3b82f6", "USD")
        img = Image.open(io.BytesIO(png_bytes))
        assert img.size == (1320, 400)

    def test_on_track_vs_behind_produce_different_images(self):
        on_track = _render_trend_chart_png(
            self._make_trend_data(on_track=True), "#3b82f6", "USD"
        )
        behind = _render_trend_chart_png(
            self._make_trend_data(on_track=False), "#3b82f6", "USD"
        )
        assert on_track != behind

    def test_flat_values_no_crash(self):
        """All values the same should not cause division by zero."""
        points = [
            {"date": f"2026-01-{i + 1:02d}", "current_value": 500,
             "ideal_value": 500, "progress_pct": 50, "on_track": True}
            for i in range(5)
        ]
        result = _render_trend_chart_png(
            {"data_points": points}, "#3b82f6", "USD"
        )
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_btc_currency(self):
        points = [
            {"date": f"2026-01-{i + 1:02d}",
             "current_value": 0.05 + i * 0.01,
             "ideal_value": 0.05 + i * 0.008,
             "progress_pct": 10 * (i + 1), "on_track": True}
            for i in range(5)
        ]
        result = _render_trend_chart_png(
            {"data_points": points}, "#3b82f6", "BTC"
        )
        assert isinstance(result, bytes)
        assert len(result) > 100


# ---- _build_standard_goal_card email mode tests ----


class TestStandardGoalCardEmailMode:
    """Tests for CID image embedding in email mode goal cards."""

    def _make_goal(self, goal_id=42, on_track=True, with_trend=True):
        g = {
            "id": goal_id,
            "name": "Reach $10K",
            "target_type": "balance",
            "target_currency": "USD",
            "current_value": 7500,
            "target_value": 10000,
            "progress_pct": 75.0,
            "on_track": on_track,
        }
        if with_trend:
            g["trend_data"] = {
                "data_points": [
                    {"date": f"2026-01-{i + 1:02d}",
                     "current_value": 5000 + i * 300,
                     "ideal_value": 5000 + i * 250,
                     "progress_pct": 50 + i * 3,
                     "on_track": on_track}
                    for i in range(10)
                ]
            }
        return g

    def test_email_mode_uses_cid_img_instead_of_svg(self):
        """Email mode should embed <img src='cid:...'> instead of SVG."""
        inline_images = []
        result = _build_standard_goal_card(
            self._make_goal(), "#3b82f6",
            email_mode=True, inline_images=inline_images,
        )
        assert "<svg" not in result
        assert "cid:goal-chart-42" in result
        assert '<img' in result
        assert len(inline_images) == 1
        cid, png_bytes = inline_images[0]
        assert cid == "goal-chart-42"
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    def test_web_mode_uses_svg(self):
        """Non-email mode should use inline SVG."""
        inline_images = []
        result = _build_standard_goal_card(
            self._make_goal(), "#3b82f6",
            email_mode=False, inline_images=inline_images,
        )
        assert "<svg" in result
        assert "cid:" not in result
        assert len(inline_images) == 0

    def test_no_trend_data_no_chart(self):
        """Goal without trend data should not produce a chart."""
        inline_images = []
        result = _build_standard_goal_card(
            self._make_goal(with_trend=False), "#3b82f6",
            email_mode=True, inline_images=inline_images,
        )
        assert "<svg" not in result
        assert "cid:" not in result
        assert len(inline_images) == 0
