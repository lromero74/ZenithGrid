"""Periodic safety audit: do open long positions still hold the coins they expect to sell?

This is the proactive guard against the drift that produced the INSUFFICIENT_FUND sell
failures — a position records `total_base_acquired` for a coin, but the live exchange
wallet holds less (dust-swept, rebalanced, partially filled elsewhere, manual move). The
audit sums each real account's open long *spot* positions per base currency and compares
to the account-scoped live Coinbase available balance. Any coin whose wallet balance is
below the recorded amount (beyond a tiny haircut) is logged as a WARNING and recorded to
the real-money audit trail so the shortfall is traceable before a sell fails.

Read-only: it builds the account-scoped client and fetches balances; it never trades.

Layering: services only (models + exchange_service + realmoney_audit). The pure helpers
(`expected_base_by_currency`, `find_coin_shortfalls`) hold the comparison logic and are
unit-tested without a DB or exchange.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Mirror sell_executor's SELL_BALANCE_HAIRCUT: a wallet within 0.1% of the recorded
# amount can still close the position (the clamp handles the rounding), so don't cry
# wolf over sub-0.1% dust differences.
COVERAGE_HAIRCUT = 0.999

# How often the background audit runs, and the grace period after startup.
AUDIT_INTERVAL_SECONDS = 3600
AUDIT_STARTUP_DELAY_SECONDS = 180


def expected_base_by_currency(positions) -> Dict[str, float]:
    """Sum recorded base coins across open LONG SPOT positions, grouped by base currency.

    Shorts (which sold base for quote) and futures (no spot holding) are excluded — they
    don't hold a spot coin waiting to be sold. Closed positions and malformed product_ids
    are skipped.
    """
    expected: Dict[str, float] = {}
    for p in positions:
        if getattr(p, "status", "open") != "open":
            continue
        if (getattr(p, "direction", None) or "long") != "long":
            continue
        if (getattr(p, "product_type", None) or "spot") != "spot":
            continue
        product_id = getattr(p, "product_id", None)
        if not product_id or "-" not in product_id:
            continue
        base = product_id.split("-")[0]
        expected[base] = expected.get(base, 0.0) + float(getattr(p, "total_base_acquired", 0.0) or 0.0)
    return expected


def find_coin_shortfalls(
    expected: Dict[str, float], wallet: Dict[str, float], haircut: float = COVERAGE_HAIRCUT
) -> List[Dict[str, Any]]:
    """Return one record per coin whose available wallet balance can't cover what the
    open positions recorded (below ``expected * haircut``). Empty list means all good.
    """
    shortfalls: List[Dict[str, Any]] = []
    for currency, exp in expected.items():
        if exp <= 0:
            continue
        available = float(wallet.get(currency, 0.0) or 0.0)
        if available < exp * haircut:
            shortfalls.append({
                "currency": currency,
                "expected": exp,
                "available": available,
                "deficit": exp - available,
                "coverage_pct": (available / exp * 100.0) if exp else 0.0,
            })
    return shortfalls


def _wallet_from_accounts(raw_accounts) -> Dict[str, float]:
    """Flatten the exchange get_accounts() payload into {currency: available_balance}."""
    wallet: Dict[str, float] = {}
    for a in raw_accounts or []:
        currency = a.get("currency")
        if not currency:
            continue
        ab = a.get("available_balance") or {}
        try:
            wallet[currency] = float(ab.get("value", 0) or 0)
        except (TypeError, ValueError):
            wallet[currency] = 0.0
    return wallet


async def audit_account(db, account) -> Optional[Dict[str, Any]]:
    """Audit one real account's open-long-spot coin coverage. Returns a summary dict
    (or None if it has nothing to check). Logs + records any shortfalls."""
    from sqlalchemy import select

    from app.models import Position
    from app.services.exchange_service import get_coinbase_for_account
    from app.services.realmoney_audit import record_event, set_subsystem

    positions = (await db.execute(
        select(Position).where(Position.account_id == account.id, Position.status == "open")
    )).scalars().all()

    expected = expected_base_by_currency(positions)
    if not expected:
        return None

    client = await get_coinbase_for_account(account)
    wallet = _wallet_from_accounts(await client.get_accounts(force_fresh=True))
    shortfalls = find_coin_shortfalls(expected, wallet)

    set_subsystem("position_coin_audit")
    if shortfalls:
        for sf in shortfalls:
            logger.warning(
                "Coin coverage SHORTFALL account=%s %s: recorded %.8f, wallet %.8f "
                "(%.1f%% — deficit %.8f). A full-size sell may fail with INSUFFICIENT_FUND.",
                account.id, sf["currency"], sf["expected"], sf["available"],
                sf["coverage_pct"], sf["deficit"],
            )
            record_event(
                "coin_coverage_shortfall",
                account_id=account.id,
                currency=sf["currency"],
                recorded=sf["expected"],
                available=sf["available"],
                deficit=sf["deficit"],
                coverage_pct=sf["coverage_pct"],
            )
    else:
        logger.info(
            "Coin coverage OK account=%s: %d coin(s) fully sellable.",
            account.id, len(expected),
        )

    return {
        "account_id": account.id,
        "coins_checked": len(expected),
        "shortfalls": shortfalls,
    }


async def run_position_coin_audit(db) -> List[Dict[str, Any]]:
    """Audit every real (non-paper) CEX account. Returns per-account summaries."""
    from sqlalchemy import select

    from app.models import Account

    accounts = (await db.execute(
        select(Account).where(
            Account.type == "cex",
            Account.is_paper_trading.is_(False),
            Account.is_active.is_(True),
        )
    )).scalars().all()

    summaries: List[Dict[str, Any]] = []
    for account in accounts:
        try:
            summary = await audit_account(db, account)
            if summary is not None:
                summaries.append(summary)
        except Exception as e:
            logger.error("Coin coverage audit failed for account %s: %s", account.id, e, exc_info=True)
    return summaries


# ---------------------------------------------------------------------------
# Background monitor (same start/stop pattern as the other service monitors)
# ---------------------------------------------------------------------------
_monitor_task: Optional[asyncio.Task] = None
_running = False


async def _monitor_loop():
    global _running
    _running = True
    await asyncio.sleep(AUDIT_STARTUP_DELAY_SECONDS)
    while _running:
        try:
            from app.database import async_session_maker
            async with async_session_maker() as db:
                await run_position_coin_audit(db)
        except Exception as e:
            logger.error("Position coin audit loop error: %s", e, exc_info=True)
        await asyncio.sleep(AUDIT_INTERVAL_SECONDS)


async def start_position_coin_audit_monitor():
    """Start the position-coin coverage background audit."""
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        logger.warning("Position coin audit monitor already running")
        return
    _monitor_task = asyncio.create_task(_monitor_loop())
    logger.info("Position coin audit monitor started")


async def stop_position_coin_audit_monitor():
    """Stop the position-coin coverage background audit."""
    global _running, _monitor_task
    _running = False
    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
        _monitor_task = None
    logger.info("Position coin audit monitor stopped")
