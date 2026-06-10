"""
Tests for GET /api/accounts/{id}/speculative-weights/proposals.

Owner-only read endpoint surfacing a user's full proposal history.
"""

from datetime import timedelta
from app.utils.timeutil import utcnow

import pytest
from fastapi import HTTPException

from app.indicators.speculative_signals import DEFAULT_WEIGHTS
from app.models import Account, SpeculativeWeightsProposal, User
from app.routers.accounts_query_router import (
    list_speculative_weights_proposals,
)


@pytest.fixture
async def owner_account(db_session):
    user = User(email="list@t.com", hashed_password="h", is_active=True)
    db_session.add(user)
    await db_session.flush()
    account = Account(
        user_id=user.id, name="A", type="cex",
        is_active=True, is_default=True, speculative_allocation_pct=5.0,
    )
    db_session.add(account)
    await db_session.flush()
    return user, account


@pytest.fixture
async def intruder(db_session):
    u = User(email="intruder@t.com", hashed_password="h", is_active=True)
    db_session.add(u)
    await db_session.flush()
    return u


class TestListProposals:
    @pytest.mark.asyncio
    async def test_empty_list_when_none_exist(self, db_session, owner_account):
        user, account = owner_account
        result = await list_speculative_weights_proposals(
            account_id=account.id, db=db_session, current_user=user,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_reverse_chronological(self, db_session, owner_account):
        user, account = owner_account
        older = SpeculativeWeightsProposal(
            user_id=user.id, account_id=account.id, status="applied",
            algorithm="proportional-alpha-v1", sample_size=500,
            overall_win_rate_pct=15.0,
            baseline_weights=dict(DEFAULT_WEIGHTS),
            proposed_weights={**DEFAULT_WEIGHTS, "volume_surge": 22},
            created_at=utcnow() - timedelta(days=30),
            decided_at=utcnow() - timedelta(days=30),
        )
        newer = SpeculativeWeightsProposal(
            user_id=user.id, account_id=account.id, status="pending",
            algorithm="proportional-alpha-v1", sample_size=600,
            overall_win_rate_pct=16.0,
            baseline_weights={**DEFAULT_WEIGHTS, "volume_surge": 22},
            proposed_weights={**DEFAULT_WEIGHTS, "volume_surge": 27},
            created_at=utcnow(),
        )
        db_session.add_all([older, newer])
        await db_session.flush()

        result = await list_speculative_weights_proposals(
            account_id=account.id, db=db_session, current_user=user,
        )
        assert len(result) == 2
        assert result[0]["status"] == "pending"  # newer first
        assert result[1]["status"] == "applied"

    @pytest.mark.asyncio
    async def test_non_owner_gets_404(self, db_session, owner_account, intruder):
        _, account = owner_account
        with pytest.raises(HTTPException) as exc:
            await list_speculative_weights_proposals(
                account_id=account.id, db=db_session, current_user=intruder,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_scoped_to_path_account_not_all_user_accounts(self, db_session, owner_account):
        """A user with two speculative accounts must only see proposals for
        the account in the URL path — not a merged list across both."""
        user, account_a = owner_account
        account_b = Account(
            user_id=user.id, name="B", type="cex",
            is_active=True, is_default=False, speculative_allocation_pct=5.0,
        )
        db_session.add(account_b)
        await db_session.flush()

        db_session.add_all([
            SpeculativeWeightsProposal(
                user_id=user.id, account_id=account_a.id, status="pending",
                algorithm="proportional-alpha-v1", sample_size=500,
                overall_win_rate_pct=15.0,
                baseline_weights=dict(DEFAULT_WEIGHTS),
                proposed_weights=dict(DEFAULT_WEIGHTS),
                created_at=utcnow(),
            ),
            SpeculativeWeightsProposal(
                user_id=user.id, account_id=account_b.id, status="pending",
                algorithm="proportional-alpha-v1", sample_size=600,
                overall_win_rate_pct=16.0,
                baseline_weights=dict(DEFAULT_WEIGHTS),
                proposed_weights=dict(DEFAULT_WEIGHTS),
                created_at=utcnow(),
            ),
        ])
        await db_session.flush()

        result_a = await list_speculative_weights_proposals(
            account_id=account_a.id, db=db_session, current_user=user,
        )
        result_b = await list_speculative_weights_proposals(
            account_id=account_b.id, db=db_session, current_user=user,
        )
        assert len(result_a) == 1
        assert len(result_b) == 1
        # And the sample_size distinguishes them unambiguously.
        assert result_a[0]["sample_size"] == 500
        assert result_b[0]["sample_size"] == 600

    @pytest.mark.asyncio
    async def test_other_user_proposals_not_leaked(self, db_session, owner_account):
        """Even if another user has proposals on some other account,
        owner's list must only return their own rows."""
        user, account = owner_account
        other = User(email="noise@t.com", hashed_password="h", is_active=True)
        db_session.add(other)
        await db_session.flush()

        db_session.add_all([
            SpeculativeWeightsProposal(
                user_id=user.id, account_id=account.id, status="pending",
                algorithm="proportional-alpha-v1", sample_size=500,
                overall_win_rate_pct=15.0,
                baseline_weights=dict(DEFAULT_WEIGHTS),
                proposed_weights=dict(DEFAULT_WEIGHTS),
                created_at=utcnow(),
            ),
            SpeculativeWeightsProposal(
                user_id=other.id, account_id=None, status="pending",
                algorithm="proportional-alpha-v1", sample_size=500,
                overall_win_rate_pct=15.0,
                baseline_weights=dict(DEFAULT_WEIGHTS),
                proposed_weights=dict(DEFAULT_WEIGHTS),
                created_at=utcnow(),
            ),
        ])
        await db_session.flush()

        result = await list_speculative_weights_proposals(
            account_id=account.id, db=db_session, current_user=user,
        )
        assert len(result) == 1  # only user's own
