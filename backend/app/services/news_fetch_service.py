"""
News Fetch Service

Orchestrates fetching news articles and videos from configured sources,
storing them in the database, and managing caches.

Extracted from news_router.py to fix the service→router dependency inversion.
content_refresh_service imports from here; news_router imports from here.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import aiohttp
from sqlalchemy import select, update

from app.database import async_session_maker
from app.models import NewsArticle
from app.news_data import (
    NEWS_SOURCES,
    VIDEO_CACHE_CHECK_MINUTES,
    VIDEO_SOURCES,
    VideoItem,
    load_video_cache,
    merge_news_items,
    prune_old_items,
    save_video_cache,
)
from app.services.news_image_cache import download_and_save_image

logger = logging.getLogger(__name__)


async def fetch_all_news() -> None:
    """Fetch news from all sources, cache images, and store in database."""
    # Import helpers that remain in news_router (will move in news_router PRP)
    import app.routers.news_router as _nr
    from app.routers.news_router import (
        _get_source_key_to_id_map,
        cleanup_articles_with_images,
        fetch_reddit_news,
        fetch_rss_news,
        get_news_sources_from_db,
        store_article_in_db,
    )

    fresh_items = []

    db_sources = await get_news_sources_from_db()
    sources_to_use = db_sources if db_sources else NEWS_SOURCES

    # Build source_key -> source_id map for linking articles to content_sources
    source_key_to_id = await _get_source_key_to_id_map("news")

    connector = aiohttp.TCPConnector()
    async with aiohttp.ClientSession(connector=connector, max_field_size=16384) as session:
        tasks = []
        for source_id, config in sources_to_use.items():
            if config["type"] == "reddit":
                tasks.append(fetch_reddit_news(session, source_id, config))
            elif config["type"] == "rss":
                tasks.append(fetch_rss_news(session, source_id, config))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                fresh_items.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Task failed: {result}")

        new_articles_count = 0
        articles_to_download = []
        async with async_session_maker() as db:
            seen_urls = set()
            for item in fresh_items:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                article = await store_article_in_db(
                    db, item, category=item.category,
                    source_id=source_key_to_id.get(item.source),
                )
                if article:
                    new_articles_count += 1

            await db.commit()

            if new_articles_count > 0:
                for item in fresh_items:
                    result = await db.execute(
                        select(NewsArticle.id).where(
                            NewsArticle.url == item.url,
                            NewsArticle.cached_thumbnail_path.is_(None),
                        )
                    )
                    row = result.first()
                    if row and item.thumbnail:
                        articles_to_download.append((row[0], item.thumbnail))

        if articles_to_download:
            for article_id, thumbnail_url in articles_to_download:
                filename = await download_and_save_image(session, thumbnail_url, article_id)
                if filename:
                    async with async_session_maker() as db:
                        await db.execute(
                            update(NewsArticle)
                            .where(NewsArticle.id == article_id)
                            .values(cached_thumbnail_path=filename)
                        )
                        await db.commit()

        if new_articles_count > 0:
            logger.info(f"Added {new_articles_count} new news articles to database")

    # Run per-source retention cleanup (articles + images)
    try:
        deleted, imgs = await cleanup_articles_with_images()
        if deleted > 0:
            logger.info(f"Post-fetch cleanup: {deleted} articles, {imgs} images")
    except Exception as e:
        logger.warning(f"Post-fetch article cleanup failed: {e}")

    _nr._last_news_refresh = datetime.now(timezone.utc)


async def fetch_all_videos() -> Dict[str, Any]:
    """Fetch videos from all YouTube sources and store in database."""
    # Import helpers that remain in news_router (will move in news_router PRP)
    from app.routers.news_router import (
        _get_source_key_to_id_map,
        cleanup_old_videos,
        fetch_youtube_videos,
        get_video_sources_from_db,
        store_video_in_db,
    )
    import app.routers.news_router as _nr

    fresh_items: List[VideoItem] = []

    db_sources = await get_video_sources_from_db()
    sources_to_use = db_sources if db_sources else VIDEO_SOURCES

    # Build source_key -> source_id map for linking videos to content_sources
    source_key_to_id = await _get_source_key_to_id_map("video")

    async with aiohttp.ClientSession() as session:
        tasks = []
        for source_id, config in sources_to_use.items():
            tasks.append(fetch_youtube_videos(session, source_id, config))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                fresh_items.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Video fetch task failed: {result}")

    new_count = 0
    async with async_session_maker() as db:
        for item in fresh_items:
            video = await store_video_in_db(
                db, item, category=item.category,
                source_id=source_key_to_id.get(item.source),
            )
            if video:
                new_count += 1
        await db.commit()
        await cleanup_old_videos(db)

    if new_count > 0:
        logger.info(f"Stored {new_count} new videos in database")

    # Also save to JSON cache for backward compatibility
    fresh_dicts = [item.model_dump() for item in fresh_items]
    existing_cache = load_video_cache(for_merge=True)
    existing_items = existing_cache.get("videos", []) if existing_cache else []
    merged_items = merge_news_items(existing_items, fresh_dicts)
    merged_items = prune_old_items(merged_items)

    sources_list = [
        {"id": sid, "name": cfg["name"], "website": cfg["website"], "description": cfg.get("description", "")}
        for sid, cfg in sources_to_use.items()
    ]

    now = datetime.now(timezone.utc)
    cache_data = {
        "videos": merged_items,
        "sources": sources_list,
        "cached_at": now.isoformat(),
        "cache_expires_at": (now + timedelta(minutes=VIDEO_CACHE_CHECK_MINUTES)).isoformat(),
        "total_items": len(merged_items),
    }
    save_video_cache(cache_data)

    _nr._last_video_refresh = datetime.now(timezone.utc)
    return cache_data
