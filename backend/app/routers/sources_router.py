"""
Content Sources Router

Manages news and video source subscriptions for users.
Users can subscribe/unsubscribe from sources to customize their feed.
System sources are provided by default; users can add custom sources.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ContentSource, User, UserSourceSubscription
from app.routers.auth_dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["sources"])


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
    is_subscribed: bool = True  # Default to subscribed if no preference set
    category: str = "CryptoCurrency"


class SourceListResponse(BaseModel):
    """Response model for list of sources."""
    sources: List[SourceResponse]
    total: int


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
    channel_id: Optional[str] = None  # Required for video sources


# =============================================================================
# Helper Functions
# =============================================================================


async def get_user_subscription_status(
    db: AsyncSession,
    user_id: int,
    source_id: int
) -> Optional[bool]:
    """Get user's subscription status for a source. Returns None if no preference."""
    result = await db.execute(
        select(UserSourceSubscription)
        .where(UserSourceSubscription.user_id == user_id)
        .where(UserSourceSubscription.source_id == source_id)
    )
    subscription = result.scalars().first()
    return subscription.is_subscribed if subscription else None


async def set_user_subscription(
    db: AsyncSession,
    user_id: int,
    source_id: int,
    is_subscribed: bool
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
    else:
        subscription = UserSourceSubscription(
            user_id=user_id,
            source_id=source_id,
            is_subscribed=is_subscribed
        )
        db.add(subscription)

    await db.commit()
    await db.refresh(subscription)
    return subscription


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
    # Build query for sources
    query = select(ContentSource).where(ContentSource.is_enabled.is_(True))
    if type:
        query = query.where(ContentSource.type == type)
    query = query.order_by(ContentSource.type, ContentSource.name)

    result = await db.execute(query)
    sources = result.scalars().all()

    # Get user's subscriptions
    sub_result = await db.execute(
        select(UserSourceSubscription)
        .where(UserSourceSubscription.user_id == current_user.id)
    )
    subscriptions = {s.source_id: s.is_subscribed for s in sub_result.scalars().all()}

    # Build response with subscription status
    source_list = []
    for source in sources:
        # Default to subscribed if no explicit preference
        is_subscribed = subscriptions.get(source.id, True)
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
        ))

    return SourceListResponse(sources=source_list, total=len(source_list))


@router.get("/subscribed", response_model=SourceListResponse)
async def list_subscribed_sources(
    type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List sources the user is subscribed to (for fetching content).

    Query params:
    - type: Filter by source type ("news" or "video")
    """
    # Build query for enabled sources
    query = select(ContentSource).where(ContentSource.is_enabled.is_(True))
    if type:
        query = query.where(ContentSource.type == type)

    result = await db.execute(query)
    sources = result.scalars().all()

    # Get user's unsubscribed sources
    sub_result = await db.execute(
        select(UserSourceSubscription)
        .where(UserSourceSubscription.user_id == current_user.id)
        .where(UserSourceSubscription.is_subscribed.is_(False))
    )
    unsubscribed_ids = {s.source_id for s in sub_result.scalars().all()}

    # Filter to only subscribed sources
    subscribed_sources = [s for s in sources if s.id not in unsubscribed_ids]

    source_list = [
        SourceResponse(
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
        )
        for source in subscribed_sources
    ]

    return SourceListResponse(sources=source_list, total=len(source_list))


@router.post("/{source_id}/subscribe", response_model=SubscriptionResponse)
async def subscribe_to_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Subscribe to a content source."""
    # Verify source exists
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
    # Verify source exists
    result = await db.execute(
        select(ContentSource).where(ContentSource.id == source_id)
    )
    source = result.scalars().first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await set_user_subscription(db, current_user.id, source_id, False)
    logger.info(f"User {current_user.id} unsubscribed from source {source.name}")

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

    Custom sources are user-created and can be deleted by the user.
    """
    # Validate type
    if request.type not in ("news", "video"):
        raise HTTPException(status_code=400, detail="Type must be 'news' or 'video'")

    # Check if source_key already exists
    result = await db.execute(
        select(ContentSource).where(ContentSource.source_key == request.source_key)
    )
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Source key already exists")

    # Require channel_id for video sources
    if request.type == "video" and not request.channel_id:
        raise HTTPException(status_code=400, detail="channel_id required for video sources")

    # Create custom source (owned by creating user)
    source = ContentSource(
        source_key=request.source_key,
        name=request.name,
        type=request.type,
        url=request.url,
        website=request.website,
        description=request.description,
        channel_id=request.channel_id,
        is_system=False,  # User-created
        is_enabled=True,
        user_id=current_user.id,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    # Auto-subscribe user to their custom source
    await set_user_subscription(db, current_user.id, source.id, True)

    logger.info(f"User {current_user.id} added custom source: {source.name}")

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
    )


@router.delete("/{source_id}")
async def delete_custom_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a custom content source.

    Only non-system sources can be deleted.
    """
    result = await db.execute(
        select(ContentSource).where(ContentSource.id == source_id)
    )
    source = result.scalars().first()

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if source.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system sources")

    # Only the owner (or a superuser) can delete custom sources
    if source.user_id and source.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized to delete this source")

    source_name = source.name
    await db.delete(source)
    await db.commit()

    logger.info(f"User {current_user.id} deleted custom source: {source_name}")

    return {"message": f"Deleted source: {source_name}"}
