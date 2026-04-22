"""
Tests for the GET /api/accounts/{id}/speculative-bucket endpoint
added in PRPs/high-risk-doubling-preset.md Task C1.

Calls the router function directly (matching the test_account_value_router
pattern in this repo) — avoids HTTP client setup while still covering
the auth/scoping + response shape.
"""

import pytest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.models import Account, User
from app.routers.accounts_query_router import get_speculative_bucket_route


@pytest.fixture
async def owner_user_account(db_session):
    user = User(
        email="owner@test.com", hashed_password="h", is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    account = Account(
        user_id=user.id, name="Owner", type="cex",
        is_active=True, is_default=True,
        speculative_allocation_pct=5.0,
    )
    db_session.add(account)
    await db_session.flush()
    return user, account


@pytest.fixture
async def intruder_user(db_session):
    user = User(
        email="intruder@test.com", hashed_password="h", is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


class TestSpeculativeBucketEndpoint:
    @pytest.mark.asyncio
    async def test_returns_bucket_info_for_owner(self, db_session, owner_user_account):
        """Happy path: the owner of an account with a configured bucket
        gets the full snapshot."""
        user, account = owner_user_account

        with patch(
            "app.routers.accounts_query_router.get_account_value_summary",
            new_callable=AsyncMock,
            return_value={
                "total_usd_value": 10_000.0,
                "total_btc_value": 0.1,
                "btc_usd_price": 100_000.0,
            },
        ):
            result = await get_speculative_bucket_route(
                account_id=account.id,
                db=db_session, current_user=user,
            )

        assert result["bucket_pct"] == 5.0
        assert result["bucket_usd"] == 500.0
        assert result["deployed_cost_basis_usd"] == 0.0
        assert result["available_usd"] == 500.0

    @pytest.mark.asyncio
    async def test_404_for_unreachable_account(self, db_session, owner_user_account, intruder_user):
        """A user with no access must get 404 — matches other
        accounts_query_router endpoints."""
        _, owner_account = owner_user_account

        with pytest.raises(HTTPException) as exc:
            await get_speculative_bucket_route(
                account_id=owner_account.id,
                db=db_session, current_user=intruder_user,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_404_for_nonexistent_account(self, db_session, owner_user_account):
        user, _ = owner_user_account

        with pytest.raises(HTTPException) as exc:
            await get_speculative_bucket_route(
                account_id=99999, db=db_session, current_user=user,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_survives_summary_failure(self, db_session, owner_user_account):
        """If the account-value summary path fails, the endpoint must still
        return a snapshot — bucket_pct is preserved but bucket_usd collapses
        to 0 (no aggregate to multiply)."""
        user, account = owner_user_account

        with patch(
            "app.routers.accounts_query_router.get_account_value_summary",
            new_callable=AsyncMock,
            side_effect=RuntimeError("exchange down"),
        ):
            result = await get_speculative_bucket_route(
                account_id=account.id,
                db=db_session, current_user=user,
            )

        assert result["bucket_pct"] == 5.0
        assert result["bucket_usd"] == 0.0
        assert result["available_usd"] == 0.0
