"""
Display Name API Router

Endpoints for setting/updating display names and checking availability.
Display names must be unique (case-insensitive).
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])

# Display name rules
DISPLAY_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{3,20}$")


# ----- Pydantic Schemas -----

class DisplayNameUpdate(BaseModel):
    display_name: str = Field(..., min_length=3, max_length=20)


# ----- Endpoints -----

@router.put("/display-name")
async def set_display_name(
    body: DisplayNameUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Set or update the current user's display name. Must be unique (case-insensitive)."""
    name = body.display_name.strip()

    if not DISPLAY_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=400,
            detail="Display name must be 3-20 characters: letters, numbers, underscores, hyphens only",
        )

    # Case-insensitive uniqueness check
    result = await db.execute(
        select(User.id).where(
            func.lower(User.display_name) == name.lower(),
            User.id != current_user.id,
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Display name is already taken")

    current_user.display_name = name
    await db.commit()
    return {"display_name": name}


@router.get("/display-name/check")
async def check_display_name(
    name: str = Query(..., min_length=3, max_length=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Check if a display name is available."""
    name = name.strip()

    if not DISPLAY_NAME_PATTERN.match(name):
        return {"available": False, "reason": "Invalid format"}

    result = await db.execute(
        select(User.id).where(
            func.lower(User.display_name) == name.lower(),
            User.id != current_user.id,
        )
    )
    taken = result.scalar_one_or_none() is not None
    return {"available": not taken, "name": name}
