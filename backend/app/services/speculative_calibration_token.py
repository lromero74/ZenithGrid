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

import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from jose import JWTError, jwt

from app.config import settings

logger = logging.getLogger(__name__)


# Token lifetime: long enough that the user can act on the email over a
# weekend, short enough that a leaked inbox weeks later cannot silently
# dismiss future alerts. 30 days matches the cooldown itself — one email
# cycle.
DISMISS_TOKEN_TTL_DAYS = 30

_TOKEN_TYPE = "speculative_calibration_dismiss"


def create_dismiss_token(*, user_id: int, account_id: int) -> str:
    """Issue a short-lived JWT scoped to (user_id, account_id)."""
    expire = datetime.utcnow() + timedelta(days=DISMISS_TOKEN_TTL_DAYS)
    payload = {
        "sub": str(user_id),
        "account_id": int(account_id),
        "type": _TOKEN_TYPE,
        "exp": expire,
        "iat": datetime.utcnow(),
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
    hits a GET-forwarding route on the frontend or a lightweight dismiss
    page. The URL shape is:
        {base_url}/settings/speculative-bucket?dismiss_token=...&account_id=...

    The frontend catches the `dismiss_token` query param, POSTs it to
    the API, and shows a confirmation. Using a frontend-hosted link
    keeps the click behavior sane (no mail client hitting a POST
    endpoint directly) while still carrying the signed token through.
    """
    token = create_dismiss_token(user_id=user_id, account_id=account_id)
    base = base_url.rstrip("/")
    return (
        f"{base}/settings/speculative-bucket"
        f"?dismiss_token={quote(token, safe='')}"
        f"&account_id={int(account_id)}"
    )
