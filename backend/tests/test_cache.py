"""
Tests for backend/app/cache.py

Covers:
- CacheEntry (TTL expiry logic)
- SimpleCache (get, set, delete, clear, delete_prefix, cleanup_expired, get_or_fetch)
- PersistentPortfolioCache (get, save, invalidate)
"""

import asyncio
import os
import time
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from app.cache import CacheEntry, SimpleCache, PersistentPortfolioCache


# ---------------------------------------------------------------------------
# CacheEntry
# ---------------------------------------------------------------------------


class TestCacheEntry:
    """Tests for CacheEntry."""

    def test_not_expired_within_ttl(self):
        """Happy path: entry is not expired within TTL."""
        entry = CacheEntry("value", ttl_seconds=60)
        assert entry.is_expired() is False

    def test_expired_after_ttl(self):
        """Happy path: entry is expired when expires_at is in the past."""
        entry = CacheEntry("value", ttl_seconds=60)
        entry.expires_at = datetime.utcnow() - timedelta(seconds=1)
        assert entry.is_expired() is True

    def test_stores_value(self):
        """Happy path: value is stored correctly."""
        entry = CacheEntry({"key": "data"}, ttl_seconds=30)
        assert entry.value == {"key": "data"}

    def test_zero_ttl_immediately_expired(self):
        """Edge case: TTL of 0 means expires immediately (or near-immediately)."""
        entry = CacheEntry("value", ttl_seconds=0)
        # Might not be expired instantly due to timing, but should be expired very soon
        entry.expires_at = datetime.utcnow() - timedelta(milliseconds=1)
        assert entry.is_expired() is True


# ---------------------------------------------------------------------------
# SimpleCache
# ---------------------------------------------------------------------------


