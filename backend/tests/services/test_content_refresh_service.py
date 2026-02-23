"""
Tests for backend/app/services/content_refresh_service.py

Covers:
- ContentRefreshService lifecycle (start/stop)
- Status property
- _refresh_news and _refresh_videos error handling
- Refresh interval constants
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from app.services.content_refresh_service import (
    ContentRefreshService,
    NEWS_REFRESH_INTERVAL,
    VIDEO_REFRESH_INTERVAL,
    INITIAL_DELAY,
)


# ---------------------------------------------------------------------------
# Service lifecycle
# ---------------------------------------------------------------------------


class TestContentRefreshServiceLifecycle:
    """Tests for start/stop of the ContentRefreshService."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Happy path: service starts and stops cleanly."""
        svc = ContentRefreshService()
        await svc.start()

        assert svc._running is True
        assert svc._task is not None

        await svc.stop()
        assert svc._running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """Edge case: calling start twice does not create duplicate tasks."""
        svc = ContentRefreshService()
        await svc.start()
        first_task = svc._task

        await svc.start()  # Second call - should be a no-op
        assert svc._task is first_task

        await svc.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        """Edge case: stop on never-started service does not crash."""
        svc = ContentRefreshService()
        await svc.stop()
        assert svc._running is False


# ---------------------------------------------------------------------------
# Status property
# ---------------------------------------------------------------------------


class TestContentRefreshServiceStatus:
    """Tests for the status property."""

    def test_status_initial_state(self):
        """Happy path: initial status has correct default values."""
        svc = ContentRefreshService()
        status = svc.status

        assert status["running"] is False
        assert status["last_news_refresh"] is None
        assert status["last_video_refresh"] is None
        assert status["news_interval_minutes"] == NEWS_REFRESH_INTERVAL // 60
        assert status["video_interval_minutes"] == VIDEO_REFRESH_INTERVAL // 60

    def test_status_after_refresh(self):
        """Happy path: status reflects last refresh timestamps."""
        svc = ContentRefreshService()
        now = datetime(2025, 6, 15, 12, 0, 0)
        svc._last_news_refresh = now
        svc._last_video_refresh = now

        status = svc.status
        assert status["last_news_refresh"] == now.isoformat()
        assert status["last_video_refresh"] == now.isoformat()

    def test_status_running_true_after_start(self):
        """Status shows running=True after start (without waiting for loop)."""
        svc = ContentRefreshService()
        svc._running = True
        assert svc.status["running"] is True


# ---------------------------------------------------------------------------
# _refresh_news / _refresh_videos
# ---------------------------------------------------------------------------


class TestRefreshMethods:
    """Tests for _refresh_news and _refresh_videos."""

    @pytest.mark.asyncio
    async def test_refresh_news_success(self):
        """Happy path: successful refresh updates last_news_refresh."""
        svc = ContentRefreshService()
        mock_fetch = AsyncMock()

        await svc._refresh_news(mock_fetch)

        mock_fetch.assert_awaited_once()
        assert svc._last_news_refresh is not None

    @pytest.mark.asyncio
    async def test_refresh_news_error_does_not_crash(self):
        """Failure: fetch error is caught and service continues."""
        svc = ContentRefreshService()
        mock_fetch = AsyncMock(side_effect=RuntimeError("Network error"))

        await svc._refresh_news(mock_fetch)

        # Should not have updated the timestamp
        assert svc._last_news_refresh is None

    @pytest.mark.asyncio
    async def test_refresh_videos_success(self):
        """Happy path: successful refresh updates last_video_refresh."""
        svc = ContentRefreshService()
        mock_fetch = AsyncMock()

        await svc._refresh_videos(mock_fetch)

        mock_fetch.assert_awaited_once()
        assert svc._last_video_refresh is not None

    @pytest.mark.asyncio
    async def test_refresh_videos_error_does_not_crash(self):
        """Failure: fetch error is caught and service continues."""
        svc = ContentRefreshService()
        mock_fetch = AsyncMock(side_effect=ValueError("Bad data"))

        await svc._refresh_videos(mock_fetch)

        assert svc._last_video_refresh is None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify refresh interval constants are sane."""

    def test_news_interval_30_minutes(self):
        """News refresh interval is 30 minutes (1800 seconds)."""
        assert NEWS_REFRESH_INTERVAL == 30 * 60

    def test_video_interval_60_minutes(self):
        """Video refresh interval is 60 minutes (3600 seconds)."""
        assert VIDEO_REFRESH_INTERVAL == 60 * 60

    def test_initial_delay_10_seconds(self):
        """Initial delay is 10 seconds."""
        assert INITIAL_DELAY == 10
