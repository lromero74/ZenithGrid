"""
Per-user effective-weights cache for the speculative scorer.

Every AI evaluation on a speculative-tagged bot resolves the user's
currently-effective WEIGHTS via `get_effective_weights(db, user_id)`.
Resolution order:

  1. In-process cache if not expired (TTL = 60s).
  2. Latest `status='applied'` row in `speculative_weights_proposals`
     for the given user_id.
  3. DEFAULT_WEIGHTS from `app.indicators.speculative_signals`.

The cache is a plain in-process dict with a short TTL, keyed on user_id.
It's thread-safe via Python's GIL for the dict operations; a slightly
stale read (up to 60s) is acceptable — the scorer tolerates one extra
eval on prior weights, and the apply-endpoint calls `invalidate_weights_cache`
synchronously before returning 200 so the caller's next request
always sees the new weights.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.indicators.speculative_signals import DEFAULT_WEIGHTS

logger = logging.getLogger(__name__)


# TTL short enough that a stale cache after an apply self-corrects
# quickly, long enough that the DB isn't hit on every scorer call.
_CACHE_TTL_SECONDS: float = 60.0

# user_id → (weights_dict, expires_at_monotonic)
_cache: Dict[int, tuple[Dict[str, int], float]] = {}


async def get_effective_weights(
    db: AsyncSession, user_id: int,
) -> Dict[str, int]:
    """Return the scorer weights currently effective for `user_id`.

    Always returns a fresh defensive copy so the caller can't mutate
    our cache state.
    """
    now = time.monotonic()
    cached = _cache.get(user_id)
    if cached and cached[1] > now:
        return dict(cached[0])

    # Lazy import — SpeculativeWeightsProposal lives in the trading models
    # module which imports other models; keeping this import local avoids
    # a circular import risk at module load time.
    from app.models import SpeculativeWeightsProposal

    stmt = (
        select(SpeculativeWeightsProposal.proposed_weights)
        .where(
            SpeculativeWeightsProposal.user_id == user_id,
            SpeculativeWeightsProposal.status == "applied",
        )
        .order_by(SpeculativeWeightsProposal.decided_at.desc())
        .limit(1)
    )
    try:
        raw = (await db.execute(stmt)).scalar_one_or_none()
    except Exception:
        # DB error mid-scorer-call must never break trading — fall back
        # to module defaults and log.
        logger.exception(
            "get_effective_weights: DB query failed for user %s — "
            "falling back to DEFAULT_WEIGHTS", user_id,
        )
        raw = None

    weights = _parse_weights(raw) if raw is not None else dict(DEFAULT_WEIGHTS)
    _cache[user_id] = (weights, now + _CACHE_TTL_SECONDS)
    return dict(weights)


def invalidate_weights_cache(user_id: Optional[int] = None) -> None:
    """Drop a user's cached entry. Pass None to clear all entries
    (useful in tests and after bulk admin actions)."""
    if user_id is None:
        _cache.clear()
    else:
        _cache.pop(user_id, None)


def _parse_weights(raw) -> Dict[str, int]:
    """Normalize JSON-column output.

    PostgreSQL JSONB via SQLAlchemy returns dict directly. SQLite's TEXT
    fallback may return a JSON-string that needs parsing. Tolerate both.
    """
    if isinstance(raw, str):
        return {k: int(v) for k, v in json.loads(raw).items()}
    if raw is None:
        return dict(DEFAULT_WEIGHTS)
    return {k: int(v) for k, v in dict(raw).items()}
