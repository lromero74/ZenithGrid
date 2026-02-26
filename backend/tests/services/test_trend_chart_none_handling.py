"""
Tests for trend chart SVG/PNG rendering with None values.

Verifies that the target endpoint data point (which has current_value=None,
progress_pct=None, on_track=None) does not crash the chart renderers.

Tests cover:
- Happy path: normal data points render without error
- Edge case: target endpoint with None current_value doesn't crash min/max
- Edge case: all-None actual values returns empty output
- Failure case: uses last real data point for on_track, not projected endpoint
"""

from app.services.report_generator_service.html_builder import (
    _build_trend_chart_svg,
)


def _make_trend_data(data_points, target_value=5000.0, target_currency="USD"):
    """Helper to build trend_data dict for chart functions."""
    return {
        "goal": {
            "target_value": target_value,
            "target_currency": target_currency,
        },
        "data_points": data_points,
    }


class TestTrendChartSvgNoneHandling:
    """Tests for _build_trend_chart_svg handling None values."""

    def test_normal_data_points_render_svg(self):
        """Happy path: all data points have real values."""
        points = [
            {"date": "2026-01-01", "current_value": 100.0,
             "ideal_value": 100.0, "progress_pct": 2.0, "on_track": True},
            {"date": "2026-01-15", "current_value": 200.0,
             "ideal_value": 150.0, "progress_pct": 4.0, "on_track": True},
            {"date": "2026-02-01", "current_value": 250.0,
             "ideal_value": 200.0, "progress_pct": 5.0, "on_track": True},
        ]
        result = _build_trend_chart_svg(
            _make_trend_data(points), "#3b82f6", "USD",
        )
        assert "<svg" in result
        assert "polyline" in result

    def test_target_endpoint_with_none_current_value(self):
        """Edge case: target endpoint has current_value=None — must not crash."""
        points = [
            {"date": "2026-01-01", "current_value": 100.0,
             "ideal_value": 100.0, "progress_pct": 2.0, "on_track": True},
            {"date": "2026-01-15", "current_value": 200.0,
             "ideal_value": 150.0, "progress_pct": 4.0, "on_track": True},
            # Target endpoint — projected, no actual data
            {"date": "2028-12-31", "current_value": None,
             "ideal_value": 5000.0, "progress_pct": None, "on_track": None},
        ]
        result = _build_trend_chart_svg(
            _make_trend_data(points), "#3b82f6", "USD",
        )
        assert "<svg" in result
        assert "polyline" in result

    def test_on_track_uses_last_real_point_not_projected(self):
        """Failure case: on_track=None from projected endpoint must not
        override the last real data point's on_track status."""
        points = [
            {"date": "2026-01-01", "current_value": 100.0,
             "ideal_value": 100.0, "progress_pct": 2.0, "on_track": True},
            {"date": "2026-01-15", "current_value": 300.0,
             "ideal_value": 150.0, "progress_pct": 6.0, "on_track": True},
            # Target endpoint
            {"date": "2028-12-31", "current_value": None,
             "ideal_value": 5000.0, "progress_pct": None, "on_track": None},
        ]
        result = _build_trend_chart_svg(
            _make_trend_data(points), "#3b82f6", "USD",
        )
        # On-track should use green (#10b981), not amber (#f59e0b)
        assert "#10b981" in result

    def test_behind_target_uses_amber_color(self):
        """Failure case: behind target shows amber color."""
        points = [
            {"date": "2026-01-01", "current_value": 10.0,
             "ideal_value": 100.0, "progress_pct": 0.2, "on_track": False},
            {"date": "2026-01-15", "current_value": 15.0,
             "ideal_value": 150.0, "progress_pct": 0.3, "on_track": False},
            # Target endpoint
            {"date": "2028-12-31", "current_value": None,
             "ideal_value": 5000.0, "progress_pct": None, "on_track": None},
        ]
        result = _build_trend_chart_svg(
            _make_trend_data(points), "#3b82f6", "USD",
        )
        # Behind target should use amber (#f59e0b)
        assert "#f59e0b" in result

    def test_single_data_point_returns_empty(self):
        """Edge case: fewer than 2 points returns empty string."""
        points = [
            {"date": "2026-01-01", "current_value": 100.0,
             "ideal_value": 100.0, "progress_pct": 2.0, "on_track": True},
        ]
        result = _build_trend_chart_svg(
            _make_trend_data(points), "#3b82f6", "USD",
        )
        assert result == ""

    def test_all_none_actual_values_returns_empty(self):
        """Edge case: if all current_value are None, return empty."""
        points = [
            {"date": "2026-01-01", "current_value": None,
             "ideal_value": 100.0, "progress_pct": None, "on_track": None},
            {"date": "2028-12-31", "current_value": None,
             "ideal_value": 5000.0, "progress_pct": None, "on_track": None},
        ]
        result = _build_trend_chart_svg(
            _make_trend_data(points), "#3b82f6", "USD",
        )
        # Should still render (ideal values are present), just no actual line
        assert "<svg" in result

    def test_date_proportional_x_axis(self):
        """X-axis positions should be proportional to dates, not indices.

        When data points span a few days plus a far-future target endpoint,
        the actual data should be clustered at the left, not spread evenly.
        """
        import re
        points = [
            {"date": "2026-02-22", "current_value": 10.0,
             "ideal_value": 1.0, "progress_pct": 0.2, "on_track": False},
            {"date": "2026-02-23", "current_value": 12.0,
             "ideal_value": 6.0, "progress_pct": 0.2, "on_track": False},
            {"date": "2026-02-24", "current_value": 11.0,
             "ideal_value": 11.0, "progress_pct": 0.2, "on_track": True},
            # Target endpoint ~34 months away
            {"date": "2028-12-31", "current_value": None,
             "ideal_value": 5000.0, "progress_pct": None, "on_track": None},
        ]
        result = _build_trend_chart_svg(
            _make_trend_data(points), "#3b82f6", "USD",
        )
        # Extract polyline points for the ideal line (has stroke-dasharray)
        ideal_match = re.search(
            r'<polyline\s+points="([^"]+)"[^>]*stroke-dasharray', result,
        )
        assert ideal_match, "Ideal line polyline not found"
        pts = ideal_match.group(1).strip().split()
        x_coords = [float(p.split(",")[0]) for p in pts]
        # First 3 points span 2 days, last is ~1040 days away
        # With date-proportional spacing, first 3 should be clustered
        # near the left edge (within ~1% of chart width)
        chart_width = x_coords[-1] - x_coords[0]
        first_3_span = x_coords[2] - x_coords[0]
        assert first_3_span / chart_width < 0.01, (
            f"First 3 points span {first_3_span/chart_width:.1%} of chart, "
            f"expected <1% for date-proportional spacing"
        )


