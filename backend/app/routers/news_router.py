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
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import (
    ContentSource, NewsArticle, User, UserContentSeenStatus,
    UserSourceSubscription, VideoArticle,
)
from app.auth.dependencies import get_current_user, require_superuser
from app.news_data import (
    CACHE_FILE,
    NEWS_CACHE_CHECK_MINUTES,
    NEWS_CATEGORIES,
    NEWS_ITEM_MAX_AGE_DAYS,
    NEWS_SOURCES,
    VIDEO_CACHE_CHECK_MINUTES,
    VIDEO_SOURCES,
    ArticleContentResponse,
    NewsResponse,
    VideoResponse,
    load_video_cache,
)
from app.routers.news_metrics_router import router as metrics_router
from app.routers.news_tts_router import router as tts_router
from app.services.news_fetch_service import (
    cleanup_articles_with_images,
    cleanup_old_videos,
    fetch_all_news,
    fetch_all_videos,
    get_last_news_refresh,
    get_last_video_refresh,
    get_news_sources_from_db,
    get_video_sources_from_db,
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/news", tags=["news"])

# Include sub-routers (metrics + TTS)
router.include_router(metrics_router)
router.include_router(tts_router)

# =============================================================================
# Database Functions for Content Sources
# =============================================================================


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
            "category": cfg.get("category", "CryptoCurrency"),
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
        {
            "id": sid, "name": cfg["name"],
            "website": cfg["website"],
            "category": cfg.get("category", "CryptoCurrency"),
        }
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
    # S8: Clamp page_size to prevent resource exhaustion (0 = return all for client-side pagination)
    if page_size < 0:
        raise HTTPException(400, "page_size must be non-negative")
    if page_size > 0:
        page_size = min(page_size, 200)
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

    if not get_last_news_refresh():
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
    current_user: User = Depends(require_superuser),
):
    """Flag an article as having a playback/content issue (superuser only)."""
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
    if not filepath.resolve().is_relative_to(NEWS_IMAGES_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid image path")
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
        "last_refresh": get_last_news_refresh().isoformat() + "Z" if get_last_news_refresh() else None,
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

    if not get_last_video_refresh():
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


@router.get("/article-content", response_model=ArticleContentResponse)
async def get_article_content(
    url: str,
    current_user: User = Depends(get_current_user),
):
    """Extract article content from a news URL (delegates to service layer)."""
    from app.services.article_content_service import fetch_article_content
    return await fetch_article_content(url, current_user.id)
