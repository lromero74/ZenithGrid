"""
Article content extraction service.

Handles fetching, extracting, caching, and rate-limiting article content
from external sources. All business logic for the /article-content endpoint
lives here; the router is a thin wrapper.
"""

import asyncio
import concurrent.futures
import logging
import re
import time
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import aiohttp
import trafilatura
from sqlalchemy import select

from app.database import async_session_maker
from app.models import ContentSource, NewsArticle
from app.news_data import ArticleContentResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Shared thread pool for trafilatura (CPU-bound)
_trafilatura_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

# L1: In-memory article content cache
_article_cache: Dict[str, Tuple[Any, float]] = {}
_article_cache_lock = asyncio.Lock()
_ARTICLE_CACHE_TTL = 1800  # 30 minutes
_ARTICLE_CACHE_MAX = 100

# Per-domain crawl delay tracking
_domain_last_fetch: Dict[str, float] = {}
_domain_last_fetch_lock = asyncio.Lock()

# Per-user rate limiting for external article fetches
_article_fetch_counts: Dict[int, List[float]] = {}
_ARTICLE_FETCH_MAX = 30
_ARTICLE_FETCH_WINDOW = 3600  # 1 hour

# Domain aliases: some sources use redirect/CDN domains in RSS feed links
DOMAIN_ALIASES = {
    "independent.co.uk": ["the-independent.com"],
}

# Known paywalled domains
PAYWALLED_DOMAINS = {
    'www.ft.com', 'ft.com',
    'www.wsj.com', 'wsj.com',
    'www.barrons.com', 'barrons.com',
}

# Audio player UI patterns that trafilatura accidentally extracts
_PLAYER_UI_PATTERNS = [
    r'(?m)^Select Voice\s*$',
    r'(?m)^Select Speed\s*$',
    r'(?m)^(?:0\.(?:5|75)x|1\.?(?:00|25|5)?x|1\.75x|2\.?0?x)\s*$',
    r'(?m)^Play Audio\s*$',
    r'(?m)^Listen to this article\s*$',
    r'(?m)^Read Aloud\s*$',
    r'(?m)^Pause\s*$',
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
                bare = domain[4:] if domain.startswith("www.") else domain
                allowed.add(bare)
                allowed.add(f"www.{bare}")
                for alias in DOMAIN_ALIASES.get(bare, []):
                    allowed.add(alias)
                    allowed.add(f"www.{alias}")
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
                match = (domain_bare == src_bare)
                if not match:
                    aliases = DOMAIN_ALIASES.get(src_bare, [])
                    match = domain_bare in aliases
                if match:
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


async def _mark_content_fetch_failed(url: str):
    """Persist that content extraction failed so we never re-fetch."""
    try:
        from datetime import datetime
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


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------


async def fetch_article_content(url: str, user_id: int) -> ArticleContentResponse:
    """
    Extract article content from a news URL.

    Uses trafilatura to extract the main article text, title, and metadata.
    Results are cached persistently in the database so all users benefit.
    Only allows fetching from domains in the content_sources database table.
    """
    from datetime import datetime

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
                if db_article.content:
                    db_response = ArticleContentResponse(
                        url=url,
                        title=db_article.title,
                        content=db_article.content,
                        author=db_article.author,
                        success=True,
                    )
                    async with _article_cache_lock:
                        _article_cache[url] = (db_response, time.time())
                    return db_response

                if db_article.content_fetch_failed:
                    fail_response = ArticleContentResponse(
                        url=url,
                        success=False,
                        error="Content extraction previously failed for this article.",
                    )
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
        async with _article_cache_lock:
            _article_cache[url] = (no_scrape_response, time.time())
        return no_scrape_response

    # Per-user rate limit on external article fetches
    now_ts = time.time()
    user_fetches = _article_fetch_counts.get(user_id, [])
    user_fetches = [t for t in user_fetches if now_ts - t < _ARTICLE_FETCH_WINDOW]
    _article_fetch_counts[user_id] = user_fetches
    if len(user_fetches) >= _ARTICLE_FETCH_MAX:
        return ArticleContentResponse(
            url=url,
            success=False,
            error="Rate limit reached. You can fetch up to 30 articles per hour.",
        )
    _article_fetch_counts[user_id].append(now_ts)

    # URL validation
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ArticleContentResponse(
                url=url, success=False, error="Invalid URL format"
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
            url=url, success=False, error=f"URL validation failed: {str(e)}"
        )

    # Fetch and extract
    try:
        # Respect per-source crawl delay
        if crawl_delay > 0:
            fetch_domain = urlparse(url).netloc.lower()
            async with _domain_last_fetch_lock:
                last_fetch = _domain_last_fetch.get(fetch_domain, 0)
                elapsed = time.time() - last_fetch
                if elapsed < crawl_delay:
                    await asyncio.sleep(crawl_delay - elapsed)
                _domain_last_fetch[fetch_domain] = time.time()

        async with aiohttp.ClientSession(
            max_line_size=32768, max_field_size=32768,
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
                        url=url, success=False,
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
                url=url, success=False,
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
                url=url, success=False,
                error="This source requires a subscription. Open on the website to read the full article."
            )

        # Strip media player UI artifacts
        for pattern in _PLAYER_UI_PATTERNS:
            extracted = re.sub(pattern, '', extracted)
        extracted = re.sub(r'\n{3,}', '\n\n', extracted).strip()

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
            url=url, title=title, content=extracted,
            author=author, date=date, success=True,
        )

        # L1: Cache in memory
        async with _article_cache_lock:
            if len(_article_cache) >= _ARTICLE_CACHE_MAX:
                oldest_key = min(_article_cache, key=lambda k: _article_cache[k][1])
                del _article_cache[oldest_key]
            _article_cache[url] = (result, time.time())

        # L2: Persist to DB
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
            url=url, success=False,
            error="Request timed out. The website may be slow or unavailable."
        )
    except Exception as e:
        logger.error(f"Error extracting article content: {e}")
        await _mark_content_fetch_failed(url)
        return ArticleContentResponse(
            url=url, success=False,
            error=f"Failed to extract content: {str(e)}"
        )
