"""In-memory rebalancer gate state and the bot-rebalancer-group cache.

The portfolio/bot rebalancer "gates" a bot (blocks new base orders) when its
quote currency, or the bot itself, is overweight. That gate state is
process-local (resets on restart) and shared between the monitor — which sets it
each cycle via the mark_*/clear_* helpers — and the API routers, which read it
via is_rebalancer_gated / is_rebalancer_bot_overweight.

Extracted from multi_bot_monitor to keep that module under the size limit.
"""

import time
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Bot IDs gated by the rebalancer on their most recent cycle (resets on restart)
_gated_bots: set = set()

# Bot IDs currently overweight per the bot budget rebalancer (resets on restart)
_overweight_bots: set = set()

# Short-TTL cache of BotRebalancerGroup rows to avoid per-bot DB hits every cycle
_group_cache: Dict[tuple, Any] = {}
_GROUP_CACHE_TTL = 60  # seconds


def is_rebalancer_gated(bot_id: int) -> bool:
    """Return True if this bot is currently gated by the rebalancer."""
    return bot_id in _gated_bots


def is_rebalancer_bot_overweight(bot_id: int) -> bool:
    """Return True if this bot is currently overweight per the bot budget rebalancer."""
    return bot_id in _overweight_bots


def mark_gated(bot_id: int) -> None:
    """Gate a bot — block its new base orders until the quote rebalances."""
    _gated_bots.add(bot_id)


def clear_gated(bot_id: int) -> None:
    """Un-gate a bot (fresh data says its quote is no longer overweight)."""
    _gated_bots.discard(bot_id)


def mark_overweight(bot_id: int) -> None:
    """Mark a bot as overweight per the bot budget rebalancer."""
    _overweight_bots.add(bot_id)


def clear_overweight(bot_id: int) -> None:
    """Clear a bot's overweight flag."""
    _overweight_bots.discard(bot_id)


async def clear_rebalancer_gates_for_account(
    db: AsyncSession,
    account_id: int,
) -> int:
    """Drop in-memory rebalancer gate state for one account.

    Called when the user disables portfolio rebalancing so the monitor
    stops blocking bots that were gated by stale or now-irrelevant data.
    Looks up the account's bot IDs from the DB so the in-memory sets are
    only cleared for this account (no cross-account leaks).

    Returns the number of bot IDs removed from the gated sets.
    """
    from app.models import Bot
    res = await db.execute(
        select(Bot.id).where(Bot.account_id == account_id)
    )
    bot_ids = {row[0] for row in res.all()}
    removed = 0
    for bid in bot_ids:
        if bid in _gated_bots:
            _gated_bots.discard(bid)
            removed += 1
        if bid in _overweight_bots:
            _overweight_bots.discard(bid)
            removed += 1

    # Also drop this account's cached rebalancer-group rows (keys are
    # (account_id, base_currency)) so a later re-enable re-reads fresh settings
    # instead of serving up-to-60s-stale group config.
    for key in [k for k in _group_cache if k[0] == account_id]:
        _group_cache.pop(key, None)

    return removed


async def get_bot_rebalancer_group(
    db: AsyncSession,
    account_id: int,
    base_currency: str,
) -> Optional[Any]:
    """Load a BotRebalancerGroup with a short TTL cache to avoid per-bot DB hits every cycle."""
    cache_key = (account_id, base_currency)
    cached = _group_cache.get(cache_key)
    if cached is not None:
        group, ts = cached
        if time.monotonic() - ts < _GROUP_CACHE_TTL:
            return group

    from app.models.trading import BotRebalancerGroup
    result = await db.execute(
        select(BotRebalancerGroup).where(
            BotRebalancerGroup.account_id == account_id,
            BotRebalancerGroup.base_currency == base_currency,
        )
    )
    group = result.scalar_one_or_none()
    _group_cache[cache_key] = (group, time.monotonic())
    return group
