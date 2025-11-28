"""
Blacklist Router

Handles coin blacklist management:
- List all blacklisted coins
- Add coins to blacklist
- Remove coins from blacklist
- Update blacklist entry reasons
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import BlacklistedCoin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/blacklist", tags=["blacklist"])


# Pydantic schemas for blacklist operations
class BlacklistEntry(BaseModel):
    """Response model for a blacklisted coin"""

    id: int
    symbol: str
    reason: Optional[str] = None
    created_at: str

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


@router.get("/", response_model=List[BlacklistEntry])
async def list_blacklisted_coins(db: AsyncSession = Depends(get_db)):
    """Get all blacklisted coins"""
    query = select(BlacklistedCoin).order_by(BlacklistedCoin.symbol)
    result = await db.execute(query)
    coins = result.scalars().all()

    return [
        BlacklistEntry(
            id=coin.id,
            symbol=coin.symbol,
            reason=coin.reason,
            created_at=coin.created_at.isoformat() if coin.created_at else "",
        )
        for coin in coins
    ]


@router.post("/", response_model=List[BlacklistEntry], status_code=201)
async def add_to_blacklist(request: BlacklistAddRequest, db: AsyncSession = Depends(get_db)):
    """
    Add one or more coins to the blacklist.

    If a coin is already blacklisted, it will be skipped (no error).
    """
    added_entries = []

    for symbol in request.symbols:
        # Normalize symbol to uppercase
        normalized_symbol = symbol.upper().strip()

        if not normalized_symbol:
            continue

        # Check if already blacklisted
        existing_query = select(BlacklistedCoin).where(BlacklistedCoin.symbol == normalized_symbol)
        existing_result = await db.execute(existing_query)
        if existing_result.scalars().first():
            logger.info(f"Symbol {normalized_symbol} already blacklisted, skipping")
            continue

        # Add to blacklist
        entry = BlacklistedCoin(symbol=normalized_symbol, reason=request.reason)
        db.add(entry)
        await db.flush()  # Get the ID without committing

        added_entries.append(
            BlacklistEntry(
                id=entry.id,
                symbol=entry.symbol,
                reason=entry.reason,
                created_at=entry.created_at.isoformat() if entry.created_at else "",
            )
        )
        logger.info(f"Added {normalized_symbol} to blacklist: {request.reason}")

    await db.commit()

    return added_entries


@router.post("/single", response_model=BlacklistEntry, status_code=201)
async def add_single_to_blacklist(request: BlacklistAddSingleRequest, db: AsyncSession = Depends(get_db)):
    """
    Add a single coin to the blacklist with its own reason.
    Returns error if coin is already blacklisted.
    """
    # Normalize symbol to uppercase
    normalized_symbol = request.symbol.upper().strip()

    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="Symbol cannot be empty")

    # Check if already blacklisted
    existing_query = select(BlacklistedCoin).where(BlacklistedCoin.symbol == normalized_symbol)
    existing_result = await db.execute(existing_query)
    if existing_result.scalars().first():
        raise HTTPException(status_code=409, detail=f"{normalized_symbol} is already blacklisted")

    # Add to blacklist
    entry = BlacklistedCoin(symbol=normalized_symbol, reason=request.reason)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    logger.info(f"Added {normalized_symbol} to blacklist: {request.reason}")

    return BlacklistEntry(
        id=entry.id,
        symbol=entry.symbol,
        reason=entry.reason,
        created_at=entry.created_at.isoformat() if entry.created_at else "",
    )


@router.delete("/{symbol}")
async def remove_from_blacklist(symbol: str, db: AsyncSession = Depends(get_db)):
    """Remove a coin from the blacklist"""
    normalized_symbol = symbol.upper().strip()

    query = select(BlacklistedCoin).where(BlacklistedCoin.symbol == normalized_symbol)
    result = await db.execute(query)
    entry = result.scalars().first()

    if not entry:
        raise HTTPException(status_code=404, detail=f"{normalized_symbol} is not in the blacklist")

    await db.delete(entry)
    await db.commit()

    logger.info(f"Removed {normalized_symbol} from blacklist")

    return {"message": f"{normalized_symbol} removed from blacklist"}


@router.put("/{symbol}", response_model=BlacklistEntry)
async def update_blacklist_reason(symbol: str, request: BlacklistUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update the reason for a blacklisted coin"""
    normalized_symbol = symbol.upper().strip()

    query = select(BlacklistedCoin).where(BlacklistedCoin.symbol == normalized_symbol)
    result = await db.execute(query)
    entry = result.scalars().first()

    if not entry:
        raise HTTPException(status_code=404, detail=f"{normalized_symbol} is not in the blacklist")

    entry.reason = request.reason
    await db.commit()
    await db.refresh(entry)

    logger.info(f"Updated reason for {normalized_symbol}: {request.reason}")

    return BlacklistEntry(
        id=entry.id,
        symbol=entry.symbol,
        reason=entry.reason,
        created_at=entry.created_at.isoformat() if entry.created_at else "",
    )


@router.get("/check/{symbol}")
async def check_if_blacklisted(symbol: str, db: AsyncSession = Depends(get_db)):
    """Check if a specific coin is blacklisted"""
    normalized_symbol = symbol.upper().strip()

    query = select(BlacklistedCoin).where(BlacklistedCoin.symbol == normalized_symbol)
    result = await db.execute(query)
    entry = result.scalars().first()

    return {
        "symbol": normalized_symbol,
        "is_blacklisted": entry is not None,
        "reason": entry.reason if entry else None,
    }
