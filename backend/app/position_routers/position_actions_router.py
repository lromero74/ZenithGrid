"""
Position Actions Router

Handles basic position actions: cancel and force-close.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bot, Position
from app.coinbase_unified_client import CoinbaseClient
from app.position_routers.dependencies import get_coinbase
from app.trading_engine_v2 import StrategyTradingEngine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{position_id}/cancel")
async def cancel_position(position_id: int, db: AsyncSession = Depends(get_db)):
    """Cancel a position without selling (leave balances as-is)"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        # Mark position as cancelled
        position.status = "cancelled"
        position.closed_at = datetime.utcnow()

        await db.commit()

        return {"message": f"Position {position_id} cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{position_id}/force-close")
async def force_close_position(
    position_id: int, db: AsyncSession = Depends(get_db), coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Force close a position at current market price"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        # Get the bot associated with this position
        bot_query = select(Bot).where(Bot.id == position.bot_id)
        bot_result = await db.execute(bot_query)
        bot = bot_result.scalars().first()

        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found for this position")

        # Get current price for the position's product
        current_price = await coinbase.get_current_price(position.product_id)

        # Create strategy instance for this bot
        from app.strategies import StrategyRegistry

        strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)

        # Execute sell using trading engine
        engine = StrategyTradingEngine(
            db=db, coinbase=coinbase, bot=bot, strategy=strategy, product_id=position.product_id
        )
        trade, profit_quote, profit_percentage = await engine.execute_sell(
            position=position, current_price=current_price, signal_data=None
        )

        return {
            "message": f"Position {position_id} closed successfully",
            "profit_quote": profit_quote,
            "profit_percentage": profit_percentage,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
