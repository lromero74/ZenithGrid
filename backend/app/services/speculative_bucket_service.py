"""
Speculative Bucket Service.

Enforces an account-level hard cap on total cost-basis exposure across all
bots whose strategy_config["is_speculative"] == True. A user sets
Account.speculative_allocation_pct once (as a % of aggregate USD value);
every speculative bot on that account must opt into the shared bucket.

Cost-basis (not mark-to-market) accounting: a 2x winner does NOT expand
headroom for new bets — unrealized gains belong to the user but cannot
fund additional speculative entries. Otherwise the "5% of portfolio"
promise would silently break whenever a few winners happened.

Account-scoped: all queries filter by Account.id so a speculative bot on
user A's account cannot see or affect user B's bucket.

Mirrors the query shape in app.services.budget_calculator (bidirectional
bot reservations). See PRPs/high-risk-doubling-preset.md §Recommended
Design §1 for design rationale.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Bot, Position

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _speculative_bot_filter():
    """SQL predicate for 'this bot is tagged speculative'.

    Mirrors the enable_bidirectional filter in budget_calculator.py —
    JSON field access via the ->> operator, which SQLAlchemy translates
    to PostgreSQL's ->> and SQLite's equivalent json_extract idiom.

    IMPORTANT: `is_speculative` must be stored as the JSON **string**
    "true" (not the JSON bool `true`). PostgreSQL's ->> on a bool returns
    'true' but SQLite's ->> returns 1 — so matching a bool across both
    backends would need an IN ('true', '1') predicate. Keeping the value
    as a string is simpler and matches the existing `enable_bidirectional`
    convention. The preset merge in bot_crud_router serializes it as
    a string for this reason.
    """
    return Bot.strategy_config.op("->>")("is_speculative") == "true"


def _position_cost_basis_usd(position: Position, btc_usd_price: float) -> float:
    """Convert a position's cost basis (quote currency) to USD.

    For USD-quote bots the cost basis is already in USD. For BTC-quote
    bots we multiply by the supplied current BTC/USD price.
    Non-USD, non-BTC quotes are treated as 1:1 with USD for stablecoins
    (USDC/USDT), falling back to 1.0 for anything else (rare in practice
    since the speculative preset is USD-biased).
    """
    total_quote = float(position.total_quote_spent or 0.0)
    if total_quote <= 0:
        return 0.0

    quote = ""
    if position.product_id and "-" in position.product_id:
        quote = position.product_id.split("-", 1)[1].upper()

    if quote in ("USD", "USDC", "USDT"):
        return total_quote
    if quote == "BTC":
        return total_quote * (btc_usd_price or 0.0)
    # Unknown quote — return the raw number and let the caller log.
    return total_quote


async def _speculative_bots_for_account(
    db: AsyncSession, account_id: int, exclude_bot_id: Optional[int] = None,
) -> list[Bot]:
    query = (
        select(Bot)
        .join(Account, Bot.account_id == Account.id)
        .where(
            Bot.account_id == account_id,
            _speculative_bot_filter(),
        )
    )
    if exclude_bot_id is not None:
        query = query.where(Bot.id != exclude_bot_id)

    result = await db.execute(query)
    return list(result.scalars().all())


async def _open_positions_for_bots(
    db: AsyncSession, bot_ids: list[int],
) -> list[Position]:
    if not bot_ids:
        return []
    result = await db.execute(
        select(Position).where(
            Position.bot_id.in_(bot_ids),
            Position.status == "open",
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_speculative_bucket_info(
    db: AsyncSession,
    account_id: int,
    aggregate_usd_value: float,
    btc_usd_price: float = 0.0,
) -> dict:
    """Return the user's full speculative bucket snapshot.

    Args:
        db: Async DB session.
        account_id: Account to scope all queries to.
        aggregate_usd_value: Total account value in USD (same denominator
            used by other budget math). Bucket size is
            speculative_allocation_pct × aggregate_usd_value.
        btc_usd_price: Current BTC/USD price — needed only when any
            speculative bot on this account trades BTC-quoted pairs.

    Returns a dict shaped as documented in PRP §Recommended Design §1.
    Safe to call when no speculative bots exist; returns bucket info
    with zeros.
    """
    # Fetch the account to read the configured allocation %
    account_row = await db.execute(
        select(Account).where(Account.id == account_id)
    )
    account = account_row.scalars().first()
    bucket_pct = float(account.speculative_allocation_pct or 0.0) if account else 0.0
    bucket_usd = max(0.0, aggregate_usd_value * bucket_pct / 100.0)

    bots = await _speculative_bots_for_account(db, account_id)
    bot_ids = [b.id for b in bots]
    positions = await _open_positions_for_bots(db, bot_ids)

    deployed_cost_basis_usd = sum(
        _position_cost_basis_usd(p, btc_usd_price) for p in positions
    )
    available_usd = max(0.0, bucket_usd - deployed_cost_basis_usd)

    max_concurrent_slots = 0
    for bot in bots:
        cfg = bot.strategy_config or {}
        max_concurrent_slots += int(cfg.get("max_concurrent_deals", 1) or 1)

    remaining_slots = max(1, max_concurrent_slots - len(positions))
    per_slot_budget_usd = available_usd / remaining_slots if remaining_slots > 0 else 0.0

    return {
        "bucket_pct": bucket_pct,
        "bucket_usd": round(bucket_usd, 2),
        "deployed_cost_basis_usd": round(deployed_cost_basis_usd, 2),
        "available_usd": round(available_usd, 2),
        "active_bot_count": len(bots),
        "open_position_count": len(positions),
        "max_concurrent_slots": max_concurrent_slots,
        "per_slot_budget_usd": round(per_slot_budget_usd, 2),
    }


async def validate_speculative_entry(
    db: AsyncSession,
    bot: Bot,
    intended_cost_basis_usd: float,
    aggregate_usd_value: float,
    btc_usd_price: float = 0.0,
) -> tuple[bool, str]:
    """Gate a speculative-tagged bot's new-position attempt against the bucket.

    Returns (allowed, reason). Called from _run_new_position_preflight in
    signal_processor.buy_decision. Returns (False, ...) when:
    - The account has no bucket configured (speculative_allocation_pct == 0).
    - The intended cost basis would exceed bucket headroom.
    """
    if bot.account_id is None:
        return False, "Speculative bot has no account_id — cannot validate bucket"

    info = await get_speculative_bucket_info(
        db, bot.account_id, aggregate_usd_value, btc_usd_price=btc_usd_price,
    )

    if info["bucket_pct"] <= 0:
        return False, (
            "Speculative bucket not configured for this account — "
            "set Account.speculative_allocation_pct before running speculative bots"
        )

    if intended_cost_basis_usd <= 0:
        # Nothing to deploy — trivially allowed. Let the real budget check
        # downstream decide if the actual order size is viable.
        return True, ""

    if intended_cost_basis_usd > info["available_usd"]:
        return False, (
            f"Speculative bucket full: need ${intended_cost_basis_usd:.2f} but only "
            f"${info['available_usd']:.2f} available "
            f"(${info['deployed_cost_basis_usd']:.2f} of ${info['bucket_usd']:.2f} already deployed "
            f"across {info['open_position_count']} open positions on "
            f"{info['active_bot_count']} speculative bots)"
        )

    return True, ""
