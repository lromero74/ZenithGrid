"""
Settings Service

Provides access to application settings stored in the database.
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

# AI Provider constants (single source of truth)
VALID_AI_PROVIDERS = ["claude", "openai", "gemini", "grok"]
DEFAULT_AI_PROVIDER = "claude"
AI_REVIEW_PROVIDER_KEY = "ai_review_provider"


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


def get_configured_ai_providers() -> List[str]:
    """Return only AI providers that have API keys configured."""
    from app.config import settings as app_settings

    configured = []
    provider_keys = {
        "claude": app_settings.anthropic_api_key,
        "openai": app_settings.openai_api_key,
        "gemini": app_settings.gemini_api_key,
        "grok": app_settings.grok_api_key,
    }

    for provider, key in provider_keys.items():
        if key:
            configured.append(provider)

    return configured


async def get_ai_review_provider(db: AsyncSession) -> str:
    """Get configured AI provider for coin review from database."""
    query = select(Settings).where(Settings.key == AI_REVIEW_PROVIDER_KEY)
    result = await db.execute(query)
    setting = result.scalars().first()

    if setting and setting.value and setting.value.lower() in VALID_AI_PROVIDERS:
        return setting.value.lower()

    return DEFAULT_AI_PROVIDER
