"""MFA code verification for sensitive actions.

Shared across routers that gate destructive operations (panic-sell,
account deletion, etc.). Supports both TOTP (authenticator app) and
email-based MFA.
"""
from app.utils.timeutil import utcnow
from typing import Optional

import pyotp
from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption import decrypt_value
from app.models.auth import User
from app.services.user_rate_limit import (
    clear_user_failures,
    record_user_failure,
)

# After this many failed MFA attempts within the window, the user is locked
# out of MFA-gated actions. Keeps TOTP/email codes brute-force resistant.
_MFA_MAX_FAILURES = 5
_MFA_LOCKOUT_WINDOW = 900.0  # 15 minutes


async def verify_mfa(db: AsyncSession, user: User, mfa_code: Optional[str]) -> None:
    """Verify MFA code if the user has MFA configured.

    TOTP users: verifies against stored TOTP secret.
    Email MFA users (no TOTP): verifies against a recent EmailVerificationToken.
    Raises HTTPException(403) on failure, HTTPException(429) after too many
    failures. No-op when MFA is not configured.
    """
    if user.mfa_enabled and user.totp_secret:
        if not mfa_code:
            raise HTTPException(status_code=403, detail="MFA code required")
        secret = decrypt_value(user.totp_secret)
        totp = pyotp.TOTP(secret)
        if not totp.verify(mfa_code, valid_window=1):
            record_user_failure(
                user_id=user.id,
                bucket="mfa_verify",
                max_failures=_MFA_MAX_FAILURES,
                window_seconds=_MFA_LOCKOUT_WINDOW,
                message="Too many invalid MFA attempts. Please try again later.",
            )
            raise HTTPException(status_code=403, detail="Invalid MFA code")
        clear_user_failures(user_id=user.id, bucket="mfa_verify")
        return

    if user.mfa_email_enabled:
        from app.models.auth import EmailVerificationToken
        if not mfa_code:
            raise HTTPException(status_code=403, detail="MFA code required")
        result = await db.execute(
            select(EmailVerificationToken).where(
                and_(
                    EmailVerificationToken.user_id == user.id,
                    EmailVerificationToken.token_type == "action_mfa",
                    EmailVerificationToken.verification_code == mfa_code,
                    EmailVerificationToken.used_at.is_(None),
                    EmailVerificationToken.expires_at > utcnow(),
                )
            )
        )
        token_record = result.scalars().first()
        if not token_record:
            record_user_failure(
                user_id=user.id,
                bucket="mfa_verify",
                max_failures=_MFA_MAX_FAILURES,
                window_seconds=_MFA_LOCKOUT_WINDOW,
                message="Too many invalid MFA attempts. Please try again later.",
            )
            raise HTTPException(status_code=403, detail="Invalid or expired MFA code")
        token_record.used_at = utcnow()
        await db.commit()
        clear_user_failures(user_id=user.id, bucket="mfa_verify")
        return
