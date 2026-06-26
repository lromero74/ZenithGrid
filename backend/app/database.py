import logging
import os
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.server_resources import get_resource_plan

logger = logging.getLogger(__name__)

_process_role = os.environ.get("PROCESS_ROLE", "combined").lower()
_pg_server_settings = {
    "search_path": "auth,trading,reporting,social,content,system,public",
    "application_name": f"zenithgrid-{_process_role}",
}


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
    _engine_kwargs["connect_args"] = {"server_settings": _pg_server_settings}
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
    # Mirror the write pool's search_path so unqualified table names in raw SQL
    # resolve on read sessions too (otherwise read-pool raw SQL hits "relation not found").
    _read_engine_kwargs["connect_args"] = {"server_settings": _pg_server_settings}
else:
    _read_engine_kwargs["connect_args"] = {"check_same_thread": False}

read_engine = create_async_engine(settings.database_url, **_read_engine_kwargs)

read_async_session_maker = async_sessionmaker(
    read_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


def _pool_metric(pool: Any, method_name: str) -> int | None:
    method = getattr(pool, method_name, None)
    if not callable(method):
        return None
    try:
        return int(method())
    except Exception:
        return None


def _pool_snapshot(async_engine, label: str) -> dict[str, Any]:
    pool = async_engine.sync_engine.pool
    size = _pool_metric(pool, "size")
    checked_in = _pool_metric(pool, "checkedin")
    checked_out = _pool_metric(pool, "checkedout")
    overflow = _pool_metric(pool, "overflow")
    max_overflow = getattr(pool, "_max_overflow", None)
    if isinstance(max_overflow, int) and size is not None:
        capacity = size + max(0, max_overflow)
    elif size is not None and overflow is not None:
        capacity = size + max(0, overflow)
    else:
        capacity = None

    utilization_pct = None
    if capacity and checked_out is not None:
        utilization_pct = round((checked_out / capacity) * 100, 2)

    return {
        "label": label,
        "pool_class": type(pool).__name__,
        "size": size,
        "checked_in": checked_in,
        "checked_out": checked_out,
        "overflow": overflow,
        "max_overflow": max_overflow if isinstance(max_overflow, int) else None,
        "capacity": capacity,
        "utilization_pct": utilization_pct,
    }


def get_pool_capacity_snapshot() -> dict[str, Any]:
    """Return current SQLAlchemy pool utilization for capacity guard endpoints."""
    plan = get_resource_plan()
    host: dict[str, Any] = {}
    try:
        import psutil
        cpu_times = psutil.cpu_times_percent(interval=None)
        host["cpu"] = {
            "percent": psutil.cpu_percent(interval=None),
            "steal_pct": getattr(cpu_times, "steal", None),
            "load_avg": os.getloadavg() if hasattr(os, "getloadavg") else None,
        }
        mem = psutil.virtual_memory()
        host["memory"] = {
            "available_mb": round(mem.available / (1024 * 1024), 1),
            "percent": mem.percent,
        }
    except Exception:
        host["cpu"] = {"percent": None, "steal_pct": None, "load_avg": None}
    return {
        "process_role": _process_role,
        "resource_plan": {
            "pg_max_connections": plan.pg_max_connections,
            "usable": plan.usable,
            "monitor_slots": plan.monitor_slots,
            "api_slots": plan.api_slots,
            "read_slots": plan.read_slots,
            "bot_concurrency_max": plan.bot_concurrency_max,
            "pair_concurrency_max": plan.pair_concurrency_max,
        },
        "host": host,
        "write": _pool_snapshot(engine, "write"),
        "read": _pool_snapshot(read_engine, "read"),
    }


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
        else:
            # Long-running prod: validate/recycle pooled conns so a stale one doesn't
            # raise OperationalError on the next use after an idle period.
            kwargs["pool_pre_ping"] = True
            kwargs["pool_recycle"] = 3600
            kwargs["connect_args"] = {
                "options": "-c search_path=auth,trading,reporting,social,content,system,public",
                "application_name": f"zenithgrid-{_process_role}-sync",
            }
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
    from app.seeds import seed_default_coins, seed_default_sources

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default data
    await seed_default_sources(async_session_maker)
    await seed_default_coins(async_session_maker)
