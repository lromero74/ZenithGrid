"""
Paper Trading Account Management Router

Provides API endpoints for managing virtual paper trading accounts:
- View paper account balances
- Make virtual deposits in any currency
- Reset account to default amounts
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account
from app.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/paper-trading", tags=["paper-trading"])

# Default paper trading balances
DEFAULT_PAPER_BALANCES = {
    "BTC": 1.0,
    "ETH": 10.0,
    "USD": 100000.0,
    "USDC": 0.0,
    "USDT": 0.0
}


@router.get("/balance")
async def get_paper_balance(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get paper trading account balance for current user.

    Returns virtual balances for all supported currencies.
    """
    # Fetch paper trading account for this user
    result = await db.execute(
        select(Account).where(
            Account.user_id == current_user.id,
            Account.is_paper_trading.is_(True)
        )
    )
    paper_account = result.scalar_one_or_none()

    if not paper_account:
        raise HTTPException(status_code=404, detail="Paper trading account not found")

    # Parse JSON balances
    if paper_account.paper_balances:
        balances = json.loads(paper_account.paper_balances)
    else:
        balances = DEFAULT_PAPER_BALANCES
        # Save default balances if none exist
        paper_account.paper_balances = json.dumps(DEFAULT_PAPER_BALANCES)
        await db.commit()

    return {
        "account_id": paper_account.id,
        "account_name": paper_account.name,
        "balances": balances,
        "is_paper_trading": True
    }


@router.post("/deposit")
async def deposit_to_paper_account(
    currency: str,
    amount: float,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Make a virtual deposit to paper trading account.

    Args:
        currency: Currency code (BTC, ETH, USD, USDC, USDT)
        amount: Amount to deposit (must be positive)

    Returns updated balances.
    """
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Deposit amount must be positive")

    currency = currency.upper()
    supported_currencies = ["BTC", "ETH", "USD", "USDC", "USDT"]

    if currency not in supported_currencies:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported currency. Supported: {', '.join(supported_currencies)}"
        )

    # Fetch paper trading account
    result = await db.execute(
        select(Account).where(
            Account.user_id == current_user.id,
            Account.is_paper_trading.is_(True)
        )
    )
    paper_account = result.scalar_one_or_none()

    if not paper_account:
        raise HTTPException(status_code=404, detail="Paper trading account not found")

    # Load current balances
    if paper_account.paper_balances:
        balances = json.loads(paper_account.paper_balances)
    else:
        balances = DEFAULT_PAPER_BALANCES.copy()

    # Add deposit
    current_balance = balances.get(currency, 0.0)
    balances[currency] = current_balance + amount

    # Save updated balances
    paper_account.paper_balances = json.dumps(balances)
    await db.commit()

    logger.info(
        f"Paper trading deposit: user_id={current_user.id}, "
        f"currency={currency}, amount={amount}, "
        f"new_balance={balances[currency]}"
    )

    return {
        "success": True,
        "currency": currency,
        "deposited": amount,
        "new_balance": balances[currency],
        "balances": balances
    }


@router.post("/reset")
async def reset_paper_account(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Reset paper trading account to default balances and wipe all history.

    This will:
    - Reset balances to defaults (BTC: 1.0, ETH: 10.0, USD: 100,000.0)
    - Delete all paper trading positions (history)
    - Delete all paper trading trades
    - Cancel and delete all pending orders
    - Reset deal numbers (they'll restart from 1)

    Default amounts:
    - BTC: 1.0
    - ETH: 10.0
    - USD: 100,000.0
    - USDC: 0.0
    - USDT: 0.0

    Returns updated balances.
    """
    from app.models import Bot, PendingOrder, Position

    # Fetch paper trading account
    result = await db.execute(
        select(Account).where(
            Account.user_id == current_user.id,
            Account.is_paper_trading.is_(True)
        )
    )
    paper_account = result.scalar_one_or_none()

    if not paper_account:
        raise HTTPException(status_code=404, detail="Paper trading account not found")

    # Get all bots using this paper account
    bots_result = await db.execute(
        select(Bot).where(Bot.account_id == paper_account.id)
    )
    paper_bots = bots_result.scalars().all()
    bot_ids = [bot.id for bot in paper_bots]

    # Count items before deletion (for logging)
    positions_result = await db.execute(
        select(Position).where(Position.account_id == paper_account.id)
    )
    positions = positions_result.scalars().all()
    position_count = len(positions)

    pending_result = await db.execute(
        select(PendingOrder).where(PendingOrder.bot_id.in_(bot_ids)) if bot_ids else select(PendingOrder).where(False)
    )
    pending_count = len(pending_result.scalars().all())

    # Delete all positions (cascade will delete trades)
    for position in positions:
        await db.delete(position)

    # Delete all pending orders for paper bots
    if bot_ids:
        pending_orders_result = await db.execute(
            select(PendingOrder).where(PendingOrder.bot_id.in_(bot_ids))
        )
        for order in pending_orders_result.scalars().all():
            await db.delete(order)

    # Reset balances to defaults
    paper_account.paper_balances = json.dumps(DEFAULT_PAPER_BALANCES)

    await db.commit()

    logger.info(
        f"Paper trading account reset: user_id={current_user.id}, "
        f"account_id={paper_account.id}, "
        f"deleted {position_count} positions, {pending_count} pending orders"
    )

    return {
        "success": True,
        "message": "Paper trading account reset to default balances and history wiped",
        "balances": DEFAULT_PAPER_BALANCES,
        "deleted": {
            "positions": position_count,
            "pending_orders": pending_count
        }
    }


@router.post("/withdraw")
async def withdraw_from_paper_account(
    currency: str,
    amount: float,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Make a virtual withdrawal from paper trading account.

    Args:
        currency: Currency code (BTC, ETH, USD, USDC, USDT)
        amount: Amount to withdraw (must be positive)

    Returns updated balances.
    """
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Withdrawal amount must be positive")

    currency = currency.upper()
    supported_currencies = ["BTC", "ETH", "USD", "USDC", "USDT"]

    if currency not in supported_currencies:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported currency. Supported: {', '.join(supported_currencies)}"
        )

    # Fetch paper trading account
    result = await db.execute(
        select(Account).where(
            Account.user_id == current_user.id,
            Account.is_paper_trading.is_(True)
        )
    )
    paper_account = result.scalar_one_or_none()

    if not paper_account:
        raise HTTPException(status_code=404, detail="Paper trading account not found")

    # Load current balances
    if paper_account.paper_balances:
        balances = json.loads(paper_account.paper_balances)
    else:
        balances = DEFAULT_PAPER_BALANCES.copy()

    # Check sufficient funds
    current_balance = balances.get(currency, 0.0)
    if current_balance < amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient {currency}. Available: {current_balance}, Requested: {amount}"
        )

    # Subtract withdrawal
    balances[currency] = current_balance - amount

    # Save updated balances
    paper_account.paper_balances = json.dumps(balances)
    await db.commit()

    logger.info(
        f"Paper trading withdrawal: user_id={current_user.id}, "
        f"currency={currency}, amount={amount}, "
        f"new_balance={balances[currency]}"
    )

    return {
        "success": True,
        "currency": currency,
        "withdrawn": amount,
        "new_balance": balances[currency],
        "balances": balances
    }
