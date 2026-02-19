"""
Crypto News Router

Fetches and caches crypto news from multiple sources.
Cache behavior:
- Checks for new content every 15 minutes
- Merges new items with existing cache (new items at top)
- Prunes items older than 7 days

News and video sources are dynamically configured in news_sources.py
and managed via the admin UI (Settings > News Sources).

Sub-routers:
- news_metrics_router: Market sentiment & blockchain metrics endpoints
- news_tts_router: Text-to-speech endpoints
"""

import asyncio
import concurrent.futures
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
import feedparser
import trafilatura
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import (
    ContentSource, NewsArticle, User, UserContentSeenStatus,
    UserSourceSubscription, VideoArticle,
)
from app.auth.dependencies import get_current_user
from app.news_data import (
    CACHE_FILE,
    NEWS_CACHE_CHECK_MINUTES,
    NEWS_CATEGORIES,
    NEWS_ITEM_MAX_AGE_DAYS,
    NEWS_SOURCES,
    VIDEO_CACHE_CHECK_MINUTES,
    VIDEO_SOURCES,
    ArticleContentResponse,
    NewsItem,
    NewsResponse,
    VideoItem,
    VideoResponse,
    load_video_cache,
    merge_news_items,
    prune_old_items,
    save_video_cache,
)
from app.routers.news_metrics_router import router as metrics_router
from app.routers.news_tts_router import router as tts_router
from app.services.news_image_cache import download_and_save_image

logger = logging.getLogger(__name__)

# Track when we last refreshed news/videos (in-memory for this process)
_last_news_refresh: Optional[datetime] = None
_last_video_refresh: Optional[datetime] = None

router = APIRouter(prefix="/api/news", tags=["news"])

# Include sub-routers (metrics + TTS)
router.include_router(metrics_router)
router.include_router(tts_router)

# Shared thread pool for trafilatura (CPU-bound)
_trafilatura_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

# Article content cache: url -> (ArticleContentResponse, timestamp)
_article_cache: Dict[str, Tuple[Any, float]] = {}
_article_cache_lock = asyncio.Lock()
_ARTICLE_CACHE_TTL = 1800  # 30 minutes
_ARTICLE_CACHE_MAX = 100

# Per-domain crawl delay tracking: domain -> last_fetch_timestamp
_domain_last_fetch: Dict[str, float] = {}
_domain_last_fetch_lock = asyncio.Lock()


# =============================================================================
# Database Functions for Content Sources
# =============================================================================


async def get_allowed_article_domains() -> set[str]:
    """
    Get allowed domains for article content extraction from database.
    Extracts domains from website URLs of all enabled content sources.
    """
    async with async_session_maker() as db:
        result = await db.execute(
            select(ContentSource.website)
            .where(ContentSource.is_enabled.is_(True))
            .where(ContentSource.website.isnot(None))
        )
        websites = result.scalars().all()

    allowed = set()
    for website in websites:
        try:
            parsed = urlparse(website)
            domain = parsed.netloc.lower()
            if domain:
                allowed.add(domain)
                # Also add www. variant if not present, or non-www if www present
                if domain.startswith("www."):
                    allowed.add(domain[4:])
                else:
                    allowed.add(f"www.{domain}")
        except Exception:
            pass

    return allowed


async def get_source_scrape_policy(url: str) -> Tuple[bool, int]:
    """
    Look up the scrape policy for the source that owns a given article URL.

    Returns (scrape_allowed, crawl_delay_seconds).
    Defaults to (True, 0) if the source can't be determined.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        domain_bare = domain[4:] if domain.startswith("www.") else domain

        async with async_session_maker() as db:
            result = await db.execute(
                select(ContentSource)
                .where(ContentSource.is_enabled.is_(True))
                .where(ContentSource.website.isnot(None))
            )
            sources = result.scalars().all()

        for source in sources:
            try:
                src_domain = urlparse(source.website).netloc.lower()
                src_bare = src_domain[4:] if src_domain.startswith("www.") else src_domain
                if domain_bare == src_bare:
                    scrape = source.content_scrape_allowed
                    delay = source.crawl_delay_seconds
                    return (
                        scrape if scrape is not None else True,
                        delay if delay is not None else 0,
                    )
            except Exception:
                continue

    except Exception as e:
        logger.warning(f"Failed to look up scrape policy for {url}: {e}")

    return (True, 0)


async def get_news_sources_from_db() -> Dict[str, Dict]:
    """Get news sources from database, formatted like NEWS_SOURCES dict."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(ContentSource)
            .where(ContentSource.type == "news")
            .where(ContentSource.is_enabled.is_(True))
        )
        sources = result.scalars().all()

    return {
        s.source_key: {
            "name": s.name,
            "url": s.url,
            "type": "reddit" if "reddit" in s.source_key else "rss",
            "website": s.website,
            "category": getattr(s, 'category', 'CryptoCurrency'),
            "content_scrape_allowed": getattr(
                s, 'content_scrape_allowed', True
            ),
        }
        for s in sources
    }


async def get_video_sources_from_db() -> Dict[str, Dict]:
    """Get video sources from database, formatted like VIDEO_SOURCES dict."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(ContentSource)
            .where(ContentSource.type == "video")
            .where(ContentSource.is_enabled.is_(True))
        )
        sources = result.scalars().all()

    return {
        s.source_key: {
            "name": s.name,
            "channel_id": s.channel_id,
            "url": s.url,
            "website": s.website,
            "description": s.description or "",
            "category": getattr(s, 'category', 'CryptoCurrency'),
        }
        for s in sources
    }


async def get_all_sources_from_db() -> Dict[str, List[Dict]]:
    """Get all sources from database for API responses."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(ContentSource).where(ContentSource.is_enabled.is_(True))
        )
        sources = result.scalars().all()

    news_sources = []
    video_sources = []

    for s in sources:
        if s.type == "news":
            news_sources.append({
                "id": s.source_key,
                "name": s.name,
                "website": s.website,
                "type": "reddit" if "reddit" in s.source_key else "rss",
            })
        elif s.type == "video":
            video_sources.append({
                "id": s.source_key,
                "name": s.name,
                "website": s.website,
                "description": s.description,
            })

    return {"news": news_sources, "video": video_sources}


