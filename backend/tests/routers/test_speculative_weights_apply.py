"""
Tests for POST /api/accounts/{id}/speculative-weights/apply-proposal.

Owner-only, signed-token-scoped, state-machine-checked. Mirrors the
dismiss-endpoint test pattern exactly — each failure mode gets its own
case so regressions are easy to localize.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from app.config import settings
from app.indicators.speculative_signals import DEFAULT_WEIGHTS
from app.models import Account, SpeculativeWeightsProposal, User
from app.routers.accounts_mutation_router import (
    apply_speculative_weights_proposal,
)
from app.services.speculative_calibration_apply_token import (
    create_apply_proposal_token,
)
from app.services.speculative_weights_cache import (
    get_effective_weights,
    invalidate_weights_cache,
)


@pytest.fixture
async def owner_user_account(db_session):
    user = User(email="own@apply.t", hashed_password="h", is_active=True)
    db_session.add(user)
    await db_session.flush()
    account = Account(
        user_id=user.id, name="A", type="cex",
        is_active=True, is_default=True,
        speculative_allocation_pct=5.0,
    )
    db_session.add(account)
    await db_session.flush()
    return user, account


@pytest.fixture
async def other_user(db_session):
    u = User(email="other@apply.t", hashed_password="h", is_active=True)
    db_session.add(u)
    await db_session.flush()
    return u


async def _make_pending_proposal(db, user_id, account_id, proposed=None):
    row = SpeculativeWeightsProposal(
        user_id=user_id,
        account_id=account_id,
        status="pending",
        algorithm="proportional-alpha-v1",
        sample_size=500,
        overall_win_rate_pct=15.0,
        baseline_weights=dict(DEFAULT_WEIGHTS),
        proposed_weights=proposed or {**DEFAULT_WEIGHTS, "volume_surge": 30},
    )
    db.add(row)
    await db.flush()
    return row


class TestApplyProposalEndpoint:
    @pytest.mark.asyncio
    async def test_happy_path_marks_applied_and_returns_weights(self, db_session, owner_user_account):
        user, account = owner_user_account
        prop = await _make_pending_proposal(db_session, user.id, account.id)
        token = create_apply_proposal_token(
            user_id=user.id, account_id=account.id, proposal_id=prop.id,
        )
        result = await apply_speculative_weights_proposal(
            account_id=account.id, apply_token=token, proposal_id=prop.id,
            db=db_session, current_user=user,
        )
        assert result["applied"] is True
        assert result["proposal_id"] == prop.id
        assert result["weights"]["volume_surge"] == 30

        await db_session.refresh(prop)
        assert prop.status == "applied"
        assert prop.decided_at is not None
        assert prop.decided_by == user.id

    @pytest.mark.asyncio
    async def test_apply_invalidates_cache_so_next_lookup_sees_new_weights(self, db_session, owner_user_account):
        invalidate_weights_cache()
        user, account = owner_user_account
        # Prime the cache with the current (defaults) weights.
        await get_effective_weights(db_session, user.id)

        prop = await _make_pending_proposal(
            db_session, user.id, account.id,
            proposed={**DEFAULT_WEIGHTS, "volume_surge": 32},
        )
        token = create_apply_proposal_token(
            user_id=user.id, account_id=account.id, proposal_id=prop.id,
        )
        await apply_speculative_weights_proposal(
            account_id=account.id, apply_token=token, proposal_id=prop.id,
            db=db_session, current_user=user,
        )
        # Cache was invalidated inside the endpoint — next lookup must
        # pick up the freshly applied row.
        weights = await get_effective_weights(db_session, user.id)
        assert weights["volume_surge"] == 32

    @pytest.mark.asyncio
    async def test_cross_user_sees_404(self, db_session, owner_user_account, other_user):
        user, account = owner_user_account
        prop = await _make_pending_proposal(db_session, user.id, account.id)
        # Other user forges a token that claims to be for their own (user_id, account, proposal).
        # The account ownership check fails first (Account.user_id == other_user.id) → 404.
        token = create_apply_proposal_token(
            user_id=other_user.id, account_id=account.id, proposal_id=prop.id,
        )
        with pytest.raises(HTTPException) as exc:
            await apply_speculative_weights_proposal(
                account_id=account.id, apply_token=token, proposal_id=prop.id,
                db=db_session, current_user=other_user,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_token_for_wrong_proposal_id_rejected(self, db_session, owner_user_account):
        user, account = owner_user_account
        prop = await _make_pending_proposal(db_session, user.id, account.id)
        # Token carries proposal_id=999 but caller passes prop.id in the path.
        bogus = create_apply_proposal_token(
            user_id=user.id, account_id=account.id, proposal_id=999,
        )
        with pytest.raises(HTTPException) as exc:
            await apply_speculative_weights_proposal(
                account_id=account.id, apply_token=bogus, proposal_id=prop.id,
                db=db_session, current_user=user,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_already_applied_proposal_returns_409(self, db_session, owner_user_account):
        user, account = owner_user_account
        prop = await _make_pending_proposal(db_session, user.id, account.id)
        prop.status = "applied"
        prop.decided_at = datetime.utcnow()
        prop.decided_by = user.id
        await db_session.flush()

        token = create_apply_proposal_token(
            user_id=user.id, account_id=account.id, proposal_id=prop.id,
        )
        with pytest.raises(HTTPException) as exc:
            await apply_speculative_weights_proposal(
                account_id=account.id, apply_token=token, proposal_id=prop.id,
                db=db_session, current_user=user,
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_invalid_token_403(self, db_session, owner_user_account):
        user, account = owner_user_account
        prop = await _make_pending_proposal(db_session, user.id, account.id)
        with pytest.raises(HTTPException) as exc:
            await apply_speculative_weights_proposal(
                account_id=account.id, apply_token="garbage",
                proposal_id=prop.id, db=db_session, current_user=user,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_expired_token_403(self, db_session, owner_user_account):
        user, account = owner_user_account
        prop = await _make_pending_proposal(db_session, user.id, account.id)
        expired = jwt.encode(
            {
                "sub": str(user.id), "account_id": account.id, "proposal_id": prop.id,
                "type": "speculative_calibration_apply_proposal",
                "exp": datetime.utcnow() - timedelta(days=1),
                "iat": datetime.utcnow() - timedelta(days=40),
            },
            settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(HTTPException) as exc:
            await apply_speculative_weights_proposal(
                account_id=account.id, apply_token=expired,
                proposal_id=prop.id, db=db_session, current_user=user,
            )
        assert exc.value.status_code == 403
