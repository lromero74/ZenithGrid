"""
Tests for report generator chart functions (SVG and PDF trend charts).
"""

from app.services.report_generator_service import (
    _build_trend_chart_svg,
    _format_chart_value,
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
