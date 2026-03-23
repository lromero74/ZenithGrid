import logging

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.server_resources import get_resource_plan

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# Build engine kwargs based on database backend
_engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

if settings.is_postgres:
    # Pool sizes are derived from pg max_connections via server_resources.ResourcePlan.
    # Adjust MONITOR_RESOURCE_SHARE in server_resources.py to tune aggressiveness.
    # idle_in_transaction_session_timeout=15min is set at the PostgreSQL level to
    # auto-kill connections that previous process restarts leave behind.
    _rp = get_resource_plan()
    _engine_kwargs["pool_size"] = _rp.write_pool_size
    _engine_kwargs["max_overflow"] = _rp.write_pool_overflow
    _engine_kwargs["pool_timeout"] = 10  # Fail fast instead of hanging 30s
    # Set search_path so unqualified table names in raw SQL resolve correctly
    # across all 6 domain schemas. SQLAlchemy ORM uses fully-qualified names,
    # so this is mainly for ad-hoc queries and any legacy unqualified references.
    # asyncpg uses server_settings (not psycopg2-style "options").
    _engine_kwargs["connect_args"] = {
        "server_settings": {"search_path": "auth,trading,reporting,social,content,system,public"}
    }
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

# Read-only connection pool for analytics queries.
# Separate pool budget (size=4, overflow=2) so aggregate report/account-value
# queries never compete with trading writes for connections.
# Points at the SAME database — zero-infrastructure change.
# Medium-term: point settings.read_database_url at a streaming replica here.
_read_engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

if settings.is_postgres:
    _rp = get_resource_plan()
    _read_engine_kwargs["pool_size"] = _rp.read_pool_size
    _read_engine_kwargs["max_overflow"] = _rp.read_pool_overflow
    _read_engine_kwargs["pool_timeout"] = 10
    _read_engine_kwargs["execution_options"] = {"postgresql_readonly": True}
else:
    _read_engine_kwargs["connect_args"] = {"check_same_thread": False}

read_engine = create_async_engine(settings.database_url, **_read_engine_kwargs)

read_async_session_maker = async_sessionmaker(
    read_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
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


async def get_read_db():
    """Read-only DB session dependency for analytics endpoints.

    Routes to the separate read connection pool (size=4, overflow=2).
    On PostgreSQL, sessions carry the postgresql_readonly execution option,
    preventing accidental writes. On SQLite (tests), the option is silently
    ignored — sessions behave identically to get_db() sessions.
    """
    async with read_async_session_maker() as session:
        yield session


async def init_db():
    from app.database_seeds import seed_default_coins, seed_default_sources

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default data
    await seed_default_sources(async_session_maker)
    await seed_default_coins(async_session_maker)
