"""
Background service for refreshing news and video content caches.

This service runs in the background and periodically fetches fresh content
from news sources and YouTube channels, storing results in the database.
Users never have to wait for cache refreshes - they always get instant
responses from the database.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Cache refresh intervals (in seconds) — kept for status reporting
NEWS_REFRESH_INTERVAL = 30 * 60     # 30 minutes
VIDEO_REFRESH_INTERVAL = 60 * 60    # 60 minutes


class ContentRefreshService:
    """Background service that periodically refreshes news and video caches."""

    def __init__(self):
        self._last_news_refresh: datetime | None = None
        self._last_video_refresh: datetime | None = None
        self._session_maker = None  # optional injected session maker

    def set_session_maker(self, sm):
        """Inject a session maker (for testing or non-default pools)."""
        self._session_maker = sm

    def _get_sm(self):
        """Return the injected session maker, falling back to the default."""
        from app.database import async_session_maker as _default
        return self._session_maker or _default

    async def refresh_news(self):
        """Fetch and cache news articles. Called by APScheduler every 30 minutes."""
        from app.services.news_fetch_service import fetch_all_news
        await self._refresh_news(fetch_all_news, self._get_sm())

    async def refresh_videos(self):
        """Fetch and cache video articles. Called by APScheduler every hour."""
        from app.services.news_fetch_service import fetch_all_videos
        await self._refresh_videos(fetch_all_videos, self._get_sm())

    async def _refresh_news(self, fetch_func, session_maker=None):
        """Refresh news articles."""
        try:
            logger.info("Content refresh: Fetching news articles...")
            await fetch_func(session_maker=session_maker)
            self._last_news_refresh = datetime.utcnow()
            logger.info("Content refresh: News articles updated successfully")
        except Exception as e:
            logger.error(f"Content refresh: Failed to refresh news: {e}")

    async def _refresh_videos(self, fetch_func, session_maker=None):
        """Refresh video articles."""
        try:
            logger.info("Content refresh: Fetching videos...")
            await fetch_func(session_maker=session_maker)
            self._last_video_refresh = datetime.utcnow()
            logger.info("Content refresh: Videos updated successfully")
        except Exception as e:
            logger.error(f"Content refresh: Failed to refresh videos: {e}")

    @property
    def status(self) -> dict:
        """Get current status of the refresh service."""
        return {
            "last_news_refresh": self._last_news_refresh.isoformat() if self._last_news_refresh else None,
            "last_video_refresh": self._last_video_refresh.isoformat() if self._last_video_refresh else None,
            "news_interval_minutes": NEWS_REFRESH_INTERVAL // 60,
            "video_interval_minutes": VIDEO_REFRESH_INTERVAL // 60,
        }


# Global instance
content_refresh_service = ContentRefreshService()
