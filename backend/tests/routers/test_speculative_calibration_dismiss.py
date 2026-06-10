"""
Tests for POST /api/accounts/{id}/speculative-calibration/dismiss.

Called when the user clicks the 'dismiss' link in the calibration alert
email. The endpoint:
- Requires a valid `dismiss_token` scoped to the same (user_id, account_id)
- Sets Account.speculative_calibration_last_alerted_at = now, extending
  the cooldown by another 30 days without triggering an actual send.
- Rejects cross-user and forged/expired tokens with 403.

Calls the router function directly (matches Phase C endpoint tests).
"""

from app.utils.timeutil import utcnow

import pytest
from fastapi import HTTPException

from app.models import Account, User
from app.routers.accounts_mutation_router import (
    dismiss_speculative_calibration_alert,
)
from app.services.speculative_calibration_token import create_dismiss_token


@pytest.fixture
async def owner_user_account(db_session):
    user = User(email="own@t.com", hashed_password="h", is_active=True)
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
    user = User(email="other@t.com", hashed_password="h", is_active=True)
    db_session.add(user)
    await db_session.flush()
    return user


class TestDismissEndpoint:
    @pytest.mark.asyncio
    async def test_happy_path_resets_cooldown(self, db_session, owner_user_account):
        user, account = owner_user_account
        token = create_dismiss_token(user_id=user.id, account_id=account.id)

        before = utcnow()
        result = await dismiss_speculative_calibration_alert(
            account_id=account.id, dismiss_token=token,
            db=db_session, current_user=user,
        )
        after = utcnow()

        assert result["dismissed"] is True
        # The cooldown timestamp should be updated to ~now.
        await db_session.refresh(account)
        assert account.speculative_calibration_last_alerted_at is not None
        assert before <= account.speculative_calibration_last_alerted_at <= after

    @pytest.mark.asyncio
    async def test_cross_user_token_rejected(
        self, db_session, owner_user_account, other_user,
    ):
        """A token signed for user A must not let user B dismiss A's alert."""
        owner, account = owner_user_account
        # Intruder forges a token that claims to be for (other_user, account).
        token = create_dismiss_token(
            user_id=other_user.id, account_id=account.id,
        )

        # Endpoint checks `accessible_accounts_filter(current_user.id)` first
        # so other_user can't touch owner's account at all — 404 is correct,
        # 403 would over-disclose existence.
        with pytest.raises(HTTPException) as exc:
            await dismiss_speculative_calibration_alert(
                account_id=account.id, dismiss_token=token,
                db=db_session, current_user=other_user,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_token_bound_to_wrong_account_rejected(
        self, db_session, owner_user_account,
    ):
        """A token signed for a different account must not pass even with a
        legitimate session on the target account."""
        user, account = owner_user_account
        token = create_dismiss_token(user_id=user.id, account_id=account.id + 999)

        with pytest.raises(HTTPException) as exc:
            await dismiss_speculative_calibration_alert(
                account_id=account.id, dismiss_token=token,
                db=db_session, current_user=user,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, db_session, owner_user_account):
        user, account = owner_user_account

        with pytest.raises(HTTPException) as exc:
            await dismiss_speculative_calibration_alert(
                account_id=account.id, dismiss_token="not.a.jwt",
                db=db_session, current_user=user,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, db_session, owner_user_account):
        user, account = owner_user_account
        from datetime import timedelta
        from jose import jwt
        from app.config import settings

        # Manually forge an expired token.
        expired_payload = {
            "sub": str(user.id), "account_id": account.id,
            "type": "speculative_calibration_dismiss",
            "exp": utcnow() - timedelta(days=1),
            "iat": utcnow() - timedelta(days=40),
        }
        expired = jwt.encode(
            expired_payload, settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(HTTPException) as exc:
            await dismiss_speculative_calibration_alert(
                account_id=account.id, dismiss_token=expired,
                db=db_session, current_user=user,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_type_token_rejected(self, db_session, owner_user_account):
        """A JWT with the right signature but a different `type` (e.g. a stolen
        access token) must not be accepted."""
        user, account = owner_user_account
        from datetime import timedelta
        from jose import jwt
        from app.config import settings
        access_like = jwt.encode(
            {
                "sub": str(user.id), "account_id": account.id,
                "type": "access",  # wrong type
                "exp": utcnow() + timedelta(hours=1),
                "iat": utcnow(),
            },
            settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(HTTPException) as exc:
            await dismiss_speculative_calibration_alert(
                account_id=account.id, dismiss_token=access_like,
                db=db_session, current_user=user,
            )
        assert exc.value.status_code == 403
