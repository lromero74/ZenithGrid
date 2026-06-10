"""
Signed-token helpers for the "Apply proposed weights" email link.

Mirrors speculative_calibration_token.py (the dismiss-link module) but
uses a distinct `type` so a dismiss token cannot be replayed as an apply
token and vice versa. The payload additionally carries `proposal_id` so
the endpoint knows which row to transition.

URL shape:  {frontend_url}/settings?apply_token=...&account_id=...&proposal_id=...
"""

from __future__ import annotations
from app.utils.timeutil import utcnow

import logging
from datetime import timedelta
from typing import Optional
from urllib.parse import quote

from jose import JWTError, jwt

from app.config import settings
from app.services.speculative_calibration_token import (
    CALIBRATION_EMAIL_LINK_TTL_DAYS,
)

logger = logging.getLogger(__name__)

# Kept as a module-level alias so test files and any external callers can
# still import `APPLY_TOKEN_TTL_DAYS` directly; the canonical value lives in
# speculative_calibration_token so dismiss and apply can't drift.
APPLY_TOKEN_TTL_DAYS = CALIBRATION_EMAIL_LINK_TTL_DAYS
_TOKEN_TYPE = "speculative_calibration_apply_proposal"


def create_apply_proposal_token(
    *, user_id: int, account_id: int, proposal_id: int,
) -> str:
    """Issue a JWT scoped to (user_id, account_id, proposal_id)."""
    expire = utcnow() + timedelta(days=APPLY_TOKEN_TTL_DAYS)
    payload = {
        "sub": str(user_id),
        "account_id": int(account_id),
        "proposal_id": int(proposal_id),
        "type": _TOKEN_TYPE,
        "exp": expire,
        "iat": utcnow(),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )


def decode_apply_proposal_token(token: str) -> Optional[dict]:
    """Return the decoded payload if valid + correct type, else None."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None
    except Exception:
        logger.exception("decode_apply_proposal_token: unexpected decode error")
        return None
    if payload.get("type") != _TOKEN_TYPE:
        return None
    return payload


def build_apply_proposal_url(
    *, user_id: int, account_id: int, proposal_id: int, base_url: str,
) -> str:
    """Compose the full clickable URL for the calibration email."""
    token = create_apply_proposal_token(
        user_id=user_id, account_id=account_id, proposal_id=proposal_id,
    )
    base = base_url.rstrip("/")
    return (
        f"{base}/settings"
        f"?apply_token={quote(token, safe='')}"
        f"&account_id={int(account_id)}"
        f"&proposal_id={int(proposal_id)}"
    )
