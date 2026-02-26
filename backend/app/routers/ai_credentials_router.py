"""
AI Provider Credentials API routes

Handles CRUD operations for per-user AI provider API keys:
- Claude (Anthropic)
- Gemini (Google)
- Grok (xAI)
- Groq (Llama models)
- OpenAI (GPT)

Each user can store their own API keys for AI providers.
The .env file keys remain as system-wide fallback for services like
news analysis and coin categorization.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.exceptions import AppError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.encryption import encrypt_value, decrypt_value, is_encrypted
from app.models import AIProviderCredential, User
from app.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-credentials", tags=["ai-credentials"])

# Valid AI providers
VALID_PROVIDERS = ["claude", "gemini", "grok", "groq", "openai"]


# =============================================================================
# Pydantic Models
# =============================================================================


class AICredentialCreate(BaseModel):
    """Model for creating/updating an AI credential"""
    provider: str = Field(..., description="AI provider: claude, gemini, grok, groq, openai")
    api_key: str = Field(..., description="API key for the provider")


class AICredentialUpdate(BaseModel):
    """Model for updating an AI credential"""
    api_key: Optional[str] = Field(None, description="New API key (if changing)")
    is_active: Optional[bool] = Field(None, description="Enable/disable this credential")


class AICredentialResponse(BaseModel):
    """Response model for AI credential data (never returns full API key)"""
    id: int
    provider: str
    is_active: bool
    has_api_key: bool  # True if API key is set
    api_key_preview: str  # Shows only last 4 chars like "...abc1234"
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AIProviderStatus(BaseModel):
    """Status of an AI provider including both user and system keys"""
    provider: str
    name: str
    billing_url: str
    has_user_key: bool  # User has their own key
    has_system_key: bool  # System-wide key in .env
    is_active: bool  # User's key is active (if they have one)
    free_tier: Optional[str] = None  # Free tier info if applicable


def _api_key_preview(api_key: str) -> str:
    """Get a safe preview of an API key (last 8 chars of plaintext)."""
    if not api_key:
        return "..."
    plaintext = decrypt_value(api_key) if is_encrypted(api_key) else api_key
    return f"...{plaintext[-8:]}" if len(plaintext) > 8 else "..."


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("", response_model=List[AICredentialResponse])
async def list_ai_credentials(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all AI credentials for the current user.

    Returns credentials for all providers that the user has configured.
    API keys are masked for security (only last 4 chars shown).
    """
    try:
        query = select(AIProviderCredential)
        query = query.where(AIProviderCredential.user_id == current_user.id)
        query = query.order_by(AIProviderCredential.provider)

        result = await db.execute(query)
        credentials = result.scalars().all()

        return [
            AICredentialResponse(
                id=cred.id,
                provider=cred.provider,
                is_active=cred.is_active,
                has_api_key=bool(cred.api_key),
                api_key_preview=_api_key_preview(cred.api_key),
                created_at=cred.created_at,
                updated_at=cred.updated_at,
                last_used_at=cred.last_used_at,
            )
            for cred in credentials
        ]

    except Exception as e:
        logger.error(f"Error listing AI credentials: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/status", response_model=List[AIProviderStatus])
