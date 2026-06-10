"""
News Service — business logic for news article queries and response assembly.

Extracted from news_router.py. Contains:
- Database query functions for articles and sources
- Article-to-response-dict transformation
- Paginated response assembly
"""

import logging
from app.utils.timeutil import utcnow
import math
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import (
    ContentSource, NewsArticle, UserContentSeenStatus, UserSourceSubscription,
)
from app.news_data import (
    NEWS_CACHE_CHECK_MINUTES,
    NEWS_ITEM_MAX_AGE_DAYS,
    NEWS_SOURCES,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Source queries
# =============================================================================


async def get_all_sources_from_db() -> Dict[str, List[Dict]]:
    """Get all enabled sources from database for API responses."""
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
# Article queries
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
    - Per-user retention_days: applied post-query in Python for DB portability
    - user_category override applied in response layer, not here
    """

    default_cutoff = utcnow() - timedelta(days=NEWS_ITEM_MAX_AGE_DAYS)

    query = (
        select(NewsArticle, UserSourceSubscription.retention_days)
        .outerjoin(
            ContentSource, NewsArticle.source_id == ContentSource.id
        )
        .outerjoin(
            UserSourceSubscription,
            (UserSourceSubscription.source_id == ContentSource.id)
            & (UserSourceSubscription.user_id == user_id),
        )
        .where(
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
        .where(NewsArticle.published_at >= default_cutoff)
    )

    if category:
        query = query.where(NewsArticle.category == category)

    now = utcnow()
    use_sql_retention = db.bind.dialect.name == "postgresql" if db.bind else False

    interval_1day = literal_column("INTERVAL '1 day'")
    if use_sql_retention:
        query = query.where(
            (UserSourceSubscription.retention_days.is_(None))
            | (NewsArticle.published_at >= now - UserSourceSubscription.retention_days * interval_1day)
        )

    query = query.order_by(desc(NewsArticle.published_at))

    if use_sql_retention:
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0

        if page_size > 0:
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
        result = await db.execute(query)
        filtered = [article for article, _retention in result.all()]
    else:
        result = await db.execute(query)
        filtered = []
        for article, retention_days in result.all():
            if retention_days is not None:
                cutoff = now - timedelta(days=retention_days)
                if article.published_at and article.published_at < cutoff:
                    continue
            filtered.append(article)
        total_count = len(filtered)
        if page_size > 0:
            start = (page - 1) * page_size
            filtered = filtered[start:start + page_size]

    return filtered, total_count


async def get_articles_from_db(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = None,
) -> tuple[List[NewsArticle], int]:
    """Get articles without user filtering (for internal use)."""

    cutoff = utcnow() - timedelta(days=NEWS_ITEM_MAX_AGE_DAYS)

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


# =============================================================================
# Transformation / assembly
# =============================================================================


def article_to_news_item(
    article: "NewsArticle",
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


def build_news_response(
    news_items: List[Dict],
    sources: Dict[str, Dict],
    total_count: int,
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    """Assemble the paginated news API response dict."""
    sources_list = [
        {
            "id": sid, "name": cfg["name"],
            "website": cfg["website"],
            "category": cfg.get("category", "CryptoCurrency"),
        }
        for sid, cfg in sources.items()
    ]

    total_pages = (
        1 if page_size == 0
        else math.ceil(total_count / page_size) if total_count > 0
        else 1
    )

    now = utcnow()
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


async def get_news_from_db(
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Get paginated news articles from database and format for API response."""
    from app.services.news_fetch_service import get_news_sources_from_db

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

    return build_news_response(
        news_items=news_items,
        sources=sources_to_use,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )
