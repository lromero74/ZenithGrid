"""
TDD tests for exchange_service._exchange_client_lock thread safety.

Verifies that _exchange_client_lock is a threading.Lock (loop-agnostic),
so get_exchange_client_for_account works correctly when called from both
the main event loop and the secondary event loop.

Also verifies that get_exchange_client_for_account accepts session_maker
as an optional parameter (for PropGuardClient session isolation).
"""
import asyncio
import inspect
import threading
import unittest.mock as mock


# ─── Lock type helpers ────────────────────────────────────────────────────────
_THREADING_LOCK_TYPE = type(threading.Lock())


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestExchangeClientLockType:
    def test_exchange_client_lock_is_threading_lock(self):
        from app.services import exchange_service
        assert type(exchange_service._exchange_client_lock) is _THREADING_LOCK_TYPE

    def test_exchange_client_lock_is_not_asyncio_lock(self):
        from app.services import exchange_service
        assert not isinstance(exchange_service._exchange_client_lock, asyncio.Lock)

    def test_exchange_client_lock_supports_context_manager(self):
        from app.services import exchange_service
        acquired = False
        with exchange_service._exchange_client_lock:
            acquired = True
        assert acquired


class TestExchangeClientLockCrossLoop:
    def test_lock_acquirable_from_thread(self):
        """Lock must be acquirable inside a plain thread (no event loop)."""
        from app.services import exchange_service

        errors = []

        def _worker():
            try:
                with exchange_service._exchange_client_lock:
                    pass
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=_worker)
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive(), "thread timed out"
        assert errors == [], f"thread raised: {errors}"

    def test_lock_acquirable_from_multiple_threads(self):
        from app.services import exchange_service

        acquired = []
        errors = []

        def _worker():
            try:
                with exchange_service._exchange_client_lock:
                    acquired.append(1)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        assert errors == [], f"threads raised: {errors}"
        assert len(acquired) == 5


class TestGetExchangeClientSignature:
    def test_accepts_session_maker_param(self):
        """get_exchange_client_for_account must accept session_maker kwarg."""
        from app.services.exchange_service import get_exchange_client_for_account
        sig = inspect.signature(get_exchange_client_for_account)
        assert "session_maker" in sig.parameters, (
            "get_exchange_client_for_account must accept session_maker= "
            "so PropGuardClient can use the secondary loop's session pool"
        )

    def test_session_maker_param_has_default_none(self):
        """session_maker must default to None (backwards-compatible)."""
        from app.services.exchange_service import get_exchange_client_for_account
        sig = inspect.signature(get_exchange_client_for_account)
        default = sig.parameters["session_maker"].default
        assert default is None


class TestGetExchangeClientCache:
    def test_cache_hit_skips_db(self):
        """Fast-path cache hit should return without any DB or lock usage."""
        from app.services import exchange_service

        sentinel = mock.MagicMock()
        exchange_service._exchange_client_cache[99999] = sentinel

        try:
            db = mock.AsyncMock()
            result = asyncio.get_event_loop().run_until_complete(
                exchange_service.get_exchange_client_for_account(db, 99999)
            )
            assert result is sentinel
            db.execute.assert_not_called()
        finally:
            exchange_service._exchange_client_cache.pop(99999, None)

    def test_cache_miss_double_check_prevents_duplicates(self):
        """
        When _exchange_client_lock is acquired for a cache miss, and another
        task has already populated the cache, the double-check must return
        the cached client without doing DB work.
        """
        from app.services import exchange_service

        sentinel = mock.MagicMock()

        original_lock = exchange_service._exchange_client_lock

        class _InjectCacheOnAcquire:
            """Simulate: another coroutine populated the cache while we waited."""
            def __enter__(self):
                exchange_service._exchange_client_cache[88888] = sentinel
                return self

            def __exit__(self, *args):
                pass

        exchange_service._exchange_client_lock = _InjectCacheOnAcquire()

        try:
            db = mock.AsyncMock()
            result = asyncio.get_event_loop().run_until_complete(
                exchange_service.get_exchange_client_for_account(db, 88888)
            )
            assert result is sentinel, "double-check should return cached client"
            db.execute.assert_not_called()
        finally:
            exchange_service._exchange_client_lock = original_lock
            exchange_service._exchange_client_cache.pop(88888, None)
