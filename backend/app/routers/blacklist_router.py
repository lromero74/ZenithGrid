"""
Blacklist Router

Handles coin blacklist management:
- List all blacklisted coins
- Add coins to blacklist
- Remove coins from blacklist
- Update blacklist entry reasons
- Category trading settings (which categories can trade)
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import BlacklistedCoin, Settings, User
from app.auth.dependencies import get_current_user, require_superuser
from app.services.settings_service import (
    ALLOWED_CATEGORIES_KEY,
    get_allowed_categories,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/blacklist", tags=["blacklist"])

# Valid coin categories
VALID_CATEGORIES = ["APPROVED", "BORDERLINE", "QUESTIONABLE", "BLACKLISTED"]
# AI Provider settings
VALID_AI_PROVIDERS = ["claude", "openai", "gemini", "grok"]
DEFAULT_AI_PROVIDER = "claude"
AI_REVIEW_PROVIDER_KEY = "ai_review_provider"


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


# Pydantic schemas for blacklist operations
class BlacklistEntry(BaseModel):
    """Response model for a blacklisted coin"""

    id: int
    symbol: str
    reason: Optional[str] = None
    created_at: str
    is_global: bool = False  # True if this is an AI-generated global entry
    user_override_category: Optional[str] = None  # Non-null if current user has an override

    class Config:
        from_attributes = True


class BlacklistAddRequest(BaseModel):
    """Request model for adding coins to blacklist"""

    symbols: List[str]  # Can add multiple at once
    reason: Optional[str] = None  # Optional reason (same for all if bulk adding)


class BlacklistAddSingleRequest(BaseModel):
    """Request model for adding a single coin with specific reason"""

    symbol: str
    reason: Optional[str] = None


class BlacklistUpdateRequest(BaseModel):
    """Request model for updating a blacklist entry's reason"""

    reason: Optional[str] = None


# ============================================================================
# Category Trading Settings (MUST be before /{symbol} routes to avoid conflicts)
# ============================================================================

class UserOverrideRequest(BaseModel):
    """Request model for creating/updating a per-user category override"""
    category: str  # APPROVED, BORDERLINE, QUESTIONABLE, BLACKLISTED
    reason: Optional[str] = None


class UserOverrideResponse(BaseModel):
    """Response model for a user override"""
    symbol: str
    category: str
    reason: Optional[str] = None


class CategorySettingsRequest(BaseModel):
    """Request model for updating allowed categories"""
    allowed_categories: List[str]


class CategorySettingsResponse(BaseModel):
    """Response model for category settings"""
    allowed_categories: List[str]
    all_categories: List[str] = VALID_CATEGORIES


async def get_ai_review_provider(db: AsyncSession) -> str:
    """Get configured AI provider for coin review from database."""
    query = select(Settings).where(Settings.key == AI_REVIEW_PROVIDER_KEY)
    result = await db.execute(query)
    setting = result.scalars().first()

    if setting and setting.value and setting.value.lower() in VALID_AI_PROVIDERS:
        return setting.value.lower()

    return DEFAULT_AI_PROVIDER


