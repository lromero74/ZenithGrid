"""
Account value summary service.

Provides a fast account-level total for the dashboard/header without forcing
the frontend to wait on the full portfolio payload. Paper accounts prefer a
cached live summary or the most recent snapshot so first login stays fast.
"""

import asyncio
import logging
import threading
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import api_cache
from app.models import Account, AccountValueSnapshot, User
from app.services.account_access import accessible_accounts_filter
from app.services.account_service import get_portfolio_for_account
from app.services.exchange_service import get_coinbase_for_account
from app.services.paper_valuation_service import build_paper_holdings_and_totals
from app.services.portfolio_service import get_cex_portfolio

logger = logging.getLogger(__name__)

SUMMARY_CACHE_TTL_SECONDS = 60
_refresh_lock = threading.Lock()
_refresh_in_flight: set[int] = set()


def _summary_cache_key(account_id: int) -> str:
    return f"account_value_summary_{account_id}"


async def get_account_value_summary(
    db: AsyncSession,
    current_user: User,
    account_id: int,
    force_fresh: bool = False,
) -> Dict[str, Any]:
    """Return a small, dashboard-friendly value summary for one account."""
    result = await db.execute(
        select(Account).where(
            Account.id == account_id,
            accessible_accounts_filter(current_user.id),
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Not found")

    cache_key = _summary_cache_key(account_id)

    if not force_fresh:
        cached = await api_cache.get(cache_key)
        if cached is not None:
            return cached

    if account.is_paper_trading and not force_fresh:
        snapshot_result = await db.execute(
            select(AccountValueSnapshot)
            .where(AccountValueSnapshot.account_id == account.id)
            .order_by(AccountValueSnapshot.snapshot_date.desc())
            .limit(1)
        )
        snapshot = snapshot_result.scalar_one_or_none()
        if snapshot:
            is_refreshing = _schedule_paper_summary_refresh(account)
            return {
                "account_id": account.id,
                "account_name": account.name,
                "total_usd_value": float(snapshot.total_value_usd or 0.0),
                "total_btc_value": float(snapshot.total_value_btc or 0.0),
                "btc_usd_price": float(snapshot.btc_usd_price or 0.0),
                "as_of": snapshot.snapshot_date.isoformat(),
                "is_stale": True,
                "is_refreshing": is_refreshing,
            }

    if account.is_paper_trading:
        summary = await _build_live_paper_account_value_summary(account)
    elif account.type == "cex" and (account.exchange or "coinbase") == "coinbase":
        portfolio = await get_cex_portfolio(
            account,
            db,
            get_coinbase_for_account,
            force_fresh=force_fresh,
            include_details=False,
        )
        summary = {
            "account_id": account.id,
            "account_name": account.name,
            "total_usd_value": float(portfolio.get("total_usd_value", 0.0) or 0.0),
            "total_btc_value": float(portfolio.get("total_btc_value", 0.0) or 0.0),
            "btc_usd_price": float(portfolio.get("btc_usd_price", 0.0) or 0.0),
            "as_of": datetime.utcnow().isoformat(),
            "is_stale": False,
            "is_refreshing": False,
        }
    else:
        portfolio = await get_portfolio_for_account(db, current_user, account_id, force_fresh=force_fresh)
        summary = {
            "account_id": account.id,
            "account_name": account.name,
            "total_usd_value": float(portfolio.get("total_usd_value", 0.0) or 0.0),
            "total_btc_value": float(portfolio.get("total_btc_value", 0.0) or 0.0),
            "btc_usd_price": float(portfolio.get("btc_usd_price", 0.0) or 0.0),
            "as_of": datetime.utcnow().isoformat(),
            "is_stale": False,
            "is_refreshing": False,
        }

    await api_cache.set(cache_key, summary, SUMMARY_CACHE_TTL_SECONDS)
    return summary


def _schedule_paper_summary_refresh(account: Account) -> bool:
    """Trigger a background refresh for a paper account if one isn't already running."""
    with _refresh_lock:
        if account.id in _refresh_in_flight:
            return True
        _refresh_in_flight.add(account.id)

    loop = asyncio.get_running_loop()
    loop.create_task(
        _refresh_paper_summary_cache(
            account.id,
            account.name,
            account.paper_balances,
        )
    )
    return True


async def _refresh_paper_summary_cache(account_id: int, account_name: str, paper_balances: str | None) -> None:
    """Rebuild and cache a paper summary in the background."""
    try:
        account = SimpleNamespace(
            id=account_id,
            name=account_name,
            paper_balances=paper_balances,
        )
        summary = await _build_live_paper_account_value_summary(account)
        await api_cache.set(_summary_cache_key(account_id), summary, SUMMARY_CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("Background paper summary refresh failed for account %s", account_id, exc_info=True)
    finally:
        with _refresh_lock:
            _refresh_in_flight.discard(account_id)


async def _build_live_paper_account_value_summary(account: Account) -> Dict[str, Any]:
    """Compute a live total for a paper account with bounded price-fetch concurrency."""
    valuation = await build_paper_holdings_and_totals(account)

    return {
        "account_id": account.id,
        "account_name": account.name,
        "total_usd_value": valuation["total_usd_value"],
        "total_btc_value": valuation["total_btc_value"],
        "btc_usd_price": valuation["btc_usd_price"],
        "as_of": datetime.utcnow().isoformat(),
        "is_stale": False,
        "is_refreshing": False,
    }
