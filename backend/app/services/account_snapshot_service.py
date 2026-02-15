"""
Account Value Snapshot Service

Captures daily snapshots of account values for historical charting.
Runs once per day via scheduled task.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AccountValueSnapshot
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
        # Use the same portfolio calculation that the header/dashboard uses
        from app.routers.accounts.portfolio_utils import get_cex_portfolio, get_dex_portfolio
        from app.routers.accounts_router import get_coinbase_for_account

        if account.is_paper_trading:
            # Paper trading - use exchange client directly
            client = await get_exchange_client_for_account(db, account.id)
            if not client:
                logger.error(f"Failed to get exchange client for account {account.id}")
                return False

            total_btc = await client.calculate_aggregate_btc_value()
            total_usd = await client.calculate_aggregate_usd_value()

            portfolio = {
                "total_btc_value": total_btc,
                "total_usd_value": total_usd
            }
        elif account.type == "cex":
            portfolio = await get_cex_portfolio(account, db, get_coinbase_for_account)
        elif account.type == "dex":
            portfolio = await get_dex_portfolio(account, db, get_coinbase_for_account)
        else:
            logger.error(f"Unknown account type: {account.type}")
            return False

        # Extract totals from portfolio
        total_btc = portfolio.get("total_btc_value", 0.0)
        total_usd = portfolio.get("total_usd_value", 0.0)

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
        select(Account.id, Account.name, Account).where(
            Account.user_id == user_id,
            Account.is_active.is_(True)
        )
    )
    account_tuples = result.all()

    success_count = 0
    errors = []

    for account_id, account_name, account in account_tuples:
        try:
            success = await capture_account_snapshot(db, account)
            if success:
                success_count += 1
            else:
                errors.append(f"Account {account_id} ({account_name}): Snapshot failed")
        except Exception as e:
            errors.append(f"Account {account_id} ({account_name}): {str(e)}")

    return {
        "success_count": success_count,
        "total_accounts": len(account_tuples),
        "errors": errors
    }


async def get_account_value_history(
    db: AsyncSession,
    user_id: int,
    days: int = 365,
    include_paper_trading: bool = False,
    account_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get account value history for a user.

    If account_id is provided, returns snapshots for that specific account only.
    Otherwise, returns aggregated snapshots across all user accounts.

    Args:
        db: Database session
        user_id: User ID
        days: Number of days to fetch (default 365)
        include_paper_trading: Whether to include paper trading accounts (default False)
        account_id: Optional specific account ID to filter by

    Returns:
        List of daily snapshots with values (aggregated if account_id is None)
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    if account_id is not None:
        # Single account mode - return snapshots for specific account only
        query = (
            select(
                AccountValueSnapshot.snapshot_date,
                AccountValueSnapshot.total_value_btc.label("total_btc"),
                AccountValueSnapshot.total_value_usd.label("total_usd")
            )
            .where(
                AccountValueSnapshot.user_id == user_id,
                AccountValueSnapshot.account_id == account_id,
                AccountValueSnapshot.snapshot_date >= cutoff_date
            )
            .order_by(AccountValueSnapshot.snapshot_date)
        )
    else:
        # Aggregated mode - sum across user's accounts
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
            query = query.where(Account.is_paper_trading.is_(False))

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
        query = query.where(Account.is_paper_trading.is_(False))

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