async def _get_source_key_to_id_map(source_type: Optional[str] = None) -> Dict[str, int]:
    """Build a mapping of source_key -> content_sources.id for linking articles/videos."""
    async with async_session_maker() as db:
        query = select(ContentSource.source_key, ContentSource.id)
        if source_type:
            query = query.where(ContentSource.type == source_type)
        result = await db.execute(query)
        return {row[0]: row[1] for row in result.all()}


# =============================================================================
# Database Functions for News Articles
# =============================================================================


async def get_articles_for_user(
    db: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = None,
) -> tuple[List[NewsArticle], int]:
    """Get paginated news articles filtered by user's subscriptions and retention.

    - System sources: shown unless user explicitly unsubscribed
    - Custom sources: shown only if user is subscribed
    - Per-user retention_days: filters visibility (query-time only)
    - user_category override applied in response layer, not here
    """
    from sqlalchemy import case, func

    default_cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_ITEM_MAX_AGE_DAYS)

    # Retention cutoff: use per-user retention_days if set, otherwise system default.
    # NOTE: SQLite printf('-%d days', NULL) returns '-0 days' (not NULL),
    # so coalesce won't reach the fallback. Use case() to handle NULL explicitly.
    retention_cutoff = case(
        (UserSourceSubscription.retention_days.is_not(None),
         func.datetime('now', func.printf('-%d days', UserSourceSubscription.retention_days))),
        else_=default_cutoff,
    )

    # Base query: articles with source_id JOIN through ContentSource
    # LEFT JOIN subscription for per-user overrides
    query = (
        select(NewsArticle)
        .outerjoin(
            ContentSource, NewsArticle.source_id == ContentSource.id
        )
        .outerjoin(
            UserSourceSubscription,
            (UserSourceSubscription.source_id == ContentSource.id)
            & (UserSourceSubscription.user_id == user_id),
        )
        .where(
            # Subscription filter:
            # System sources: show unless explicitly unsubscribed
            # Custom sources: show only if explicitly subscribed
            # Articles with no source_id: always show (legacy)
            (NewsArticle.source_id.is_(None))
            | (
                (ContentSource.is_system.is_(True))
                & (
                    UserSourceSubscription.is_subscribed.is_(None)
                    | UserSourceSubscription.is_subscribed.is_(True)
                )
            )
            | (
                (ContentSource.is_system.is_(False))
                & (UserSourceSubscription.is_subscribed.is_(True))
            )
        )
        .where(NewsArticle.published_at >= retention_cutoff)
    )

    if category:
        query = query.where(NewsArticle.category == category)

    # Count
    from sqlalchemy import literal_column
    count_query = select(
        func.count(literal_column('1'))
    ).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    # Paginate (page_size=0 means return all)
    query = query.order_by(desc(NewsArticle.published_at))
    if page_size > 0:
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total_count


async def get_articles_from_db(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = None,
) -> tuple[List[NewsArticle], int]:
    """Legacy: get articles without user filtering (for internal use)."""
    from sqlalchemy import func

    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_ITEM_MAX_AGE_DAYS)

    conditions = [NewsArticle.published_at >= cutoff]
    if category:
        conditions.append(NewsArticle.category == category)

    count_query = select(func.count(NewsArticle.id))
    for condition in conditions:
        count_query = count_query.where(condition)
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    query = select(NewsArticle)
    for condition in conditions:
        query = query.where(condition)
    query = query.order_by(desc(NewsArticle.published_at))
    if page_size > 0:
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total_count


async def store_article_in_db(
    db: AsyncSession,
    item: NewsItem,
    cached_thumbnail_path: Optional[str] = None,
    category: str = "CryptoCurrency",
    source_id: Optional[int] = None,
) -> Optional[NewsArticle]:
    """Store a news article in the database. Returns None if already exists."""
    result = await db.execute(
        select(NewsArticle).where(NewsArticle.url == item.url)
    )
    existing = result.scalars().first()
    if existing:
        return None

    published_at = None
    if item.published:
        try:
            pub_str = item.published.rstrip("Z")
            published_at = datetime.fromisoformat(pub_str)
        except (ValueError, TypeError):
            pass

    thumbnail_url = item.thumbnail
    if thumbnail_url and not thumbnail_url.startswith(("http://", "https://")):
        thumbnail_url = None

    article = NewsArticle(
        title=item.title,
        url=item.url,
        source=item.source,
        published_at=published_at,
        summary=item.summary,
        original_thumbnail_url=thumbnail_url,
        cached_thumbnail_path=cached_thumbnail_path,
        category=category,
        source_id=source_id,
        fetched_at=datetime.now(timezone.utc),
    )
    db.add(article)
    return article


async def cleanup_old_articles(
    db: AsyncSession,
    max_age_days: int = NEWS_ITEM_MAX_AGE_DAYS,
    min_keep: int = 5,
) -> int:
    """Delete old articles using per-source retention: keep the greater of
    min_keep articles or articles within max_age_days, per source.
    Articles with no source_id use flat max_age_days cutoff."""
    from sqlalchemy import delete

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    total_deleted = 0

    # Per-source cleanup: for each source_id, keep newer of min_keep or age
    source_ids_result = await db.execute(
        select(NewsArticle.source_id).where(
            NewsArticle.source_id.isnot(None)
        ).group_by(NewsArticle.source_id)
    )
    source_ids = [row[0] for row in source_ids_result.all()]

    for sid in source_ids:
        # Get the published_at of the min_keep-th newest article
        nth_result = await db.execute(
            select(NewsArticle.published_at)
            .where(NewsArticle.source_id == sid)
            .order_by(desc(NewsArticle.published_at))
            .offset(min_keep - 1)
            .limit(1)
        )
        nth_date = nth_result.scalar()

        # Effective cutoff: keep articles newer than whichever is older
        # (the age cutoff or the min_keep boundary)
        if nth_date and nth_date < cutoff:
            effective_cutoff = nth_date
        else:
            effective_cutoff = cutoff

        result = await db.execute(
            delete(NewsArticle).where(
                NewsArticle.source_id == sid,
                NewsArticle.published_at < effective_cutoff,
            )
        )
        total_deleted += result.rowcount

    # Flat cutoff for articles with no source_id (legacy/orphan)
    result = await db.execute(
        delete(NewsArticle).where(
            NewsArticle.source_id.is_(None),
            NewsArticle.fetched_at < cutoff,
        )
    )
    total_deleted += result.rowcount

    if total_deleted > 0:
        await db.commit()
        logger.info(f"Cleaned up {total_deleted} old news articles")
    return total_deleted


