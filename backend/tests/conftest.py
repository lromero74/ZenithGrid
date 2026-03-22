"""
Shared test fixtures for ZenithGrid backend tests.

Provides reusable fixtures for:
- Async database sessions (in-memory SQLite)
- FastAPI test client
- Mock exchange clients
- Sample model factories
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


def _is_postgres_url(url: str) -> bool:
    return "postgresql" in url or "postgres" in url


def pytest_configure(config):
    """Print which database backend the production app uses vs. the test fixture."""
    import os
    from app.config import settings

    test_db_url = os.environ.get("TEST_DATABASE_URL", "")
    if test_db_url and _is_postgres_url(test_db_url):
        print("\n[TEST DB] PostgreSQL via TEST_DATABASE_URL (dedicated test DB)")
    elif settings.is_postgres:
        print("\n[TEST DB] SQLite in-memory (app uses PostgreSQL in production)")
    else:
        print("\n[TEST DB] SQLite in-memory")


@pytest.fixture
async def async_engine():
    """Create an async test database engine.

    Tests always run against an isolated database — never production:
    - Default: in-memory SQLite. Uses schema_translate_map to flatten the 6
      PostgreSQL domain schemas (auth, trading, reporting, social, content,
      system) to None, since SQLite has no named schema support.
    - Set TEST_DATABASE_URL to a dedicated (non-production) PostgreSQL URL to
      run tests with full PostgreSQL fidelity. Tables are created and dropped
      per run. Never set this to the production DATABASE_URL.
    """
    import os
    from app.models import Base

    test_db_url = os.environ.get("TEST_DATABASE_URL", "")

    if test_db_url and _is_postgres_url(test_db_url):
        # Dedicated test PostgreSQL DB — safe to create/drop tables
        engine = create_async_engine(test_db_url, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
    else:
        # Default: in-memory SQLite with schema flattening
        _SCHEMA_MAP = {
            "auth": None,
            "trading": None,
            "reporting": None,
            "social": None,
            "content": None,
            "system": None,
        }
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            execution_options={"schema_translate_map": _SCHEMA_MAP},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def db_session(async_engine):
    """Provide a transactional async database session for tests.

    Each test gets its own session that rolls back after the test.
    """
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db_session(db_session):
    """Override the FastAPI dependency for database sessions."""

    async def _override():
        yield db_session

    return _override


# ---------------------------------------------------------------------------
# Mock exchange client
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_exchange_client():
    """Create a mock exchange client for testing without hitting real APIs."""
    client = MagicMock()
    client.get_account_balance = AsyncMock(return_value={
        "BTC": {"available": "0.01", "hold": "0.005"},
        "USD": {"available": "1000.00", "hold": "0.00"},
    })
    client.get_product_ticker = AsyncMock(return_value={
        "price": "50000.00",
        "bid": "49999.00",
        "ask": "50001.00",
    })
    client.place_order = AsyncMock(return_value={
        "order_id": "test-order-123",
        "status": "pending",
    })
    client.cancel_order = AsyncMock(return_value=True)
    return client


# ---------------------------------------------------------------------------
# Sample data factories
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_candles():
    """Generate sample candle data for strategy tests."""
    def _make_candles(prices, volume=100.0):
        return [
            {
                "open": p * 0.99,
                "high": p * 1.01,
                "low": p * 0.98,
                "close": p,
                "volume": volume,
            }
            for p in prices
        ]
    return _make_candles


# ---------------------------------------------------------------------------
# Sync DB connection (for schema inspection — PostgreSQL only)
# ---------------------------------------------------------------------------


@pytest.fixture
def db_sync_conn():
    """Synchronous DB connection for schema inspection (PostgreSQL only).

    Used by test_domain_schemas.py to verify table placement in named schemas.
    On SQLite the tests using this fixture are skipped via pytestmark.
    """
    import os
    import importlib.util
    # Load db_utils directly by file path to avoid shadowing from tests/migrations/
    _spec = importlib.util.spec_from_file_location(
        "_db_utils",
        os.path.join(os.path.dirname(__file__), "..", "migrations", "db_utils.py"),
    )
    _db_utils = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_db_utils)
    conn = _db_utils.get_migration_connection()
    yield conn
    conn.close()
