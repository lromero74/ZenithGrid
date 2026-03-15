"""
Tests for backend/app/services/article_content_service.py

Covers in-memory caching, DB caching, domain validation, paywall detection,
rate limiting, player UI stripping, scrape policy lookup, and error handling.
All HTTP requests and DB calls are mocked.
"""

import asyncio
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.news_data import ArticleContentResponse
import app.services.article_content_service as acs_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level caches and rate-limit state between tests."""
    acs_mod._article_cache.clear()
    acs_mod._domain_last_fetch.clear()
    acs_mod._article_fetch_counts.clear()
    yield
    acs_mod._article_cache.clear()
    acs_mod._domain_last_fetch.clear()
    acs_mod._article_fetch_counts.clear()


@pytest.fixture
def mock_async_session():
    """Create a mock async DB session via async_session_maker context manager."""
    mock_db = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_db, mock_cm


# ===========================================================================
# PAYWALLED_DOMAINS constant
# ===========================================================================


class TestPaywalledDomains:
    """Tests for the PAYWALLED_DOMAINS constant."""

    def test_known_paywalled_domains_present(self):
        """Happy path: known paywalled domains are in the set."""
        assert "www.ft.com" in acs_mod.PAYWALLED_DOMAINS
        assert "wsj.com" in acs_mod.PAYWALLED_DOMAINS
        assert "barrons.com" in acs_mod.PAYWALLED_DOMAINS

    def test_non_paywalled_domain_absent(self):
        """Edge case: arbitrary domain not in paywalled set."""
        assert "example.com" not in acs_mod.PAYWALLED_DOMAINS


# ===========================================================================
# DOMAIN_ALIASES
# ===========================================================================


class TestDomainAliases:
    """Tests for DOMAIN_ALIASES mapping."""

    def test_independent_alias(self):
        """Happy path: independent.co.uk has known alias."""
        assert "the-independent.com" in acs_mod.DOMAIN_ALIASES["independent.co.uk"]


# ===========================================================================
# _PLAYER_UI_PATTERNS
# ===========================================================================


class TestPlayerUIPatterns:
    """Tests for player UI stripping patterns."""

    def test_select_voice_stripped(self):
        """Audio player 'Select Voice' text is matched by patterns."""
        import re
        text = "Some article text\nSelect Voice\nMore text"
        for pattern in acs_mod._PLAYER_UI_PATTERNS:
            text = re.sub(pattern, '', text)
        assert "Select Voice" not in text

    def test_speed_labels_stripped(self):
        """Speed option labels like '1.5x' are matched."""
        import re
        text = "Content\n1.5x\n2x\n0.75x\nEnd"
        for pattern in acs_mod._PLAYER_UI_PATTERNS:
            text = re.sub(pattern, '', text)
        assert "1.5x" not in text
        assert "2x" not in text


# ===========================================================================
# fetch_article_content — L1 in-memory cache
# ===========================================================================


class TestFetchArticleContentL1Cache:
    """Tests for in-memory (L1) cache behavior."""

    @pytest.mark.asyncio
    async def test_returns_cached_response_within_ttl(self):
        """Happy path: cached response returned without DB lookup."""
        url = "https://example.com/article"
        cached = ArticleContentResponse(url=url, content="cached text", success=True)
        acs_mod._article_cache[url] = (cached, time.time())

        result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is True
        assert result.content == "cached text"

    @pytest.mark.asyncio
    async def test_expired_cache_not_returned(self):
        """Edge case: expired L1 cache entry triggers DB lookup."""
        url = "https://allowed.com/article"
        cached = ArticleContentResponse(url=url, content="stale", success=True)
        # Set cache entry as expired (older than TTL)
        acs_mod._article_cache[url] = (cached, time.time() - acs_mod._ARTICLE_CACHE_TTL - 10)

        # Mock DB to return content so we don't need full HTTP flow
        mock_article = MagicMock()
        mock_article.content = "fresh from db"
        mock_article.title = "Title"
        mock_article.author = "Author"
        mock_article.content_fetch_failed = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_article

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is True
        assert result.content == "fresh from db"


# ===========================================================================
# fetch_article_content — L2 DB cache
# ===========================================================================


class TestFetchArticleContentL2Cache:
    """Tests for database (L2) cache behavior."""

    @pytest.mark.asyncio
    async def test_returns_db_cached_content(self):
        """Happy path: content from DB returned and promoted to L1."""
        url = "https://example.com/db-cached"
        mock_article = MagicMock()
        mock_article.content = "DB content"
        mock_article.title = "DB Title"
        mock_article.author = "DB Author"
        mock_article.content_fetch_failed = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_article

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is True
        assert result.content == "DB content"
        assert result.title == "DB Title"
        # Check L1 was populated
        assert url in acs_mod._article_cache

    @pytest.mark.asyncio
    async def test_returns_failure_for_previously_failed_fetch(self):
        """Edge case: article marked as content_fetch_failed returns failure."""
        url = "https://example.com/failed"
        mock_article = MagicMock()
        mock_article.content = None
        mock_article.content_fetch_failed = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_article

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is False
        assert "previously failed" in result.error


# ===========================================================================
# fetch_article_content — scrape policy
# ===========================================================================


class TestFetchArticleContentScrapePolicy:
    """Tests for source scrape policy checks."""

    @pytest.mark.asyncio
    async def test_scrape_not_allowed_returns_failure(self):
        """Failure: source with scrape_allowed=False returns error."""
        url = "https://noscrape.com/article"

        # DB returns no article (no cache hit)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm), \
             patch.object(acs_mod, 'get_source_scrape_policy', return_value=(False, 0)):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is False
        assert "not available" in result.error


# ===========================================================================
# fetch_article_content — rate limiting
# ===========================================================================


class TestFetchArticleContentRateLimiting:
    """Tests for per-user rate limiting on external fetches."""

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_error(self):
        """Failure: user who has exceeded 30 fetches/hour gets rate limited."""
        url = "https://allowed.com/article"
        user_id = 42

        # Pre-fill user fetch timestamps (30 recent fetches)
        now = time.time()
        acs_mod._article_fetch_counts[user_id] = [now - i for i in range(30)]

        # Mock DB to return no cached article
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm), \
             patch.object(acs_mod, 'get_source_scrape_policy', return_value=(True, 0)):
            result = await acs_mod.fetch_article_content(url, user_id=user_id)

        assert result.success is False
        assert "Rate limit" in result.error

    @pytest.mark.asyncio
    async def test_old_fetch_timestamps_pruned(self):
        """Edge case: timestamps older than the window are pruned."""
        user_id = 99
        old_time = time.time() - acs_mod._ARTICLE_FETCH_WINDOW - 100
        acs_mod._article_fetch_counts[user_id] = [old_time] * 30

        url = "https://allowed.com/article"

        # Mock DB to return cached content so we don't go to HTTP
        mock_article = MagicMock()
        mock_article.content = "content"
        mock_article.title = "T"
        mock_article.author = None
        mock_article.content_fetch_failed = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_article
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm):
            result = await acs_mod.fetch_article_content(url, user_id=user_id)

        # Should succeed because old timestamps were pruned (DB cache hit)
        assert result.success is True


# ===========================================================================
# fetch_article_content — URL validation
# ===========================================================================


class TestFetchArticleContentURLValidation:
    """Tests for URL validation checks."""

    @pytest.mark.asyncio
    async def test_invalid_url_returns_error(self):
        """Failure: URL without scheme/netloc fails validation."""
        url = "not-a-url"

        # Mock DB to return nothing cached
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm), \
             patch.object(acs_mod, 'get_source_scrape_policy', return_value=(True, 0)):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is False
        assert "Invalid URL" in result.error or "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_disallowed_domain_returns_error(self):
        """Failure: domain not in allowed list is rejected."""
        url = "https://evil.com/article"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm), \
             patch.object(acs_mod, 'get_source_scrape_policy', return_value=(True, 0)), \
             patch.object(acs_mod, 'get_allowed_article_domains', return_value={"allowed.com"}):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_paywalled_domain_returns_subscription_error(self):
        """Failure: paywalled domain returns subscription message."""
        url = "https://www.ft.com/article/12345"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm), \
             patch.object(acs_mod, 'get_source_scrape_policy', return_value=(True, 0)), \
             patch.object(acs_mod, 'get_allowed_article_domains',
                          return_value={"www.ft.com", "ft.com"}):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is False
        assert "subscription" in result.error.lower()


# ===========================================================================
# fetch_article_content — HTTP fetch and extraction
# ===========================================================================


class TestFetchArticleContentExtraction:
    """Tests for the HTTP fetch + trafilatura extraction path."""

    @pytest.mark.asyncio
    async def test_successful_extraction(self):
        """Happy path: article fetched and extracted successfully."""
        url = "https://allowed.com/article/1"

        # Mock DB: no cached content
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        # Mock HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html><body>Article</body></html>")
        mock_response_cm = AsyncMock()
        mock_response_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session_http = MagicMock()
        mock_session_http.get = MagicMock(return_value=mock_response_cm)
        mock_http_cm = AsyncMock()
        mock_http_cm.__aenter__ = AsyncMock(return_value=mock_session_http)
        mock_http_cm.__aexit__ = AsyncMock(return_value=False)

        # Mock trafilatura
        mock_metadata = MagicMock()
        mock_metadata.title = "Test Title"
        mock_metadata.author = "Test Author"
        mock_metadata.date = "2025-01-01"

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm), \
             patch.object(acs_mod, 'get_source_scrape_policy', return_value=(True, 0)), \
             patch.object(acs_mod, 'get_allowed_article_domains',
                          return_value={"allowed.com", "www.allowed.com"}), \
             patch('aiohttp.ClientSession', return_value=mock_http_cm), \
             patch('trafilatura.extract', return_value="Extracted article content here."), \
             patch('trafilatura.extract_metadata', return_value=mock_metadata):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is True
        assert result.content == "Extracted article content here."
        assert result.title == "Test Title"
        assert result.author == "Test Author"

    @pytest.mark.asyncio
    async def test_http_error_returns_failure(self):
        """Failure: non-200 HTTP status returns error."""
        url = "https://allowed.com/article/404"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response_cm = AsyncMock()
        mock_response_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session_http = MagicMock()
        mock_session_http.get = MagicMock(return_value=mock_response_cm)
        mock_http_cm = AsyncMock()
        mock_http_cm.__aenter__ = AsyncMock(return_value=mock_session_http)
        mock_http_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm), \
             patch.object(acs_mod, 'get_source_scrape_policy', return_value=(True, 0)), \
             patch.object(acs_mod, 'get_allowed_article_domains',
                          return_value={"allowed.com", "www.allowed.com"}), \
             patch('aiohttp.ClientSession', return_value=mock_http_cm), \
             patch.object(acs_mod, '_mark_content_fetch_failed', new_callable=AsyncMock):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is False
        assert "HTTP 403" in result.error

    @pytest.mark.asyncio
    async def test_extraction_returns_none_marks_failed(self):
        """Failure: trafilatura returns None marks article as failed."""
        url = "https://allowed.com/article/empty"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html></html>")
        mock_response_cm = AsyncMock()
        mock_response_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session_http = MagicMock()
        mock_session_http.get = MagicMock(return_value=mock_response_cm)
        mock_http_cm = AsyncMock()
        mock_http_cm.__aenter__ = AsyncMock(return_value=mock_session_http)
        mock_http_cm.__aexit__ = AsyncMock(return_value=False)

        mock_mark_failed = AsyncMock()

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm), \
             patch.object(acs_mod, 'get_source_scrape_policy', return_value=(True, 0)), \
             patch.object(acs_mod, 'get_allowed_article_domains',
                          return_value={"allowed.com", "www.allowed.com"}), \
             patch('aiohttp.ClientSession', return_value=mock_http_cm), \
             patch('trafilatura.extract', return_value=None), \
             patch.object(acs_mod, '_mark_content_fetch_failed', mock_mark_failed):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is False
        assert "Could not extract" in result.error
        mock_mark_failed.assert_called_once_with(url)

    @pytest.mark.asyncio
    async def test_timeout_returns_failure(self):
        """Failure: timeout during fetch returns appropriate error."""
        url = "https://allowed.com/article/slow"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_http_cm = AsyncMock()
        mock_http_cm.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_http_cm.__aexit__ = AsyncMock(return_value=False)

        mock_mark_failed = AsyncMock()

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm), \
             patch.object(acs_mod, 'get_source_scrape_policy', return_value=(True, 0)), \
             patch.object(acs_mod, 'get_allowed_article_domains',
                          return_value={"allowed.com", "www.allowed.com"}), \
             patch('aiohttp.ClientSession', return_value=mock_http_cm), \
             patch.object(acs_mod, '_mark_content_fetch_failed', mock_mark_failed):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is False
        assert "timed out" in result.error.lower() or "Failed to extract" in result.error


# ===========================================================================
# fetch_article_content — paywall detection
# ===========================================================================


class TestPaywallDetection:
    """Tests for dynamic paywall content detection."""

    @pytest.mark.asyncio
    async def test_paywall_content_detected(self):
        """Failure: short content with multiple paywall phrases is rejected."""
        url = "https://allowed.com/article/paywalled"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html>paywall</html>")
        mock_response_cm = AsyncMock()
        mock_response_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session_http = MagicMock()
        mock_session_http.get = MagicMock(return_value=mock_response_cm)
        mock_http_cm = AsyncMock()
        mock_http_cm.__aenter__ = AsyncMock(return_value=mock_session_http)
        mock_http_cm.__aexit__ = AsyncMock(return_value=False)

        # Short content with 2+ paywall phrases
        paywall_text = "Subscribe to read the full article. Already a subscriber? Sign in."

        mock_mark_failed = AsyncMock()

        with patch.object(acs_mod, 'async_session_maker', return_value=mock_session_cm), \
             patch.object(acs_mod, 'get_source_scrape_policy', return_value=(True, 0)), \
             patch.object(acs_mod, 'get_allowed_article_domains',
                          return_value={"allowed.com", "www.allowed.com"}), \
             patch('aiohttp.ClientSession', return_value=mock_http_cm), \
             patch('trafilatura.extract', return_value=paywall_text), \
             patch('trafilatura.extract_metadata', return_value=None), \
             patch.object(acs_mod, '_mark_content_fetch_failed', mock_mark_failed):
            result = await acs_mod.fetch_article_content(url, user_id=1)

        assert result.success is False
        assert "subscription" in result.error.lower()


# ===========================================================================
# L1 cache eviction
# ===========================================================================


class TestL1CacheEviction:
    """Tests for in-memory cache max size eviction."""

    def test_cache_max_size_constant(self):
        """The cache max size is 100."""
        assert acs_mod._ARTICLE_CACHE_MAX == 100

    def test_cache_ttl_constant(self):
        """The cache TTL is 30 minutes (1800 seconds)."""
        assert acs_mod._ARTICLE_CACHE_TTL == 1800
