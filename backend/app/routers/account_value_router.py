"""
Account Value History API Router

Endpoints for fetching and managing account value snapshots over time.
"""

import logging
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError

from app.database import get_db, get_read_db
from app.auth.dependencies import get_current_user
from app.models import Account, User
from app.services import account_snapshot_service
from app.services.account_access import accessible_accounts_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account-value", tags=["account-value"])


async def _resolve_snapshot_user_id(
    db: AsyncSession, current_user_id: int, account_id: int | None
) -> int:
    """
    Return the user_id to use when querying AccountValueSnapshot rows.

    Snapshots are stored with the account OWNER's user_id.  When a member
    (observer/manager) requests history for a specific account, we look up
    the owner's user_id so the query matches the stored rows.

    Falls back to current_user_id when no account_id is given (aggregated
    view) — in that case the caller only sees their own accounts anyway.
    """
    if account_id is None:
        return current_user_id

    result = await db.execute(
        select(Account.user_id).where(
            Account.id == account_id,
            accessible_accounts_filter(current_user_id),
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found or not accessible")
    return row[0]


@router.get("/history")
async def get_account_value_history(
    days: int = Query(365, ge=1, le=1825, description="Number of days to fetch (max 5 years)"),
    include_paper_trading: bool = Query(False, description="Include paper trading accounts (default: false)"),
    account_id: int = Query(None, description="Specific account ID (omit for all accounts)"),
    db: AsyncSession = Depends(get_read_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get historical account value snapshots.

    If account_id is provided, returns snapshots for that specific account only.
    Otherwise, returns aggregated snapshots across all user accounts.

    By default, excludes paper trading accounts (virtual money) when aggregating.
    """
    try:
        snapshot_user_id = await _resolve_snapshot_user_id(db, current_user.id, account_id)
        history = await account_snapshot_service.get_account_value_history(
            db, snapshot_user_id, days, include_paper_trading, account_id
        )
        return history
    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Failed to fetch account value history: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/latest")
async def get_latest_snapshot(
    include_paper_trading: bool = Query(False, description="Include paper trading accounts (default: false)"),
    db: AsyncSession = Depends(get_read_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get the most recent account value snapshot.
    By default, excludes paper trading accounts (virtual money).
    """
    try:
        snapshot = await account_snapshot_service.get_latest_snapshot(db, current_user.id, include_paper_trading)
        return snapshot
    except Exception as e:
        logger.error(f"Failed to fetch latest snapshot: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/capture")
async def capture_snapshots(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Manually trigger snapshot capture for all user accounts.

    Useful for testing or if daily capture fails.
    """
    try:
        result = await account_snapshot_service.capture_all_account_snapshots(db, current_user.id)
        return result
    except Exception as e:
        logger.error(f"Failed to capture snapshots: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/activity")
async def get_daily_activity(
    days: int = Query(365, ge=1, le=1825, description="Number of days to fetch (max 5 years)"),
    include_paper_trading: bool = Query(False, description="Include paper trading accounts"),
    account_id: int = Query(None, description="Specific account ID (omit for all accounts)"),
    db: AsyncSession = Depends(get_read_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get daily activity (trades, deposits, withdrawals) aggregated by day/line/category.

    Used for chart markers on the account value chart.
    """
    try:
        snapshot_user_id = await _resolve_snapshot_user_id(db, current_user.id, account_id)
        activity = await account_snapshot_service.get_daily_activity(
            db, snapshot_user_id, days, include_paper_trading, account_id
        )
        return activity
    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Failed to fetch daily activity: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/reservations")
async def get_bidirectional_reservations(
    account_id: int = Query(..., description="Account ID to fetch reservations for"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get reserved USD and BTC amounts for bidirectional bots on specified account.

    Returns breakdown of total, available, and reserved amounts for both USD and BTC.
    Reservations are from bidirectional DCA bots that lock capital for both long and short sides.
    """
    from app.services.budget_calculator import calculate_available_usd, calculate_available_btc
    from app.services.exchange_service import get_exchange_client_for_account
    from app.models import Account
    from sqlalchemy import select

    try:
        # Verify account is accessible to user (owner or active member)
        from app.services.account_access import accessible_accounts_filter
        account_query = select(Account).where(
            Account.id == account_id,
            accessible_accounts_filter(current_user.id)
        )
        account_result = await db.execute(account_query)
        account = account_result.scalars().first()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found or not accessible")

        # Get exchange client for this account
        exchange = await get_exchange_client_for_account(db, account_id)
        if not exchange:
            raise HTTPException(status_code=400, detail="No exchange client for account")

        # Get raw balances (use individual cached balance methods, not get_account)
        raw_usd = (
            await exchange.get_usd_balance()
            + await exchange.get_usdc_balance()
            + await exchange.get_usdt_balance()
        )
        raw_btc = await exchange.get_btc_balance()

        # Get current BTC price for calculations
        current_btc_price = await exchange.get_btc_usd_price()

        # Calculate available amounts (after subtracting bidirectional reservations)
        available_usd = await calculate_available_usd(db, raw_usd, current_btc_price, account_id)
        available_btc = await calculate_available_btc(db, raw_btc, current_btc_price, account_id)

        # Calculate reserved amounts
        reserved_usd = max(0.0, raw_usd - available_usd)
        reserved_btc = max(0.0, raw_btc - available_btc)

        return {
            "account_id": account_id,
            "account_name": account.name,
            "is_paper_trading": account.is_paper_trading or False,
            "total_usd": raw_usd,
            "available_usd": available_usd,
            "reserved_usd": reserved_usd,
            "total_btc": raw_btc,
            "available_btc": available_btc,
            "reserved_btc": reserved_btc,
            "btc_usd_price": current_btc_price,
        }

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Failed to fetch bidirectional reservations: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")
