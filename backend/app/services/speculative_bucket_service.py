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

from app.models import Account, AIOpinionLog, Bot, Position

logger = logging.getLogger(__name__)


# Calibration alert thresholds (Phase F Task F2). Kept at module level
# so the monitor and tests reference the same constants.
CALIBRATION_MIN_CLOSED = 50
CALIBRATION_MIN_COMPONENT_FIRES = 30
CALIBRATION_MIN_DIVERGENCE_PP = 20.0

# Rebalance floor warning: require min_balance_usd to be at least this
# multiple of per_slot_budget_usd. One slot's worth plus a cushion for
# the next candidate entry and fees. If the rebalancer drops below this
# floor, speculative entries may fail with "insufficient free USD" even
# when the bucket itself shows headroom.
REBALANCE_FLOOR_SAFETY_MULTIPLE = 2.0


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

    warnings = _build_bucket_warnings(
        account=account, bucket_pct=bucket_pct,
        per_slot_budget_usd=per_slot_budget_usd,
    )

    return {
        "bucket_pct": bucket_pct,
        "bucket_usd": round(bucket_usd, 2),
        "deployed_cost_basis_usd": round(deployed_cost_basis_usd, 2),
        "available_usd": round(available_usd, 2),
        "active_bot_count": len(bots),
        "open_position_count": len(positions),
        "max_concurrent_slots": max_concurrent_slots,
        "per_slot_budget_usd": round(per_slot_budget_usd, 2),
        "warnings": warnings,
    }


def _build_bucket_warnings(
    *, account: Optional[Account], bucket_pct: float,
    per_slot_budget_usd: float,
) -> list[dict]:
    """Surface cross-dependency issues between the speculative bucket and
    other account-level settings that can silently starve the bot.

    Returns a list of {code, message} dicts — empty when nothing's wrong.
    Codes are stable so the frontend can key on them without scraping
    the message text.
    """
    warnings: list[dict] = []
    if account is None or bucket_pct <= 0 or per_slot_budget_usd <= 0:
        return warnings

    if getattr(account, "rebalance_enabled", False):
        # The rebalancer can only starve the speculative bucket if it moves USD
        # OUT into non-USD targets. With a ~100% USD target it only converts INTO
        # USD and can never drain cash, so the floor warning doesn't apply.
        non_usd_target = sum(
            float(getattr(account, f"rebalance_target_{c}_pct", 0.0) or 0.0)
            for c in ("btc", "eth", "usdc", "usdt")
        )
        rebalancer_can_drain_usd = non_usd_target > 0

        min_floor = float(getattr(account, "min_balance_usd", 0.0) or 0.0)
        required = per_slot_budget_usd * REBALANCE_FLOOR_SAFETY_MULTIPLE
        if rebalancer_can_drain_usd and min_floor < required:
            warnings.append({
                "code": "rebalance_floor_too_low",
                "message": (
                    f"Rebalance USD floor is ${min_floor:.0f} but per-slot budget is "
                    f"${per_slot_budget_usd:.0f} — raise min_balance_usd to at least "
                    f"${required:.0f} so the rebalancer doesn't drain cash between "
                    f"speculative entries."
                ),
            })

    return warnings


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


# ---------------------------------------------------------------------------
# Phase F — calibration analysis
# ---------------------------------------------------------------------------


