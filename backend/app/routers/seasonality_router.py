"""
Seasonality Management Router

Handles seasonality toggle feature for automatic bot management based on market cycles.
- GET /api/seasonality - Get current seasonality status
- POST /api/seasonality - Toggle seasonality on/off
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Settings, User
from app.routers.auth_dependencies import get_current_user_optional
from app.services.season_detector import get_seasonality_status, SeasonalityStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/seasonality", tags=["seasonality"])


# Pydantic models for request/response
class SeasonalityToggleRequest(BaseModel):
    enabled: bool


class SeasonalityResponse(BaseModel):
    enabled: bool
    season: str  # 'accumulation', 'bull', 'distribution', 'bear'
    season_name: str  # 'Spring', 'Summer', 'Fall', 'Winter'
    subtitle: str  # Technical term
    description: str
    progress: float
    confidence: float
    signals: list[str]
    mode: str  # 'risk_on' or 'risk_off'
    btc_bots_allowed: bool
    usd_bots_allowed: bool
    threshold_crossed: bool
    last_transition: Optional[str]


async def get_setting(db: AsyncSession, key: str) -> Optional[str]:
    """Get a setting value by key."""
    result = await db.execute(select(Settings).where(Settings.key == key))
    setting = result.scalars().first()
    return setting.value if setting else None


async def set_setting(db: AsyncSession, key: str, value: str, value_type: str = "string", description: str = None):
    """Set a setting value, creating if it doesn't exist."""
    result = await db.execute(select(Settings).where(Settings.key == key))
    setting = result.scalars().first()

    if setting:
        setting.value = value
        setting.updated_at = datetime.utcnow()
    else:
        setting = Settings(
            key=key,
            value=value,
            value_type=value_type,
            description=description,
            updated_at=datetime.utcnow()
        )
        db.add(setting)

    await db.commit()


@router.get("", response_model=SeasonalityResponse)
async def get_seasonality(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Get current seasonality status.

    Returns the current market season, progress, mode (risk_on/risk_off),
    and which bot types are allowed/blocked.
    """
    # Get current season status from detector
    status: SeasonalityStatus = await get_seasonality_status()

    # Get enabled state from database
    enabled_str = await get_setting(db, "seasonality_enabled")
    enabled = enabled_str == "true" if enabled_str else False

    # Get last transition timestamp
    last_transition = await get_setting(db, "seasonality_last_transition")

    return SeasonalityResponse(
        enabled=enabled,
        season=status.season_info.season,
        season_name=status.season_info.name,
        subtitle=status.season_info.subtitle,
        description=status.season_info.description,
        progress=status.season_info.progress,
        confidence=status.season_info.confidence,
        signals=status.season_info.signals,
        mode=status.mode,
        btc_bots_allowed=status.btc_bots_allowed if enabled else True,  # Always allowed if disabled
        usd_bots_allowed=status.usd_bots_allowed if enabled else True,
        threshold_crossed=status.threshold_crossed,
        last_transition=last_transition
    )


@router.post("", response_model=SeasonalityResponse)
async def toggle_seasonality(
    request: SeasonalityToggleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Toggle seasonality tracking on or off.

    When enabled, bots will be automatically managed based on market cycle:
    - Risk-On (Winter 80% through Summer 80%): BTC bots allowed, USD bots blocked
    - Risk-Off (Summer 80% through Winter 80%): USD bots allowed, BTC bots blocked
    """
    # Update the enabled setting
    await set_setting(
        db,
        "seasonality_enabled",
        "true" if request.enabled else "false",
        "bool",
        "Whether seasonality-based bot management is enabled"
    )

    # If enabling, record the current mode
    if request.enabled:
        status = await get_seasonality_status()
        await set_setting(
            db,
            "seasonality_mode",
            status.mode,
            "string",
            "Current seasonality mode (risk_on or risk_off)"
        )
        await set_setting(
            db,
            "seasonality_last_transition",
            datetime.utcnow().isoformat(),
            "string",
            "Timestamp of last mode transition"
        )
        logger.info(f"Seasonality enabled - current mode: {status.mode}")
    else:
        logger.info("Seasonality disabled - all bot restrictions removed")

    # Return current status
    return await get_seasonality(db, current_user)


@router.get("/check-bot")
async def check_bot_allowed(
    bot_type: str,  # 'btc' or 'usd'
    db: AsyncSession = Depends(get_db)
):
    """
    Check if a bot type is currently allowed based on seasonality.

    Used by bot control endpoints to validate enable requests.
    Returns: {allowed: bool, reason: string | null}
    """
    # Check if seasonality is enabled
    enabled_str = await get_setting(db, "seasonality_enabled")
    enabled = enabled_str == "true" if enabled_str else False

    if not enabled:
        return {"allowed": True, "reason": None}

    # Get current season status
    status = await get_seasonality_status()

    if bot_type.lower() == 'btc':
        if status.btc_bots_allowed:
            return {"allowed": True, "reason": None}
        else:
            return {
                "allowed": False,
                "reason": f"BTC bots are blocked during {status.mode.replace('_', '-')} mode ({status.season_info.name} at {status.season_info.progress:.0f}%)"
            }
    elif bot_type.lower() == 'usd':
        if status.usd_bots_allowed:
            return {"allowed": True, "reason": None}
        else:
            return {
                "allowed": False,
                "reason": f"USD bots are blocked during {status.mode.replace('_', '-')} mode ({status.season_info.name} at {status.season_info.progress:.0f}%)"
            }
    else:
        return {"allowed": True, "reason": None}  # Unknown type, allow by default