async def get_seen_content_ids(
    db: AsyncSession, user_id: int, content_type: str,
) -> set:
    """Return set of content IDs the user has marked as seen."""
    result = await db.execute(
        select(UserContentSeenStatus.content_id).where(
            UserContentSeenStatus.user_id == user_id,
            UserContentSeenStatus.content_type == content_type,
        )
    )
    return {row[0] for row in result.all()}


def article_to_news_item(
    article: NewsArticle,
    sources: Optional[Dict[str, Dict]] = None,
    seen_ids: Optional[set] = None,
) -> Dict[str, Any]:
    """Convert a NewsArticle database object to a NewsItem dict for API response."""
    source_map = sources if sources else NEWS_SOURCES
    if article.cached_thumbnail_path:
        thumbnail = f"/api/news/image/{article.id}"
    else:
        thumbnail = article.original_thumbnail_url
    return {
        "id": article.id,
        "title": article.title,
        "url": article.url,
        "source": article.source,
        "source_name": source_map.get(
            article.source, {}
        ).get("name", article.source),
        "published": (
            article.published_at.isoformat() + "Z"
            if article.published_at else None
        ),
        "summary": article.summary,
        "thumbnail": thumbnail,
        "category": getattr(article, 'category', 'CryptoCurrency'),
        "content_scrape_allowed": source_map.get(
            article.source, {}
        ).get("content_scrape_allowed", True),
        "is_seen": article.id in seen_ids if seen_ids else False,
        "has_issue": bool(getattr(article, 'has_issue', False)),
    }


# ============================================================================
# VIDEO DATABASE FUNCTIONS
# ============================================================================


async def store_video_in_db(
    db: AsyncSession,
    item: VideoItem,
    category: str = "CryptoCurrency",
    source_id: Optional[int] = None,
) -> Optional[VideoArticle]:
    """Store a video article in the database. Returns None if already exists."""
    result = await db.execute(
        select(VideoArticle).where(VideoArticle.url == item.url)
    )
    existing = result.scalars().first()
    if existing:
        return None

    published_at = None
    if item.published:
        try:
            pub_str = item.published.rstrip("Z")
            published_at = datetime.fromisoformat(pub_str)
        except (ValueError, TypeError):
            pass

    video = VideoArticle(
        title=item.title,
        url=item.url,
        video_id=item.video_id,
        source=item.source,
        channel_name=item.channel_name,
        published_at=published_at,
        description=item.description,
        thumbnail_url=item.thumbnail,
        category=category,
        source_id=source_id,
        fetched_at=datetime.now(timezone.utc),
    )
    db.add(video)
    return video


async def get_videos_for_user(
    db: AsyncSession,
    user_id: int,
    category: Optional[str] = None,
) -> List[VideoArticle]:
    """Get videos filtered by user's subscriptions and retention."""
    from sqlalchemy import case, func

    default_cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_ITEM_MAX_AGE_DAYS)

    # Same NULL-safe retention logic as get_articles_for_user
    retention_cutoff = case(
        (UserSourceSubscription.retention_days.is_not(None),
         func.datetime('now', func.printf('-%d days', UserSourceSubscription.retention_days))),
        else_=default_cutoff,
    )

    query = (
        select(VideoArticle)
        .outerjoin(
            ContentSource, VideoArticle.source_id == ContentSource.id
        )
        .outerjoin(
            UserSourceSubscription,
            (UserSourceSubscription.source_id == ContentSource.id)
            & (UserSourceSubscription.user_id == user_id),
        )
        .where(
            (VideoArticle.source_id.is_(None))
            | (
                (ContentSource.is_system.is_(True))
                & (
                    UserSourceSubscription.is_subscribed.is_(None)
                    | UserSourceSubscription.is_subscribed.is_(True)
                )
            )
            | (
                (ContentSource.is_system.is_(False))
                & (UserSourceSubscription.is_subscribed.is_(True))
            )
        )
        .where(VideoArticle.published_at >= retention_cutoff)
    )

    if category:
        query = query.where(VideoArticle.category == category)

    query = query.order_by(desc(VideoArticle.published_at))
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_videos_from_db_list(
    db: AsyncSession, category: Optional[str] = None
) -> List[VideoArticle]:
    """Legacy: get videos without user filtering (for internal use)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_ITEM_MAX_AGE_DAYS)
    conditions = [VideoArticle.published_at >= cutoff]
    if category:
        conditions.append(VideoArticle.category == category)

    query = select(VideoArticle)
    for condition in conditions:
        query = query.where(condition)
    query = query.order_by(desc(VideoArticle.published_at))

    result = await db.execute(query)
    return list(result.scalars().all())


async def cleanup_old_videos(
    db: AsyncSession,
    max_age_days: int = NEWS_ITEM_MAX_AGE_DAYS,
    min_keep: int = 5,
) -> int:
    """Delete old videos using per-source retention: keep the greater of
    min_keep videos or videos within max_age_days, per source.
    Videos with no source_id use flat max_age_days cutoff."""
    from sqlalchemy import delete

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    total_deleted = 0

    # Per-source cleanup
    source_ids_result = await db.execute(
        select(VideoArticle.source_id).where(
            VideoArticle.source_id.isnot(None)
        ).group_by(VideoArticle.source_id)
    )
    source_ids = [row[0] for row in source_ids_result.all()]

    for sid in source_ids:
        nth_result = await db.execute(
            select(VideoArticle.published_at)
            .where(VideoArticle.source_id == sid)
            .order_by(desc(VideoArticle.published_at))
            .offset(min_keep - 1)
            .limit(1)
        )
        nth_date = nth_result.scalar()

        if nth_date and nth_date < cutoff:
            effective_cutoff = nth_date
        else:
            effective_cutoff = cutoff

        result = await db.execute(
            delete(VideoArticle).where(
                VideoArticle.source_id == sid,
                VideoArticle.published_at < effective_cutoff,
            )
        )
        total_deleted += result.rowcount

    # Flat cutoff for videos with no source_id
    result = await db.execute(
        delete(VideoArticle).where(
            VideoArticle.source_id.is_(None),
            VideoArticle.fetched_at < cutoff,
        )
    )
    total_deleted += result.rowcount

    if total_deleted > 0:
        await db.commit()
        logger.info(f"Cleaned up {total_deleted} old videos")
    return total_deleted


def video_to_item(
    video: VideoArticle,
    sources: Optional[Dict[str, Dict]] = None,
    seen_ids: Optional[set] = None,
) -> Dict[str, Any]:
    """Convert a VideoArticle database object to a VideoItem dict for API response."""
    source_map = sources if sources else VIDEO_SOURCES
    return {
        "id": video.id,
        "title": video.title,
        "url": video.url,
        "video_id": video.video_id,
        "source": video.source,
        "source_name": source_map.get(video.source, {}).get("name", video.source),
        "channel_name": video.channel_name,
        "published": video.published_at.isoformat() + "Z" if video.published_at else None,
        "thumbnail": video.thumbnail_url,
        "description": video.description,
        "category": getattr(video, 'category', 'CryptoCurrency'),
        "is_seen": video.id in seen_ids if seen_ids else False,
    }


async def get_videos_from_db(
    category: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Get videos from database and format for API response."""
    db_sources = await get_video_sources_from_db()
    sources_to_use = db_sources if db_sources else VIDEO_SOURCES

    async with async_session_maker() as db:
        if user_id:
            videos = await get_videos_for_user(
                db, user_id, category=category,
            )
            seen_ids = await get_seen_content_ids(db, user_id, "video")
        else:
            videos = await get_videos_from_db_list(
                db, category=category,
            )
            seen_ids = set()

    video_items = [
        video_to_item(video, sources_to_use, seen_ids) for video in videos
    ]

    sources_list = [
        {
            "id": sid, "name": cfg["name"],
            "website": cfg["website"],
            "description": cfg.get("description", ""),
        }
        for sid, cfg in sources_to_use.items()
    ]

    now = datetime.now(timezone.utc)
    return {
        "videos": video_items,
        "sources": sources_list,
        "cached_at": now.isoformat() + "Z",
        "cache_expires_at": (
            now + timedelta(minutes=VIDEO_CACHE_CHECK_MINUTES)
        ).isoformat() + "Z",
        "total_items": len(video_items),
    }


