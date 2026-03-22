"""
Async Redis client singleton for ZenithGrid.

A single client instance is shared across the application.
DB 0 is used for rate limiting and general cache.
DB 1 is used by the APScheduler job store.

Lifecycle:
    startup  → call init_redis() to create and warm the connection pool
    shutdown → call close_redis() to flush and close gracefully

For one-off use outside the lifespan (tests, scripts):
    client = await get_redis()
    await client.aclose()
"""

import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def get_redis_sync() -> aioredis.Redis:
    """Return a fresh (not pooled) Redis client — for tests and sync contexts."""
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> aioredis.Redis:
    """Return the shared async Redis client, creating it if needed."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def init_redis() -> None:
    """Initialize the Redis connection pool and verify connectivity."""
    global _redis
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    await _redis.ping()
    logger.info("Redis connected: %s", settings.redis_url)


async def close_redis() -> None:
    """Close the Redis connection pool gracefully."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("Redis connection closed")
