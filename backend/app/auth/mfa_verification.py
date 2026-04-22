"""MFA code verification for sensitive actions.

Shared across routers that gate destructive operations (panic-sell,
account deletion, etc.). Supports both TOTP (authenticator app) and
email-based MFA.
"""
from datetime import datetime
from typing import Optional

import pyotp
from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption import decrypt_value
from app.models.auth import User


async def verify_mfa(db: AsyncSession, user: User, mfa_code: Optional[str]) -> None:
    """Verify MFA code if the user has MFA configured.

    TOTP users: verifies against stored TOTP secret.
    Email MFA users (no TOTP): verifies against a recent EmailVerificationToken.
    Raises HTTPException(403) on failure. No-op when MFA is not configured.
    """
    if user.mfa_enabled and user.totp_secret:
        if not mfa_code:
            raise HTTPException(status_code=403, detail="MFA code required")
        secret = decrypt_value(user.totp_secret)
        totp = pyotp.TOTP(secret)
        if not totp.verify(mfa_code, valid_window=1):
            raise HTTPException(status_code=403, detail="Invalid MFA code")
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
                    EmailVerificationToken.expires_at > datetime.utcnow(),
                )
            )
        )
        token_record = result.scalars().first()
        if not token_record:
            raise HTTPException(status_code=403, detail="Invalid or expired MFA code")
        token_record.used_at = datetime.utcnow()
        await db.commit()
        return
