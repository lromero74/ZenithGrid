"""Tests for news_service — business logic extracted from news_router."""

import math
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.news_service import (
    article_to_news_item,
    build_news_response,
    get_all_sources_from_db,
)


class TestArticleToNewsItem:
    """Unit tests for article_to_news_item transformation."""

    def _make_article(self, **overrides):
        article = MagicMock()
        article.id = overrides.get("id", 1)
        article.title = overrides.get("title", "Test Article")
        article.url = overrides.get("url", "https://example.com/article")
        article.source = overrides.get("source", "test_source")
        article.published_at = overrides.get("published_at", datetime(2026, 1, 15, 12, 0))
        article.summary = overrides.get("summary", "Test summary")
        article.cached_thumbnail_path = overrides.get("cached_thumbnail_path", None)
        article.original_thumbnail_url = overrides.get("original_thumbnail_url", "https://img.com/thumb.jpg")
        article.category = overrides.get("category", "CryptoCurrency")
        article.has_issue = overrides.get("has_issue", False)
        return article

    def test_happy_path_basic_conversion(self):
        """article_to_news_item returns a dict with all expected fields."""
        article = self._make_article()
        sources = {"test_source": {"name": "Test Source", "website": "https://test.com", "content_scrape_allowed": True}}
        result = article_to_news_item(article, sources=sources, seen_ids=set())

        assert result["id"] == 1
        assert result["title"] == "Test Article"
        assert result["source"] == "test_source"
        assert result["source_name"] == "Test Source"
        assert result["thumbnail"] == "https://img.com/thumb.jpg"
        assert result["is_seen"] is False
        assert result["category"] == "CryptoCurrency"

    def test_cached_thumbnail_uses_api_path(self):
        """When cached_thumbnail_path is set, thumbnail points to the API endpoint."""
        article = self._make_article(cached_thumbnail_path="/some/path.jpg")
        result = article_to_news_item(article)

        assert result["thumbnail"] == "/api/news/image/1"

    def test_seen_ids_marks_article_as_seen(self):
        """Articles in seen_ids set are marked is_seen=True."""
        article = self._make_article(id=42)
        result = article_to_news_item(article, seen_ids={42, 100})

        assert result["is_seen"] is True

    def test_unknown_source_uses_source_key_as_name(self):
        """When source is not in sources map, source key is used as name."""
        article = self._make_article(source="unknown_src")
        result = article_to_news_item(article, sources={})

        assert result["source_name"] == "unknown_src"


class TestBuildNewsResponse:
    """Tests for the build_news_response assembly function."""

    def test_pagination_fields_correct(self):
        """Response includes correct pagination metadata."""
        news_items = [{"id": i} for i in range(10)]
        sources = {"s1": {"name": "Src", "website": "https://src.com", "category": "Crypto"}}

        result = build_news_response(
            news_items=news_items,
            sources=sources,
            total_count=25,
            page=2,
            page_size=10,
        )

        assert result["total_items"] == 25
        assert result["page"] == 2
        assert result["page_size"] == 10
        assert result["total_pages"] == 3  # ceil(25/10)
        assert len(result["news"]) == 10

    def test_zero_page_size_returns_single_page(self):
        """page_size=0 means all items, total_pages should be 1."""
        result = build_news_response(
            news_items=[],
            sources={},
            total_count=0,
            page=1,
            page_size=0,
        )

        assert result["total_pages"] == 1

    def test_sources_list_includes_category(self):
        """Sources are formatted with id, name, website, category."""
        sources = {
            "s1": {"name": "Source One", "website": "https://s1.com", "category": "Tech"},
        }
        result = build_news_response(
            news_items=[], sources=sources, total_count=0, page=1, page_size=50,
        )

        assert len(result["sources"]) == 1
        assert result["sources"][0]["id"] == "s1"
        assert result["sources"][0]["category"] == "Tech"

    def test_response_includes_cache_timestamps(self):
        """Response has cached_at and cache_expires_at fields."""
        result = build_news_response(
            news_items=[], sources={}, total_count=0, page=1, page_size=50,
        )

        assert "cached_at" in result
        assert "cache_expires_at" in result
        assert result["cached_at"].endswith("Z")