def _parse_components(raw) -> list:
    """Normalize the speculative_components payload to a list of tuples.

    The scorer persists `[(name, fired, contribution), ...]`. PostgreSQL JSONB
    round-trips that as list-of-lists. SQLite's TEXT column (see migration
    083) may round-trip as a JSON string. Be lenient in both directions.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        # SQLite TEXT path — parse on read.
        import json as _json
        try:
            raw = _json.loads(raw)
        except Exception:
            return []
    if not isinstance(raw, list):
        return []
    return raw


async def analyze_speculative_calibration(
    db: AsyncSession, user_id: int,
) -> Optional[dict]:
    """Return a recalibration-analysis dict, or None if the user does not yet
    have enough closed speculative-bot data to warrant an alert.

    All three thresholds must hold simultaneously:
    - At least CALIBRATION_MIN_CLOSED closed positions from is_speculative
      bots owned by `user_id`, with a non-null doubling_probability_score
      in the matching ai_opinion_log row.
    - At least one component with CALIBRATION_MIN_COMPONENT_FIRES fires
      across those rows.
    - Top-scoring component's win rate minus bottom-scoring component's
      win rate >= CALIBRATION_MIN_DIVERGENCE_PP percentage points
      (only components with >= CALIBRATION_MIN_COMPONENT_FIRES fires
      are eligible for the top/bottom pick).

    Output shape is documented in PRPs/high-risk-doubling-preset.md §Task F2.
    """
    stmt = (
        select(AIOpinionLog, Position)
        .join(Position, AIOpinionLog.position_id == Position.id)
        .join(Bot, AIOpinionLog.bot_id == Bot.id)
        .where(
            AIOpinionLog.user_id == user_id,
            AIOpinionLog.doubling_probability_score.isnot(None),
            Position.status == "closed",
            _speculative_bot_filter(),
        )
    )
    rows = (await db.execute(stmt)).all()

    total_closed = len(rows)
    if total_closed < CALIBRATION_MIN_CLOSED:
        return None

    wins = sum(
        1 for _, pos in rows
        if (pos.profit_percentage or 0.0) > 0
    )
    losses = total_closed - wins
    overall_win_rate_pct = (wins / total_closed) * 100.0 if total_closed else 0.0

    overall_realized_pnl_usd = sum(
        float(getattr(pos, "profit_usd", None) or 0.0)
        for _, pos in rows
    )

    # Tally fires and wins per component. A component "fired" on a row if its
    # tuple in AIOpinionLog.speculative_components has fired=True. Wins are
    # counted by joining back to Position.profit_percentage > 0.
    component_fires: dict = {}
    component_wins: dict = {}
    for log_row, pos in rows:
        components = _parse_components(log_row.speculative_components)
        is_win = (pos.profit_percentage or 0.0) > 0
        for entry in components:
            if not entry or len(entry) < 2:
                continue
            name = entry[0]
            fired = bool(entry[1])
            if not fired:
                continue
            component_fires[name] = component_fires.get(name, 0) + 1
            if is_win:
                component_wins[name] = component_wins.get(name, 0) + 1

    if not component_fires:
        return None

    # Check "at least one component fired at least CALIBRATION_MIN_COMPONENT_FIRES times".
    if max(component_fires.values()) < CALIBRATION_MIN_COMPONENT_FIRES:
        return None

    components_list = []
    for name, fires in component_fires.items():
        win_rate = (component_wins.get(name, 0) / fires) * 100.0 if fires else 0.0
        components_list.append({
            "name": name,
            "fires": fires,
            "win_rate_pct": round(win_rate, 2),
        })
    components_list.sort(key=lambda c: c["win_rate_pct"], reverse=True)

    # Divergence is computed only across components with enough fires to
    # be statistically meaningful. A noisy component that fired 3 times
    # at 100% win rate should not trip the alert.
    eligible = [c for c in components_list
                if c["fires"] >= CALIBRATION_MIN_COMPONENT_FIRES]
    if len(eligible) < 2:
        # Only one component has enough fires — can't compute divergence.
        # Treat the analysis as not yet actionable.
        return None

    top = eligible[0]
    bottom = eligible[-1]
    divergence_pp = top["win_rate_pct"] - bottom["win_rate_pct"]
    if divergence_pp < CALIBRATION_MIN_DIVERGENCE_PP:
        return None

    return {
        "total_closed": total_closed,
        "wins": wins,
        "losses": losses,
        "overall_win_rate_pct": round(overall_win_rate_pct, 2),
        "overall_realized_pnl_usd": round(overall_realized_pnl_usd, 2),
        "components": components_list,
        "top_component": top["name"],
        "top_win_rate_pct": top["win_rate_pct"],
        "bottom_component": bottom["name"],
        "bottom_win_rate_pct": bottom["win_rate_pct"],
        "divergence_pp": round(divergence_pp, 2),
    }
