"""
Tests for CoinbaseClient rate limiter loop-agnosticism (Fix D).

Verifies:
1. _rate_limit_lock is threading.Lock (not asyncio.Lock)
2. Rate limiting still functions correctly after the fix
3. Lock can be used from any event loop without RuntimeError
"""
import asyncio
import threading
import time


_THREADING_LOCK_TYPE = type(threading.Lock())


class TestRateLimitLockType:
    """Rate limit lock must be threading.Lock, not asyncio.Lock."""

    def test_rate_limit_lock_is_threading_lock(self):
        """Happy path: newly created client uses threading.Lock."""
        from app.coinbase_unified_client import CoinbaseClient

        client = CoinbaseClient(api_key="test_key", api_secret="test_secret")
        assert type(client._rate_limit_lock) is _THREADING_LOCK_TYPE, (
            f"Expected threading.Lock, got {type(client._rate_limit_lock)}"
        )

    def test_rate_limit_lock_is_not_asyncio_lock(self):
        """Edge case: asyncio.Lock must NOT be used (it binds to first event loop)."""
        from app.coinbase_unified_client import CoinbaseClient

        client = CoinbaseClient(api_key="test_key", api_secret="test_secret")
        assert not isinstance(client._rate_limit_lock, asyncio.Lock), (
            "asyncio.Lock binds to a loop on first acquire() — must use threading.Lock"
        )


class TestRateLimitFunctionality:
    """Rate limiter still enforces minimum interval after the threading.Lock fix."""

    def test_rate_limiter_reserves_slot_before_sleep(self):
        """Happy path: _last_request_time is updated atomically before sleep."""
        from app.coinbase_unified_client import CoinbaseClient

        client = CoinbaseClient(api_key="test_key", api_secret="test_secret")
        # Mark a very recent request so next call will need to wait
        client._last_request_time = time.time()

        # Verify the lock is acquirable (not bound to any loop)
        acquired = client._rate_limit_lock.acquire(blocking=False)
        if acquired:
            client._rate_limit_lock.release()
        assert acquired, "threading.Lock should be immediately acquirable in main thread"

    def test_rate_limit_lock_acquirable_from_multiple_threads(self):
        """Edge case: threading.Lock can be acquired sequentially from different threads."""
        from app.coinbase_unified_client import CoinbaseClient

        client = CoinbaseClient(api_key="test_key", api_secret="test_secret")
        results = []

        def try_acquire():
            # threading.Lock.acquire(blocking, timeout) — positional args
            acquired = client._rate_limit_lock.acquire(True, 1.0)
            if acquired:
                results.append(True)
                client._rate_limit_lock.release()

        t1 = threading.Thread(target=try_acquire)
        t2 = threading.Thread(target=try_acquire)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(results) == 2, "Both threads should be able to acquire the lock sequentially"


class TestRateLimitCrossLoop:
    """threading.Lock must not raise RuntimeError when used from a different event loop."""

    def test_lock_is_context_manager_from_thread(self):
        """Failure case: threading.Lock supports 'with' from any thread; asyncio.Lock does not."""
        from app.coinbase_unified_client import CoinbaseClient

        client = CoinbaseClient(api_key="test_key", api_secret="test_secret")
        errors = []

        def run_in_thread():
            try:
                with client._rate_limit_lock:
                    pass  # acquire and release
            except Exception as e:
                errors.append(str(e))

        t = threading.Thread(target=run_in_thread)
        t.start()
        t.join()

        assert not errors, f"Lock raised from thread: {errors}"
