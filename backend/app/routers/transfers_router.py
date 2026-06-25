"""
Transfers API Router

Endpoints for managing deposit/withdrawal tracking:
- Sync transfers from Coinbase
- List transfers with filtering
- Manual entry for transfers the API can't see
- Summary stats for reports and dashboard
"""

import logging
from app.utils.timeutil import utcnow
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import Account, AccountTransfer, User
from app.services.account_access import accessible_account_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/transfers", tags=["transfers"])


# ----- Pydantic Schemas -----

class ManualTransferCreate(BaseModel):
    account_id: int
    transfer_type: str = Field(..., pattern="^(deposit|withdrawal)$")
    amount: float = Field(..., gt=0)
    currency: str = Field(..., min_length=1, max_length=10)
    amount_usd: Optional[float] = Field(None, ge=0)
    occurred_at: datetime


class TransferOut(BaseModel):
    id: int
    account_id: int
    transfer_type: str
    amount: float
    currency: str
    amount_usd: Optional[float]
    occurred_at: str
    source: str
    created_at: Optional[str]


# ----- Helpers -----

def _transfer_to_dict(t: AccountTransfer) -> dict:
    return {
        "id": t.id,
        "account_id": t.account_id,
        "transfer_type": t.transfer_type,
        "amount": t.amount,
        "currency": t.currency,
        "amount_usd": t.amount_usd,
        "occurred_at": t.occurred_at.isoformat() if t.occurred_at else None,
        "source": t.source,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


# ----- Endpoints -----

@router.post("/sync")
async def sync_transfers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Trigger a sync of deposit/withdrawal data from Coinbase."""
    from app.services.transfer_sync_service import sync_all_user_transfers

    try:
        count = await sync_all_user_transfers(db, current_user.id)
        return {
            "status": "ok",
            "new_transfers": count,
        }
    except Exception as e:
        logger.error(f"Transfer sync failed for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Transfer sync failed")


@router.get("")
async def list_transfers(
    start: Optional[str] = Query(None, description="ISO date start"),
    end: Optional[str] = Query(None, description="ISO date end"),
    account_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List transfers with optional date range and account filtering."""
    acc_ids = await accessible_account_ids(db, current_user.id)
    filters = [or_(
        AccountTransfer.user_id == current_user.id,
        AccountTransfer.account_id.in_(acc_ids),
    )]

    if account_id:
        filters.append(AccountTransfer.account_id == account_id)
    if start:
        try:
            start_dt = datetime.fromisoformat(start)
            filters.append(AccountTransfer.occurred_at >= start_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start date")
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
            filters.append(AccountTransfer.occurred_at <= end_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end date")

    # Count
    count_result = await db.execute(
        select(func.count(AccountTransfer.id)).where(and_(*filters))
    )
    total = count_result.scalar()

    # Fetch
    result = await db.execute(
        select(AccountTransfer)
        .where(and_(*filters))
        .order_by(AccountTransfer.occurred_at.desc())
        .offset(offset)
        .limit(limit)
    )
    transfers = result.scalars().all()

    return {
        "total": total,
        "transfers": [_transfer_to_dict(t) for t in transfers],
    }


@router.post("")
async def create_manual_transfer(
    body: ManualTransferCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Manually create a transfer record (for transfers the API can't see)."""
    # Verify account belongs to user
    result = await db.execute(
        select(Account).where(
            Account.id == body.account_id,
            Account.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    transfer = AccountTransfer(
        user_id=current_user.id,
        account_id=body.account_id,
        transfer_type=body.transfer_type,
        amount=body.amount,
        currency=body.currency,
        amount_usd=body.amount_usd,
        occurred_at=body.occurred_at,
        source="manual",
    )
    db.add(transfer)
    await db.commit()
    await db.refresh(transfer)

    return _transfer_to_dict(transfer)


@router.delete("/{transfer_id}")
async def delete_transfer(
    transfer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Delete a transfer record (manual entries only)."""
    result = await db.execute(
        select(AccountTransfer).where(
            AccountTransfer.id == transfer_id,
            AccountTransfer.user_id == current_user.id,
        )
    )
    transfer = result.scalar_one_or_none()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")

    await db.delete(transfer)
    await db.commit()
    return {"detail": "Transfer deleted"}


@router.get("/summary")
async def get_transfer_summary(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    account_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get deposit/withdrawal summary for a date range."""
    acc_ids = await accessible_account_ids(db, current_user.id)
    filters = [or_(
        AccountTransfer.user_id == current_user.id,
        AccountTransfer.account_id.in_(acc_ids),
    )]

    if account_id:
        filters.append(AccountTransfer.account_id == account_id)
    if start:
        try:
            filters.append(
                AccountTransfer.occurred_at >= datetime.fromisoformat(start)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start date")
    if end:
        try:
            filters.append(
                AccountTransfer.occurred_at <= datetime.fromisoformat(end)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end date")

    # Aggregate in SQL (sum + count grouped by type) rather than hydrating every
    # transfer row into Python — bounds the work to one row per transfer_type.
    agg = await db.execute(
        select(
            AccountTransfer.transfer_type,
            func.coalesce(func.sum(AccountTransfer.amount_usd), 0.0),
            func.count(),
        ).where(and_(*filters)).group_by(AccountTransfer.transfer_type)
    )
    by_type = {row[0]: (float(row[1] or 0.0), int(row[2] or 0)) for row in agg.all()}
    total_deposits, deposit_count = by_type.get("deposit", (0.0, 0))
    total_withdrawals, withdrawal_count = by_type.get("withdrawal", (0.0, 0))

    return {
        "net_deposits_usd": round(total_deposits - total_withdrawals, 2),
        "total_deposits_usd": round(total_deposits, 2),
        "total_withdrawals_usd": round(total_withdrawals, 2),
        "deposit_count": deposit_count,
        "withdrawal_count": withdrawal_count,
    }


@router.get("/recent-summary")
async def get_recent_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Quick summary for the dashboard — last 30 days of transfers.

    Used for:
    - Deposit note below projection table
    - Account value chart annotations
    """
    cutoff = utcnow() - timedelta(days=30)
    acc_ids = await accessible_account_ids(db, current_user.id)

    result = await db.execute(
        select(AccountTransfer).where(
            or_(
                AccountTransfer.user_id == current_user.id,
                AccountTransfer.account_id.in_(acc_ids),
            ),
            AccountTransfer.occurred_at >= cutoff,
        ).order_by(AccountTransfer.occurred_at.desc())
    )
    transfers = result.scalars().all()

    deposits = [t for t in transfers if t.transfer_type == "deposit"]
    withdrawals = [t for t in transfers if t.transfer_type == "withdrawal"]

    return {
        "last_30d_net_deposits_usd": round(
            sum(t.amount_usd or 0 for t in deposits)
            - sum(t.amount_usd or 0 for t in withdrawals),
            2,
        ),
        "last_30d_deposit_count": len(deposits),
        "last_30d_withdrawal_count": len(withdrawals),
        "transfers": [
            {
                "occurred_at": t.occurred_at.isoformat(),
                "type": t.transfer_type,
                "amount_usd": t.amount_usd,
                "currency": t.currency,
                "amount": t.amount,
            }
            for t in transfers
        ],
    }
