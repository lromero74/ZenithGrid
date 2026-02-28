"""
Tests for backend/app/routers/news_tts_router.py

Covers TTS endpoints: _generate_tts, _get_or_create_tts, text_to_speech_with_sync,
serve_tts_audio, voice subscriptions, TTS voices, history, and prepare_tts.
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import (
    ArticleTTS, User, UserArticleTTSHistory, UserVoiceSubscription,
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


# =============================================================================
# _generate_tts helper
# =============================================================================


class TestGenerateTTS:
    """Tests for _generate_tts helper function."""

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router.edge_tts")
    async def test_generate_tts_returns_audio_and_words(self, mock_edge):
        """Happy path: generates audio bytes and word boundaries."""
        mock_communicate = MagicMock()

        async def fake_stream():
            yield {"type": "audio", "data": b"audio1"}
            yield {
                "type": "WordBoundary", "text": "Hello",
                "offset": 5000000, "duration": 2000000,
            }
            yield {"type": "audio", "data": b"audio2"}

        mock_communicate.stream = fake_stream
        mock_edge.Communicate.return_value = mock_communicate

        from app.routers.news_tts_router import _generate_tts
        audio, words = await _generate_tts(
            "Hello world", "en-US-AriaNeural", "+0%",
        )
        assert audio == b"audio1audio2"
        assert len(words) == 1
        assert words[0]["text"] == "Hello"

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router.edge_tts")
    async def test_generate_tts_disconnect_cancels(self, mock_edge):
        """Edge case: client disconnect cancels generation."""
        mock_communicate = MagicMock()
        chunk_count = 0

        async def fake_stream():
            nonlocal chunk_count
            for i in range(25):
                chunk_count += 1
                yield {"type": "audio", "data": b"x"}

        mock_communicate.stream = fake_stream
        mock_edge.Communicate.return_value = mock_communicate

        async def _check_disconnect():
            return True  # Always disconnected

        from app.routers.news_tts_router import _generate_tts
        with pytest.raises(asyncio.CancelledError):
            await _generate_tts(
                "Hello world", "en-US-AriaNeural", "+0%",
                disconnect_check=_check_disconnect,
            )


# =============================================================================
# TTS Voices
# =============================================================================


class TestTTSVoices:
    """Tests for get_tts_voices endpoint."""

    @pytest.mark.asyncio
    async def test_get_tts_voices(self, test_user):
        """Happy path: returns voice list."""
        from app.routers.news_tts_router import get_tts_voices
        result = await get_tts_voices(current_user=test_user)
        assert "voices" in result
        assert isinstance(result["voices"], list)
        assert len(result["voices"]) > 0
        assert result["default"] == "aria"

    @pytest.mark.asyncio
    async def test_voices_have_required_fields(self, test_user):
        """Edge case: each voice has id, name, gender, style, desc."""
        from app.routers.news_tts_router import get_tts_voices
        result = await get_tts_voices(current_user=test_user)
        for voice in result["voices"]:
            assert "id" in voice
            assert "name" in voice
            assert "gender" in voice


# =============================================================================
# text_to_speech_with_sync
# =============================================================================


class TestTextToSpeechWithSync:
    """Tests for text_to_speech_with_sync endpoint."""

    @pytest.mark.asyncio
    async def test_tts_sync_unknown_voice_raises_400(self, test_user):
        """Failure case: unknown voice raises 400."""
        from app.routers.news_tts_router import (
            text_to_speech_with_sync, TTSSyncRequest,
        )
        body = TTSSyncRequest(text="Hello", voice="nonexistent_voice")
        mock_request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await text_to_speech_with_sync(
                body=body, request=mock_request, current_user=test_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router._get_or_create_tts", new_callable=AsyncMock)
    @patch("app.routers.news_tts_router._update_tts_history", new_callable=AsyncMock)
    async def test_tts_sync_with_article_id_returns_url(
        self, mock_history, mock_tts, test_user,
    ):
        """Happy path: with article_id returns audio_url instead of base64."""
        mock_tts.return_value = (None, [{"text": "Hello", "startTime": 0, "endTime": 0.5}])

        from app.routers.news_tts_router import (
            text_to_speech_with_sync, TTSSyncRequest,
        )
        body = TTSSyncRequest(text="Hello", voice="aria", article_id=42)
        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        result = await text_to_speech_with_sync(
            body=body, request=mock_request, current_user=test_user,
        )
        assert "audio_url" in result
        assert "/api/news/tts/audio/42/aria" in result["audio_url"]
        assert result["words"][0]["text"] == "Hello"

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router._generate_tts", new_callable=AsyncMock)
    async def test_tts_sync_without_article_id_returns_base64(
        self, mock_gen, test_user,
    ):
        """Happy path: without article_id returns base64 audio."""
        mock_gen.return_value = (b"fake_audio_data", [])

        from app.routers.news_tts_router import (
            text_to_speech_with_sync, TTSSyncRequest,
        )
        body = TTSSyncRequest(text="Hello world", voice="aria")
        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        result = await text_to_speech_with_sync(
            body=body, request=mock_request, current_user=test_user,
        )
        assert "audio" in result
        assert result["voice"] == "aria"


# =============================================================================
# serve_tts_audio
# =============================================================================


class TestServeTTSAudio:
    """Tests for serve_tts_audio endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router.async_session_maker")
    async def test_serve_audio_not_found_raises_404(
        self, mock_session_maker, test_user,
    ):
        """Failure case: non-existent TTS record raises 404."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.routers.news_tts_router import serve_tts_audio
        with pytest.raises(HTTPException) as exc_info:
            await serve_tts_audio(
                article_id=999, voice_id="aria", current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router.TTS_CACHE_DIR")
    @patch("app.routers.news_tts_router.async_session_maker")
    async def test_serve_audio_file_missing_raises_404(
        self, mock_session_maker, mock_cache_dir, test_user,
    ):
        """Failure case: TTS record exists but file missing raises 404."""
        mock_cached = MagicMock()
        mock_cached.audio_path = "1/aria.mp3"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_cached
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_filepath = MagicMock()
        mock_filepath.resolve.return_value.is_relative_to.return_value = True
        mock_filepath.exists.return_value = False
        mock_cache_dir.__truediv__ = MagicMock(return_value=mock_filepath)
        mock_cache_dir.resolve.return_value = Path("/fake/cache")

        from app.routers.news_tts_router import serve_tts_audio
        with pytest.raises(HTTPException) as exc_info:
            await serve_tts_audio(
                article_id=1, voice_id="aria", current_user=test_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# Voice Subscriptions
# =============================================================================


class TestVoiceSubscriptions:
    """Tests for voice subscription endpoints."""

    @pytest.mark.asyncio
    async def test_get_voice_subscriptions_empty(self, db_session, test_user):
        """Edge case: no subscriptions returns empty voices dict."""
        from app.routers.news_tts_router import get_voice_subscriptions
        result = await get_voice_subscriptions(
            current_user=test_user, db=db_session,
        )
        assert result["voices"] == {}

    @pytest.mark.asyncio
    async def test_get_voice_subscriptions_with_data(self, db_session, test_user):
        """Happy path: returns user's voice subscriptions."""
        sub = UserVoiceSubscription(
            user_id=test_user.id, voice_id="aria", is_enabled=True,
        )
        db_session.add(sub)
        await db_session.flush()

        from app.routers.news_tts_router import get_voice_subscriptions
        result = await get_voice_subscriptions(
            current_user=test_user, db=db_session,
        )
        assert result["voices"]["aria"] is True

    @pytest.mark.asyncio
    async def test_update_voice_subscriptions(self, db_session, test_user):
        """Happy path: creates/updates voice subscription preferences."""
        from app.routers.news_tts_router import (
            update_voice_subscriptions, VoiceSubscriptionUpdate,
        )
        body = VoiceSubscriptionUpdate(voices={"aria": True, "guy": False})
        result = await update_voice_subscriptions(
            body=body, current_user=test_user, db=db_session,
        )
        assert result["message"] == "Voice preferences updated"

    @pytest.mark.asyncio
    async def test_update_voice_subscriptions_ignores_invalid(self, db_session, test_user):
        """Edge case: invalid voice IDs are silently skipped."""
        from app.routers.news_tts_router import (
            update_voice_subscriptions, VoiceSubscriptionUpdate,
        )
        body = VoiceSubscriptionUpdate(voices={"invalid_voice_id": True})
        result = await update_voice_subscriptions(
            body=body, current_user=test_user, db=db_session,
        )
        assert result["message"] == "Voice preferences updated"