# =============================================================================
# News & Video Fetch Functions
# =============================================================================


async def fetch_youtube_videos(session: aiohttp.ClientSession, source_id: str, config: Dict) -> List[VideoItem]:
    """Fetch videos from YouTube RSS feed"""
    items = []
    try:
        headers = {"User-Agent": "ZenithGrid/1.0"}
        async with session.get(config["url"], headers=headers, timeout=15) as response:
            if response.status != 200:
                logger.warning(f"YouTube RSS returned {response.status} for {source_id}")
                return items

            content = await response.text()
            feed = feedparser.parse(content)

            for entry in feed.entries[:8]:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).isoformat() + "Z"
                    except (ValueError, TypeError):
                        pass

                video_id = ""
                link = entry.get("link", "")
                if "watch?v=" in link:
                    video_id = link.split("watch?v=")[-1].split("&")[0]
                elif "/shorts/" in link:
                    video_id = link.split("/shorts/")[-1].split("?")[0]

                thumbnail = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg" if video_id else None

                description = None
                if hasattr(entry, "media_group") and entry.media_group:
                    desc = entry.media_group.get("media_description", "")
                    if desc:
                        description = desc[:200] if len(desc) > 200 else desc
                elif hasattr(entry, "summary"):
                    description = entry.summary[:200] if len(entry.summary) > 200 else entry.summary

                items.append(VideoItem(
                    title=entry.get("title", ""),
                    url=link,
                    video_id=video_id,
                    source=source_id,
                    source_name=config["name"],
                    channel_name=config["name"],
                    published=published,
                    thumbnail=thumbnail,
                    description=description,
                    category=config.get("category", "CryptoCurrency"),
                ))
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching videos from {source_id}")
    except Exception as e:
        logger.error(f"Error fetching videos from {source_id}: {e}")

    return items


async def fetch_all_videos() -> Dict[str, Any]:
    """Fetch videos from all YouTube sources and store in database."""
    global _last_video_refresh
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

    _last_video_refresh = datetime.now(timezone.utc)
    return cache_data


async def fetch_reddit_news(session: aiohttp.ClientSession, source_id: str, config: Dict) -> List[NewsItem]:
    """Fetch news from Reddit JSON API"""
    items = []
    try:
        headers = {
            "User-Agent": "ZenithGrid:v1.0 (by /u/zenithgrid_bot)",
            "Accept": "application/json",
        }
        async with session.get(config["url"], headers=headers, timeout=15) as response:
            if response.status != 200:
                logger.warning(f"Reddit API returned {response.status} for {source_id}")
                return items

            data = await response.json()
            posts = data.get("data", {}).get("children", [])

            for post in posts[:15]:
                post_data = post.get("data", {})
                if post_data.get("stickied"):
                    continue

                thumbnail = post_data.get("thumbnail")
                if thumbnail in ["self", "default", "nsfw", "spoiler", ""]:
                    thumbnail = None

                items.append(NewsItem(
                    title=post_data.get("title", ""),
                    url=f"https://reddit.com{post_data.get('permalink', '')}",
                    source=source_id,
                    source_name=config["name"],
                    published=datetime.utcfromtimestamp(post_data.get("created_utc", 0)).isoformat() + "Z",
                    summary=post_data.get("selftext", "")[:200] if post_data.get("selftext") else None,
                    thumbnail=thumbnail,
                    category=config.get("category", "CryptoCurrency"),
                ))
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {source_id}")
    except Exception as e:
        logger.error(f"Error fetching {source_id}: {e}")

    return items


async def fetch_og_meta(session: aiohttp.ClientSession, url: str) -> Dict[str, Optional[str]]:
    """Fetch og:image and og:description meta tags from an article URL."""
    import html as html_module
    result = {"image": None, "description": None}
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status != 200:
                return result
            html_content = await response.text()
            import re

            # Extract og:image
            match = re.search(
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                html_content,
                re.IGNORECASE
            )
            if not match:
                match = re.search(
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                    html_content,
                    re.IGNORECASE
                )
            if match:
                result["image"] = html_module.unescape(match.group(1))

            # Extract og:description
            match = re.search(
                r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
                html_content,
                re.IGNORECASE
            )
            if not match:
                match = re.search(
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
                    html_content,
                    re.IGNORECASE
                )
            if not match:
                match = re.search(
                    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
                    html_content,
                    re.IGNORECASE
                )
                if not match:
                    match = re.search(
                        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
                        html_content,
                        re.IGNORECASE
                    )
            if match:
                desc = html_module.unescape(match.group(1)).strip()
                result["description"] = desc[:200] if len(desc) > 200 else desc

            return result
    except Exception:
        return result


