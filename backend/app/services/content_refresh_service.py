"""
Background service for refreshing news and video content caches.

This service runs in the background and periodically fetches fresh content
from news sources and YouTube channels, storing results in the database.
Users never have to wait for cache refreshes - they always get instant
responses from the database.
"""

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Cache refresh intervals (in seconds)
NEWS_REFRESH_INTERVAL = 30 * 60     # 30 minutes
VIDEO_REFRESH_INTERVAL = 60 * 60    # 60 minutes
INITIAL_DELAY = 10                  # Wait 10 seconds after startup


class ContentRefreshService:
    """Background service that periodically refreshes news and video caches."""

    def __init__(self):
        self._task = None
        self._running = False
        self._last_news_refresh: datetime | None = None
        self._last_video_refresh: datetime | None = None

    async def start(self):
        """Start the background refresh task."""
        if self._running:
            logger.warning("Content refresh service already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._refresh_loop())
        logger.info("Content refresh service started")

    async def stop(self):
        """Stop the background refresh task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Content refresh service stopped")

    async def _refresh_loop(self):
        """Main loop that handles periodic content refresh."""
        # Import here to avoid circular imports
        from app.routers.news_router import fetch_all_news, fetch_all_videos

        # Wait a bit after startup before first refresh
        await asyncio.sleep(INITIAL_DELAY)

        # Do initial refresh immediately
        logger.info("Content refresh: Running initial content fetch...")
        await self._refresh_news(fetch_all_news)
        await asyncio.sleep(5)  # Stagger to avoid CPU spike
        await self._refresh_videos(fetch_all_videos)

        while self._running:
            try:
                # Calculate time until next refresh
                now = datetime.utcnow()

                # Check if news needs refresh
                if self._last_news_refresh:
                    news_age = (now - self._last_news_refresh).total_seconds()
                    if news_age >= NEWS_REFRESH_INTERVAL:
                        await self._refresh_news(fetch_all_news)
                else:
                    await self._refresh_news(fetch_all_news)

                # Check if videos need refresh
                if self._last_video_refresh:
                    video_age = (now - self._last_video_refresh).total_seconds()
                    if video_age >= VIDEO_REFRESH_INTERVAL:
                        await self._refresh_videos(fetch_all_videos)
                else:
                    await self._refresh_videos(fetch_all_videos)

            except Exception as e:
                logger.error(f"Error in content refresh loop: {e}")

            # Sleep for a minute before checking again
            await asyncio.sleep(60)

    async def _refresh_news(self, fetch_func):
        """Refresh news articles."""
        try:
            logger.info("Content refresh: Fetching news articles...")
            await fetch_func()
            self._last_news_refresh = datetime.utcnow()
            logger.info("Content refresh: News articles updated successfully")
        except Exception as e:
            logger.error(f"Content refresh: Failed to refresh news: {e}")

    async def _refresh_videos(self, fetch_func):
        """Refresh video articles."""
        try:
            logger.info("Content refresh: Fetching videos...")
            await fetch_func()
            self._last_video_refresh = datetime.utcnow()
            logger.info("Content refresh: Videos updated successfully")
        except Exception as e:
            logger.error(f"Content refresh: Failed to refresh videos: {e}")

    @property
    def status(self) -> dict:
        """Get current status of the refresh service."""
        return {
            "running": self._running,
            "last_news_refresh": self._last_news_refresh.isoformat() if self._last_news_refresh else None,
            "last_video_refresh": self._last_video_refresh.isoformat() if self._last_video_refresh else None,
            "news_interval_minutes": NEWS_REFRESH_INTERVAL // 60,
            "video_interval_minutes": VIDEO_REFRESH_INTERVAL // 60,
        }


# Global instance
content_refresh_service = ContentRefreshService()
