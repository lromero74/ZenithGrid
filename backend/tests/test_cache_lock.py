"""
TDD tests for SimpleCache._lock thread safety.

api_cache is a module-level SimpleCache used by account_balance_api and
public_market_data.  If its _lock is asyncio.Lock, the secondary event
loop gets "Future attached to a different loop" the first time it tries
to call api_cache.get() or api_cache.set().

Converting to threading.Lock is safe because no `await` expression
appears inside any of the _lock-guarded blocks.
"""
import asyncio
import threading
import unittest.mock as mock


_THREADING_LOCK_TYPE = type(threading.Lock())


class TestSimpleCacheLockType:
    def test_cache_lock_is_threading_lock(self):
        from app.cache import SimpleCache
        cache = SimpleCache()
        assert type(cache._lock) is _THREADING_LOCK_TYPE

    def test_api_cache_lock_is_threading_lock(self):
        """The module-level singleton must also use threading.Lock."""
        from app.cache import api_cache
        assert type(api_cache._lock) is _THREADING_LOCK_TYPE

    def test_cache_lock_is_not_asyncio_lock(self):
        from app.cache import SimpleCache
        cache = SimpleCache()
        assert not isinstance(cache._lock, asyncio.Lock)

    def test_cache_lock_supports_sync_context_manager(self):
        from app.cache import SimpleCache
        cache = SimpleCache()
        acquired = False
        with cache._lock:
            acquired = True
        assert acquired


class TestCacheLockCrossLoop:
    def test_lock_acquirable_from_thread(self):
        """Lock must be acquirable inside a plain thread (no event loop)."""
        from app.cache import api_cache

        errors = []

        def _worker():
            try:
                with api_cache._lock:
                    pass
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=_worker)
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive()
        assert errors == [], f"thread raised: {errors}"

    def test_cache_get_callable_from_secondary_loop(self):
        """api_cache.get() must work on a different event loop than the one
        that ran the first cache operation."""
        from app.cache import api_cache

        # Simulate main loop using the cache first
        loop1 = asyncio.new_event_loop()
        loop1.run_until_complete(api_cache.set("_test_key", "value", 60))
        loop1.close()

        # Now a secondary loop uses the same cache — must not raise
        loop2 = asyncio.new_event_loop()
        errors = []
        try:
            result = loop2.run_until_complete(api_cache.get("_test_key"))
            assert result == "value"
        except Exception as exc:
            errors.append(exc)
        finally:
            loop2.close()
            loop1 = asyncio.new_event_loop()
            loop1.run_until_complete(api_cache.delete("_test_key"))
            loop1.close()

        assert errors == [], f"secondary loop raised: {errors}"
