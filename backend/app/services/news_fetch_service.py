"""
News Fetch Service

Orchestrates fetching news articles and videos from configured sources,
storing them in the database, and managing caches.

Contains all news/video fetching, storing, and cleanup logic.
Routers import from here — never the reverse.
"""

import asyncio
import html as html_module
import logging
import re
import shutil
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import aiohttp
import feedparser
from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import ArticleTTS, ContentSource, NewsArticle, VideoArticle
from app.news_data import (
    NEWS_ITEM_MAX_AGE_DAYS,
    NEWS_SOURCES,
    VIDEO_CACHE_CHECK_MINUTES,
    VIDEO_SOURCES,
    NewsItem,
    VideoItem,
    load_video_cache,
    merge_news_items,
    prune_old_items,
    save_video_cache,
)
from app.paths import TTS_CACHE_DIR
from app.services.news_image_cache import NEWS_IMAGES_DIR, download_and_save_image

logger = logging.getLogger(__name__)

# Track when we last refreshed news/videos (in-memory for this process)
_last_news_refresh: Optional[datetime] = None
_last_video_refresh: Optional[datetime] = None


def get_last_news_refresh() -> Optional[datetime]:
    """Get the timestamp of the last news refresh."""
    return _last_news_refresh


def get_last_video_refresh() -> Optional[datetime]:
    """Get the timestamp of the last video refresh."""
    return _last_video_refresh


# =============================================================================
# Source Query Functions
# =============================================================================


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


async def _get_source_key_to_id_map(source_type: Optional[str] = None) -> Dict[str, int]:
    """Build a mapping of source_key -> content_sources.id for linking articles/videos."""
    async with async_session_maker() as db:
        query = select(ContentSource.source_key, ContentSource.id)
        if source_type:
            query = query.where(ContentSource.type == source_type)
        result = await db.execute(query)
        return {row[0]: row[1] for row in result.all()}


# =============================================================================
# Fetch Functions
# =============================================================================


async def fetch_og_meta(session: aiohttp.ClientSession, url: str) -> Dict[str, Optional[str]]:
    """Fetch og:image and og:description meta tags from an article URL."""
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


async def fetch_youtube_videos(
    session: aiohttp.ClientSession, source_id: str, config: Dict,
) -> List[VideoItem]:
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


async def fetch_reddit_news(
    session: aiohttp.ClientSession, source_id: str, config: Dict,
) -> List[NewsItem]:
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


async def fetch_rss_news(
    session: aiohttp.ClientSession, source_id: str, config: Dict,
) -> List[NewsItem]:
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
                    content_html = (
                        entry.get("content", [{}])[0].get("value", "")
                        if entry.get("content") else ""
                    )
                    description_html = entry.get("description", "") or entry.get("summary", "")
                    for html in [content_html, description_html]:
                        if html:
                            img_match = re.search(
                                r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE,
                            )
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


# =============================================================================
# Storage Functions
# =============================================================================


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


# =============================================================================
# Cleanup Functions
# =============================================================================


async def cleanup_old_videos(
    db: AsyncSession,
    max_age_days: int = NEWS_ITEM_MAX_AGE_DAYS,
    min_keep: int = 5,
) -> int:
    """Delete old videos using per-source retention: keep the greater of
    min_keep videos or videos within max_age_days, per source.
    Videos with no source_id use flat max_age_days cutoff."""
    # Use naive datetime to match SQLite's naive storage (avoids aware vs naive comparison)
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
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


async def cleanup_articles_with_images(
    max_age_days: int = NEWS_ITEM_MAX_AGE_DAYS,
    min_keep: int = 5,
) -> tuple:
    """Run per-source article cleanup and delete associated files.
    Cleans up: image files, TTS audio cache dirs, TTS DB records.
    Returns (articles_deleted, image_files_deleted)."""
    image_files_deleted = 0
    tts_dirs_deleted = 0
    async with async_session_maker() as db:
        # Collect image paths and article IDs that will be deleted
        # We need to query before deleting
        # Use naive datetime to match SQLite's naive storage
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
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

        # Delete TTS DB records and articles for the exact IDs we collected
        articles_deleted = 0
        if article_ids_to_delete:
            await db.execute(
                ArticleTTS.__table__.delete().where(
                    ArticleTTS.article_id.in_(article_ids_to_delete)
                )
            )
            result = await db.execute(
                delete(NewsArticle).where(
                    NewsArticle.id.in_(article_ids_to_delete)
                )
            )
            articles_deleted = result.rowcount
            await db.commit()
            if articles_deleted:
                logger.info(
                    f"Cleaned up {articles_deleted} old news articles"
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


# =============================================================================
# Orchestration Functions
# =============================================================================


async def fetch_all_news() -> None:
    """Fetch news from all sources, cache images, and store in database."""
    global _last_news_refresh

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

    _last_news_refresh = datetime.now(timezone.utc)


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