@router.get("/categories", response_model=CategorySettingsResponse)
async def get_category_settings(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get current category trading settings.

    Returns which categories are allowed to open new positions.
    """
    allowed = await get_allowed_categories(db)

    return CategorySettingsResponse(
        allowed_categories=allowed,
        all_categories=VALID_CATEGORIES,
    )


@router.put("/categories", response_model=CategorySettingsResponse)
async def update_category_settings(
    request: CategorySettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_superuser)
):
    """
    Update which categories are allowed to trade.

    Categories: APPROVED, BORDERLINE, QUESTIONABLE, BLACKLISTED
    """
    # Validate categories
    invalid = [c for c in request.allowed_categories if c.upper() not in VALID_CATEGORIES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid categories: {invalid}. Valid: {VALID_CATEGORIES}"
        )

    # Normalize to uppercase
    allowed = [c.upper() for c in request.allowed_categories]

    # Update or create setting
    query = select(Settings).where(Settings.key == ALLOWED_CATEGORIES_KEY)
    result = await db.execute(query)
    setting = result.scalars().first()

    if setting:
        setting.value = json.dumps(allowed)
        setting.value_type = "json"
    else:
        setting = Settings(
            key=ALLOWED_CATEGORIES_KEY,
            value=json.dumps(allowed),
            value_type="json",
            description="Categories of coins allowed to open new positions"
        )
        db.add(setting)

    await db.commit()

    logger.info(f"Updated allowed coin categories: {allowed}")

    return CategorySettingsResponse(
        allowed_categories=allowed,
        all_categories=VALID_CATEGORIES,
    )


# ============================================================================
# AI Provider Settings for Coin Review
# ============================================================================

class AIProviderSettingsRequest(BaseModel):
    """Request model for updating AI review provider"""
    provider: str


class AIProviderSettingsResponse(BaseModel):
    """Response model for AI provider settings"""
    provider: str
    available_providers: List[str] = VALID_AI_PROVIDERS


@router.get("/ai-provider", response_model=AIProviderSettingsResponse)
async def get_ai_provider_setting(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get current AI provider for coin review.

    Returns which AI provider will be used for the AI coin review feature.
    Only returns providers that have API keys configured.
    """
    configured_providers = get_configured_ai_providers()
    provider = await get_ai_review_provider(db)

    # If current provider isn't configured, default to first configured one
    if provider not in configured_providers and configured_providers:
        provider = configured_providers[0]

    return AIProviderSettingsResponse(
        provider=provider,
        available_providers=configured_providers,
    )


@router.put("/ai-provider", response_model=AIProviderSettingsResponse)
async def update_ai_provider_setting(
    request: AIProviderSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_superuser)
):
    """
    Update which AI provider to use for coin review.

    Only providers with configured API keys are available.
    Admin only.
    """
    configured_providers = get_configured_ai_providers()

    # Validate provider is configured
    provider = request.provider.lower()
    if provider not in configured_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{provider}' is not configured. Available: {configured_providers}"
        )

    # Update or create setting
    query = select(Settings).where(Settings.key == AI_REVIEW_PROVIDER_KEY)
    result = await db.execute(query)
    setting = result.scalars().first()

    if setting:
        setting.value = provider
        setting.value_type = "string"
    else:
        setting = Settings(
            key=AI_REVIEW_PROVIDER_KEY,
            value=provider,
            value_type="string",
            description="AI provider for coin review (claude, openai, gemini, grok)"
        )
        db.add(setting)

    await db.commit()

    logger.info(f"Updated AI review provider: {provider}")

    return AIProviderSettingsResponse(
        provider=provider,
        available_providers=configured_providers,
    )


# ============================================================================
# Per-User Category Overrides
# ============================================================================


def _extract_category(reason: Optional[str]) -> str:
    """Extract category from reason prefix."""
    if not reason:
        return "BLACKLISTED"
    for cat in VALID_CATEGORIES:
        if reason.startswith(f"[{cat}]"):
            return cat
    return "BLACKLISTED"


@router.get("/overrides/", response_model=List[UserOverrideResponse])
async def list_user_overrides(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all category overrides for the current user."""
    query = select(BlacklistedCoin).where(
        BlacklistedCoin.user_id == current_user.id
    ).order_by(BlacklistedCoin.symbol)
    result = await db.execute(query)
    overrides = result.scalars().all()

    return [
        UserOverrideResponse(
            symbol=o.symbol,
            category=_extract_category(o.reason),
            reason=o.reason.split("] ", 1)[1] if o.reason and "] " in o.reason else o.reason,
        )
        for o in overrides
    ]


@router.put("/overrides/{symbol}", response_model=UserOverrideResponse)
async def set_user_override(
    symbol: str,
    request: UserOverrideRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create or update a per-user category override for a coin."""
    normalized_symbol = symbol.upper().strip()
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="Symbol cannot be empty")

    category = request.category.upper()
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category: {category}. Valid: {VALID_CATEGORIES}",
        )

    # Build reason with category prefix
    reason_text = request.reason or "User override"
    full_reason = f"[{category}] {reason_text}"

    # Check for existing user override
    query = select(BlacklistedCoin).where(
        BlacklistedCoin.symbol == normalized_symbol,
        BlacklistedCoin.user_id == current_user.id,
    )
    result = await db.execute(query)
    existing = result.scalars().first()

    if existing:
        existing.reason = full_reason
    else:
        entry = BlacklistedCoin(
            symbol=normalized_symbol,
            reason=full_reason,
            user_id=current_user.id,
        )
        db.add(entry)

    await db.commit()
    logger.info(f"User {current_user.id} set override for {normalized_symbol}: {category}")

    return UserOverrideResponse(
        symbol=normalized_symbol,
        category=category,
        reason=reason_text,
    )


