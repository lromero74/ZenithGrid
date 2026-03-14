"""
Donations API Router

Endpoints for donation tracking, self-reporting, and admin management.
Monthly goal progress is calculated from confirmed donations.
"""

import logging
import time
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission, Perm
from app.database import get_db
from app.models import User
from app.models.donations import Donation
from app.models.system import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/donations", tags=["donations"])

# Self-report rate limiting: 5 per day per user
_report_timestamps: dict[int, list[float]] = defaultdict(list)
_REPORT_RATE_MAX = 5
_REPORT_RATE_WINDOW = 86400  # 24 hours


def _check_report_rate(user_id: int) -> None:
    now = time.monotonic()
    attempts = _report_timestamps[user_id]
    cutoff = now - _REPORT_RATE_WINDOW
    attempts[:] = [t for t in attempts if t > cutoff]
    if len(attempts) >= _REPORT_RATE_MAX:
        raise HTTPException(
            status_code=429,
            detail="Too many donation reports. Please try again later.",
        )
    attempts.append(now)


# ── Schemas ──────────────────────────────────────────────────────────


class DonationReport(BaseModel):
    amount: float = Field(..., gt=0)
    currency: str = Field(default="USD", max_length=10)
    payment_method: str = Field(..., max_length=50)
    tx_reference: str | None = None
    donor_name: str | None = None


class DonationCreate(BaseModel):
    amount: float = Field(..., gt=0)
    currency: str = Field(default="USD", max_length=10)
    payment_method: str = Field(..., max_length=50)
    tx_reference: str | None = None
    donor_name: str | None = None
    notes: str | None = None
    donation_date: datetime | None = None


class GoalUpdate(BaseModel):
    target: float = Field(..., gt=0)


# ── Public (authenticated) endpoints ────────────────────────────────


@router.get("/goal")
async def get_donation_goal(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.SOCIAL_CHAT)),
):
    """Get current quarter's donation goal progress."""
    now = datetime.utcnow()
    quarter = (now.month - 1) // 3 + 1  # 1-4
    quarter_start_month = (quarter - 1) * 3 + 1  # 1, 4, 7, 10
    quarter_start = datetime(now.year, quarter_start_month, 1)
    if quarter < 4:
        quarter_end = datetime(now.year, quarter_start_month + 3, 1)
    else:
        quarter_end = datetime(now.year + 1, 1, 1)

    # Get target from settings
    result = await db.execute(
        select(Settings).where(Settings.key == "donation_goal_quarterly")
    )
    setting = result.scalar_one_or_none()
    target = float(setting.value) if setting else 300.0

    # Sum confirmed donations this quarter
    result = await db.execute(
        select(
            func.coalesce(func.sum(Donation.amount), 0),
            func.count(Donation.id),
        ).where(
            Donation.status == "confirmed",
            Donation.donation_date >= quarter_start,
            Donation.donation_date < quarter_end,
        )
    )
    row = result.one()
    current = float(row[0])
    count = int(row[1])

    percentage = min(round((current / target) * 100, 1), 100.0) if target > 0 else 0

    return {
        "target": target,
        "current": round(current, 2),
        "percentage": percentage,
        "quarter": f"{now.year} Q{quarter}",
        "donation_count": count,
    }


@router.post("/report")
async def report_donation(
    data: DonationReport,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.SOCIAL_CHAT)),
):
    """User self-reports a donation (status=pending until admin confirms)."""
    _check_report_rate(current_user.id)

    donation = Donation(
        user_id=current_user.id,
        amount=data.amount,
        currency=data.currency,
        payment_method=data.payment_method,
        tx_reference=data.tx_reference,
        donor_name=data.donor_name or current_user.display_name,
        status="pending",
        donation_date=datetime.utcnow(),
    )
    db.add(donation)
    await db.commit()
    await db.refresh(donation)

    return {
        "id": donation.id,
        "status": "pending",
        "message": "Thank you! Your donation will be confirmed by an admin.",
    }


# ── Admin endpoints ─────────────────────────────────────────────────


@router.get("")
async def list_donations(
    status: str | None = None,
    month: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """List donations with optional status and month filters."""
    query = select(Donation).order_by(Donation.donation_date.desc())

    if status:
        query = query.where(Donation.status == status)

    if month:
        try:
            year, mon = month.split("-")
            query = query.where(
                func.extract("month", Donation.donation_date) == int(mon),
                func.extract("year", Donation.donation_date) == int(year),
            )
        except (ValueError, AttributeError):
            pass

    result = await db.execute(query)
    donations = result.scalars().all()

    # Get user display names
    user_ids = {d.user_id for d in donations if d.user_id}
    name_map: dict[int, str] = {}
    if user_ids:
        name_result = await db.execute(
            select(User.id, User.display_name).where(User.id.in_(user_ids))
        )
        for uid, dname in name_result.all():
            name_map[uid] = dname or f"User {uid}"

    return [
        {
            "id": d.id,
            "user_id": d.user_id,
            "user_name": name_map.get(d.user_id) if d.user_id else None,
            "amount": d.amount,
            "currency": d.currency,
            "payment_method": d.payment_method,
            "tx_reference": d.tx_reference,
            "donor_name": d.donor_name,
            "notes": d.notes,
            "status": d.status,
            "confirmed_by": d.confirmed_by,
            "donation_date": d.donation_date.isoformat() if d.donation_date else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in donations
    ]


@router.post("")
async def add_donation(
    data: DonationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """Admin manually adds a confirmed donation."""
    donation = Donation(
        amount=data.amount,
        currency=data.currency,
        payment_method=data.payment_method,
        tx_reference=data.tx_reference,
        donor_name=data.donor_name,
        notes=data.notes,
        status="confirmed",
        confirmed_by=current_user.id,
        donation_date=data.donation_date or datetime.utcnow(),
    )
    db.add(donation)
    await db.commit()
    await db.refresh(donation)

    return {"id": donation.id, "status": "confirmed"}


@router.put("/{donation_id}/confirm")
async def confirm_donation(
    donation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """Admin confirms a pending donation."""
    result = await db.execute(
        select(Donation).where(Donation.id == donation_id)
    )
    donation = result.scalar_one_or_none()
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")

    if donation.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm a donation with status '{donation.status}'",
        )

    donation.status = "confirmed"
    donation.confirmed_by = current_user.id
    await db.commit()

    return {"id": donation.id, "status": "confirmed"}


@router.put("/{donation_id}/reject")
async def reject_donation(
    donation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """Admin rejects a pending donation."""
    result = await db.execute(
        select(Donation).where(Donation.id == donation_id)
    )
    donation = result.scalar_one_or_none()
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")

    if donation.status == "confirmed":
        raise HTTPException(
            status_code=400,
            detail="Cannot reject an already confirmed donation",
        )

    donation.status = "rejected"
    await db.commit()

    return {"id": donation.id, "status": "rejected"}


@router.put("/goal")
async def update_goal(
    data: GoalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """Admin updates the monthly donation goal target."""
    result = await db.execute(
        select(Settings).where(Settings.key == "donation_goal_quarterly")
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = str(data.target)
    else:
        db.add(Settings(
            key="donation_goal_quarterly",
            value=str(data.target),
            value_type="float",
            description="Monthly donation goal in USD",
        ))

    await db.commit()
    return {"target": data.target}
