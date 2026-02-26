"""
Tests for chart horizon computation and minimap support.

Tests compute_horizon_date() and clip_trend_data() utilities used by
goal trend charts to limit the visible date range and enable minimap rendering.
"""

from datetime import datetime, timedelta


class TestComputeHorizonDate:
    """Tests for compute_horizon_date() utility."""

    def _make_points(self, start_date: str, num_days: int):
        """Helper: generate data_points spanning num_days from start_date."""
        start = datetime.strptime(start_date, "%Y-%m-%d")
        return [
            {
                "date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
                "current_value": 100 + i * 10,
                "ideal_value": 100 + i * 5,
                "progress_pct": 50 + i,
                "on_track": True,
            }
            for i in range(num_days + 1)  # inclusive of start
        ]

    def test_auto_horizon_default_period(self):
        """Auto mode with default period (30 days) and multiplier (1.0) → 30-day look-ahead."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 10)
        target = (datetime(2026, 1, 1) + timedelta(days=1000)).strftime("%Y-%m-%d")

        result = compute_horizon_date(points, target, "auto")
        result_date = datetime.strptime(result, "%Y-%m-%d")
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")

        expected = last_data + timedelta(days=30)
        assert result_date == expected

    def test_auto_horizon_weekly_period(self):
        """Auto mode with weekly period (7 days) × multiplier 1.0 → 7-day look-ahead."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 10)
        target = (datetime(2026, 1, 1) + timedelta(days=1000)).strftime("%Y-%m-%d")

        result = compute_horizon_date(
            points, target, "auto",
            schedule_period_days=7, lookahead_multiplier=1.0,
        )
        result_date = datetime.strptime(result, "%Y-%m-%d")
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")

        expected = last_data + timedelta(days=7)
        assert result_date == expected

    def test_auto_horizon_quarterly_with_fractional_multiplier(self):
        """Quarterly period (90 days) × 0.33 multiplier → ~30-day look-ahead."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 10)
        target = (datetime(2026, 1, 1) + timedelta(days=1000)).strftime("%Y-%m-%d")

        result = compute_horizon_date(
            points, target, "auto",
            schedule_period_days=90, lookahead_multiplier=0.33,
        )
        result_date = datetime.strptime(result, "%Y-%m-%d")
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")

        # int(90 * 0.33) = 29 days
        expected = last_data + timedelta(days=29)
        assert result_date == expected

    def test_auto_horizon_multiplier_3x(self):
        """Monthly period (30 days) × 3.0 multiplier → 90-day look-ahead."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 10)
        target = (datetime(2026, 1, 1) + timedelta(days=1000)).strftime("%Y-%m-%d")

        result = compute_horizon_date(
            points, target, "auto",
            schedule_period_days=30, lookahead_multiplier=3.0,
        )
        result_date = datetime.strptime(result, "%Y-%m-%d")
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")

        expected = last_data + timedelta(days=90)
        assert result_date == expected

    def test_auto_horizon_minimum_1_day(self):
        """Look-ahead is at least 1 day even with tiny multiplier."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 10)
        target = (datetime(2026, 1, 1) + timedelta(days=1000)).strftime("%Y-%m-%d")

        result = compute_horizon_date(
            points, target, "auto",
            schedule_period_days=1, lookahead_multiplier=0.001,
        )
        result_date = datetime.strptime(result, "%Y-%m-%d")
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")

        expected = last_data + timedelta(days=1)
        assert result_date == expected

    def test_auto_horizon_target_within_range(self):
        """When target is near the data, horizon is capped at target."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 10)
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")
        # Target is only 5 days beyond last data point
        target = (last_data + timedelta(days=5)).strftime("%Y-%m-%d")

        # Default auto: 30-day look-ahead, but capped at target (5 days away)
        result = compute_horizon_date(points, target, "auto")
        assert result == target

    def test_full_horizon_returns_target(self):
        """chart_horizon='full' always returns target_date."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 10)
        target = "2029-01-01"

        result = compute_horizon_date(points, target, "full")
        assert result == target

    def test_custom_days_horizon(self):
        """chart_horizon='90' returns 90 days from last data point."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 10)
        target = "2029-01-01"

        result = compute_horizon_date(points, target, "90")
        result_date = datetime.strptime(result, "%Y-%m-%d")
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")

        expected = last_data + timedelta(days=90)
        assert result_date == expected

    def test_custom_days_capped_at_target(self):
        """Custom days horizon should not exceed target date."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 10)
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")
        target = (last_data + timedelta(days=30)).strftime("%Y-%m-%d")

        result = compute_horizon_date(points, target, "90")
        assert result == target

    def test_empty_data_points_returns_target(self):
        """With no data points, return target date as fallback."""
        from app.services.goal_snapshot_service import compute_horizon_date

        result = compute_horizon_date([], "2029-01-01", "auto")
        assert result == "2029-01-01"

    def test_single_data_point(self):
        """With single point, use default auto look-ahead (30 days)."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = [{"date": "2026-01-01", "current_value": 100,
                   "ideal_value": 100, "progress_pct": 0, "on_track": True}]
        target = "2029-01-01"

        result = compute_horizon_date(points, target, "auto")
        result_date = datetime.strptime(result, "%Y-%m-%d")
        expected = datetime(2026, 1, 1) + timedelta(days=30)
        assert result_date == expected

    def test_elapsed_fraction(self):
        """Elapsed mode: look-ahead = elapsed_days × fraction."""
        from app.services.goal_snapshot_service import compute_horizon_date

        # 12 days of data, fraction 0.33 → look-ahead = int(12 * 0.33) = 3 days
        points = self._make_points("2026-01-01", 12)
        target = "2029-01-01"

        result = compute_horizon_date(
            points, target, "elapsed",
            lookahead_multiplier=0.33,
        )
        result_date = datetime.strptime(result, "%Y-%m-%d")
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")

        expected = last_data + timedelta(days=3)  # int(12 * 0.33) = 3
        assert result_date == expected

    def test_elapsed_fraction_1x(self):
        """Elapsed mode with multiplier 1.0: look-ahead = elapsed_days."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 20)
        target = "2029-01-01"

        result = compute_horizon_date(
            points, target, "elapsed",
            lookahead_multiplier=1.0,
        )
        result_date = datetime.strptime(result, "%Y-%m-%d")
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")

        expected = last_data + timedelta(days=20)
        assert result_date == expected

    def test_elapsed_single_data_point_minimum(self):
        """Elapsed mode with 1 data point: elapsed=1 (min), look-ahead ≥ 1."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = [{"date": "2026-01-01", "current_value": 100,
                   "ideal_value": 100, "progress_pct": 0, "on_track": True}]
        target = "2029-01-01"

        result = compute_horizon_date(
            points, target, "elapsed",
            lookahead_multiplier=0.5,
        )
        result_date = datetime.strptime(result, "%Y-%m-%d")
        # elapsed=0 → max(0,1)=1, int(1*0.5)=0 → max(0,1)=1
        expected = datetime(2026, 1, 1) + timedelta(days=1)
        assert result_date == expected

    def test_elapsed_capped_at_target(self):
        """Elapsed mode should cap at target date."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 100)
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")
        target = (last_data + timedelta(days=10)).strftime("%Y-%m-%d")

        result = compute_horizon_date(
            points, target, "elapsed",
            lookahead_multiplier=1.0,
        )
        # 100 days elapsed × 1.0 = 100-day look-ahead, but target is only 10 days away
        assert result == target


class TestClipTrendData:
    """Tests for clip_trend_data() utility."""

    def _make_trend_data(self, start_date: str, num_days: int, target_date: str):
        """Helper: generate a full trend_data dict."""
        start = datetime.strptime(start_date, "%Y-%m-%d")
        data_points = []
        for i in range(num_days + 1):
            dt = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            data_points.append({
                "date": dt,
                "current_value": 100 + i * 10,
                "ideal_value": 100 + i * 5,
                "progress_pct": 50 + i,
                "on_track": True,
            })
        # Add target endpoint (ideal-only)
        data_points.append({
            "date": target_date,
            "current_value": None,
            "ideal_value": 500,
            "progress_pct": None,
            "on_track": None,
        })
        return {
            "goal": {"id": 1, "name": "Test", "start_date": start_date,
                     "target_date": target_date},
            "ideal_start_value": 100,
            "ideal_end_value": 500,
            "data_points": data_points,
        }

    def test_clip_removes_points_beyond_horizon(self):
        """Points beyond horizon_date should be removed; synthetic endpoint at horizon."""
        from app.services.goal_snapshot_service import clip_trend_data

        trend = self._make_trend_data("2026-01-01", 30, "2027-01-01")
        horizon = "2026-01-16"
        clipped = clip_trend_data(trend, horizon)

        # All real data dates should be <= horizon
        real_dates = [p["date"] for p in clipped["data_points"]
                      if p["current_value"] is not None]
        for d in real_dates:
            assert d <= horizon

        # Last point should be ideal-only endpoint AT the horizon (not target)
        last = clipped["data_points"][-1]
        assert last["current_value"] is None
        assert last["ideal_value"] is not None
        assert last["date"] == horizon

    def test_clip_preserves_original(self):
        """clip_trend_data should not modify the original dict."""
        from app.services.goal_snapshot_service import clip_trend_data

        trend = self._make_trend_data("2026-01-01", 30, "2027-01-01")
        original_len = len(trend["data_points"])
        clip_trend_data(trend, "2026-01-16")
        assert len(trend["data_points"]) == original_len

    def test_clip_with_full_range_keeps_all(self):
        """Clipping at target date should keep all points."""
        from app.services.goal_snapshot_service import clip_trend_data

        trend = self._make_trend_data("2026-01-01", 10, "2026-01-15")
        clipped = clip_trend_data(trend, "2026-01-15")
        assert len(clipped["data_points"]) == len(trend["data_points"])

    def test_clip_adds_ideal_endpoint_at_horizon(self):
        """Clipped data should end with a synthetic ideal-only point at horizon."""
        from app.services.goal_snapshot_service import clip_trend_data

        trend = self._make_trend_data("2026-01-01", 30, "2027-01-01")
        horizon = "2026-01-16"
        clipped = clip_trend_data(trend, horizon)

        last = clipped["data_points"][-1]
        assert last["current_value"] is None
        assert last["date"] == horizon  # Endpoint is at horizon, not target
        assert last["ideal_value"] is not None
        # Ideal value should be interpolated (between start and end)
        assert last["ideal_value"] > trend["ideal_start_value"]
        assert last["ideal_value"] < trend["ideal_end_value"]

    def test_clip_empty_data_points(self):
        """Clipping empty data should return empty."""
        from app.services.goal_snapshot_service import clip_trend_data

        trend = {
            "goal": {"id": 1},
            "ideal_start_value": 0,
            "ideal_end_value": 100,
            "data_points": [],
        }
        clipped = clip_trend_data(trend, "2026-01-16")
        assert clipped["data_points"] == []


class TestMinimapSVG:
    """Tests for minimap SVG rendering."""

    def test_minimap_svg_rendered_when_enabled(self):
        """_build_minimap_svg returns SVG content with minimap class."""
        from app.services.report_generator_service.html_builder import (
            _build_minimap_svg,
        )

        data_points = [
            {"date": "2026-01-01", "current_value": 100, "ideal_value": 100,
             "progress_pct": 0, "on_track": True},
            {"date": "2026-01-10", "current_value": 150, "ideal_value": 120,
             "progress_pct": 50, "on_track": True},
            {"date": "2027-01-01", "current_value": None, "ideal_value": 500,
             "progress_pct": None, "on_track": None},
        ]

        result = _build_minimap_svg(
            full_data_points=data_points,
            horizon_date="2026-02-01",
            target_date="2027-01-01",
            brand_color="#3b82f6",
            currency="USD",
        )

        assert "<svg" in result
        assert "minimap" in result

    def test_minimap_not_rendered_when_insufficient_data(self):
        """With fewer than 2 data points, minimap returns empty string."""
        from app.services.report_generator_service.html_builder import (
            _build_minimap_svg,
        )

        result = _build_minimap_svg(
            full_data_points=[{"date": "2026-01-01", "current_value": 100,
                               "ideal_value": 100, "progress_pct": 0,
                               "on_track": True}],
            horizon_date="2026-02-01",
            target_date="2027-01-01",
            brand_color="#3b82f6",
            currency="USD",
        )
        assert result == ""

    def test_minimap_viewport_box_present(self):
        """Minimap SVG should contain a viewport rectangle."""
        from app.services.report_generator_service.html_builder import (
            _build_minimap_svg,
        )

        data_points = [
            {"date": "2026-01-01", "current_value": 100, "ideal_value": 100,
             "progress_pct": 0, "on_track": True},
            {"date": "2026-06-01", "current_value": 300, "ideal_value": 250,
             "progress_pct": 60, "on_track": True},
            {"date": "2027-01-01", "current_value": None, "ideal_value": 500,
             "progress_pct": None, "on_track": None},
        ]

        result = _build_minimap_svg(
            full_data_points=data_points,
            horizon_date="2026-08-01",
            target_date="2027-01-01",
            brand_color="#3b82f6",
            currency="USD",
        )

        assert "viewport" in result.lower() or "rect" in result
