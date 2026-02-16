"""
Simple in-memory cache for API responses

Reduces API spam by caching balance and price checks.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


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