async def fetch_og_image(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """Fetch og:image meta tag from an article URL (convenience wrapper)."""
    meta = await fetch_og_meta(session, url)
    return meta["image"]


async def fetch_rss_news(session: aiohttp.ClientSession, source_id: str, config: Dict) -> List[NewsItem]:
    """Fetch news from RSS feed"""
    items = []
    try:
        headers = {"User-Agent": "ZenithGrid/1.0"}
        async with session.get(config["url"], headers=headers, timeout=15) as response:
            if response.status != 200:
                logger.warning(f"RSS feed returned {response.status} for {source_id}")
                return items

            content = await response.text()
            feed = feedparser.parse(content)

            for entry in feed.entries[:10]:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).isoformat() + "Z"
                    except (ValueError, TypeError):
                        pass

                # Get summary
                summary = None
                if hasattr(entry, "summary"):
                    summary = entry.summary
                    if "<" in summary:
                        import re
                        summary = re.sub(r"<[^>]+>", "", summary)
                    summary = summary[:200] if len(summary) > 200 else summary

                # Get thumbnail
                thumbnail = None
                if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                    thumbnail = entry.media_thumbnail[0].get("url")
                elif hasattr(entry, "media_content") and entry.media_content:
                    thumbnail = entry.media_content[0].get("url")
                elif hasattr(entry, "enclosures") and entry.enclosures:
                    for enc in entry.enclosures:
                        if enc.get("type", "").startswith("image/"):
                            thumbnail = enc.get("url")
                            break

                # Fallback: extract first img src from description/content HTML
                if not thumbnail:
                    import re
                    content_html = entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""
                    description_html = entry.get("description", "") or entry.get("summary", "")
                    for html in [content_html, description_html]:
                        if html:
                            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
                            if img_match:
                                thumbnail = img_match.group(1)
                                break

                items.append(NewsItem(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    source=source_id,
                    source_name=config["name"],
                    published=published,
                    summary=summary,
                    thumbnail=thumbnail,
                    category=config.get("category", "CryptoCurrency"),
                ))

            # Fetch og:image and og:description for items missing thumbnail or summary
            items_needing_og = [
                (i, item) for i, item in enumerate(items)
                if (not item.thumbnail or not item.summary) and item.url
            ]
            if items_needing_og:
                logger.info(
                    f"Fetching og:meta for {len(items_needing_og)} "
                    f"{source_id} articles missing thumbnail/summary"
                )
                og_tasks = [fetch_og_meta(session, item.url) for _, item in items_needing_og]
                og_results = await asyncio.gather(*og_tasks, return_exceptions=True)
                for (idx, item), og_meta in zip(items_needing_og, og_results):
                    if isinstance(og_meta, dict):
                        new_thumbnail = item.thumbnail or og_meta.get("image")
                        new_summary = item.summary or og_meta.get("description")
                        if new_thumbnail != item.thumbnail or new_summary != item.summary:
                            items[idx] = NewsItem(
                                title=item.title,
                                url=item.url,
                                source=item.source,
                                source_name=item.source_name,
                                published=item.published,
                                summary=new_summary,
                                thumbnail=new_thumbnail,
                                category=item.category,
                            )

    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {source_id}")
    except Exception as e:
        logger.error(f"Error fetching {source_id}: {e}")

    return items


async def fetch_all_news() -> None:
    """Fetch news from all sources, cache images, and store in database."""
    global _last_news_refresh
    fresh_items: List[NewsItem] = []

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

    _last_news_refresh = datetime.now(timezone.utc)


