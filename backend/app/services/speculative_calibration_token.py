"""
Dismiss-token signing for the speculative calibration alert.

The monitor emails the account owner with a link that resets the 30-day
cooldown without sending a fresh alert. The link carries a short-lived
signed token so:
- anyone with the mailbox can dismiss (no app session required — that's
  the point; the email is the notification surface), but
- the token is scoped to one user + one account, and
- it expires, so a leaked email link can't silently dismiss future alerts
  months later.

Uses the same `jwt_secret_key` + `jwt_algorithm` as the rest of the auth
layer (see app.auth_routers.helpers). Fresh module rather than piggybacking
on that file because the auth_routers package is tightly scoped to the
login flow — mixing a preset-domain token in there would muddy the layering.
"""

from __future__ import annotations
from app.utils.timeutil import utcnow

import logging
from datetime import timedelta
from typing import Optional
from urllib.parse import quote

from jose import JWTError, jwt

from app.config import settings

logger = logging.getLogger(__name__)


# Shared TTL for calibration-email links (both dismiss and apply tokens use
# it). Long enough that the user can act on the email over a weekend, short
# enough that a leaked inbox weeks later cannot silently mutate scorer state
# or dismiss future alerts. Happens to equal the monitor's COOLDOWN_DAYS
# today but that's coincidence — the cooldown governs "how soon before the
# NEXT alert fires", this governs "how long is the email's link valid".
CALIBRATION_EMAIL_LINK_TTL_DAYS = 30

# Back-compat alias — existing callers + tests reference this name.
DISMISS_TOKEN_TTL_DAYS = CALIBRATION_EMAIL_LINK_TTL_DAYS

_TOKEN_TYPE = "speculative_calibration_dismiss"


def create_dismiss_token(*, user_id: int, account_id: int) -> str:
    """Issue a short-lived JWT scoped to (user_id, account_id)."""
    expire = utcnow() + timedelta(days=DISMISS_TOKEN_TTL_DAYS)
    payload = {
        "sub": str(user_id),
        "account_id": int(account_id),
        "type": _TOKEN_TYPE,
        "exp": expire,
        "iat": utcnow(),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )


def decode_dismiss_token(token: str) -> Optional[dict]:
    """Return decoded payload if valid + correct type, else None.

    Also returns None on expiry — the caller treats None as "reject"
    without needing to distinguish expired vs. forged tokens.
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None
    except Exception:
        # Defensive — some jwt backends raise generic ValueErrors on bad input.
        logger.exception("decode_dismiss_token: unexpected decode error")
        return None

    if payload.get("type") != _TOKEN_TYPE:
        return None
    return payload


def build_dismiss_url(*, user_id: int, account_id: int, base_url: str) -> str:
    """Compose the full dismiss URL included in the alert email.

    The endpoint is POST, but the email includes a clickable link that
    lands on the Settings page. The frontend's SpeculativeAllocationSection
    catches the `dismiss_token` + `account_id` query params, POSTs them
    to the API, and shows a confirmation toast.

    URL shape: {base_url}/settings?dismiss_token=...&account_id=...
    """
    token = create_dismiss_token(user_id=user_id, account_id=account_id)
    base = base_url.rstrip("/")
    return (
        f"{base}/settings"
        f"?dismiss_token={quote(token, safe='')}"
        f"&account_id={int(account_id)}"
    )
