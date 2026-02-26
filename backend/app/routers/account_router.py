"""
Account and portfolio API routes

Handles account-related endpoints:
- Account balances (BTC, ETH, totals)
- Aggregate portfolio value calculations
- Full portfolio breakdown
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.exceptions import AppError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account, User
from app.auth.dependencies import get_current_user
from app.services import portfolio_conversion_service as pcs
from app.services.exchange_service import get_exchange_client_for_account
from app.services.portfolio_service import (
    get_account_balances,
    get_account_portfolio_data,
    get_coinbase_from_db,
    get_user_paper_account,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["account"])


@router.get("/balances")
async def get_balances(
    account_id: Optional[int] = Query(None, description="Account ID (defaults to first active CEX account)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current account balances with capital reservation tracking."""
    try:
        return await get_account_balances(db, current_user, account_id)
    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error getting balances: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/aggregate-value")
async def get_aggregate_value(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get aggregate portfolio value (BTC + USD) for bot budgeting"""
    try:
        # Check if user is paper-only
        paper_account = await get_user_paper_account(db, current_user.id)
        if paper_account:
            client = await get_exchange_client_for_account(db, paper_account.id)
            if client:
                aggregate_btc = await client.calculate_aggregate_btc_value()
                aggregate_usd = await client.calculate_aggregate_usd_value()
                btc_usd_price = await client.get_btc_usd_price()
                return {
                    "aggregate_btc_value": aggregate_btc,
                    "aggregate_usd_value": aggregate_usd,
                    "btc_usd_price": btc_usd_price,
                }
            # Paper account but client creation failed — return defaults
            return {
                "aggregate_btc_value": 0.0,
                "aggregate_usd_value": 0.0,
                "btc_usd_price": 0.0,
            }

        coinbase = await get_coinbase_from_db(db, current_user.id)
        aggregate_btc = await coinbase.calculate_aggregate_btc_value()
        aggregate_usd = await coinbase.calculate_aggregate_usd_value()
        btc_usd_price = await coinbase.get_btc_usd_price()

        return {
            "aggregate_btc_value": aggregate_btc,
            "aggregate_usd_value": aggregate_usd,
            "btc_usd_price": btc_usd_price,
        }
    except (HTTPException, AppError):
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/portfolio")
async def get_portfolio(
    force_fresh: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full portfolio breakdown (all coins)."""
    try:
        return await get_account_portfolio_data(db, current_user, force_fresh)
    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.exception(f"Portfolio endpoint error: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/conversion-status/{task_id}")
async def get_conversion_status(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Get status of a portfolio conversion task (requires auth)
    """
    progress = pcs.get_task_progress(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Conversion task not found")
    return progress


@router.post("/sell-portfolio-to-base")
async def sell_portfolio_to_base_currency(
    background_tasks: BackgroundTasks,
    target_currency: str = Query("BTC", description="Target currency: BTC or USD"),
    confirm: bool = Query(False, description="Must be true to execute"),
    account_id: Optional[int] = Query(None, description="Account ID to convert (defaults to default account)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start portfolio conversion to BTC or USD (runs in background).

    Returns immediately with a task_id to check progress via /conversion-status/{task_id}
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="Must confirm with confirm=true")

    if target_currency not in ["BTC", "USD"]:
        raise HTTPException(status_code=400, detail="target_currency must be BTC or USD")

    # Get the specified account or user's default account
    if account_id:
        account_query = select(Account).where(
            Account.id == account_id,
            Account.user_id == current_user.id
        )
    else:
        account_query = select(Account).where(
            Account.user_id == current_user.id,
            Account.is_default.is_(True)
        )
    account_result = await db.execute(account_query)
    account = account_result.scalars().first()

    if not account:
        if account_id:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
        else:
            raise HTTPException(status_code=404, detail="No default account found")

    # Generate task ID and start background task
    task_id = str(uuid.uuid4())

    # Start the conversion in the background
    background_tasks.add_task(
        pcs.run_portfolio_conversion,
        task_id=task_id,
        account_id=account.id,
        target_currency=target_currency,
        user_id=current_user.id
    )

    return {
        "task_id": task_id,
        "message": f"Portfolio conversion to {target_currency} started",
        "status_url": f"/api/account/conversion-status/{task_id}"
    }
