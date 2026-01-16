"""
Account Value Snapshot Service

Captures daily snapshots of account values for historical charting.
Runs once per day via scheduled task.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AccountValueSnapshot, User
from app.services.exchange_service import get_exchange_client_for_account

logger = logging.getLogger(__name__)


async def capture_account_snapshot(db: AsyncSession, account: Account) -> bool:
    """
    Capture a single account value snapshot.

    Args:
        db: Database session
        account: Account to snapshot

    Returns:
        True if snapshot captured successfully
    """
    try:
        # Get exchange client for account
        client = await get_exchange_client_for_account(db, account)

        # Fetch current account balances
        balances = await client.get_account()

        # Calculate total BTC value
        total_btc = 0.0
        for currency, amount in balances.items():
            if currency == "BTC":
                total_btc += amount
            elif currency == "ETH":
                # Convert ETH to BTC
                try:
                    eth_btc_price = await client.get_current_price("ETH-BTC")
                    total_btc += amount * eth_btc_price
                except Exception as e:
                    logger.warning(f"Failed to get ETH-BTC price: {e}")
            # USD/USDC/USDT converted to BTC using BTC-USD price
            elif currency in ["USD", "USDC", "USDT"]:
                try:
                    btc_usd_price = await client.get_btc_usd_price()
                    total_btc += amount / btc_usd_price
                except Exception as e:
                    logger.warning(f"Failed to get BTC-USD price: {e}")

        # Calculate total USD value
        try:
            btc_usd_price = await client.get_btc_usd_price()
            total_usd = total_btc * btc_usd_price
        except Exception as e:
            logger.error(f"Failed to get BTC-USD price for USD calculation: {e}")
            total_usd = 0.0

        # Create snapshot with today's date (00:00:00)
        snapshot_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # Check if snapshot already exists for today
        result = await db.execute(
            select(AccountValueSnapshot).where(
                AccountValueSnapshot.account_id == account.id,
                AccountValueSnapshot.snapshot_date == snapshot_date
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing snapshot
            existing.total_value_btc = total_btc
            existing.total_value_usd = total_usd
            logger.info(f"Updated snapshot for account {account.id}: {total_btc:.8f} BTC / ${total_usd:.2f} USD")
        else:
            # Create new snapshot
            snapshot = AccountValueSnapshot(
                account_id=account.id,
                user_id=account.user_id,
                snapshot_date=snapshot_date,
                total_value_btc=total_btc,
                total_value_usd=total_usd
            )
            db.add(snapshot)
            logger.info(f"Created snapshot for account {account.id}: {total_btc:.8f} BTC / ${total_usd:.2f} USD")

        await db.commit()
        return True

    except Exception as e:
        logger.error(f"Failed to capture snapshot for account {account.id}: {e}")
        await db.rollback()
        return False


async def capture_all_account_snapshots(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    """
    Capture snapshots for all active accounts belonging to a user.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        Dict with success count and errors
    """
    result = await db.execute(
        select(Account).where(
            Account.user_id == user_id,
            Account.is_active == True
        )
    )
    accounts = result.scalars().all()

    success_count = 0
    errors = []

    for account in accounts:
        try:
            success = await capture_account_snapshot(db, account)
            if success:
                success_count += 1
            else:
                errors.append(f"Account {account.id} ({account.name}): Snapshot failed")
        except Exception as e:
            errors.append(f"Account {account.id} ({account.name}): {str(e)}")

    return {
        "success_count": success_count,
        "total_accounts": len(accounts),
        "errors": errors
    }


async def get_account_value_history(
    db: AsyncSession,
    user_id: int,
    days: int = 365,
    include_paper_trading: bool = False
) -> List[Dict[str, Any]]:
    """
    Get aggregated account value history for a user across all their accounts.

    Args:
        db: Database session
        user_id: User ID
        days: Number of days to fetch (default 365)
        include_paper_trading: Whether to include paper trading accounts (default False)

    Returns:
        List of daily snapshots with aggregated values
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Query snapshots grouped by date, summing across user's accounts
    # Exclude paper trading accounts by default (virtual money shouldn't mix with real)
    query = (
        select(
            AccountValueSnapshot.snapshot_date,
            func.sum(AccountValueSnapshot.total_value_btc).label("total_btc"),
            func.sum(AccountValueSnapshot.total_value_usd).label("total_usd")
        )
        .join(Account, AccountValueSnapshot.account_id == Account.id)
        .where(
            AccountValueSnapshot.user_id == user_id,
            AccountValueSnapshot.snapshot_date >= cutoff_date
        )
    )

    # Filter out paper trading accounts unless explicitly requested
    if not include_paper_trading:
        query = query.where(Account.is_paper_trading == False)

    query = query.group_by(AccountValueSnapshot.snapshot_date).order_by(AccountValueSnapshot.snapshot_date)

    result = await db.execute(query)

    snapshots = []
    for row in result:
        snapshots.append({
            "date": row.snapshot_date.strftime("%Y-%m-%d"),
            "timestamp": row.snapshot_date.isoformat(),
            "total_value_btc": float(row.total_btc),
            "total_value_usd": float(row.total_usd)
        })

    return snapshots


async def get_latest_snapshot(db: AsyncSession, user_id: int, include_paper_trading: bool = False) -> Dict[str, Any]:
    """
    Get the most recent aggregated snapshot for a user.

    Args:
        db: Database session
        user_id: User ID
        include_paper_trading: Whether to include paper trading accounts (default False)

    Returns:
        Latest snapshot data or empty dict if none found
    """
    query = (
        select(
            AccountValueSnapshot.snapshot_date,
            func.sum(AccountValueSnapshot.total_value_btc).label("total_btc"),
            func.sum(AccountValueSnapshot.total_value_usd).label("total_usd")
        )
        .join(Account, AccountValueSnapshot.account_id == Account.id)
        .where(AccountValueSnapshot.user_id == user_id)
    )

    # Filter out paper trading accounts unless explicitly requested
    if not include_paper_trading:
        query = query.where(Account.is_paper_trading == False)

    query = query.group_by(AccountValueSnapshot.snapshot_date).order_by(AccountValueSnapshot.snapshot_date.desc()).limit(1)

    result = await db.execute(query)

    row = result.first()
    if not row:
        return {}

    return {
        "date": row.snapshot_date.strftime("%Y-%m-%d"),
        "timestamp": row.snapshot_date.isoformat(),
        "total_value_btc": float(row.total_btc),
        "total_value_usd": float(row.total_usd)
    }
