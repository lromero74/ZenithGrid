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


@pytest.fixture
async def async_engine():
    """Create an in-memory async SQLite engine for testing."""
    from app.models import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
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
