"""
Tests for shutdown helpers in app.main.

Focus: _cancel_task() must not let a cancelled task's redis-wrapped
cancellation escape and fail the lifespan shutdown. Cancelling a coroutine
blocked inside a Redis read (the pub/sub subscriber parked in
pubsub.listen()) surfaces as redis.exceptions.RedisError — typically
TimeoutError/ConnectionError — rather than asyncio.CancelledError, because
redis-py wraps the cancellation.
"""

import asyncio

import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.main import _cancel_task


async def _block_then(exc_factory):
    """Block forever; on cancellation, raise exc_factory() instead of CancelledError."""
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        if exc_factory is None:
            raise
        raise exc_factory()


@pytest.mark.asyncio
async def test_cancel_task_none_is_noop():
    """Happy path: passing None returns without error."""
    await _cancel_task(None)


@pytest.mark.asyncio
async def test_cancel_task_swallows_plain_cancellation():
    """Edge case: an ordinary task that honours cancellation stops cleanly."""
    task = asyncio.create_task(_block_then(None))
    await asyncio.sleep(0)  # let it reach the await
    await _cancel_task(task)
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_cancel_task_swallows_redis_timeout_on_cancel():
    """Regression: redis-wrapped cancellation (TimeoutError) must not escape."""
    task = asyncio.create_task(
        _block_then(lambda: RedisTimeoutError("Timeout reading from localhost:6379"))
    )
    await asyncio.sleep(0)
    # Must NOT raise — previously this propagated and failed lifespan shutdown.
    await _cancel_task(task)
    assert task.done()


@pytest.mark.asyncio
async def test_cancel_task_propagates_unexpected_error():
    """Failure case: a genuinely unexpected error is NOT swallowed."""
    task = asyncio.create_task(_block_then(lambda: ValueError("boom")))
    await asyncio.sleep(0)
    with pytest.raises(ValueError, match="boom"):
        await _cancel_task(task)