@router.delete("/overrides/{symbol}")
async def remove_user_override(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a per-user category override (revert to global category)."""
    normalized_symbol = symbol.upper().strip()

    query = select(BlacklistedCoin).where(
        BlacklistedCoin.symbol == normalized_symbol,
        BlacklistedCoin.user_id == current_user.id,
    )
    result = await db.execute(query)
    entry = result.scalars().first()

    if not entry:
        raise HTTPException(status_code=404, detail=f"No override found for {normalized_symbol}")

    await db.delete(entry)
    await db.commit()
    logger.info(f"User {current_user.id} removed override for {normalized_symbol}")

    return {"message": f"Override removed for {normalized_symbol}, reverted to global category"}


# ============================================================================
# Blacklist CRUD Operations
# ============================================================================

@router.get("/", response_model=List[BlacklistEntry])
async def list_blacklisted_coins(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all coin categorizations.

    Returns global AI-generated entries (visible to all users).
    Includes user_override_category if the current user has an override for that coin.
    """
    # Show global entries (user_id IS NULL) to everyone
    query = select(BlacklistedCoin).where(
        BlacklistedCoin.user_id.is_(None)
    ).order_by(BlacklistedCoin.symbol)

    result = await db.execute(query)
    coins = result.scalars().all()

    # Fetch current user's overrides to annotate entries
    override_query = select(BlacklistedCoin).where(
        BlacklistedCoin.user_id == current_user.id
    )
    override_result = await db.execute(override_query)
    user_overrides = {o.symbol: _extract_category(o.reason) for o in override_result.scalars().all()}

    return [
        BlacklistEntry(
            id=coin.id,
            symbol=coin.symbol,
            reason=coin.reason,
            created_at=coin.created_at.isoformat() if coin.created_at else "",
            is_global=True,
            user_override_category=user_overrides.get(coin.symbol),
        )
        for coin in coins
    ]


@router.post("/", response_model=List[BlacklistEntry], status_code=201)
async def add_to_blacklist(
    request: BlacklistAddRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_superuser)
):
    """
    Add one or more coins to the global categorization list.

    Admin only - regular users cannot modify coin categories.
    """
    added_entries = []

    for symbol in request.symbols:
        # Normalize symbol to uppercase
        normalized_symbol = symbol.upper().strip()

        if not normalized_symbol:
            continue

        # Check if already exists in global entries
        existing_query = select(BlacklistedCoin).where(
            BlacklistedCoin.symbol == normalized_symbol,
            BlacklistedCoin.user_id.is_(None)
        )
        existing_result = await db.execute(existing_query)
        if existing_result.scalars().first():
            logger.info(f"Symbol {normalized_symbol} already categorized, skipping")
            continue

        # Add to global categorization (user_id = None)
        entry = BlacklistedCoin(
            symbol=normalized_symbol,
            reason=request.reason,
            user_id=None  # Global entry
        )
        db.add(entry)
        await db.flush()  # Get the ID without committing

        added_entries.append(
            BlacklistEntry(
                id=entry.id,
                symbol=entry.symbol,
                reason=entry.reason,
                created_at=entry.created_at.isoformat() if entry.created_at else "",
                is_global=True,
            )
        )
        logger.info(f"Added {normalized_symbol} to categorization: {request.reason}")

    await db.commit()

    return added_entries


