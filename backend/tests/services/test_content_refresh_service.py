"""
Tests for backend/app/services/content_refresh_service.py

Scheduling is driven by APScheduler (see app/scheduler.py) — this module no
longer owns its own start/stop lifecycle. Tests focus on:
- refresh_news / refresh_videos delegate to the fetch helpers with the
  injected session maker
- _refresh_news / _refresh_videos error handling
- status property (last_*_refresh + configured intervals)
- Refresh interval constants
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.services.content_refresh_service import (
    ContentRefreshService,
    NEWS_REFRESH_INTERVAL,
    VIDEO_REFRESH_INTERVAL,
)


# ---------------------------------------------------------------------------
# Public entry points (delegate to fetch helpers)
# ---------------------------------------------------------------------------


class TestPublicRefreshEntryPoints:
    """refresh_news / refresh_videos call the fetch helpers with the configured sm."""

    @pytest.mark.asyncio
    async def test_refresh_news_calls_fetch_all_news(self):
        svc = ContentRefreshService()
        sentinel_sm = object()
        svc.set_session_maker(sentinel_sm)

        mock_fetch = AsyncMock()
        with patch(
            "app.services.news_fetch_service.fetch_all_news",
            new=mock_fetch,
        ):
            await svc.refresh_news()

        mock_fetch.assert_awaited_once_with(session_maker=sentinel_sm)
        assert svc._last_news_refresh is not None

    @pytest.mark.asyncio
    async def test_refresh_videos_calls_fetch_all_videos(self):
        svc = ContentRefreshService()
        sentinel_sm = object()
        svc.set_session_maker(sentinel_sm)

        mock_fetch = AsyncMock()
        with patch(
            "app.services.news_fetch_service.fetch_all_videos",
            new=mock_fetch,
        ):
            await svc.refresh_videos()

        mock_fetch.assert_awaited_once_with(session_maker=sentinel_sm)
        assert svc._last_video_refresh is not None


# ---------------------------------------------------------------------------
# Status property
# ---------------------------------------------------------------------------


class TestContentRefreshServiceStatus:
    """Tests for the status property."""

    def test_status_initial_state(self):
        """Happy path: initial status has correct default values."""
        svc = ContentRefreshService()
        status = svc.status

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
# Session maker injection
# ---------------------------------------------------------------------------


class TestSessionMakerInjection:
    def test_set_session_maker_overrides_default(self):
        svc = ContentRefreshService()
        sentinel = object()
        svc.set_session_maker(sentinel)
        assert svc._get_sm() is sentinel

    def test_default_session_maker_used_when_not_injected(self):
        svc = ContentRefreshService()
        from app.database import async_session_maker
        assert svc._get_sm() is async_session_maker


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
