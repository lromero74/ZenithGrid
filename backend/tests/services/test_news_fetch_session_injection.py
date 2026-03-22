"""
Tests for session_maker injection in news_fetch_service and ContentRefreshService (Fix C).

Verifies:
1. get_news_sources_from_db accepts and uses injected session_maker
2. get_video_sources_from_db accepts and uses injected session_maker
3. fetch_all_news accepts and uses injected session_maker
4. fetch_all_videos accepts and uses injected session_maker
5. ContentRefreshService has set_session_maker / _get_sm pattern
"""
import inspect
from unittest.mock import AsyncMock, MagicMock


class TestGetNewsSourcesFromDbInjection:
    """get_news_sources_from_db must accept session_maker parameter."""

    def test_get_news_sources_accepts_session_maker_param(self):
        """Happy path: function signature includes session_maker parameter."""
        from app.services.news_fetch_service import get_news_sources_from_db

        sig = inspect.signature(get_news_sources_from_db)
        assert "session_maker" in sig.parameters, (
            "get_news_sources_from_db must accept session_maker parameter"
        )

    def test_get_news_sources_uses_injected_session_maker(self):
        """Happy path: injected session_maker is called instead of default."""
        import asyncio
        from app.services.news_fetch_service import get_news_sources_from_db

        mock_sm = MagicMock()
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_sm.return_value = mock_session

        asyncio.get_event_loop().run_until_complete(
            get_news_sources_from_db(session_maker=mock_sm)
        )
        mock_sm.assert_called_once()


class TestGetVideoSourcesFromDbInjection:
    """get_video_sources_from_db must accept session_maker parameter."""

    def test_get_video_sources_accepts_session_maker_param(self):
        """Happy path: function signature includes session_maker parameter."""
        from app.services.news_fetch_service import get_video_sources_from_db

        sig = inspect.signature(get_video_sources_from_db)
        assert "session_maker" in sig.parameters, (
            "get_video_sources_from_db must accept session_maker parameter"
        )

    def test_get_video_sources_uses_injected_session_maker(self):
        """Happy path: injected session_maker is called instead of default."""
        import asyncio
        from app.services.news_fetch_service import get_video_sources_from_db

        mock_sm = MagicMock()
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_sm.return_value = mock_session

        asyncio.get_event_loop().run_until_complete(
            get_video_sources_from_db(session_maker=mock_sm)
        )
        mock_sm.assert_called_once()


class TestFetchAllNewsInjection:
    """fetch_all_news must accept and propagate session_maker."""

    def test_fetch_all_news_accepts_session_maker_param(self):
        """Happy path: function signature includes session_maker parameter."""
        from app.services.news_fetch_service import fetch_all_news

        sig = inspect.signature(fetch_all_news)
        assert "session_maker" in sig.parameters, (
            "fetch_all_news must accept session_maker parameter"
        )


class TestFetchAllVideosInjection:
    """fetch_all_videos must accept and propagate session_maker."""

    def test_fetch_all_videos_accepts_session_maker_param(self):
        """Happy path: function signature includes session_maker parameter."""
        from app.services.news_fetch_service import fetch_all_videos

        sig = inspect.signature(fetch_all_videos)
        assert "session_maker" in sig.parameters, (
            "fetch_all_videos must accept session_maker parameter"
        )


class TestContentRefreshServiceSessionInjection:
    """ContentRefreshService must support session_maker injection."""

    def test_content_refresh_service_has_set_session_maker(self):
        """Happy path: ContentRefreshService has set_session_maker method."""
        from app.services.content_refresh_service import ContentRefreshService

        svc = ContentRefreshService()
        assert hasattr(svc, "set_session_maker"), (
            "ContentRefreshService must have set_session_maker method"
        )

    def test_content_refresh_service_has_get_sm(self):
        """Happy path: ContentRefreshService has _get_sm method."""
        from app.services.content_refresh_service import ContentRefreshService

        svc = ContentRefreshService()
        assert hasattr(svc, "_get_sm"), (
            "ContentRefreshService must have _get_sm method"
        )

    def test_content_refresh_service_set_session_maker_stores_value(self):
        """Happy path: set_session_maker stores and _get_sm returns it."""
        from app.services.content_refresh_service import ContentRefreshService

        svc = ContentRefreshService()
        mock_sm = object()
        svc.set_session_maker(mock_sm)
        assert svc._get_sm() is mock_sm

    def test_content_refresh_service_falls_back_to_default(self):
        """Edge case: _get_sm() returns default when no injection."""
        from app.database import async_session_maker
        from app.services.content_refresh_service import ContentRefreshService

        svc = ContentRefreshService()
        assert svc._get_sm() is async_session_maker
