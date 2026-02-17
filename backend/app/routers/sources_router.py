"""
Content Sources Router

Manages news and video source subscriptions for users.
Users can subscribe/unsubscribe from sources to customize their feed.
System sources are provided by default; users can add custom sources.
Custom sources are limited to 10 per user and are deduplicated across users.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ContentSource, User, UserSourceSubscription
from app.routers.auth_dependencies import get_current_user
from app.services.domain_blacklist_service import domain_blacklist_service
from app.utils.url_utils import normalize_feed_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["sources"])

MAX_CUSTOM_SOURCES_PER_USER = 10


# =============================================================================
# Pydantic Models
# =============================================================================


class SourceResponse(BaseModel):
    """Response model for a content source."""
    id: int
    source_key: str
    name: str
    type: str  # "news" or "video"
    url: str
    website: Optional[str] = None
    description: Optional[str] = None
    channel_id: Optional[str] = None
    is_system: bool
    is_enabled: bool
    is_subscribed: bool = True
    category: str = "CryptoCurrency"
    user_category: Optional[str] = None
    retention_days: Optional[int] = None


class SourceListResponse(BaseModel):
    """Response model for list of sources."""
    sources: List[SourceResponse]
    total: int
    custom_source_count: int = 0
    max_custom_sources: int = MAX_CUSTOM_SOURCES_PER_USER


class SubscriptionResponse(BaseModel):
    """Response for subscription actions."""
    source_id: int
    is_subscribed: bool
    message: str


class AddSourceRequest(BaseModel):
    """Request to add a custom source."""
    source_key: str
    name: str
    type: str  # "news" or "video"
    url: str
    website: Optional[str] = None
    description: Optional[str] = None
    channel_id: Optional[str] = None
    category: Optional[str] = None


class SourceSettingsRequest(BaseModel):
    """Request to update per-user source settings."""
    user_category: Optional[str] = Field(
        None, description="Per-user category override (null to reset)"
    )
    retention_days: Optional[int] = Field(
        None, ge=1, le=90,
        description="Per-user visibility filter in days (null to reset)",
    )


# =============================================================================
# Helper Functions
# =============================================================================


async def get_user_subscription_status(
    db: AsyncSession,
    user_id: int,
    source_id: int
) -> Optional[bool]:
    """Get user's subscription status for a source."""
    result = await db.execute(
        select(UserSourceSubscription)
        .where(UserSourceSubscription.user_id == user_id)
        .where(UserSourceSubscription.source_id == source_id)
    )
    subscription = result.scalars().first()
    return subscription.is_subscribed if subscription else None


async def get_user_subscription(
    db: AsyncSession,
    user_id: int,
    source_id: int
) -> Optional[UserSourceSubscription]:
    """Get user's subscription record for a source."""
    result = await db.execute(
        select(UserSourceSubscription)
        .where(UserSourceSubscription.user_id == user_id)
        .where(UserSourceSubscription.source_id == source_id)
    )
    return result.scalars().first()


async def set_user_subscription(
    db: AsyncSession,
    user_id: int,
    source_id: int,
    is_subscribed: bool,
    user_category: Optional[str] = None,
) -> UserSourceSubscription:
    """Set or update user's subscription status for a source."""
    result = await db.execute(
        select(UserSourceSubscription)
        .where(UserSourceSubscription.user_id == user_id)
        .where(UserSourceSubscription.source_id == source_id)
    )
    subscription = result.scalars().first()

    if subscription:
        subscription.is_subscribed = is_subscribed
        if user_category is not None:
            subscription.user_category = user_category
    else:
        subscription = UserSourceSubscription(
            user_id=user_id,
            source_id=source_id,
            is_subscribed=is_subscribed,
            user_category=user_category,
        )
        db.add(subscription)

    await db.commit()
    await db.refresh(subscription)
    return subscription


