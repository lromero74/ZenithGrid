"""
Account Value History API Router

Endpoints for fetching and managing account value snapshots over time.
"""

import logging
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.auth_dependencies import get_current_user
from app.models import User
from app.services import account_snapshot_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account-value", tags=["account-value"])


@router.get("/history")
async def get_account_value_history(
    days: int = Query(365, ge=1, le=1825, description="Number of days to fetch (max 5 years)"),
    include_paper_trading: bool = Query(False, description="Include paper trading accounts (default: false)"),
    account_id: int = Query(None, description="Specific account ID (omit for all accounts)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get historical account value snapshots.

    If account_id is provided, returns snapshots for that specific account only.
    Otherwise, returns aggregated snapshots across all user accounts.

    By default, excludes paper trading accounts (virtual money) when aggregating.
    """
    try:
        history = await account_snapshot_service.get_account_value_history(
            db, current_user.id, days, include_paper_trading, account_id
        )
        return history
    except Exception as e:
        logger.error(f"Failed to fetch account value history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest")
async def get_latest_snapshot(
    include_paper_trading: bool = Query(False, description="Include paper trading accounts (default: false)"),
    db: AsyncSession = Depends(get_db),
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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
    from app.exchange_clients.factory import create_exchange_client
    from app.models import Account
    from sqlalchemy import select

    try:
        # Verify account belongs to user
        account_query = select(Account).where(
            Account.id == account_id,
            Account.user_id == current_user.id
        )
        account_result = await db.execute(account_query)
        account = account_result.scalars().first()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found or not accessible")

        # Get exchange client for this account
        exchange = await create_exchange_client(db, account_id)

        # Get raw balances
        balances = await exchange.get_account()
        raw_usd = balances.get("USD", 0.0) + balances.get("USDC", 0.0) + balances.get("USDT", 0.0)
        raw_btc = balances.get("BTC", 0.0)

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch bidirectional reservations: {e}")
        raise HTTPException(status_code=500, detail=str(e))
