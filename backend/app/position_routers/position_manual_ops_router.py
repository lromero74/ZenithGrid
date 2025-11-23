"""
Position Manual Operations Router

Handles manual position operations: add funds and update notes.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Position
from app.coinbase_unified_client import CoinbaseClient
from app.position_routers.dependencies import get_coinbase
from app.position_routers.schemas import AddFundsRequest, UpdateNotesRequest
from app.trading_client import TradingClient
from app.trading_engine_v2 import StrategyTradingEngine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{position_id}/add-funds")
async def add_funds_to_position(
    position_id: int,
    request: AddFundsRequest,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Manually add funds to a position (manual safety order)"""
    btc_amount = request.btc_amount
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        # Check if adding funds would exceed max allowed
        if position.total_btc_spent + btc_amount > position.max_btc_allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Adding {btc_amount} BTC would exceed max allowed ({position.max_btc_allowed} BTC)"
            )

        # Get current price
        current_price = await coinbase.get_current_price()

        # Execute DCA buy using new trading engine
        trading_client = TradingClient(coinbase)
        engine = StrategyTradingEngine(
            db=db,
            trading_client=trading_client,
            bot=None,  # Manual operation, no bot
            product_id=position.product_id
        )
        trade = await engine.execute_buy(
            position=position,
            quote_amount=btc_amount,  # New engine uses quote_amount (multi-currency)
            current_price=current_price,
            trade_type="manual_safety_order",
            signal_data=None
        )

        return {
            "message": f"Added {btc_amount} BTC to position {position_id}",
            "trade_id": trade.id,
            "price": current_price,
            "eth_acquired": trade.eth_amount
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{position_id}/notes")
async def update_position_notes(
    position_id: int,
    request: UpdateNotesRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update notes for a position (like 3Commas)"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        # Update notes
        position.notes = request.notes

        await db.commit()

        return {
            "message": f"Notes updated for position {position_id}",
            "notes": position.notes
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
