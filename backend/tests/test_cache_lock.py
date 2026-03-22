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


class TestGetOrFetchCrossLoop:
    """Tests for the _in_flight cross-loop safety fix in SimpleCache.get_or_fetch.

    Root cause: _in_flight previously stored {str: asyncio.Future}.  If the main
    loop created Future1 under key "X" and the secondary loop found "X" in
    _in_flight, it would `await Future1` → RuntimeError: Task got Future attached
    to a different loop.

    Fix: key _in_flight by (id(loop), key) so each event loop has its own slot.
    """

    def test_in_flight_key_is_loop_keyed_tuple(self):
        """Happy path: _in_flight entries use (id(loop), key) tuples, not plain strings.

        After a successful get_or_fetch the entry is removed, but we can observe
        the key format while it is in-flight by inspecting _in_flight mid-fetch.
        """
        from app.cache import SimpleCache

        cache = SimpleCache()
        loop = asyncio.new_event_loop()
        observed_keys = []

        async def slow_fetch():
            # Capture whatever is in _in_flight right now
            observed_keys.extend(cache._in_flight.keys())
            return "v"

        try:
            loop.run_until_complete(cache.get_or_fetch("mykey", slow_fetch, 60))
        finally:
            loop.close()

        assert any(isinstance(k, tuple) for k in observed_keys), (
            "_in_flight key should be a (loop_id, key) tuple, not a plain string"
        )
        assert all(k[1] == "mykey" for k in observed_keys if isinstance(k, tuple))

    def test_secondary_loop_does_not_await_main_loop_future(self):
        """Cross-loop: secondary loop must not await a Future owned by the main loop.

        Inject a loop1 Future under the pre-fix plain-string key to simulate the
        race condition.  With the fix, loop2 checks (id(loop2), key), finds nothing,
        and does its own fetch instead of awaiting the wrong Future.
        Without the fix loop2 finds the plain-string key, awaits loop1's Future, and
        raises RuntimeError("Task got Future attached to a different loop").
        """
        from app.cache import SimpleCache

        cache = SimpleCache()
        loop1 = asyncio.new_event_loop()
        loop2 = asyncio.new_event_loop()

        # Inject a never-resolved Future from loop1 under the plain-string key.
        # Pre-fix code checks `if key in self._in_flight` → finds this → awaits it → boom.
        # Post-fix code checks `if loop_key in self._in_flight` → misses this → safe.
        loop1_future = loop1.create_future()
        cache._in_flight["inject_key"] = loop1_future

        errors = []
        results = []

        async def fetch():
            return "secondary_result"

        try:
            r = loop2.run_until_complete(
                cache.get_or_fetch("inject_key", fetch, ttl_seconds=60)
            )
            results.append(r)
        except RuntimeError as exc:
            errors.append(str(exc))
        finally:
            cache._in_flight.pop("inject_key", None)
            cache._in_flight.pop((id(loop2), "inject_key"), None)
            # Cancel and discard the injected future before closing loop1
            loop1.call_soon_threadsafe(loop1_future.cancel)
            loop1.run_until_complete(asyncio.sleep(0))
            loop1.close()
            loop2.close()

        assert errors == [], f"cross-loop RuntimeError: {errors}"
        assert results == ["secondary_result"]

    def test_two_loops_get_or_fetch_same_key_concurrently(self):
        """Cross-loop: two event loops can both fetch the same key independently
        without raising RuntimeError or corrupting each other's result.
        """
        from app.cache import SimpleCache

        cache = SimpleCache()
        errors = []
        results = []

        def run_on_loop(loop):
            async def fetch():
                await asyncio.sleep(0.01)
                return "ok"

            try:
                r = loop.run_until_complete(
                    cache.get_or_fetch("concurrent_key", fetch, ttl_seconds=60)
                )
                results.append(r)
            except Exception as exc:
                errors.append(exc)

        loop1 = asyncio.new_event_loop()
        loop2 = asyncio.new_event_loop()
        t1 = threading.Thread(target=run_on_loop, args=(loop1,))
        t2 = threading.Thread(target=run_on_loop, args=(loop2,))
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)
        loop1.close()
        loop2.close()

        assert errors == [], f"errors from cross-loop fetch: {errors}"
        assert len(results) == 2
        assert all(r == "ok" for r in results)
