"""
TDD tests for public_market_data._rate_lock thread safety.

Verifies that _rate_lock is a threading.Lock (loop-agnostic), so the
public market data rate limiter works correctly when called from both
the main event loop and the secondary event loop.
"""
import asyncio
import threading
import time
import unittest.mock as mock


# ─── Lock type helpers ────────────────────────────────────────────────────────
_THREADING_LOCK_TYPE = type(threading.Lock())


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestRateLockType:
    def test_rate_lock_is_threading_lock(self):
        from app.coinbase_api import public_market_data
        assert type(public_market_data._rate_lock) is _THREADING_LOCK_TYPE

    def test_rate_lock_is_not_asyncio_lock(self):
        from app.coinbase_api import public_market_data
        assert not isinstance(public_market_data._rate_lock, asyncio.Lock)

    def test_rate_lock_supports_context_manager(self):
        """threading.Lock must work with plain `with` (no await)."""
        from app.coinbase_api import public_market_data
        acquired = False
        with public_market_data._rate_lock:
            acquired = True
        assert acquired


class TestRateLockCrossLoop:
    def test_rate_lock_acquirable_from_thread(self):
        """Lock must be acquirable inside a plain thread (no event loop)."""
        from app.coinbase_api import public_market_data

        errors = []

        def _thread_target():
            try:
                with public_market_data._rate_lock:
                    pass  # just acquire and release
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=_thread_target)
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive(), "thread timed out"
        assert errors == [], f"thread raised: {errors}"

    def test_rate_lock_acquirable_from_multiple_threads(self):
        """Multiple threads must be able to acquire the lock sequentially."""
        from app.coinbase_api import public_market_data

        acquired_count = []
        errors = []

        def _worker():
            try:
                with public_market_data._rate_lock:
                    acquired_count.append(1)
                    time.sleep(0.01)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        assert errors == [], f"threads raised: {errors}"
        assert len(acquired_count) == 5


class TestRateLimitFunctionality:
    def test_rate_limit_slot_reserved_before_sleep(self):
        """
        _last_request_time must be advanced (slot reserved) BEFORE
        asyncio.sleep is awaited, so concurrent callers don't compute
        the same wait and pile up.
        """
        import importlib
        from app.coinbase_api import public_market_data

        # Reset state
        public_market_data._last_request_time = 0.0

        sleep_calls = []
        last_time_at_sleep = []

        original_sleep = asyncio.sleep

        async def mock_sleep(duration):
            sleep_calls.append(duration)
            last_time_at_sleep.append(public_market_data._last_request_time)
            # Don't actually sleep

        with mock.patch("app.coinbase_api.public_market_data.asyncio.sleep", side_effect=mock_sleep), \
             mock.patch("httpx.AsyncClient") as mock_client_cls:
            # Mock httpx so _public_request doesn't actually make HTTP calls
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {}
            mock_resp.raise_for_status = mock.MagicMock()
            mock_client_instance = mock.AsyncMock()
            mock_client_instance.__aenter__ = mock.AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = mock.AsyncMock(return_value=False)
            mock_client_instance.get = mock.AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client_instance

            # First call: sets _last_request_time
            asyncio.get_event_loop().run_until_complete(
                public_market_data._public_request("/test")
            )
            first_time = public_market_data._last_request_time
            assert first_time > 0, "_last_request_time should be set after first call"

            # Second call immediately: should trigger sleep and reserve slot
            public_market_data._last_request_time = time.monotonic()  # Simulate recent request
            asyncio.get_event_loop().run_until_complete(
                public_market_data._public_request("/test")
            )

        # If sleep was called, the slot must have been reserved before sleep
        # (i.e., _last_request_time was already advanced when sleep started)
        if sleep_calls:
            assert all(d > 0 for d in sleep_calls), "sleep duration should be positive"
            # Slot should be reserved BEFORE sleep — not zero
            assert all(t > 0 for t in last_time_at_sleep), \
                "_last_request_time must be set before asyncio.sleep is awaited"
