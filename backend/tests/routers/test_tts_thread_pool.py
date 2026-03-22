"""
Tests for Phase 1.5 — TTS dedicated thread pool.

Verifies:
  - app.state.tts_executor is created at startup (ThreadPoolExecutor, max_workers=2)
  - Executor is alive (not shut down) while app is running
  - Executor can run callables
  - shutdown_event() calls executor.shutdown(wait=True)
  - Blocking file I/O paths in _get_or_create_tts use run_in_executor
  - Errors in TTS propagate as HTTP 500, not unhandled exceptions

TDD: these tests are written BEFORE implementation and must initially FAIL on
the executor-lifecycle assertions (AttributeError: app.state has no tts_executor).
"""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# =============================================================================
# Test Class 1: Executor lifecycle
# =============================================================================


class TestTTSExecutorLifecycle:
    """Verify executor is created at startup, bounded to 2 workers, and alive."""

    def test_executor_exists_on_app_state(self):
        """Happy path: app.state.tts_executor is set after startup."""
        # FAILS before impl: AttributeError on app.state.tts_executor
        from app.main import app
        assert hasattr(app.state, "tts_executor"), (
            "app.state.tts_executor not set — add ThreadPoolExecutor in startup_event()"
        )

    def test_executor_is_thread_pool_executor(self):
        """Happy path: executor is a ThreadPoolExecutor instance."""
        from app.main import app
        assert isinstance(app.state.tts_executor, ThreadPoolExecutor), (
            f"Expected ThreadPoolExecutor, got {type(app.state.tts_executor)}"
        )

    def test_executor_bounded_to_two_workers(self):
        """Edge case: executor has max_workers=2 — not unbounded."""
        from app.main import app
        assert app.state.tts_executor._max_workers == 2, (
            f"Expected max_workers=2, got {app.state.tts_executor._max_workers}"
        )

    def test_executor_not_shut_down(self):
        """Edge case: executor accepts new work (not prematurely shut down)."""
        from app.main import app
        # submit() raises RuntimeError on a shut-down executor
        future = app.state.tts_executor.submit(lambda: "alive")
        assert future.result(timeout=2) == "alive"

    @pytest.mark.asyncio
    async def test_executor_runs_callable_via_run_in_executor(self):
        """Happy path: executor integrates with asyncio.get_running_loop().run_in_executor."""
        from app.main import app
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(app.state.tts_executor, lambda: 42)
        assert result == 42


# =============================================================================
# Test Class 2: Executor max_workers constraint
# =============================================================================


class TestTTSExecutorBounded:
    """Verify the executor queues tasks rather than spawning unlimited threads."""

    @pytest.mark.asyncio
    async def test_all_tasks_complete_even_when_queued(self):
        """Edge case: 3 tasks submitted to max_workers=2 executor all complete."""
        executor = ThreadPoolExecutor(max_workers=2)
        results = []

        def task(n):
            time.sleep(0.02)
            results.append(n)
            return n

        loop = asyncio.get_running_loop()
        gathered = await asyncio.gather(*[
            loop.run_in_executor(executor, task, i) for i in range(3)
        ])
        executor.shutdown(wait=False)

        assert sorted(gathered) == [0, 1, 2]
        assert sorted(results) == [0, 1, 2]

    def test_production_executor_max_workers_is_two(self):
        """Edge case: production executor has exactly 2 workers."""
        from app.main import app
        assert app.state.tts_executor._max_workers == 2


# =============================================================================
# Test Class 3: shutdown_event shuts down the executor
# =============================================================================


class TestTTSExecutorShutdown:
    """Verify graceful executor shutdown on app shutdown."""

    def test_standalone_shutdown_waits_for_in_flight_work(self):
        """Happy path: shutdown(wait=True) waits for in-flight task to complete."""
        executor = ThreadPoolExecutor(max_workers=1)
        results = []

        def slow():
            time.sleep(0.05)
            results.append("done")

        executor.submit(slow)
        executor.shutdown(wait=True)
        assert results == ["done"]

    @pytest.mark.asyncio
    async def test_shutdown_event_calls_executor_shutdown(self):
        """Happy path: shutdown_event() calls tts_executor.shutdown(wait=True)."""
        from app.main import app, shutdown_event

        mock_executor = MagicMock()
        original = getattr(app.state, "tts_executor", None)
        app.state.tts_executor = mock_executor

        try:
            with patch("app.main.shutdown_manager") as mock_sm, \
                 patch("app.main.price_monitor") as pm, \
                 patch("app.main.perps_monitor") as pem, \
                 patch("app.main.stop_prop_guard_monitor", new_callable=AsyncMock), \
                 patch("app.main.limit_order_monitor_task", None), \
                 patch("app.main.order_reconciliation_monitor_task", None), \
                 patch("app.main.missing_order_detector_task", None), \
                 patch("app.scheduler.scheduler") as mock_sched, \
                 patch("app.services.exchange_service.clear_exchange_client_cache"):
                mock_sm.prepare_shutdown = AsyncMock(
                    return_value={"ready": True, "message": "OK"}
                )
                for m in [pm, pem]:
                    m.stop = AsyncMock()
                mock_sched.shutdown = MagicMock()
                await shutdown_event()

            mock_executor.shutdown.assert_called_once_with(wait=True)
        finally:
            # Restore original executor so other tests aren't broken
            if original is not None:
                app.state.tts_executor = original