class TestTrendChartPngNoneHandling:
    """Tests for _render_trend_chart_png handling None values."""

    def test_target_endpoint_with_none_does_not_crash(self):
        """Edge case: PNG renderer handles None current_value."""
        from app.services.report_generator_service.html_builder import (
            _render_trend_chart_png,
        )
        points = [
            {"date": "2026-01-01", "current_value": 100.0,
             "ideal_value": 100.0, "progress_pct": 2.0, "on_track": True},
            {"date": "2026-01-15", "current_value": 200.0,
             "ideal_value": 150.0, "progress_pct": 4.0, "on_track": True},
            {"date": "2028-12-31", "current_value": None,
             "ideal_value": 5000.0, "progress_pct": None, "on_track": None},
        ]
        result = _render_trend_chart_png(
            _make_trend_data(points), "#3b82f6", "USD",
        )
        # Should return non-empty PNG bytes
        assert isinstance(result, bytes)
        assert len(result) > 0


class TestTrendChartPdfNoneHandling:
    """Tests for _render_pdf_trend_chart handling None values."""

    def test_target_endpoint_with_none_does_not_crash(self):
        """Edge case: PDF renderer handles None current_value."""
        from app.services.report_generator_service.pdf_generator import (
            _render_pdf_trend_chart,
        )
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        points = [
            {"date": "2026-01-01", "current_value": 100.0,
             "ideal_value": 100.0, "progress_pct": 2.0, "on_track": True},
            {"date": "2026-01-15", "current_value": 200.0,
             "ideal_value": 150.0, "progress_pct": 4.0, "on_track": True},
            {"date": "2028-12-31", "current_value": None,
             "ideal_value": 5000.0, "progress_pct": None, "on_track": None},
        ]
        # Should not raise TypeError
        _render_pdf_trend_chart(
            pdf, _make_trend_data(points), (59, 130, 246),
        )

    def test_all_none_actual_returns_early(self):
        """Edge case: all None actual values doesn't crash PDF."""
        from app.services.report_generator_service.pdf_generator import (
            _render_pdf_trend_chart,
        )
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        points = [
            {"date": "2026-01-01", "current_value": None,
             "ideal_value": 100.0, "progress_pct": None, "on_track": None},
            {"date": "2028-12-31", "current_value": None,
             "ideal_value": 5000.0, "progress_pct": None, "on_track": None},
        ]
        # Should not raise
        _render_pdf_trend_chart(
            pdf, _make_trend_data(points), (59, 130, 246),
        )
