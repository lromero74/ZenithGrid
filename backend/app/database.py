import logging

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=True,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    pool_pre_ping=True,
    pool_recycle=3600,
)


# Enable WAL mode for SQLite — allows concurrent reads during writes.
# Critical for server workloads where bot queries and API requests overlap.
if "sqlite" in settings.database_url:
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
