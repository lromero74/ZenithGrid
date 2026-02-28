"""
Tests for backend/app/routers/sources_router.py

Covers source management endpoints: list sources, subscribe/unsubscribe,
add/delete custom sources, update source settings, and check_robots.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import ContentSource, User, UserSourceSubscription


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
async def system_source(db_session):
    source = ContentSource(
        id=1, source_key="coindesk", name="CoinDesk", type="news",
        url="https://coindesk.com/feed", website="https://coindesk.com",
        is_system=True, is_enabled=True, category="CryptoCurrency",
    )
    db_session.add(source)
    await db_session.flush()
    return source


@pytest.fixture
async def custom_source(db_session, test_user):
    source = ContentSource(
        id=2, source_key="my_blog", name="My Blog", type="news",
        url="https://myblog.com/feed", website="https://myblog.com",
        is_system=False, is_enabled=True, category="Technology",
        user_id=test_user.id,
    )
    db_session.add(source)
    await db_session.flush()
    return source


@pytest.fixture
async def user_subscription(db_session, test_user, custom_source):
    sub = UserSourceSubscription(
        id=1, user_id=test_user.id, source_id=custom_source.id,
        is_subscribed=True,
    )
    db_session.add(sub)
    await db_session.flush()
    return sub


# =============================================================================
# list_sources
# =============================================================================


class TestListSources:
    """Tests for list_sources endpoint."""

    @pytest.mark.asyncio
    async def test_list_sources_returns_enabled(
        self, db_session, test_user, system_source,
    ):
        """Happy path: returns enabled sources."""
        from app.routers.sources_router import list_sources
        result = await list_sources(
            type=None, current_user=test_user, db=db_session,
        )
        assert result.total == 1
        assert result.sources[0].name == "CoinDesk"
        assert result.sources[0].is_subscribed is True  # default for system sources

    @pytest.mark.asyncio
    async def test_list_sources_filter_by_type(
        self, db_session, test_user, system_source,
    ):
        """Edge case: filter by type returns only matching sources."""
        from app.routers.sources_router import list_sources
        result = await list_sources(
            type="video", current_user=test_user, db=db_session,
        )
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_sources_unsubscribed_shown(
        self, db_session, test_user, system_source,
    ):
        """Edge case: unsubscribed sources still appear in list."""
        sub = UserSourceSubscription(
            user_id=test_user.id, source_id=system_source.id,
            is_subscribed=False,
        )
        db_session.add(sub)
        await db_session.flush()

        from app.routers.sources_router import list_sources
        result = await list_sources(
            type=None, current_user=test_user, db=db_session,
        )
        assert result.total == 1
        assert result.sources[0].is_subscribed is False


# =============================================================================
# subscribe / unsubscribe
# =============================================================================


class TestSubscription:
    """Tests for subscribe_to_source and unsubscribe_from_source endpoints."""

    @pytest.mark.asyncio
    async def test_subscribe_success(
        self, db_session, test_user, system_source,
    ):
        """Happy path: subscribes to a source."""
        from app.routers.sources_router import subscribe_to_source
        result = await subscribe_to_source(
            source_id=system_source.id,
            current_user=test_user, db=db_session,
        )
        assert result.is_subscribed is True
        assert result.source_id == system_source.id

    @pytest.mark.asyncio
    async def test_subscribe_not_found(self, db_session, test_user):
        """Failure case: subscribing to non-existent source raises 404."""
        from app.routers.sources_router import subscribe_to_source
        with pytest.raises(HTTPException) as exc_info:
            await subscribe_to_source(
                source_id=999, current_user=test_user, db=db_session,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unsubscribe_success(
        self, db_session, test_user, system_source,
    ):
        """Happy path: unsubscribes from a source."""
        from app.routers.sources_router import unsubscribe_from_source
        result = await unsubscribe_from_source(
            source_id=system_source.id,
            current_user=test_user, db=db_session,
        )
        assert result.is_subscribed is False

    @pytest.mark.asyncio
    async def test_unsubscribe_not_found(self, db_session, test_user):
        """Failure case: unsubscribing from non-existent source raises 404."""
        from app.routers.sources_router import unsubscribe_from_source
        with pytest.raises(HTTPException) as exc_info:
            await unsubscribe_from_source(
                source_id=999, current_user=test_user, db=db_session,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# add_custom_source
# =============================================================================


class TestAddCustomSource:
    """Tests for add_custom_source endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.sources_router.check_robots_txt", new_callable=AsyncMock)
    @patch("app.routers.sources_router.domain_blacklist_service")
    async def test_add_custom_source_success(
        self, mock_blacklist, mock_robots, db_session, test_user,
    ):
        """Happy path: adds a new custom news source."""
        mock_blacklist.is_domain_blocked.return_value = (False, None)
        mock_robots.return_value = MagicMock(
            rss_allowed=True, scraping_allowed=True,
            crawl_delay_seconds=0, domain="example.com",
        )

        from app.routers.sources_router import add_custom_source, AddSourceRequest
        request = AddSourceRequest(
            source_key="example_news", name="Example News", type="news",
            url="https://example.com/feed", category="Technology",
        )
        result = await add_custom_source(
            request=request, current_user=test_user, db=db_session,
        )
        assert result.name == "Example News"
        assert result.is_system is False
        assert result.is_subscribed is True

    @pytest.mark.asyncio
    async def test_add_custom_source_invalid_type(self, db_session, test_user):
        """Failure case: invalid type raises 400."""
        from app.routers.sources_router import add_custom_source, AddSourceRequest
        request = AddSourceRequest(
            source_key="bad", name="Bad", type="podcast",
            url="https://bad.com/feed",
        )
        with pytest.raises(HTTPException) as exc_info:
            await add_custom_source(
                request=request, current_user=test_user, db=db_session,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_add_video_source_requires_channel_id(self, db_session, test_user):
        """Failure case: video source without channel_id raises 400."""
        from app.routers.sources_router import add_custom_source, AddSourceRequest
        request = AddSourceRequest(
            source_key="my_vid", name="My Video", type="video",
            url="https://youtube.com/feed",
        )
        with pytest.raises(HTTPException) as exc_info:
            await add_custom_source(
                request=request, current_user=test_user, db=db_session,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("app.routers.sources_router.domain_blacklist_service")
    async def test_add_custom_source_blocked_domain(
        self, mock_blacklist, db_session, test_user,
    ):
        """Failure case: blocked domain raises 403."""
        mock_blacklist.is_domain_blocked.return_value = (True, "evil.com")

        from app.routers.sources_router import add_custom_source, AddSourceRequest
        request = AddSourceRequest(
            source_key="evil", name="Evil", type="news",
            url="https://evil.com/feed",
        )
        with pytest.raises(HTTPException) as exc_info:
            await add_custom_source(
                request=request, current_user=test_user, db=db_session,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("app.routers.sources_router.check_robots_txt", new_callable=AsyncMock)
    @patch("app.routers.sources_router.domain_blacklist_service")
    async def test_add_custom_source_limit_reached(
        self, mock_blacklist, mock_robots, db_session, test_user,
    ):
        """Failure case: hitting custom source limit raises 400."""
        mock_blacklist.is_domain_blocked.return_value = (False, None)

        # Create 10 custom sources + subscriptions to hit the limit
        for i in range(10):
            src = ContentSource(
                source_key=f"custom_{i}", name=f"Custom {i}", type="news",
                url=f"https://custom{i}.com/feed", is_system=False, is_enabled=True,
            )
            db_session.add(src)
            await db_session.flush()
            sub = UserSourceSubscription(
                user_id=test_user.id, source_id=src.id, is_subscribed=True,
            )
            db_session.add(sub)
        await db_session.flush()

        from app.routers.sources_router import add_custom_source, AddSourceRequest
        request = AddSourceRequest(
            source_key="one_more", name="One More", type="news",
            url="https://onemore.com/feed",
        )
        with pytest.raises(HTTPException) as exc_info:
            await add_custom_source(
                request=request, current_user=test_user, db=db_session,
            )
        assert exc_info.value.status_code == 400
        assert "limit" in exc_info.value.detail.lower()


# =============================================================================
# delete_custom_source
# =============================================================================


class TestDeleteCustomSource:
    """Tests for delete_custom_source endpoint."""

    @pytest.mark.asyncio
    async def test_delete_custom_source_success(
        self, db_session, test_user, custom_source, user_subscription,
    ):
        """Happy path: deletes custom source when last subscriber."""
        from app.routers.sources_router import delete_custom_source
        result = await delete_custom_source(
            source_id=custom_source.id,
            current_user=test_user, db=db_session,
        )
        assert "message" in result

    @pytest.mark.asyncio
    async def test_delete_system_source_raises_400(
        self, db_session, test_user, system_source,
    ):
        """Failure case: cannot delete system source."""
        from app.routers.sources_router import delete_custom_source
        with pytest.raises(HTTPException) as exc_info:
            await delete_custom_source(
                source_id=system_source.id,
                current_user=test_user, db=db_session,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_source_not_found(self, db_session, test_user):
        """Failure case: non-existent source raises 404."""
        from app.routers.sources_router import delete_custom_source
        with pytest.raises(HTTPException) as exc_info:
            await delete_custom_source(
                source_id=999, current_user=test_user, db=db_session,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# update_source_settings
# =============================================================================


class TestUpdateSourceSettings:
    """Tests for update_source_settings endpoint."""

    @pytest.mark.asyncio
    async def test_update_settings_success(
        self, db_session, test_user, system_source,
    ):
        """Happy path: updates per-user source settings."""
        from app.routers.sources_router import (
            update_source_settings, SourceSettingsRequest,
        )
        request = SourceSettingsRequest(user_category="Technology", retention_days=14)
        result = await update_source_settings(
            source_id=system_source.id, request=request,
            current_user=test_user, db=db_session,
        )
        assert result["source_id"] == system_source.id
        assert result["user_category"] == "Technology"
        assert result["retention_days"] == 14

    @pytest.mark.asyncio
    async def test_update_settings_not_found(self, db_session, test_user):
        """Failure case: non-existent source raises 404."""
        from app.routers.sources_router import (
            update_source_settings, SourceSettingsRequest,
        )
        request = SourceSettingsRequest(user_category="Tech")
        with pytest.raises(HTTPException) as exc_info:
            await update_source_settings(
                source_id=999, request=request,
                current_user=test_user, db=db_session,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# check_robots
# =============================================================================


class TestCheckRobots:
    """Tests for check_robots endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.sources_router.check_robots_txt", new_callable=AsyncMock)
    async def test_check_robots_success(self, mock_check, test_user):
        """Happy path: returns robots.txt policy."""
        mock_check.return_value = MagicMock(
            domain="example.com", robots_found=True, robots_fetch_error=None,
            rss_allowed=True, scraping_allowed=False,
            crawl_delay_seconds=5, summary="RSS OK, scraping blocked",
        )
        from app.routers.sources_router import check_robots, CheckRobotsRequest
        request = CheckRobotsRequest(url="https://example.com/feed")
        result = await check_robots(request=request, current_user=test_user)
        assert result.domain == "example.com"
        assert result.rss_allowed is True
        assert result.can_add is True

    @pytest.mark.asyncio
    async def test_check_robots_empty_url(self, test_user):
        """Failure case: empty URL raises 400."""
        from app.routers.sources_router import check_robots, CheckRobotsRequest
        request = CheckRobotsRequest(url="   ")
        with pytest.raises(HTTPException) as exc_info:
            await check_robots(request=request, current_user=test_user)
        assert exc_info.value.status_code == 400