async def count_user_custom_sources(
    db: AsyncSession, user_id: int
) -> int:
    """Count custom sources a user is subscribed to (owns or linked)."""
    result = await db.execute(
        select(func.count(UserSourceSubscription.id))
        .join(ContentSource)
        .where(
            UserSourceSubscription.user_id == user_id,
            UserSourceSubscription.is_subscribed.is_(True),
            ContentSource.is_system.is_(False),
        )
    )
    return result.scalar() or 0


async def _cleanup_orphan_source(
    db: AsyncSession, source: ContentSource
) -> bool:
    """Delete a custom source if no subscriptions remain.
    Returns True if source was deleted."""
    if source.is_system:
        return False
    sub_count_result = await db.execute(
        select(func.count(UserSourceSubscription.id)).where(
            UserSourceSubscription.source_id == source.id,
            UserSourceSubscription.is_subscribed.is_(True),
        )
    )
    if (sub_count_result.scalar() or 0) == 0:
        await db.delete(source)
        await db.commit()
        logger.info(f"Deleted orphan custom source: {source.name}")
        return True
    return False


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/", response_model=SourceListResponse)
async def list_sources(
    type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all available content sources with user's subscription status.

    Query params:
    - type: Filter by source type ("news" or "video")
    """
    query = select(ContentSource).where(ContentSource.is_enabled.is_(True))
    if type:
        query = query.where(ContentSource.type == type)
    query = query.order_by(ContentSource.type, ContentSource.name)

    result = await db.execute(query)
    sources = result.scalars().all()

    # Get user's subscriptions (includes user_category and retention_days)
    sub_result = await db.execute(
        select(UserSourceSubscription)
        .where(UserSourceSubscription.user_id == current_user.id)
    )
    subscriptions = {
        s.source_id: s for s in sub_result.scalars().all()
    }

    custom_count = await count_user_custom_sources(db, current_user.id)

    source_list = []
    for source in sources:
        sub = subscriptions.get(source.id)
        is_subscribed = sub.is_subscribed if sub else True
        user_cat = sub.user_category if sub else None
        ret_days = sub.retention_days if sub else None

        source_list.append(SourceResponse(
            id=source.id,
            source_key=source.source_key,
            name=source.name,
            type=source.type,
            url=source.url,
            website=source.website,
            description=source.description,
            channel_id=source.channel_id,
            is_system=source.is_system,
            is_enabled=source.is_enabled,
            is_subscribed=is_subscribed,
            category=getattr(source, 'category', 'CryptoCurrency'),
            user_category=user_cat,
            retention_days=ret_days,
        ))

    return SourceListResponse(
        sources=source_list,
        total=len(source_list),
        custom_source_count=custom_count,
        max_custom_sources=MAX_CUSTOM_SOURCES_PER_USER,
    )


@router.get("/subscribed", response_model=SourceListResponse)
async def list_subscribed_sources(
    type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List sources the user is subscribed to.

    Query params:
    - type: Filter by source type ("news" or "video")
    """
    query = select(ContentSource).where(ContentSource.is_enabled.is_(True))
    if type:
        query = query.where(ContentSource.type == type)

    result = await db.execute(query)
    sources = result.scalars().all()

    sub_result = await db.execute(
        select(UserSourceSubscription)
        .where(UserSourceSubscription.user_id == current_user.id)
    )
    subscriptions = {
        s.source_id: s for s in sub_result.scalars().all()
    }

    custom_count = await count_user_custom_sources(db, current_user.id)

    source_list = []
    for source in sources:
        sub = subscriptions.get(source.id)
        # Unsubscribed if explicit False
        if sub and not sub.is_subscribed:
            continue
        user_cat = sub.user_category if sub else None
        ret_days = sub.retention_days if sub else None

        source_list.append(SourceResponse(
            id=source.id,
            source_key=source.source_key,
            name=source.name,
            type=source.type,
            url=source.url,
            website=source.website,
            description=source.description,
            channel_id=source.channel_id,
            is_system=source.is_system,
            is_enabled=source.is_enabled,
            is_subscribed=True,
            category=getattr(source, 'category', 'CryptoCurrency'),
            user_category=user_cat,
            retention_days=ret_days,
        ))

    return SourceListResponse(
        sources=source_list,
        total=len(source_list),
        custom_source_count=custom_count,
        max_custom_sources=MAX_CUSTOM_SOURCES_PER_USER,
    )


@router.post("/{source_id}/subscribe", response_model=SubscriptionResponse)
async def subscribe_to_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Subscribe to a content source."""
    result = await db.execute(
        select(ContentSource).where(ContentSource.id == source_id)
    )
    source = result.scalars().first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await set_user_subscription(db, current_user.id, source_id, True)
    logger.info(f"User {current_user.id} subscribed to source {source.name}")

    return SubscriptionResponse(
        source_id=source_id,
        is_subscribed=True,
        message=f"Subscribed to {source.name}"
    )


@router.post("/{source_id}/unsubscribe", response_model=SubscriptionResponse)
async def unsubscribe_from_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Unsubscribe from a content source."""
    result = await db.execute(
        select(ContentSource).where(ContentSource.id == source_id)
    )
    source = result.scalars().first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await set_user_subscription(db, current_user.id, source_id, False)
    logger.info(
        f"User {current_user.id} unsubscribed from source {source.name}"
    )

    return SubscriptionResponse(
        source_id=source_id,
        is_subscribed=False,
        message=f"Unsubscribed from {source.name}"
    )


@router.post("/add", response_model=SourceResponse)
async def add_custom_source(
    request: AddSourceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a custom content source.

    - Limited to 10 custom sources per user.
    - Deduplicates by normalized URL across all users.
    - If a system source matches the URL, directs user to subscribe instead.
    """
    # Validate type
    if request.type not in ("news", "video"):
        raise HTTPException(
            status_code=400, detail="Type must be 'news' or 'video'"
        )

    # Require channel_id for video sources
    if request.type == "video" and not request.channel_id:
        raise HTTPException(
            status_code=400,
            detail="channel_id required for video sources",
        )

    # Check custom source limit
    custom_count = await count_user_custom_sources(db, current_user.id)
    if custom_count >= MAX_CUSTOM_SOURCES_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Custom source limit reached "
                f"({MAX_CUSTOM_SOURCES_PER_USER}). "
                f"Remove a source before adding a new one."
            ),
        )

    # Normalize URL for dedup
    normalized_url = normalize_feed_url(request.url)

    # Check domain blacklist (harmful/inappropriate content)
    blocked, matched = domain_blacklist_service.is_domain_blocked(request.url)
    if blocked:
        raise HTTPException(
            status_code=403,
            detail=(
                "This URL's domain has been flagged as hosting potentially "
                "harmful or inappropriate content and cannot be added "
                "as a content source."
            ),
        )

    # Check for system source URL match
    sys_result = await db.execute(
        select(ContentSource).where(ContentSource.is_system.is_(True))
    )
    for sys_source in sys_result.scalars().all():
        if normalize_feed_url(sys_source.url) == normalized_url:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This URL matches system source '{sys_source.name}'. "
                    f"Subscribe to it instead (ID: {sys_source.id})."
                ),
            )

    # Check for existing custom source with same normalized URL
    custom_result = await db.execute(
        select(ContentSource).where(ContentSource.is_system.is_(False))
    )
    existing_custom = None
    for cs in custom_result.scalars().all():
        if normalize_feed_url(cs.url) == normalized_url:
            existing_custom = cs
            break

    if existing_custom:
        # Link user to existing source via subscription
        sub = await get_user_subscription(
            db, current_user.id, existing_custom.id
        )
        if sub and sub.is_subscribed:
            raise HTTPException(
                status_code=400,
                detail=f"Already subscribed to '{existing_custom.name}'",
            )
        await set_user_subscription(
            db, current_user.id, existing_custom.id, True,
            user_category=request.category,
        )
        logger.info(
            f"User {current_user.id} linked to existing custom source: "
            f"{existing_custom.name}"
        )
        return SourceResponse(
            id=existing_custom.id,
            source_key=existing_custom.source_key,
            name=existing_custom.name,
            type=existing_custom.type,
            url=existing_custom.url,
            website=existing_custom.website,
            description=existing_custom.description,
            channel_id=existing_custom.channel_id,
            is_system=existing_custom.is_system,
            is_enabled=existing_custom.is_enabled,
            is_subscribed=True,
            category=getattr(
                existing_custom, 'category', 'CryptoCurrency'
            ),
            user_category=request.category,
        )

    # Check if source_key already exists
    result = await db.execute(
        select(ContentSource)
        .where(ContentSource.source_key == request.source_key)
    )
    if result.scalars().first():
        raise HTTPException(
            status_code=400, detail="Source key already exists"
        )

    # Create new custom source
    source = ContentSource(
        source_key=request.source_key,
        name=request.name,
        type=request.type,
        url=request.url,
        website=request.website,
        description=request.description,
        channel_id=request.channel_id,
        is_system=False,
        is_enabled=True,
        category=request.category or "CryptoCurrency",
        user_id=current_user.id,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    # Auto-subscribe user with their category
    await set_user_subscription(
        db, current_user.id, source.id, True,
        user_category=request.category,
    )

    logger.info(
        f"User {current_user.id} added custom source: {source.name}"
    )

    return SourceResponse(
        id=source.id,
        source_key=source.source_key,
        name=source.name,
        type=source.type,
        url=source.url,
        website=source.website,
        description=source.description,
        channel_id=source.channel_id,
        is_system=source.is_system,
        is_enabled=source.is_enabled,
        is_subscribed=True,
        category=getattr(source, 'category', 'CryptoCurrency'),
        user_category=request.category,
    )


@router.delete("/{source_id}")
async def delete_custom_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove user's subscription to a custom source.

    If no other users are subscribed, the source and its content are deleted.
    System sources cannot be deleted this way — use unsubscribe instead.
    """
    result = await db.execute(
        select(ContentSource).where(ContentSource.id == source_id)
    )
    source = result.scalars().first()

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if source.is_system:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete system sources. Use unsubscribe instead.",
        )

    # Remove this user's subscription
    sub = await get_user_subscription(db, current_user.id, source_id)
    if sub:
        sub.is_subscribed = False
        await db.commit()

    source_name = source.name

    # If no active subscriptions remain, delete source + content
    deleted = await _cleanup_orphan_source(db, source)

    if deleted:
        msg = f"Deleted source and content: {source_name}"
    else:
        msg = f"Unsubscribed from {source_name} (other users still subscribed)"

    logger.info(f"User {current_user.id} removed custom source: {source_name}")
    return {"message": msg}


@router.put("/{source_id}/settings")
async def update_source_settings(
    source_id: int,
    request: SourceSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update per-user settings for a source (category override, retention).

    Works for both system and custom sources.
    """
    # Verify source exists
    result = await db.execute(
        select(ContentSource).where(ContentSource.id == source_id)
    )
    source = result.scalars().first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Get or create subscription record
    sub = await get_user_subscription(db, current_user.id, source_id)
    if not sub:
        sub = UserSourceSubscription(
            user_id=current_user.id,
            source_id=source_id,
            is_subscribed=True,
        )
        db.add(sub)
        await db.flush()

    # Update fields (explicit None means "reset to default")
    if "user_category" in request.model_fields_set:
        sub.user_category = request.user_category
    if "retention_days" in request.model_fields_set:
        sub.retention_days = request.retention_days

    await db.commit()
    await db.refresh(sub)

    return {
        "source_id": source_id,
        "user_category": sub.user_category,
        "retention_days": sub.retention_days,
        "message": f"Updated settings for {source.name}",
    }
