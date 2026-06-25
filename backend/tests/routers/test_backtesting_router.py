"""
Tests for backend/app/routers/backtesting_router.py

Covers: account-scoping security of _prepare_backtest_inputs — a caller-supplied
account_id must belong to the caller (else it would build an exchange client from
another user's credentials).
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from app.models import User, Account
from app.routers.backtesting_router import _prepare_backtest_inputs


@pytest.mark.asyncio
async def test_prepare_backtest_rejects_foreign_account(db_session):
    """Security: passing another user's account_id raises 404 (no exchange client
    is ever built from the foreign account's credentials)."""
    me = User(id=701, email="me-bt@test.com", hashed_password="x", is_active=True)
    other = User(id=702, email="other-bt@test.com", hashed_password="x", is_active=True)
    db_session.add_all([me, other])
    await db_session.flush()
    foreign = Account(id=7777, user_id=other.id, name="Other", type="cex", is_active=True)
    db_session.add(foreign)
    await db_session.flush()

    with patch("app.strategies.StrategyRegistry.get_definition", return_value=MagicMock()):
        with pytest.raises(HTTPException) as exc:
            await _prepare_backtest_inputs(
                db_session, me, "indicator_based", 7777, "BTC-USD",
                1700000000, 1700086400, "ONE_HOUR",
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_prepare_backtest_accepts_owned_account(db_session):
    """An owned account passes the ownership check (proven by reaching the
    exchange-client build step, mocked to fail with a 400)."""
    me = User(id=703, email="me2-bt@test.com", hashed_password="x", is_active=True)
    db_session.add(me)
    await db_session.flush()
    mine = Account(id=7778, user_id=me.id, name="Mine", type="cex", is_active=True)
    db_session.add(mine)
    await db_session.flush()

    with patch("app.strategies.StrategyRegistry.get_definition", return_value=MagicMock()), \
            patch("app.services.exchange_service.get_exchange_client_for_account",
                  return_value=None):
        with pytest.raises(HTTPException) as exc:
            await _prepare_backtest_inputs(
                db_session, me, "indicator_based", 7778, "BTC-USD",
                1700000000, 1700086400, "ONE_HOUR",
            )
    # Got PAST the ownership check (would be 404) to the client-build failure (400).
    assert exc.value.status_code == 400
