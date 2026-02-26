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

    def test_auto_horizon_one_third_rule(self):
        """With data spanning 10 days and target far away, horizon ≈ 15 days."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 10)
        # Target is 1000 days away — far enough that auto should clip
        target = (datetime(2026, 1, 1) + timedelta(days=1000)).strftime("%Y-%m-%d")

        result = compute_horizon_date(points, target, "auto")
        result_date = datetime.strptime(result, "%Y-%m-%d")
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")
        target_date = datetime.strptime(target, "%Y-%m-%d")

        # 1/3 rule: look_ahead = max(data_span / 2, 7) = max(10/2, 7) = 7
        # But data_span=10, so look_ahead = 10/2 = 5 → capped to 7 (minimum)
        # horizon = last_data + 7 = 2026-01-18
        assert result_date > last_data
        assert result_date < target_date
        # Horizon should be roughly 7 days after last data point (min look-ahead)
        expected = last_data + timedelta(days=7)
        assert result_date == expected

    def test_auto_horizon_larger_span(self):
        """With data spanning 30 days, look-ahead should be 15 days (span/2)."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 30)
        target = (datetime(2026, 1, 1) + timedelta(days=1000)).strftime("%Y-%m-%d")

        result = compute_horizon_date(points, target, "auto")
        result_date = datetime.strptime(result, "%Y-%m-%d")
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")

        # look_ahead = max(30/2, 7) = 15
        expected = last_data + timedelta(days=15)
        assert result_date == expected

    def test_auto_horizon_min_7_days(self):
        """With data spanning only 1 day, minimum look-ahead is 7 days."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 1)
        target = (datetime(2026, 1, 1) + timedelta(days=365)).strftime("%Y-%m-%d")

        result = compute_horizon_date(points, target, "auto")
        result_date = datetime.strptime(result, "%Y-%m-%d")
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")

        # look_ahead = max(1/2, 7) = 7
        expected = last_data + timedelta(days=7)
        assert result_date == expected

    def test_auto_horizon_target_within_range(self):
        """When target is near the data, show full range to target."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = self._make_points("2026-01-01", 10)
        # Target is only 5 days beyond last data point
        last_data = datetime.strptime(points[-1]["date"], "%Y-%m-%d")
        target = (last_data + timedelta(days=5)).strftime("%Y-%m-%d")

        result = compute_horizon_date(points, target, "auto")
        # Horizon = last_data + 7 (min look-ahead), but capped at target
        # Since target is 5 days away and min look-ahead is 7, horizon = target
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

    def test_single_data_point_returns_min_lookahead(self):
        """With single point, use min 7-day look-ahead."""
        from app.services.goal_snapshot_service import compute_horizon_date

        points = [{"date": "2026-01-01", "current_value": 100,
                   "ideal_value": 100, "progress_pct": 0, "on_track": True}]
        target = "2029-01-01"

        result = compute_horizon_date(points, target, "auto")
        result_date = datetime.strptime(result, "%Y-%m-%d")
        expected = datetime(2026, 1, 1) + timedelta(days=7)
        assert result_date == expected


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
            "goal": {"id": 1, "name": "Test", "target_date": target_date},
            "ideal_start_value": 100,
            "ideal_end_value": 500,
            "data_points": data_points,
        }

    def test_clip_removes_points_beyond_horizon(self):
        """Points beyond horizon_date should be removed (except one ideal-only kept)."""
        from app.services.goal_snapshot_service import clip_trend_data

        trend = self._make_trend_data("2026-01-01", 30, "2027-01-01")
        # Clip at day 15 (2026-01-16)
        horizon = "2026-01-16"
        clipped = clip_trend_data(trend, horizon)

        dates = [p["date"] for p in clipped["data_points"]]
        # All real data dates should be <= horizon
        real_dates = [d for d, p in zip(dates, clipped["data_points"])
                      if p["current_value"] is not None]
        for d in real_dates:
            assert d <= horizon

        # Should keep one ideal-only point at the end for line continuity
        last = clipped["data_points"][-1]
        assert last["current_value"] is None
        assert last["ideal_value"] is not None

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
        """Clipped data should end with an ideal-only point at or near horizon."""
        from app.services.goal_snapshot_service import clip_trend_data

        trend = self._make_trend_data("2026-01-01", 30, "2027-01-01")
        horizon = "2026-01-16"
        clipped = clip_trend_data(trend, horizon)

        last = clipped["data_points"][-1]
        assert last["current_value"] is None
        assert last["date"] <= "2027-01-01"  # Never beyond target

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
