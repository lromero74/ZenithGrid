import logging

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# Build engine kwargs based on database backend
_engine_kwargs = {
    "echo": True,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

if settings.is_postgres:
    # PostgreSQL connection pool tuning for t2.micro (max_connections=25)
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 3
else:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(settings.database_url, **_engine_kwargs)


# Enable WAL mode for SQLite — allows concurrent reads during writes.
# Critical for server workloads where bot queries and API requests overlap.
if not settings.is_postgres:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False  # Disable autoflush to avoid greenlet issues
)


# Sync engine for non-async contexts (balance API, settings lookup)
_sync_engine = None


def get_sync_engine():
    """Sync SQLAlchemy engine for non-async contexts (balance API, coin review)."""
    global _sync_engine
    if _sync_engine is None:
        sync_url = settings.database_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")
        kwargs = {}
        if "sqlite" in sync_url:
            kwargs["connect_args"] = {"check_same_thread": False}
        _sync_engine = create_engine(sync_url, **kwargs)
    return _sync_engine


async def get_db():
    async with async_session_maker() as session:
        yield session


async def init_db():
    from app.database_seeds import seed_default_coins, seed_default_sources

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default data
    await seed_default_sources(async_session_maker)
    await seed_default_coins(async_session_maker)