async def get_ai_providers_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get status of all AI providers, showing both user and system keys.

    This endpoint helps users understand which providers are available
    and whether they're using their own key or the system fallback.
    """
    from app.config import settings

    # Provider info
    providers_info = {
        "claude": {
            "name": "Anthropic (Claude)",
            "billing_url": "https://console.anthropic.com/settings/usage",
            "system_key": settings.anthropic_api_key,
            "free_tier": None,
        },
        "gemini": {
            "name": "Google Gemini",
            "billing_url": "https://aistudio.google.com/app/apikey",
            "system_key": settings.gemini_api_key,
            "free_tier": None,
        },
        "grok": {
            "name": "xAI (Grok)",
            "billing_url": "https://console.x.ai/",
            "system_key": settings.grok_api_key,
            "free_tier": None,
        },
        "groq": {
            "name": "Groq (Llama 3.1 70B)",
            "billing_url": "https://console.groq.com/keys",
            "system_key": settings.groq_api_key,
            "free_tier": "14,400 RPD",
        },
        "openai": {
            "name": "OpenAI (GPT)",
            "billing_url": "https://platform.openai.com/usage",
            "system_key": settings.openai_api_key,
            "free_tier": None,
        },
    }

    # Get user's credentials
    user_credentials = {}
    query = select(AIProviderCredential).where(
        AIProviderCredential.user_id == current_user.id
    )
    result = await db.execute(query)
    for cred in result.scalars().all():
        user_credentials[cred.provider] = cred

    # Build status for each provider
    status_list = []
    for provider, info in providers_info.items():
        user_cred = user_credentials.get(provider)
        status_list.append(AIProviderStatus(
            provider=provider,
            name=info["name"],
            billing_url=info["billing_url"],
            has_user_key=bool(user_cred and user_cred.api_key),
            has_system_key=bool(info["system_key"]),
            is_active=user_cred.is_active if user_cred else False,
            free_tier=info.get("free_tier"),
        ))

    return status_list


@router.post("", response_model=AICredentialResponse)
async def create_or_update_ai_credential(
    credential_data: AICredentialCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create or update an AI credential for the current user.

    If a credential for this provider already exists, it will be updated.
    Otherwise, a new credential is created.
    """
    try:
        # Validate provider
        provider = credential_data.provider.lower()
        if provider not in VALID_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider '{provider}'. Must be one of: {', '.join(VALID_PROVIDERS)}"
            )

        # Check for existing credential
        query = select(AIProviderCredential).where(
            AIProviderCredential.user_id == current_user.id,
            AIProviderCredential.provider == provider
        )
        result = await db.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing
            existing.api_key = encrypt_value(credential_data.api_key)
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
            credential = existing
            logger.info(f"Updated AI credential for user {current_user.id}: {provider}")
        else:
            # Create new
            credential = AIProviderCredential(
                user_id=current_user.id,
                provider=provider,
                api_key=encrypt_value(credential_data.api_key),
                is_active=True,
            )
            db.add(credential)
            logger.info(f"Created AI credential for user {current_user.id}: {provider}")

        await db.commit()
        await db.refresh(credential)

        return AICredentialResponse(
            id=credential.id,
            provider=credential.provider,
            is_active=credential.is_active,
            has_api_key=bool(credential.api_key),
            api_key_preview=_api_key_preview(credential.api_key),
            created_at=credential.created_at,
            updated_at=credential.updated_at,
            last_used_at=credential.last_used_at,
        )

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error creating/updating AI credential: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/{provider}", response_model=AICredentialResponse)
async def get_ai_credential(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific AI credential by provider name."""
    try:
        provider = provider.lower()
        if provider not in VALID_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider '{provider}'. Must be one of: {', '.join(VALID_PROVIDERS)}"
            )

        query = select(AIProviderCredential).where(
            AIProviderCredential.user_id == current_user.id,
            AIProviderCredential.provider == provider
        )
        result = await db.execute(query)
        credential = result.scalar_one_or_none()

        if not credential:
            raise HTTPException(
                status_code=404,
                detail=f"No credential found for provider '{provider}'"
            )

        return AICredentialResponse(
            id=credential.id,
            provider=credential.provider,
            is_active=credential.is_active,
            has_api_key=bool(credential.api_key),
            api_key_preview=_api_key_preview(credential.api_key),
            created_at=credential.created_at,
            updated_at=credential.updated_at,
            last_used_at=credential.last_used_at,
        )

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error getting AI credential for {provider}: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.put("/{provider}", response_model=AICredentialResponse)
async def update_ai_credential(
    provider: str,
    credential_data: AICredentialUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing AI credential."""
    try:
        provider = provider.lower()
        if provider not in VALID_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider '{provider}'. Must be one of: {', '.join(VALID_PROVIDERS)}"
            )

        query = select(AIProviderCredential).where(
            AIProviderCredential.user_id == current_user.id,
            AIProviderCredential.provider == provider
        )
        result = await db.execute(query)
        credential = result.scalar_one_or_none()

        if not credential:
            raise HTTPException(
                status_code=404,
                detail=f"No credential found for provider '{provider}'"
            )

        # Update fields
        if credential_data.api_key is not None:
            credential.api_key = encrypt_value(credential_data.api_key)
        if credential_data.is_active is not None:
            credential.is_active = credential_data.is_active

        credential.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(credential)

        logger.info(f"Updated AI credential for user {current_user.id}: {provider}")

        return AICredentialResponse(
            id=credential.id,
            provider=credential.provider,
            is_active=credential.is_active,
            has_api_key=bool(credential.api_key),
            api_key_preview=_api_key_preview(credential.api_key),
            created_at=credential.created_at,
            updated_at=credential.updated_at,
            last_used_at=credential.last_used_at,
        )

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error updating AI credential for {provider}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.delete("/{provider}")
async def delete_ai_credential(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an AI credential."""
    try:
        provider = provider.lower()
        if provider not in VALID_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider '{provider}'. Must be one of: {', '.join(VALID_PROVIDERS)}"
            )

        query = select(AIProviderCredential).where(
            AIProviderCredential.user_id == current_user.id,
            AIProviderCredential.provider == provider
        )
        result = await db.execute(query)
        credential = result.scalar_one_or_none()

        if not credential:
            raise HTTPException(
                status_code=404,
                detail=f"No credential found for provider '{provider}'"
            )

        await db.delete(credential)
        await db.commit()

        logger.info(f"Deleted AI credential for user {current_user.id}: {provider}")

        return {"message": f"AI credential for '{provider}' deleted successfully"}

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error deleting AI credential for {provider}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")
