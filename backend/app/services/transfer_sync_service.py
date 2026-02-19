"""
Transfer Sync Service

Syncs deposit/withdrawal transactions from Coinbase into the
account_transfers table. Deduplicates by external_id to avoid
double-counting.

Can be called on-demand via API or scheduled as a daily background task.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AccountTransfer
from app.services.exchange_service import get_coinbase_for_account

logger = logging.getLogger(__name__)


async def sync_transfers(
    db: AsyncSession,
    user_id: int,
    account: Account,
    since: Optional[datetime] = None,
) -> int:
    """
    Fetch deposit/withdrawal transactions from Coinbase and insert new ones.

    Args:
        db: Database session
        user_id: Owner user ID
        account: Account to sync
        since: Only fetch transactions after this date (default: 90 days ago)

    Returns:
        Count of newly inserted transfers
    """
    if not since:
        since = datetime.utcnow() - timedelta(days=90)

    try:
        client = await get_coinbase_for_account(account)
    except Exception as e:
        logger.error(
            f"Failed to get Coinbase client for account {account.id}: {e}"
        )
        return 0

    # Get all Coinbase account UUIDs to scan
    try:
        cb_accounts = await client.get_accounts(force_fresh=True)
    except Exception as e:
        logger.error(f"Failed to fetch Coinbase accounts: {e}")
        return 0

    new_count = 0

    for cb_acct in cb_accounts:
        acct_uuid = cb_acct.get("uuid")
        if not acct_uuid:
            continue

        try:
            transfers = await client.get_deposit_withdrawals(
                acct_uuid, since=since
            )
        except Exception as e:
            logger.warning(
                f"Failed to fetch transfers for CB account {acct_uuid}: {e}"
            )
            continue

        for t in transfers:
            # Skip non-completed transactions
            if t.get("status") not in ("completed", ""):
                continue

            external_id = t.get("external_id")
            if not external_id:
                continue

            # Check for duplicate
            existing = await db.execute(
                select(AccountTransfer.id).where(
                    AccountTransfer.external_id == external_id
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            # Parse occurred_at
            occurred_at_str = t.get("occurred_at", "")
            try:
                occurred_at = datetime.fromisoformat(
                    occurred_at_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except (ValueError, AttributeError):
                logger.warning(
                    f"Invalid date for transaction {external_id}: "
                    f"{occurred_at_str}"
                )
                continue

            transfer = AccountTransfer(
                user_id=user_id,
                account_id=account.id,
                external_id=external_id,
                transfer_type=t["transfer_type"],
                amount=t["amount"],
                currency=t["currency"],
                amount_usd=t.get("amount_usd"),
                occurred_at=occurred_at,
                source="coinbase_api",
            )
            db.add(transfer)
            new_count += 1

    if new_count > 0:
        await db.flush()
        logger.info(
            f"Synced {new_count} new transfers for account {account.id}"
        )

    return new_count


async def sync_all_user_transfers(
    db: AsyncSession,
    user_id: int,
    since: Optional[datetime] = None,
) -> int:
    """
    Sync transfers for all of a user's active, non-paper-trading accounts.

    Returns total count of newly inserted transfers.
    """
    result = await db.execute(
        select(Account).where(
            Account.user_id == user_id,
            Account.is_active.is_(True),
            Account.is_paper_trading.is_(False),
        )
    )
    accounts = result.scalars().all()

    total_new = 0
    for account in accounts:
        try:
            count = await sync_transfers(db, user_id, account, since=since)
            total_new += count
        except Exception as e:
            logger.error(
                f"Error syncing transfers for account {account.id}: {e}"
            )

    if total_new > 0:
        await db.commit()

    return total_new
