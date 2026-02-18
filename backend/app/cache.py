"""
Simple in-memory cache for API responses

Reduces API spam by caching balance and price checks.
Includes persistent portfolio cache that survives restarts.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheEntry:
    """Single cache entry with TTL"""

    def __init__(self, value: Any, ttl_seconds: int):
        self.value = value
        self.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expires_at


class SimpleCache:
    """
    Simple in-memory cache with TTL support

    Thread-safe for asyncio use.
    """

    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            if entry.is_expired():
                del self._cache[key]
                return None

            return entry.value

    async def set(self, key: str, value: Any, ttl_seconds: int):
        """Set value in cache with TTL"""
        async with self._lock:
            self._cache[key] = CacheEntry(value, ttl_seconds)

    async def delete(self, key: str):
        """Delete a cache entry"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]

    async def clear(self):
        """Clear all cache entries"""
        async with self._lock:
            self._cache.clear()

    async def delete_prefix(self, prefix: str):
        """Delete all cache entries whose keys start with the given prefix"""
        async with self._lock:
            keys_to_delete = [key for key in self._cache if key.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]

    async def cleanup_expired(self):
        """Remove all expired entries"""
        async with self._lock:
            expired_keys = [key for key, entry in self._cache.items() if entry.is_expired()]
            for key in expired_keys:
                del self._cache[key]


# Global cache instance
api_cache = SimpleCache()


class PersistentPortfolioCache:
    """
    Disk-backed portfolio cache that survives backend restarts.

    Stores portfolio responses as JSON files so the first request after a
    restart can return data immediately instead of waiting for Coinbase API.
    """

    def __init__(self):
        _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._cache_dir = os.path.join(_backend_dir, ".portfolio_cache")
        os.makedirs(self._cache_dir, exist_ok=True)
        self._lock = asyncio.Lock()

    def _path(self, user_id: int) -> str:
        return os.path.join(self._cache_dir, f"user_{user_id}.json")

    async def get(self, user_id: int) -> Optional[dict]:
        """Load cached portfolio from disk. Returns None if missing."""
        async with self._lock:
            path = self._path(user_id)
            if not os.path.exists(path):
                return None
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                saved_at = data.get("_saved_at", "")
                logger.info(
                    f"Loaded persistent portfolio cache for user {user_id} "
                    f"(saved {saved_at})"
                )
                # Remove internal metadata before returning
                data.pop("_saved_at", None)
                return data
            except Exception as e:
                logger.warning(f"Failed to read portfolio cache: {e}")
                return None

    async def save(self, user_id: int, portfolio_data: dict):
        """Persist portfolio response to disk."""
        async with self._lock:
            path = self._path(user_id)
            try:
                data = dict(portfolio_data)
                data["_saved_at"] = datetime.utcnow().isoformat()
                with open(path, "w") as f:
                    json.dump(data, f)
            except Exception as e:
                logger.warning(f"Failed to write portfolio cache: {e}")

    async def invalidate(self, user_id: Optional[int] = None):
        """Remove cached portfolio files."""
        async with self._lock:
            if user_id is not None:
                path = self._path(user_id)
                if os.path.exists(path):
                    os.remove(path)
            else:
                # Clear all
                for f in os.listdir(self._cache_dir):
                    if f.endswith(".json"):
                        os.remove(os.path.join(self._cache_dir, f))


portfolio_cache = PersistentPortfolioCache()
