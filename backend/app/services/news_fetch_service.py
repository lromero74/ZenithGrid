"""
News Fetch Service

Thin wrapper that provides fetch_all_news and fetch_all_videos via lazy
import from news_router.  This breaks the service→router import cycle:
content_refresh_service imports from here instead of from news_router.
"""

from typing import Any, Dict


async def fetch_all_news() -> None:
    """Fetch all news from configured sources (delegates to news_router)."""
    from app.routers.news_router import fetch_all_news as _fetch_all_news
    await _fetch_all_news()


async def fetch_all_videos() -> Dict[str, Any]:
    """Fetch all videos from configured sources (delegates to news_router)."""
    from app.routers.news_router import fetch_all_videos as _fetch_all_videos
    return await _fetch_all_videos()
