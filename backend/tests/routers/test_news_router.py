"""
Tests for backend/app/routers/news_router.py

Covers news article list/filter/read endpoints, pagination,
user-specific read state, article content extraction, video endpoints,
seen/unseen marking, and cache stats.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import (
    ContentSource, NewsArticle, User, UserContentSeenStatus,
    UserSourceSubscription, VideoArticle,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_user(db_session):
    user = User(
        id=1, email="test@test.com",
        hashed_password="hashed", is_active=True, is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def admin_user(db_session):
    user = User(
        id=2, email="admin@test.com",
        hashed_password="hashed", is_active=True, is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def sample_article(db_session):
    article = NewsArticle(
        id=1, title="Bitcoin hits 100k", url="https://example.com/btc-100k",
        source="coindesk", summary="BTC surges past 100k.",
        published_at=datetime.now(timezone.utc), category="CryptoCurrency",
    )
    db_session.add(article)
    await db_session.flush()
    return article


@pytest.fixture
async def sample_video(db_session):
    video = VideoArticle(
        id=1, title="Weekly Crypto Update", url="https://youtube.com/watch?v=abc123",
        video_id="abc123", source="coin_bureau", channel_name="Coin Bureau",
        published_at=datetime.now(timezone.utc), category="CryptoCurrency",
    )
    db_session.add(video)
    await db_session.flush()
    return video


# =============================================================================
# article_to_news_item helper
# =============================================================================


class TestArticleToNewsItem:
    """Tests for article_to_news_item helper."""

    def test_converts_article_to_dict(self, sample_article):
        """Happy path: converts NewsArticle to dict."""
        # Need to access it outside async context using a sync test
        pass

    @pytest.mark.asyncio
    async def test_article_to_news_item_basic(self, db_session, sample_article):
        """Happy path: converts article to news item dict."""
        from app.routers.news_router import article_to_news_item
        result = article_to_news_item(sample_article)
        assert result["id"] == 1
        assert result["title"] == "Bitcoin hits 100k"
        assert result["source"] == "coindesk"
        assert result["is_seen"] is False

    @pytest.mark.asyncio
    async def test_article_to_news_item_with_seen_ids(self, db_session, sample_article):
        """Edge case: marks article as seen when in seen_ids."""
        from app.routers.news_router import article_to_news_item
        result = article_to_news_item(sample_article, seen_ids={1})
        assert result["is_seen"] is True

    @pytest.mark.asyncio
    async def test_article_to_news_item_cached_thumbnail(self, db_session):
        """Edge case: cached thumbnail generates /api/news/image/ URL."""
        article = NewsArticle(
            id=2, title="Test", url="https://example.com/test",
            source="test", published_at=datetime.now(timezone.utc),
            cached_thumbnail_path="test/thumb.webp",
        )
        db_session.add(article)
        await db_session.flush()

        from app.routers.news_router import article_to_news_item
        result = article_to_news_item(article)
        assert result["thumbnail"] == "/api/news/image/2"


# =============================================================================
# get_news endpoint
# =============================================================================


class TestGetNews:
    """Tests for the get_news endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_router.get_news_from_db", new_callable=AsyncMock)
    async def test_get_news_success(self, mock_get, db_session, test_user):
        """Happy path: returns paginated news from database."""
        mock_get.return_value = {
            "news": [{
                "id": 1, "title": "Test", "url": "https://example.com/test",
                "source": "coindesk", "source_name": "CoinDesk",
                "category": "CryptoCurrency",
            }],
            "sources": [],
            "cached_at": "2026-01-01T00:00:00Z",
            "cache_expires_at": "2026-01-01T00:30:00Z",
            "total_items": 1,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
            "retention_days": 7,
        }
        from app.routers.news_router import get_news
        result = await get_news(
            force_refresh=False, page=1, page_size=50,
            category=None, current_user=test_user,
        )
        assert result.total_items == 1

    @pytest.mark.asyncio
    async def test_get_news_negative_page_size_raises_400(self, test_user):
        """Failure case: negative page_size raises 400."""
        from app.routers.news_router import get_news
        with pytest.raises(HTTPException) as exc_info:
            await get_news(
                force_refresh=False, page=1, page_size=-1,
                category=None, current_user=test_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("app.routers.news_router.get_news_from_db", new_callable=AsyncMock)
    @patch("app.routers.news_router.CACHE_FILE")
    @patch("app.routers.news_router.get_last_news_refresh", return_value=None)
    async def test_get_news_503_when_no_data(
        self, mock_refresh, mock_cache_file, mock_get, test_user,
    ):
        """Failure case: no data available raises 503."""
        mock_get.return_value = {"news": [], "total_items": 0}
        mock_cache_file.exists.return_value = False

        from app.routers.news_router import get_news
        with pytest.raises(HTTPException) as exc_info:
            await get_news(
                force_refresh=False, page=1, page_size=50,
                category=None, current_user=test_user,
            )
        assert exc_info.value.status_code == 503


# =============================================================================
# get_categories
# =============================================================================


class TestGetCategories:
    """Tests for get_categories endpoint."""

    @pytest.mark.asyncio
    async def test_get_categories_returns_list(self, test_user):
        """Happy path: returns available categories."""
        from app.routers.news_router import get_categories
        result = await get_categories(current_user=test_user)
        assert "categories" in result
        assert isinstance(result["categories"], list)
        assert result["default"] == "CryptoCurrency"


# =============================================================================
# mark_content_seen
# =============================================================================


class TestMarkContentSeen:
    """Tests for seen/unseen endpoints."""

    @pytest.mark.asyncio
    @patch("app.routers.news_router.async_session_maker")
    async def test_mark_seen_success(self, mock_session_maker, test_user):
        """Happy path: marks article as seen."""
        mock_db = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.routers.news_router import mark_content_seen
        result = await mark_content_seen(
            payload={"content_type": "article", "content_id": 1, "seen": True},
            current_user=test_user,
        )
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_mark_seen_invalid_type(self, test_user):
        """Failure case: invalid content_type raises 400."""
        from app.routers.news_router import mark_content_seen
        with pytest.raises(HTTPException) as exc_info:
            await mark_content_seen(
                payload={"content_type": "podcast", "content_id": 1},
                current_user=test_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_mark_seen_invalid_id(self, test_user):
        """Failure case: non-integer content_id raises 400."""
        from app.routers.news_router import mark_content_seen
        with pytest.raises(HTTPException) as exc_info:
            await mark_content_seen(
                payload={"content_type": "article", "content_id": "abc"},
                current_user=test_user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# bulk_mark_content_seen
# =============================================================================


class TestBulkMarkContentSeen:
    """Tests for bulk seen/unseen endpoints."""

    @pytest.mark.asyncio
    async def test_bulk_mark_invalid_type(self, test_user):
        """Failure case: invalid content_type raises 400."""
        from app.routers.news_router import bulk_mark_content_seen
        with pytest.raises(HTTPException) as exc_info:
            await bulk_mark_content_seen(
                payload={"content_type": "podcast", "content_ids": [1, 2]},
                current_user=test_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_mark_empty_ids(self, test_user):
        """Failure case: empty content_ids raises 400."""
        from app.routers.news_router import bulk_mark_content_seen
        with pytest.raises(HTTPException) as exc_info:
            await bulk_mark_content_seen(
                payload={"content_type": "article", "content_ids": []},
                current_user=test_user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# mark_article_issue
# =============================================================================


class TestMarkArticleIssue:
    """Tests for mark_article_issue endpoint (superuser only)."""

    @pytest.mark.asyncio
    async def test_mark_issue_invalid_id(self, admin_user):
        """Failure case: non-integer article_id raises 400."""
        from app.routers.news_router import mark_article_issue
        with pytest.raises(HTTPException) as exc_info:
            await mark_article_issue(
                payload={"article_id": "abc"},
                current_user=admin_user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# get_sources
# =============================================================================


class TestGetSources:
    """Tests for get_sources endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_router.get_news_sources_from_db", new_callable=AsyncMock)
    async def test_get_sources_returns_list(self, mock_db_sources, test_user):
        """Happy path: returns formatted source list."""
        mock_db_sources.return_value = {
            "coindesk": {
                "name": "CoinDesk", "website": "https://coindesk.com",
                "type": "rss",
            },
        }
        from app.routers.news_router import get_sources
        result = await get_sources(current_user=test_user)
        assert len(result["sources"]) == 1
        assert result["sources"][0]["name"] == "CoinDesk"


# =============================================================================
# video_to_item helper
# =============================================================================


class TestVideoToItem:
    """Tests for video_to_item helper."""

    @pytest.mark.asyncio
    async def test_video_to_item_basic(self, db_session, sample_video):
        """Happy path: converts VideoArticle to dict."""
        from app.routers.news_router import video_to_item
        result = video_to_item(sample_video)
        assert result["id"] == 1
        assert result["title"] == "Weekly Crypto Update"
        assert result["video_id"] == "abc123"
        assert result["is_seen"] is False

    @pytest.mark.asyncio
    async def test_video_to_item_with_seen(self, db_session, sample_video):
        """Edge case: marks video as seen."""
        from app.routers.news_router import video_to_item
        result = video_to_item(sample_video, seen_ids={1})
        assert result["is_seen"] is True


# =============================================================================
# get_seen_content_ids
# =============================================================================


class TestGetSeenContentIds:
    """Tests for get_seen_content_ids helper."""

    @pytest.mark.asyncio
    async def test_returns_empty_set(self, db_session, test_user):
        """Edge case: no seen records returns empty set."""
        from app.routers.news_router import get_seen_content_ids
        result = await get_seen_content_ids(
            db=db_session, user_id=test_user.id, content_type="article",
        )
        assert result == set()

    @pytest.mark.asyncio
    async def test_returns_seen_ids(self, db_session, test_user, sample_article):
        """Happy path: returns set of seen article IDs."""
        seen = UserContentSeenStatus(
            user_id=test_user.id, content_type="article",
            content_id=sample_article.id,
        )
        db_session.add(seen)
        await db_session.flush()

        from app.routers.news_router import get_seen_content_ids
        result = await get_seen_content_ids(
            db=db_session, user_id=test_user.id, content_type="article",
        )
        assert sample_article.id in result


# =============================================================================
# get_articles_from_db (legacy)
# =============================================================================


class TestGetArticlesFromDb:
    """Tests for get_articles_from_db helper."""

    @pytest.mark.asyncio
    async def test_returns_recent_articles(self, db_session, sample_article):
        """Happy path: returns articles from database."""
        from app.routers.news_router import get_articles_from_db
        articles, total = await get_articles_from_db(
            db=db_session, page=1, page_size=50,
        )
        assert total == 1
        assert articles[0].title == "Bitcoin hits 100k"

    @pytest.mark.asyncio
    async def test_category_filter(self, db_session, sample_article):
        """Edge case: category filter works."""
        from app.routers.news_router import get_articles_from_db
        articles, total = await get_articles_from_db(
            db=db_session, page=1, page_size=50, category="NonExistent",
        )
        assert total == 0