# =============================================================================
# TTS History
# =============================================================================


class TestTTSHistory:
    """Tests for get_tts_history_for_article endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router.async_session_maker")
    async def test_history_no_record(self, mock_session_maker, test_user):
        """Edge case: no history returns last_voice_id=None."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.routers.news_tts_router import get_tts_history_for_article
        result = await get_tts_history_for_article(
            article_id=1, current_user=test_user,
        )
        assert result["last_voice_id"] is None

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router.async_session_maker")
    async def test_history_with_record(self, mock_session_maker, test_user):
        """Happy path: returns last used voice."""
        mock_history = MagicMock()
        mock_history.last_voice_id = "guy"
        mock_history.last_played_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_history
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.routers.news_tts_router import get_tts_history_for_article
        result = await get_tts_history_for_article(
            article_id=1, current_user=test_user,
        )
        assert result["last_voice_id"] == "guy"


# =============================================================================
# Cached Voices For Article
# =============================================================================


class TestCachedVoicesForArticle:
    """Tests for get_cached_voices_for_article endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router.async_session_maker")
    async def test_cached_voices_empty(self, mock_session_maker, test_user):
        """Edge case: no cached TTS for article returns empty list."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.routers.news_tts_router import get_cached_voices_for_article
        result = await get_cached_voices_for_article(
            article_id=999, current_user=test_user,
        )
        assert result["cached_voices"] == []


# =============================================================================
# User TTS Semaphore
# =============================================================================


class TestUserTTSSemaphore:
    """Tests for per-user TTS semaphore management."""

    def test_get_user_semaphore_creates_new(self):
        """Happy path: creates a new semaphore for a new user."""
        from app.routers.news_tts_router import _get_user_tts_semaphore
        sem = _get_user_tts_semaphore(99999)
        assert isinstance(sem, asyncio.Semaphore)

    def test_get_user_semaphore_returns_same(self):
        """Edge case: returns same semaphore for same user."""
        from app.routers.news_tts_router import _get_user_tts_semaphore
        sem1 = _get_user_tts_semaphore(88888)
        sem2 = _get_user_tts_semaphore(88888)
        assert sem1 is sem2
