"""
Settings Service

Provides access to application settings stored in the database.
Extracted from routers/blacklist_router.py to avoid service→router imports.
"""

import json
import logging
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Settings

logger = logging.getLogger(__name__)

# Default: only APPROVED can trade
DEFAULT_ALLOWED_CATEGORIES = ["APPROVED"]
ALLOWED_CATEGORIES_KEY = "allowed_coin_categories"


async def get_allowed_categories(db: AsyncSession) -> List[str]:
    """Get list of categories allowed to trade from database."""
    query = select(Settings).where(Settings.key == ALLOWED_CATEGORIES_KEY)
    result = await db.execute(query)
    setting = result.scalars().first()

    if setting and setting.value:
        try:
            return json.loads(setting.value)
        except json.JSONDecodeError:
            pass

    return DEFAULT_ALLOWED_CATEGORIES
