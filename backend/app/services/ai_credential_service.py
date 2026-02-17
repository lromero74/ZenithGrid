"""
AI Credential Service

Provides access to per-user AI provider API keys.
Extracted from routers/ai_credentials_router.py to avoid service→router imports.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption import decrypt_value, is_encrypted
from app.models import AIProviderCredential

logger = logging.getLogger(__name__)


async def get_user_api_key(
    db: AsyncSession,
    user_id: int,
    provider: str,
) -> Optional[str]:
    """
    Get API key for a provider from user's credentials ONLY (no system fallback).

    This is used for user-specific features like AI trading bots where users
    must provide their own API keys. System-wide keys are reserved for
    system-wide features like coin categorization.

    Args:
        db: Database session
        user_id: User ID to check credentials for
        provider: AI provider name (claude, gemini, grok, groq, openai)

    Returns:
        User's API key string if found and active, None otherwise
    """
    provider = provider.lower()

    # Check user's database credential only
    query = select(AIProviderCredential).where(
        AIProviderCredential.user_id == user_id,
        AIProviderCredential.provider == provider,
        AIProviderCredential.is_active.is_(True),
    )
    result = await db.execute(query)
    credential = result.scalar_one_or_none()

    if credential and credential.api_key:
        # Update last_used_at
        credential.last_used_at = datetime.utcnow()
        await db.commit()
        # Decrypt if encrypted
        api_key = credential.api_key
        if is_encrypted(api_key):
            api_key = decrypt_value(api_key)
        return api_key

    return None
