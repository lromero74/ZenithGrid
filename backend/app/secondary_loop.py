"""
secondary_loop.py — Dedicated asyncio event loop for Tier 2/3 background tasks.

Tier 2/3 tasks run here so they cannot exhaust the main loop's DB connection
pool or block order fill processing during heavy batch operations.
"""
import asyncio
import logging
import threading
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)

_loop: Optional[asyncio.AbstractEventLoop] = None
_thread: Optional[threading.Thread] = None
_session_maker: Optional[async_sessionmaker] = None


def get_secondary_session_maker() -> async_sessionmaker:
    """Return the secondary loop's session maker. Must be called after loop is started."""
    if _session_maker is None:
        raise RuntimeError("Secondary loop not started — call start_secondary_loop() first")
    return _session_maker


def get_secondary_loop() -> asyncio.AbstractEventLoop:
    """Return the secondary event loop. Must be called after loop is started."""
    if _loop is None:
        raise RuntimeError("Secondary loop not started")
    return _loop


def schedule(coro) -> asyncio.Future:
    """Schedule a coroutine on the secondary event loop from the main thread."""
    if _loop is None:
        raise RuntimeError("Secondary loop not started")
    return asyncio.run_coroutine_threadsafe(coro, _loop)


def _run_loop(loop: asyncio.AbstractEventLoop):
    """Thread target: run the secondary event loop forever."""
    asyncio.set_event_loop(loop)
    loop.run_forever()


async def _init_secondary_engine():
    """Initialize the DB engine on the secondary loop. Runs inside the secondary loop."""
    global _session_maker

    kwargs = {
        "echo": False,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }
    if settings.is_postgres:
        # Small pool — batch tasks don't need many connections.
        # Main pool (size=8, overflow=4) stays exclusively for Tier 1 + API handlers.
        kwargs["pool_size"] = 3
        kwargs["max_overflow"] = 2
        kwargs["pool_timeout"] = 30  # Batch tasks can wait longer
    else:
        kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_async_engine(settings.database_url, **kwargs)
    _session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


def start_secondary_loop():
    """
    Create and start the secondary event loop in a daemon thread.
    Also creates the secondary DB engine bound to that loop.
    Must be called from the main thread during FastAPI startup.
    """
    global _loop, _thread

    _loop = asyncio.new_event_loop()
    _thread = threading.Thread(target=_run_loop, args=(_loop,), daemon=True, name="secondary-loop")
    _thread.start()

    # Create engine + session maker bound to the secondary loop.
    # Must run inside the secondary loop so asyncpg binds to it.
    future = asyncio.run_coroutine_threadsafe(_init_secondary_engine(), _loop)
    future.result(timeout=30)  # Block until engine is ready
    logger.info("Secondary event loop started (Tier 2/3 tasks)")


def stop_secondary_loop():
    """Stop the secondary event loop. Called during FastAPI shutdown."""
    global _session_maker
    if _loop and _loop.is_running():
        _loop.call_soon_threadsafe(_loop.stop)
    if _thread:
        _thread.join(timeout=10)
    _session_maker = None
    logger.info("Secondary event loop stopped")