async def get_news_from_db(
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Get paginated news articles from database and format for API response."""
    import math

    db_sources = await get_news_sources_from_db()
    sources_to_use = db_sources if db_sources else NEWS_SOURCES

    async with async_session_maker() as db:
        if user_id:
            articles, total_count = await get_articles_for_user(
                db, user_id, page=page, page_size=page_size,
                category=category,
            )
            seen_ids = await get_seen_content_ids(db, user_id, "article")
        else:
            articles, total_count = await get_articles_from_db(
                db, page=page, page_size=page_size, category=category,
            )
            seen_ids = set()

    news_items = [
        article_to_news_item(article, sources_to_use, seen_ids)
        for article in articles
    ]

    sources_list = [
        {"id": sid, "name": cfg["name"], "website": cfg["website"]}
        for sid, cfg in sources_to_use.items()
    ]

    total_pages = (
        1 if page_size == 0
        else math.ceil(total_count / page_size) if total_count > 0
        else 1
    )

    now = datetime.now(timezone.utc)
    return {
        "news": news_items,
        "sources": sources_list,
        "cached_at": now.isoformat() + "Z",
        "cache_expires_at": (
            now + timedelta(minutes=NEWS_CACHE_CHECK_MINUTES)
        ).isoformat() + "Z",
        "total_items": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "retention_days": NEWS_ITEM_MAX_AGE_DAYS,
    }


# =============================================================================
# News & Video Endpoints
# =============================================================================


@router.get("/", response_model=NewsResponse)
async def get_news(
    force_refresh: bool = False,
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = Query(None, description="Filter by category (e.g., CryptoCurrency, Technology)"),
    current_user: User = Depends(get_current_user),
):
    """
    Get news from database cache with pagination.

    News is fetched from multiple sources by background service and stored in database.
    Returns immediately from database. Background refresh runs every 30 minutes.
    Use force_refresh=true to trigger immediate refresh (runs in background).
    """
    # page_size=0 means "return all articles" (no LIMIT)
    if page_size != 0:
        page_size = max(10, page_size)
    page = max(1, page)

    if force_refresh:
        logger.info("Force refresh requested - triggering news fetch...")
        asyncio.create_task(fetch_all_news())

    try:
        data = await get_news_from_db(
            page=page, page_size=page_size,
            category=category, user_id=current_user.id,
        )
        if data["news"] or data["total_items"] > 0:
            logger.debug(f"Serving page {page} with {len(data['news'])} news articles from database")
            return NewsResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get news from database: {e}")

    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                stale_cache = json.load(f)
            logger.info("Serving from JSON cache (database empty)")
            return NewsResponse(**stale_cache)
        except Exception:
            pass

    if not _last_news_refresh:
        logger.info("No news cache available - triggering initial fetch...")
        asyncio.create_task(fetch_all_news())

    raise HTTPException(status_code=503, detail="News not yet available - please try again shortly")


@router.get("/sources")
async def get_sources(current_user: User = Depends(get_current_user)):
    """Get list of news sources with links (from database)"""
    db_sources = await get_news_sources_from_db()
    sources_to_use = db_sources if db_sources else NEWS_SOURCES
    return {
        "sources": [
            {"id": sid, "name": cfg["name"], "website": cfg["website"], "type": cfg["type"]}
            for sid, cfg in sources_to_use.items()
        ],
        "note": "TikTok is not included as it lacks a public API for content. "
                "These sources provide reliable crypto news via RSS feeds or public APIs."
    }


@router.get("/categories")
async def get_categories(current_user: User = Depends(get_current_user)):
    """Get list of available news categories."""
    return {
        "categories": NEWS_CATEGORIES,
        "default": "CryptoCurrency",
    }


@router.post("/seen")
async def mark_content_seen(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    """Mark a single article or video as seen/unseen."""
    content_type = payload.get("content_type")
    content_id = payload.get("content_id")
    seen = payload.get("seen", True)

    if content_type not in ("article", "video"):
        raise HTTPException(400, "content_type must be 'article' or 'video'")
    if not isinstance(content_id, int):
        raise HTTPException(400, "content_id must be an integer")

    async with async_session_maker() as db:
        if seen:
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            stmt = sqlite_insert(UserContentSeenStatus).values(
                user_id=current_user.id,
                content_type=content_type,
                content_id=content_id,
            ).on_conflict_do_nothing(
                index_elements=["user_id", "content_type", "content_id"],
            )
            await db.execute(stmt)
        else:
            from sqlalchemy import delete
            await db.execute(
                delete(UserContentSeenStatus).where(
                    UserContentSeenStatus.user_id == current_user.id,
                    UserContentSeenStatus.content_type == content_type,
                    UserContentSeenStatus.content_id == content_id,
                )
            )
        await db.commit()

    return {"ok": True}


@router.post("/seen/bulk")
async def bulk_mark_content_seen(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    """Bulk mark articles or videos as seen/unseen."""
    content_type = payload.get("content_type")
    content_ids = payload.get("content_ids", [])
    seen = payload.get("seen", True)

    if content_type not in ("article", "video"):
        raise HTTPException(400, "content_type must be 'article' or 'video'")
    if not isinstance(content_ids, list) or not content_ids:
        raise HTTPException(400, "content_ids must be a non-empty list")

    async with async_session_maker() as db:
        if seen:
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            for cid in content_ids:
                stmt = sqlite_insert(UserContentSeenStatus).values(
                    user_id=current_user.id,
                    content_type=content_type,
                    content_id=cid,
                ).on_conflict_do_nothing(
                    index_elements=[
                        "user_id", "content_type", "content_id",
                    ],
                )
                await db.execute(stmt)
        else:
            from sqlalchemy import delete
            await db.execute(
                delete(UserContentSeenStatus).where(
                    UserContentSeenStatus.user_id == current_user.id,
                    UserContentSeenStatus.content_type == content_type,
                    UserContentSeenStatus.content_id.in_(content_ids),
                )
            )
        await db.commit()

    return {"ok": True, "count": len(content_ids)}


@router.post("/article-issue")
async def mark_article_issue(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    """Flag an article as having a playback/content issue."""
    article_id = payload.get("article_id")
    has_issue = payload.get("has_issue", True)

    if not isinstance(article_id, int):
        raise HTTPException(400, "article_id must be an integer")

    async with async_session_maker() as db:
        await db.execute(
            update(NewsArticle)
            .where(NewsArticle.id == article_id)
            .values(has_issue=bool(has_issue))
        )
        await db.commit()

    return {"ok": True}


@router.get("/image/{article_id}")
async def get_article_image(
    article_id: int,
):
    """
    Serve cached article thumbnail image from filesystem.

    Returns the image with 7-day cache headers.
    """
    from app.services.news_image_cache import NEWS_IMAGES_DIR

    async with async_session_maker() as db:
        result = await db.execute(
            select(NewsArticle.cached_thumbnail_path).where(NewsArticle.id == article_id)
        )
        row = result.first()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Image not found")

    filepath = NEWS_IMAGES_DIR / row[0]
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Image file missing")

    ext = filepath.suffix.lower()
    mime_map = {".webp": "image/webp", ".jpg": "image/jpeg", ".png": "image/png", ".gif": "image/gif"}
    mime_type = mime_map.get(ext, "image/webp")

    return Response(
        content=filepath.read_bytes(),
        media_type=mime_type,
        headers={
            "Cache-Control": "public, max-age=604800",
            "ETag": f'"{article_id}"',
        },
    )


@router.get("/cache-stats")
async def get_cache_stats(current_user: User = Depends(get_current_user)):
    """Get news cache statistics including database article count."""
    from sqlalchemy import func

    async with async_session_maker() as db:
        result = await db.execute(select(func.count(NewsArticle.id)))
        article_count = result.scalar() or 0

        result = await db.execute(
            select(func.count(NewsArticle.id)).where(
                NewsArticle.cached_thumbnail_path.isnot(None)
            )
        )
        articles_with_images = result.scalar() or 0

    return {
        "database": {
            "article_count": article_count,
            "articles_with_images": articles_with_images,
        },
        "last_refresh": _last_news_refresh.isoformat() + "Z" if _last_news_refresh else None,
        "cache_check_interval_minutes": NEWS_CACHE_CHECK_MINUTES,
        "max_age_days": NEWS_ITEM_MAX_AGE_DAYS,
    }


@router.post("/cleanup")
async def cleanup_cache(current_user: User = Depends(get_current_user)):
    """Manually trigger cleanup of old news articles and videos."""
    articles_deleted, image_files_deleted = await cleanup_articles_with_images()
    async with async_session_maker() as db:
        videos_deleted = await cleanup_old_videos(db)
    return {
        "articles_deleted": articles_deleted,
        "videos_deleted": videos_deleted,
        "image_files_deleted": image_files_deleted,
        "message": (
            f"Cleaned up {articles_deleted} articles, "
            f"{videos_deleted} videos, and "
            f"{image_files_deleted} image files"
        ),
    }


async def cleanup_articles_with_images(
    max_age_days: int = NEWS_ITEM_MAX_AGE_DAYS,
    min_keep: int = 5,
) -> tuple:
    """Run per-source article cleanup and delete associated files.
    Cleans up: image files, TTS audio cache dirs, TTS DB records.
    Returns (articles_deleted, image_files_deleted)."""
    import shutil
    from app.services.news_image_cache import NEWS_IMAGES_DIR
    from app.routers.news_tts_router import TTS_CACHE_DIR
    from app.models import ArticleTTS

    image_files_deleted = 0
    tts_dirs_deleted = 0
    async with async_session_maker() as db:
        # Collect image paths and article IDs that will be deleted
        # We need to query before deleting
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        paths_to_delete = []
        article_ids_to_delete = []

        # Per-source: find articles beyond effective cutoff
        source_ids_result = await db.execute(
            select(NewsArticle.source_id).where(
                NewsArticle.source_id.isnot(None)
            ).group_by(NewsArticle.source_id)
        )
        source_ids = [row[0] for row in source_ids_result.all()]

        for sid in source_ids:
            nth_result = await db.execute(
                select(NewsArticle.published_at)
                .where(NewsArticle.source_id == sid)
                .order_by(desc(NewsArticle.published_at))
                .offset(min_keep - 1)
                .limit(1)
            )
            nth_date = nth_result.scalar()
            effective_cutoff = (
                nth_date if nth_date and nth_date < cutoff else cutoff
            )

            result = await db.execute(
                select(
                    NewsArticle.id, NewsArticle.cached_thumbnail_path
                ).where(
                    NewsArticle.source_id == sid,
                    NewsArticle.published_at < effective_cutoff,
                )
            )
            for row in result.fetchall():
                article_ids_to_delete.append(row[0])
                if row[1]:
                    paths_to_delete.append(row[1])

        # Orphan articles (no source_id)
        result = await db.execute(
            select(
                NewsArticle.id, NewsArticle.cached_thumbnail_path
            ).where(
                NewsArticle.source_id.is_(None),
                NewsArticle.fetched_at < cutoff,
            )
        )
        for row in result.fetchall():
            article_ids_to_delete.append(row[0])
            if row[1]:
                paths_to_delete.append(row[1])

        # Delete TTS DB records for articles being removed
        if article_ids_to_delete:
            await db.execute(
                ArticleTTS.__table__.delete().where(
                    ArticleTTS.article_id.in_(article_ids_to_delete)
                )
            )
            await db.commit()

        articles_deleted = await cleanup_old_articles(
            db, max_age_days=max_age_days, min_keep=min_keep
        )

    # Delete image files
    for filename in paths_to_delete:
        filepath = NEWS_IMAGES_DIR / filename
        if filepath.exists():
            try:
                filepath.unlink()
                image_files_deleted += 1
            except OSError:
                pass

    # Delete TTS cache directories
    for aid in article_ids_to_delete:
        tts_dir = TTS_CACHE_DIR / str(aid)
        if tts_dir.is_dir():
            try:
                shutil.rmtree(tts_dir)
                tts_dirs_deleted += 1
            except OSError:
                pass

    if tts_dirs_deleted:
        logger.info(f"Cleanup: deleted {tts_dirs_deleted} TTS cache dirs")

    return articles_deleted, image_files_deleted


@router.get("/videos", response_model=VideoResponse)
async def get_videos(
    force_refresh: bool = False,
    category: Optional[str] = Query(None, description="Filter by category (e.g., CryptoCurrency)"),
    current_user: User = Depends(get_current_user),
):
    """
    Get video news from database cache.

    Videos are fetched from YouTube channels by background service and stored in database.
    Returns immediately from database. Background refresh runs every 60 minutes.
    Use force_refresh=true to trigger immediate refresh (runs in background).
    """
    if force_refresh:
        logger.info("Force refresh requested - triggering video fetch...")
        asyncio.create_task(fetch_all_videos())

    try:
        data = await get_videos_from_db(
            category=category, user_id=current_user.id,
        )
        if data["videos"]:
            logger.debug(f"Serving {len(data['videos'])} videos from database")
            return VideoResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get videos from database: {e}")

    cache = load_video_cache()
    if cache and cache.get("videos"):
        logger.info("Serving videos from JSON cache (database empty)")
        return VideoResponse(**cache)

    if not _last_video_refresh:
        logger.info("No video cache available - triggering initial fetch...")
        asyncio.create_task(fetch_all_videos())

    raise HTTPException(status_code=503, detail="Videos not yet available - please try again shortly")


@router.get("/video-sources")
async def get_video_sources(current_user: User = Depends(get_current_user)):
    """Get list of video sources (YouTube channels) with links (from database)"""
    db_sources = await get_video_sources_from_db()
    sources_to_use = db_sources if db_sources else VIDEO_SOURCES
    return {
        "sources": [
            {
                "id": sid,
                "name": cfg["name"],
                "website": cfg["website"],
                "description": cfg.get("description", ""),
            }
            for sid, cfg in sources_to_use.items()
        ],
        "note": "These are reputable crypto YouTube channels providing educational content, "
                "market analysis, and news coverage."
    }


# =============================================================================
# Article Content Extraction
# =============================================================================


async def _mark_content_fetch_failed(url: str):
    """Persist that content extraction failed so we never re-fetch."""
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(NewsArticle).where(NewsArticle.url == url)
            )
            db_article = result.scalar_one_or_none()
            if db_article:
                db_article.content_fetch_failed = True
                db_article.content_fetched_at = datetime.utcnow()
                await db.commit()
    except Exception as e:
        logger.warning(f"Failed to mark content_fetch_failed for {url}: {e}")


@router.get("/article-content", response_model=ArticleContentResponse)
async def get_article_content(
    url: str,
    current_user: User = Depends(get_current_user),
):
    """
    Extract article content from a news URL.

    Uses trafilatura to extract the main article text, title, and metadata.
    Results are cached persistently in the database so all users benefit.
    Only allows fetching from domains in the content_sources database table.
    """
    # L1: Check in-memory cache (fast, short-lived)
    now = time.time()
    async with _article_cache_lock:
        if url in _article_cache:
            cached_response, cached_at = _article_cache[url]
            if now - cached_at < _ARTICLE_CACHE_TTL:
                return cached_response

    # L2: Check DB cache (persistent, shared across users/restarts)
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(NewsArticle).where(NewsArticle.url == url)
            )
            db_article = result.scalar_one_or_none()
            if db_article:
                # Already have content — return it
                if db_article.content:
                    db_response = ArticleContentResponse(
                        url=url,
                        title=db_article.title,
                        content=db_article.content,
                        author=db_article.author,
                        success=True,
                    )
                    # Promote to L1 cache
                    async with _article_cache_lock:
                        _article_cache[url] = (db_response, time.time())
                    return db_response

                # Previous fetch failed — don't re-fetch from external source
                if db_article.content_fetch_failed:
                    fail_response = ArticleContentResponse(
                        url=url,
                        success=False,
                        error="Content extraction previously failed for this article.",
                    )
                    # Promote to L1 cache so subsequent requests are instant
                    async with _article_cache_lock:
                        _article_cache[url] = (fail_response, time.time())
                    return fail_response
    except Exception as e:
        logger.warning(f"DB content cache lookup failed: {e}")

    # Check per-source scrape policy (RSS-only sources cannot be scraped)
    scrape_allowed, crawl_delay = await get_source_scrape_policy(url)
    if not scrape_allowed:
        no_scrape_response = ArticleContentResponse(
            url=url,
            success=False,
            error="Full article content is not available for this source.",
        )
        # Cache the "not available" response so we don't re-check
        async with _article_cache_lock:
            _article_cache[url] = (no_scrape_response, time.time())
        return no_scrape_response

    # Known paywalled domains
    PAYWALLED_DOMAINS = {
        'www.ft.com', 'ft.com',
        'www.wsj.com', 'wsj.com',
        'www.barrons.com', 'barrons.com',
    }

    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ArticleContentResponse(
                url=url,
                success=False,
                error="Invalid URL format"
            )

        domain = parsed.netloc.lower()
        allowed_domains = await get_allowed_article_domains()
        if domain not in allowed_domains:
            logger.warning(f"Attempted to fetch article from non-allowed domain: {domain}")
            return ArticleContentResponse(
                url=url,
                success=False,
                error=f"Domain not allowed. Supported: {', '.join(sorted(allowed_domains))}"
            )

        if domain in PAYWALLED_DOMAINS:
            return ArticleContentResponse(
                url=url,
                success=False,
                error="This source requires a subscription. Open on the website to read the full article."
            )
    except Exception as e:
        return ArticleContentResponse(
            url=url,
            success=False,
            error=f"URL validation failed: {str(e)}"
        )

    try:
        # Respect per-source crawl delay before fetching
        if crawl_delay > 0:
            parsed_url = urlparse(url)
            fetch_domain = parsed_url.netloc.lower()
            async with _domain_last_fetch_lock:
                last_fetch = _domain_last_fetch.get(fetch_domain, 0)
                elapsed = time.time() - last_fetch
                if elapsed < crawl_delay:
                    await asyncio.sleep(crawl_delay - elapsed)
                _domain_last_fetch[fetch_domain] = time.time()

        # Increase max_field_size: some sites (Yahoo Finance) return huge
        # Set-Cookie headers (~27KB) that exceed aiohttp's 8190-byte default.
        async with aiohttp.ClientSession(
            max_line_size=32768,
            max_field_size=32768,
        ) as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"macOS"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
            async with session.get(url, headers=headers, timeout=15, allow_redirects=True) as response:
                if response.status != 200:
                    await _mark_content_fetch_failed(url)
                    return ArticleContentResponse(
                        url=url,
                        success=False,
                        error=f"Failed to fetch article: HTTP {response.status}"
                    )

                html_content = await response.text()

        # Extract article content using trafilatura (shared thread pool)
        loop = asyncio.get_event_loop()
        extracted = await loop.run_in_executor(
            _trafilatura_executor,
            lambda: trafilatura.extract(
                html_content,
                include_comments=False,
                include_tables=True,
                include_links=False,
                no_fallback=False,
                favor_recall=True,
                output_format="markdown"
            )
        )

        metadata = await loop.run_in_executor(
            _trafilatura_executor,
            lambda: trafilatura.extract_metadata(html_content)
        )

        if not extracted:
            await _mark_content_fetch_failed(url)
            return ArticleContentResponse(
                url=url,
                success=False,
                error="Could not extract article content. The page may be paywalled or use dynamic loading."
            )

        # Detect paywall content
        extracted_lower = extracted.lower()
        paywall_phrases = [
            'subscribe to read', 'subscription required', 'sign in to read',
            'premium content', 'become a member', 'start your free trial',
            'already a subscriber', 'subscribe for full access',
        ]
        paywall_hits = sum(1 for phrase in paywall_phrases if phrase in extracted_lower)
        if paywall_hits >= 2 and len(extracted) < 1500:
            await _mark_content_fetch_failed(url)
            return ArticleContentResponse(
                url=url,
                success=False,
                error="This source requires a subscription. Open on the website to read the full article."
            )

        title = None
        author = None
        date = None

        if metadata:
            title = metadata.title
            author = metadata.author
            if metadata.date:
                date = metadata.date

        logger.info(f"Successfully extracted article from {domain}: {len(extracted)} chars")

        result = ArticleContentResponse(
            url=url,
            title=title,
            content=extracted,
            author=author,
            date=date,
            success=True
        )

        # L1: Cache in memory
        async with _article_cache_lock:
            if len(_article_cache) >= _ARTICLE_CACHE_MAX:
                oldest_key = min(_article_cache, key=lambda k: _article_cache[k][1])
                del _article_cache[oldest_key]
            _article_cache[url] = (result, time.time())

        # L2: Persist to DB (fire-and-forget, don't block the response)
        try:
            async with async_session_maker() as db:
                db_result = await db.execute(
                    select(NewsArticle).where(NewsArticle.url == url)
                )
                db_article = db_result.scalar_one_or_none()
                if db_article:
                    db_article.content = extracted
                    db_article.content_fetched_at = datetime.utcnow()
                    await db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist article content to DB: {e}")

        return result

    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching article: {url}")
        await _mark_content_fetch_failed(url)
        return ArticleContentResponse(
            url=url,
            success=False,
            error="Request timed out. The website may be slow or unavailable."
        )
    except Exception as e:
        logger.error(f"Error extracting article content: {e}")
        await _mark_content_fetch_failed(url)
        return ArticleContentResponse(
            url=url,
            success=False,
            error=f"Failed to extract content: {str(e)}"
        )
