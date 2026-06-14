"""
Transfer Sync Service

Syncs deposit/withdrawal transactions from Coinbase into the
account_transfers table. Deduplicates by external_id to avoid
double-counting.

Can be called on-demand via API or scheduled as a daily background task.
"""

import asyncio
import logging
from app.utils.timeutil import utcnow
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AccountTransfer
from app.services.exchange_service import get_coinbase_for_account

logger = logging.getLogger(__name__)

# Max concurrent Coinbase sub-account transfer fetches — these are independent
# network round-trips; bounded concurrency keeps us under exchange rate limits.
TRANSFER_FETCH_CONCURRENCY = 8


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
        since = utcnow() - timedelta(days=90)

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

    # Fetch each Coinbase sub-account's transfers concurrently (bounded) — the
    # fetches are independent network round-trips, so serial scanning was
    # O(sub-accounts) x API latency and grew with the number of coins held.
    account_uuids = [a.get("uuid") for a in cb_accounts if a.get("uuid")]
    sem = asyncio.Semaphore(TRANSFER_FETCH_CONCURRENCY)

    async def _fetch(uuid):
        async with sem:
            try:
                return await client.get_deposit_withdrawals(uuid, since=since)
            except Exception as e:
                logger.warning(
                    f"Failed to fetch transfers for CB account {uuid}: {e}"
                )
                return []

    fetched = await asyncio.gather(*(_fetch(u) for u in account_uuids))

    # Pre-filter to completed transfers with external_ids (flattened across accounts)
    valid_transfers = [
        t for transfers in fetched for t in transfers
        if t.get("status") in ("completed", "") and t.get("external_id")
    ]

    new_count = 0
    if not valid_transfers:
        return new_count

    # One bulk duplicate check for ALL candidates across all sub-accounts
    # (was a separate WHERE IN query per sub-account).
    candidate_ids = [t["external_id"] for t in valid_transfers]
    existing_result = await db.execute(
        select(AccountTransfer.external_id).where(
            AccountTransfer.external_id.in_(candidate_ids)
        )
    )
    existing_ids = {row[0] for row in existing_result.fetchall()}

    seen: set = set()  # guard against the same external_id appearing twice this batch
    for t in valid_transfers:
        external_id = t["external_id"]
        if external_id in existing_ids or external_id in seen:
            continue
        seen.add(external_id)

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

        db.add(AccountTransfer(
            user_id=user_id,
            account_id=account.id,
            external_id=external_id,
            transfer_type=t["transfer_type"],
            amount=t["amount"],
            currency=t["currency"],
            amount_usd=t.get("amount_usd"),
            occurred_at=occurred_at,
            source="coinbase_api",
            original_type=t.get("coinbase_type"),
        ))
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


async def run_transfer_sync_once(session_maker=None):
    """Sync deposits/withdrawals for all active users. Called by APScheduler."""
    from sqlalchemy import select
    from app.database import async_session_maker as _default_sm
    from app.models import User
    import logging as _logging

    logger = _logging.getLogger(__name__)
    sm = session_maker or _default_sm
    try:
        async with sm() as db:
            result = await db.execute(select(User).where(User.is_active.is_(True)))
            users = result.scalars().all()

            for user in users:
                try:
                    count = await sync_all_user_transfers(db, user.id)
                    if count > 0:
                        logger.info(f"Synced {count} new transfers for user {user.id}")
                except Exception as e:
                    logger.error(f"Transfer sync failed for user {user.id}: {e}")
    except Exception as e:
        logger.error(f"Error in transfer sync: {e}")