@router.post("/single", response_model=BlacklistEntry, status_code=201)
async def add_single_to_blacklist(
    request: BlacklistAddSingleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_superuser)
):
    """
    Add a single coin to the global categorization with its own reason.

    Admin only - regular users cannot modify coin categories.
    """
    # Normalize symbol to uppercase
    normalized_symbol = request.symbol.upper().strip()

    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="Symbol cannot be empty")

    # Check if already exists in global entries
    existing_query = select(BlacklistedCoin).where(
        BlacklistedCoin.symbol == normalized_symbol,
        BlacklistedCoin.user_id.is_(None)
    )
    existing_result = await db.execute(existing_query)
    if existing_result.scalars().first():
        raise HTTPException(status_code=409, detail=f"{normalized_symbol} is already categorized")

    # Add to global categorization (user_id = None)
    entry = BlacklistedCoin(
        symbol=normalized_symbol,
        reason=request.reason,
        user_id=None  # Global entry
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    logger.info(f"Added {normalized_symbol} to categorization: {request.reason}")

    return BlacklistEntry(
        id=entry.id,
        symbol=entry.symbol,
        reason=entry.reason,
        created_at=entry.created_at.isoformat() if entry.created_at else "",
        is_global=True,
    )


@router.delete("/{symbol}")
async def remove_from_blacklist(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_superuser)
):
    """
    Remove a coin from the global categorization list.

    Admin only - regular users cannot modify coin categories.
    """
    normalized_symbol = symbol.upper().strip()

    # Only look at global entries (user_id IS NULL)
    query = select(BlacklistedCoin).where(
        BlacklistedCoin.symbol == normalized_symbol,
        BlacklistedCoin.user_id.is_(None)
    )
    result = await db.execute(query)
    entry = result.scalars().first()

    if not entry:
        raise HTTPException(status_code=404, detail=f"{normalized_symbol} is not categorized")

    await db.delete(entry)
    await db.commit()

    logger.info(f"Removed {normalized_symbol} from categorization")

    return {"message": f"{normalized_symbol} removed from categorization"}


@router.put("/{symbol}", response_model=BlacklistEntry)
async def update_blacklist_reason(
    symbol: str,
    request: BlacklistUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_superuser)
):
    """
    Update the category/reason for a coin.

    Admin only - regular users cannot modify coin categories.
    """
    normalized_symbol = symbol.upper().strip()

    # Only look at global entries (user_id IS NULL)
    query = select(BlacklistedCoin).where(
        BlacklistedCoin.symbol == normalized_symbol,
        BlacklistedCoin.user_id.is_(None)
    )
    result = await db.execute(query)
    entry = result.scalars().first()

    if not entry:
        raise HTTPException(status_code=404, detail=f"{normalized_symbol} is not categorized")

    entry.reason = request.reason
    await db.commit()
    await db.refresh(entry)

    logger.info(f"Updated category for {normalized_symbol}: {request.reason}")

    return BlacklistEntry(
        id=entry.id,
        symbol=entry.symbol,
        reason=entry.reason,
        created_at=entry.created_at.isoformat() if entry.created_at else "",
        is_global=True,
    )


@router.get("/check/{symbol}")
async def check_if_blacklisted(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check if a specific coin is categorized and get its category.

    Returns the global AI-generated categorization for the coin.
    """
    normalized_symbol = symbol.upper().strip()

    # Only look at global entries (user_id IS NULL)
    query = select(BlacklistedCoin).where(
        BlacklistedCoin.symbol == normalized_symbol,
        BlacklistedCoin.user_id.is_(None)
    )
    result = await db.execute(query)
    entry = result.scalars().first()

    # Parse category from reason prefix
    category = None
    if entry and entry.reason:
        for cat in ["APPROVED", "BORDERLINE", "QUESTIONABLE", "BLACKLISTED"]:
            if entry.reason.startswith(f"[{cat}]"):
                category = cat
                break
        if not category:
            # No prefix means BLACKLISTED
            category = "BLACKLISTED"

    return {
        "symbol": normalized_symbol,
        "is_categorized": entry is not None,
        "category": category,
        "reason": entry.reason if entry else None,
    }


@router.post("/ai-review")
async def trigger_ai_review(
    current_user: User = Depends(require_superuser)
):
    """
    Trigger an AI-powered review of all tracked coins.

    Admin only - uses configured AI provider to analyze each coin
    and update global categorizations.
    """
    from app.services.coin_review_service import run_weekly_review

    logger.info(f"Manual AI coin review triggered by admin user {current_user.email}")
    result = await run_weekly_review()

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Review failed"))

    return result
