"""
Device trust management endpoints: list, revoke, revoke-all.
"""

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import TrustedDevice, User

from app.auth_routers.schemas import TrustedDeviceResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/mfa/devices", response_model=List[TrustedDeviceResponse])
async def list_trusted_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all trusted devices for the current user.

    Returns active (non-expired) trusted devices that can bypass MFA.
    """
    result = await db.execute(
        select(TrustedDevice)
        .where(
            TrustedDevice.user_id == current_user.id,
            TrustedDevice.expires_at > datetime.utcnow(),
        )
        .order_by(TrustedDevice.created_at.desc())
    )
    devices = result.scalars().all()

    return [
        TrustedDeviceResponse(
            id=d.id,
            device_name=d.device_name,
            ip_address=d.ip_address,
            location=d.location,
            created_at=d.created_at,
            expires_at=d.expires_at,
        )
        for d in devices
    ]


@router.delete("/mfa/devices/{device_id}")
async def revoke_trusted_device(
    device_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke a specific trusted device.

    The device will need to complete MFA again on next login.
    """
    result = await db.execute(
        select(TrustedDevice).where(
            TrustedDevice.id == device_id,
            TrustedDevice.user_id == current_user.id,
        )
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trusted device not found.",
        )

    await db.delete(device)
    await db.commit()

    logger.info(f"Trusted device revoked for user: {current_user.email} (device ID: {device_id})")

    return {"message": "Device trust revoked successfully"}


@router.delete("/mfa/devices")
async def revoke_all_trusted_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke all trusted devices for the current user.

    All devices will need to complete MFA again on next login.
    """
    result = await db.execute(
        select(TrustedDevice).where(TrustedDevice.user_id == current_user.id)
    )
    devices = result.scalars().all()

    for device in devices:
        await db.delete(device)

    await db.commit()

    logger.info(f"All trusted devices revoked for user: {current_user.email} ({len(devices)} devices)")

    return {"message": f"All {len(devices)} trusted device(s) revoked"}