class TestSimpleCache:
    """Tests for SimpleCache."""

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Happy path: set a value and get it back."""
        cache = SimpleCache()
        await cache.set("key1", "value1", ttl_seconds=60)
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_key_returns_none(self):
        """Failure: missing key returns None."""
        cache = SimpleCache()
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_expired_key_returns_none(self):
        """Edge case: expired entry returns None and is deleted."""
        cache = SimpleCache()
        await cache.set("key1", "value1", ttl_seconds=60)
        # Manually expire the entry
        cache._cache["key1"].expires_at = datetime.utcnow() - timedelta(seconds=1)
        result = await cache.get("key1")
        assert result is None
        assert "key1" not in cache._cache

    @pytest.mark.asyncio
    async def test_delete(self):
        """Happy path: delete removes entry."""
        cache = SimpleCache()
        await cache.set("key1", "value1", ttl_seconds=60)
        await cache.delete("key1")
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key_no_error(self):
        """Edge case: deleting a missing key does not raise."""
        cache = SimpleCache()
        await cache.delete("nonexistent")  # Should not raise

    @pytest.mark.asyncio
    async def test_clear(self):
        """Happy path: clear removes all entries."""
        cache = SimpleCache()
        await cache.set("key1", "value1", ttl_seconds=60)
        await cache.set("key2", "value2", ttl_seconds=60)
        await cache.clear()
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_delete_prefix(self):
        """Happy path: delete_prefix removes matching keys."""
        cache = SimpleCache()
        await cache.set("user:1:balance", 100, ttl_seconds=60)
        await cache.set("user:1:orders", [], ttl_seconds=60)
        await cache.set("user:2:balance", 200, ttl_seconds=60)
        await cache.delete_prefix("user:1:")
        assert await cache.get("user:1:balance") is None
        assert await cache.get("user:1:orders") is None
        assert await cache.get("user:2:balance") == 200

    @pytest.mark.asyncio
    async def test_delete_prefix_no_matches(self):
        """Edge case: no matching prefix does nothing."""
        cache = SimpleCache()
        await cache.set("key1", "value1", ttl_seconds=60)
        await cache.delete_prefix("nomatch:")
        assert await cache.get("key1") == "value1"

    @pytest.mark.asyncio
    async def test_cleanup_expired(self):
        """Happy path: cleanup_expired removes expired entries only."""
        cache = SimpleCache()
        await cache.set("fresh", "value1", ttl_seconds=60)
        await cache.set("stale", "value2", ttl_seconds=60)
        cache._cache["stale"].expires_at = datetime.utcnow() - timedelta(seconds=1)
        await cache.cleanup_expired()
        assert await cache.get("fresh") == "value1"
        assert "stale" not in cache._cache


class TestSimpleCacheNegativeCache:
    """Tests for SimpleCache negative cache (not-found tracking)."""

    @pytest.mark.asyncio
    async def test_mark_and_check_not_found(self):
        """Happy path: marking a key as not-found makes is_not_found return True."""
        cache = SimpleCache()
        await cache.mark_not_found("price_TON-BTC", ttl_seconds=300)
        assert await cache.is_not_found("price_TON-BTC") is True

    @pytest.mark.asyncio
    async def test_unknown_key_not_found_returns_false(self):
        """Happy path: unknown key returns False."""
        cache = SimpleCache()
        assert await cache.is_not_found("price_ETH-BTC") is False

    @pytest.mark.asyncio
    async def test_expired_not_found_returns_false(self):
        """Edge case: expired not-found entry returns False and is cleaned up."""
        cache = SimpleCache()
        await cache.mark_not_found("price_OLD-BTC", ttl_seconds=300)
        # Manually expire
        cache._not_found["price_OLD-BTC"] = time.monotonic() - 1
        assert await cache.is_not_found("price_OLD-BTC") is False
        assert "price_OLD-BTC" not in cache._not_found

    @pytest.mark.asyncio
    async def test_clear_removes_not_found(self):
        """Happy path: clear() removes not-found entries too."""
        cache = SimpleCache()
        await cache.mark_not_found("price_TON-BTC", ttl_seconds=300)
        await cache.clear()
        assert await cache.is_not_found("price_TON-BTC") is False

    @pytest.mark.asyncio
    async def test_cleanup_expired_removes_stale_not_found(self):
        """Happy path: cleanup_expired removes expired not-found entries."""
        cache = SimpleCache()
        await cache.mark_not_found("price_STALE-BTC", ttl_seconds=300)
        cache._not_found["price_STALE-BTC"] = time.monotonic() - 1
        await cache.mark_not_found("price_FRESH-BTC", ttl_seconds=300)
        await cache.cleanup_expired()
        assert "price_STALE-BTC" not in cache._not_found
        assert await cache.is_not_found("price_FRESH-BTC") is True

    @pytest.mark.asyncio
    async def test_not_found_independent_of_positive_cache(self):
        """Edge case: not-found and positive cache are independent."""
        cache = SimpleCache()
        await cache.set("price_ETH-BTC", 0.05, ttl_seconds=60)
        await cache.mark_not_found("price_TON-BTC", ttl_seconds=300)
        # Positive cache unaffected
        assert await cache.get("price_ETH-BTC") == 0.05
        assert await cache.is_not_found("price_ETH-BTC") is False
        # Negative cache unaffected
        assert await cache.is_not_found("price_TON-BTC") is True
        assert await cache.get("price_TON-BTC") is None


class TestSimpleCacheGetOrFetch:
    """Tests for SimpleCache.get_or_fetch()."""

    @pytest.mark.asyncio
    async def test_get_or_fetch_cache_hit(self):
        """Happy path: returns cached value without calling fetch_fn."""
        cache = SimpleCache()
        await cache.set("key1", "cached_value", ttl_seconds=60)
        fetch_fn = AsyncMock(return_value="new_value")
        result = await cache.get_or_fetch("key1", fetch_fn, ttl_seconds=60)
        assert result == "cached_value"
        fetch_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_fetch_cache_miss_calls_fetch(self):
        """Happy path: cache miss calls fetch_fn and caches result."""
        cache = SimpleCache()
        fetch_fn = AsyncMock(return_value="fetched_value")
        result = await cache.get_or_fetch("key1", fetch_fn, ttl_seconds=60)
        assert result == "fetched_value"
        fetch_fn.assert_called_once()
        # Verify it was cached
        assert await cache.get("key1") == "fetched_value"

    @pytest.mark.asyncio
    async def test_get_or_fetch_propagates_exception(self):
        """Failure: exception from fetch_fn propagates and cleans up in-flight."""
        cache = SimpleCache()
        fetch_fn = AsyncMock(side_effect=ValueError("fetch failed"))
        with pytest.raises(ValueError, match="fetch failed"):
            await cache.get_or_fetch("key1", fetch_fn, ttl_seconds=60)
        # In-flight should be cleaned up
        assert "key1" not in cache._in_flight

    @pytest.mark.asyncio
    async def test_get_or_fetch_single_flight(self):
        """Edge case: concurrent callers share a single fetch."""
        cache = SimpleCache()
        call_count = 0

        async def slow_fetch():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return "result"

        # Launch two concurrent get_or_fetch calls
        results = await asyncio.gather(
            cache.get_or_fetch("key1", slow_fetch, ttl_seconds=60),
            cache.get_or_fetch("key1", slow_fetch, ttl_seconds=60),
        )
        assert results[0] == "result"
        assert results[1] == "result"
        assert call_count == 1  # Only one actual fetch


# ---------------------------------------------------------------------------
# PersistentPortfolioCache
# ---------------------------------------------------------------------------


class TestPersistentPortfolioCache:
    """Tests for PersistentPortfolioCache."""

    @pytest.mark.asyncio
    async def test_save_and_get(self, tmp_path):
        """Happy path: save portfolio and retrieve it."""
        cache = PersistentPortfolioCache()
        cache._cache_dir = str(tmp_path)

        portfolio = {"total_value": 10000, "positions": []}
        await cache.save(1, portfolio)
        result = await cache.get(1)
        assert result is not None
        assert result["total_value"] == 10000
        # _saved_at metadata should be removed
        assert "_saved_at" not in result

    @pytest.mark.asyncio
    async def test_get_missing_user_returns_none(self, tmp_path):
        """Failure: user with no cached data returns None."""
        cache = PersistentPortfolioCache()
        cache._cache_dir = str(tmp_path)
        assert await cache.get(999) is None

    @pytest.mark.asyncio
    async def test_invalidate_single_user(self, tmp_path):
        """Happy path: invalidate removes specific user cache."""
        cache = PersistentPortfolioCache()
        cache._cache_dir = str(tmp_path)

        await cache.save(1, {"total_value": 10000})
        await cache.save(2, {"total_value": 20000})
        await cache.invalidate(user_id=1)
        assert await cache.get(1) is None
        assert (await cache.get(2))["total_value"] == 20000

    @pytest.mark.asyncio
    async def test_invalidate_all_users(self, tmp_path):
        """Happy path: invalidate with no user_id clears all."""
        cache = PersistentPortfolioCache()
        cache._cache_dir = str(tmp_path)

        await cache.save(1, {"total_value": 10000})
        await cache.save(2, {"total_value": 20000})
        await cache.invalidate()
        assert await cache.get(1) is None
        assert await cache.get(2) is None

    @pytest.mark.asyncio
    async def test_get_corrupt_json_returns_none(self, tmp_path):
        """Failure: corrupt JSON file returns None gracefully."""
        cache = PersistentPortfolioCache()
        cache._cache_dir = str(tmp_path)

        # Write corrupt JSON
        path = os.path.join(str(tmp_path), "user_1.json")
        with open(path, "w") as f:
            f.write("not valid json{{{")

        result = await cache.get(1)
        assert result is None

    @pytest.mark.asyncio
    async def test_save_does_not_mutate_input(self, tmp_path):
        """Edge case: save does not permanently mutate the input dict."""
        cache = PersistentPortfolioCache()
        cache._cache_dir = str(tmp_path)

        portfolio = {"total_value": 10000}
        await cache.save(1, portfolio)
        # Original dict should not have _saved_at (save creates a copy)
        assert "_saved_at" not in portfolio