# =============================================================================
# Test Class 4: File I/O uses run_in_executor
# =============================================================================


class TestGetOrCreateTTSUsesExecutor:
    """Verify blocking file ops in _get_or_create_tts go through run_in_executor."""

    @pytest.mark.asyncio
    async def test_cache_hit_read_uses_run_in_executor(self):
        """Happy path: cache hit reads file via run_in_executor, not blocking read_bytes()."""
        mock_cached = MagicMock()
        mock_cached.content_hash = "abc12345"
        mock_cached.audio_path = "1/aria.mp3"
        mock_cached.word_timings = json.dumps([{"text": "hi", "startTime": 0.0, "endTime": 0.3}])

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_cached
        mock_db.execute = AsyncMock(return_value=mock_result)

        executor_calls = []

        async def fake_run_in_executor(executor, func, *args):
            executor_calls.append(func)
            # Simulate calling the function (as the real executor would)
            if callable(func):
                return func(*args)
            return b"fake_audio"

        mock_filepath = MagicMock()
        mock_filepath.exists.return_value = True
        mock_filepath.read_bytes.return_value = b"mp3_data"

        with patch("app.routers.news_tts_router.async_session_maker") as mock_sm, \
             patch("app.routers.news_tts_router.TTS_CACHE_DIR") as mock_dir:
            mock_sm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sm.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_dir.__truediv__ = MagicMock(return_value=mock_filepath)
            mock_dir.__str__ = MagicMock(return_value="/fake/tts")

            loop = asyncio.get_running_loop()
            with patch.object(loop, "run_in_executor", side_effect=fake_run_in_executor) as mock_run:
                from app.routers.news_tts_router import _get_or_create_tts
                audio, words = await _get_or_create_tts(
                    article_id=1, voice="aria", text="hello world",
                    rate="+0%", user_id=1, audio_needed=True,
                )

            # The file read must have gone through run_in_executor
            assert mock_run.called, "read_bytes() was not wrapped in run_in_executor"

    @pytest.mark.asyncio
    async def test_cache_miss_write_uses_run_in_executor(self):
        """Happy path: cache miss writes file via run_in_executor, not blocking write_bytes()."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None  # cache miss
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.flush = AsyncMock()

        mock_article_dir = MagicMock()
        mock_audio_file = MagicMock()

        def mock_truediv(other):
            if str(other).isdigit():
                return mock_article_dir
            return mock_audio_file

        executor_calls = []

        async def fake_run_in_executor(executor, func, *args):
            executor_calls.append(func.__name__ if hasattr(func, "__name__") else str(func))
            return None

        with patch("app.routers.news_tts_router.async_session_maker") as mock_sm, \
             patch("app.routers.news_tts_router._generate_tts", new_callable=AsyncMock) as mock_gen, \
             patch("app.routers.news_tts_router.TTS_CACHE_DIR") as mock_cache_dir:
            mock_sm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sm.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_gen.return_value = (b"generated_audio", [])
            mock_cache_dir.__truediv__ = MagicMock(side_effect=mock_truediv)
            mock_cache_dir.__str__ = MagicMock(return_value="/fake/tts")

            loop = asyncio.get_running_loop()
            with patch.object(loop, "run_in_executor", side_effect=fake_run_in_executor) as mock_run:
                from app.routers.news_tts_router import _get_or_create_tts
                await _get_or_create_tts(
                    article_id=99, voice="aria", text="fresh text",
                    rate="+0%", user_id=1, audio_needed=False,
                )

            assert mock_run.called, "write_bytes() was not wrapped in run_in_executor"


# =============================================================================
# Test Class 5: Error handling
# =============================================================================


class TestTTSEndpointErrorHandling:
    """Errors in TTS processing propagate as HTTP 500, not unhandled exceptions."""

    @pytest.fixture
    def test_user(self):
        user = MagicMock()
        user.id = 1
        user.is_active = True
        return user

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router._get_or_create_tts", new_callable=AsyncMock)
    async def test_executor_io_error_returns_500(self, mock_tts, test_user):
        """Failure: OSError in file I/O propagates as HTTP 500."""
        mock_tts.side_effect = OSError("Disk full")

        from app.routers.news_tts_router import text_to_speech_with_sync, TTSSyncRequest
        body = TTSSyncRequest(text="Hello world", voice="aria", article_id=1)
        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await text_to_speech_with_sync(
                body=body, request=mock_request, current_user=test_user,
            )
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @patch("app.routers.news_tts_router._get_or_create_tts", new_callable=AsyncMock)
    async def test_edge_tts_network_error_returns_500(self, mock_tts, test_user):
        """Failure: edge_tts network failure propagates as HTTP 500."""
        mock_tts.side_effect = Exception("edge_tts connection refused")

        from app.routers.news_tts_router import text_to_speech_with_sync, TTSSyncRequest
        body = TTSSyncRequest(text="Hello world", voice="aria", article_id=1)
        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await text_to_speech_with_sync(
                body=body, request=mock_request, current_user=test_user,
            )
        assert exc_info.value.status_code == 500
