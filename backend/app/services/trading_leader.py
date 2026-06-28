"""Fail-closed Redis lease that permits exactly one trading process."""

import asyncio
import inspect
import logging
import os
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4


logger = logging.getLogger(__name__)

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


async def _terminate_process() -> None:
    """Exit immediately if fencing is lost; another trader may start after TTL."""
    os._exit(70)


class TradingLeaderLease:
    """Own and renew a token-checked Redis lease for trading side effects."""

    def __init__(
        self,
        redis,
        *,
        key: str = "zenith:trading-leader",
        token: str | None = None,
        ttl_seconds: int = 30,
        renew_interval_seconds: float = 10,
        on_lease_lost: Callable[[], Awaitable[None] | None] = _terminate_process,
    ) -> None:
        self.redis = redis
        self.key = key
        self.token = token or str(uuid4())
        self.ttl_seconds = ttl_seconds
        self.renew_interval_seconds = renew_interval_seconds
        self.on_lease_lost = on_lease_lost
        self._renew_task: asyncio.Task | None = None

    async def acquire(self) -> None:
        acquired = await self.redis.set(
            self.key,
            self.token,
            nx=True,
            ex=self.ttl_seconds,
        )
        if not acquired:
            raise RuntimeError("another trading process is already active")
        self._renew_task = asyncio.create_task(self._renew_loop())
        logger.info("Trading leader lease acquired (ttl=%ss)", self.ttl_seconds)

    async def _renew_loop(self) -> None:
        last_ok = time.monotonic()
        while True:
            await asyncio.sleep(self.renew_interval_seconds)
            try:
                renewed = await self.redis.eval(
                    _RENEW_SCRIPT,
                    1,
                    self.key,
                    self.token,
                    self.ttl_seconds,
                )
            except Exception as exc:
                # A transient Redis error must NOT silently kill renewal (the
                # task would die while the process still believes it's leader).
                # The lease may still be valid until its TTL, so retry on the
                # next tick — but once we can no longer have renewed within the
                # TTL window, the key has expired and another process may claim
                # it, so fail closed.
                elapsed = time.monotonic() - last_ok
                if elapsed >= self.ttl_seconds:
                    logger.critical(
                        "Trading leader renewal failing for %.0fs (>= ttl %ss); "
                        "fail-closed: %s", elapsed, self.ttl_seconds, exc,
                    )
                    await self._fire_lease_lost()
                    return
                logger.warning(
                    "Trading leader renewal error (%.0fs since last success); will retry: %s",
                    elapsed, exc,
                )
                continue
            if renewed:
                last_ok = time.monotonic()
                continue
            logger.critical("Trading leader lease lost; terminating fail-closed")
            await self._fire_lease_lost()
            return

    async def _fire_lease_lost(self) -> None:
        result = self.on_lease_lost()
        if inspect.isawaitable(result):
            await result

    async def wait_until_stopped(self) -> None:
        if self._renew_task is not None:
            await self._renew_task

    async def release(self) -> None:
        if self._renew_task is not None:
            self._renew_task.cancel()
            try:
                await self._renew_task
            except asyncio.CancelledError:
                pass
            self._renew_task = None
        await self.redis.eval(_RELEASE_SCRIPT, 1, self.key, self.token)
        logger.info("Trading leader lease released")
