"""
Position Actions Router

Handles basic position actions: cancel, force-close, and update settings.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account, Bot, Position, User
from app.coinbase_unified_client import CoinbaseClient
from app.position_routers.dependencies import get_coinbase
from app.trading_engine_v2 import StrategyTradingEngine
from app.routers.auth_dependencies import get_current_user_optional
from app.schemas.position import UpdatePositionSettingsRequest
from app.trading_engine.position_manager import calculate_expected_position_budget, calculate_max_deal_cost

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{position_id}/cancel")
async def cancel_position(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Cancel a position without selling (leave balances as-is)"""
    try:
        query = select(Position).where(Position.id == position_id)

        # Filter by user's accounts if authenticated
        if current_user:
            accounts_query = select(Account.id).where(Account.user_id == current_user.id)
            accounts_result = await db.execute(accounts_query)
            user_account_ids = [row[0] for row in accounts_result.fetchall()]
            if user_account_ids:
                query = query.where(Position.account_id.in_(user_account_ids))
            else:
                raise HTTPException(status_code=404, detail="Position not found")

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
    position_id: int,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Force close a position at current market price"""
    try:
        query = select(Position).where(Position.id == position_id)

        # Filter by user's accounts if authenticated
        if current_user:
            accounts_query = select(Account.id).where(Account.user_id == current_user.id)
            accounts_result = await db.execute(accounts_query)
            user_account_ids = [row[0] for row in accounts_result.fetchall()]
            if user_account_ids:
                query = query.where(Position.account_id.in_(user_account_ids))
            else:
                raise HTTPException(status_code=404, detail="Position not found")

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
            db=db, exchange=coinbase, bot=bot, strategy=strategy, product_id=position.product_id
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


@router.patch("/{position_id}/settings")
async def update_position_settings(
    position_id: int,
    settings: UpdatePositionSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Update position settings (like 3Commas deal editing).

    This updates the strategy_config_snapshot for an open position,
    allowing users to modify take profit, max safety orders, etc.
    without affecting the bot's default configuration.
    """
    try:
        query = select(Position).where(Position.id == position_id)

        # Filter by user's accounts if authenticated
        if current_user:
            accounts_query = select(Account.id).where(Account.user_id == current_user.id)
            accounts_result = await db.execute(accounts_query)
            user_account_ids = [row[0] for row in accounts_result.fetchall()]
            if user_account_ids:
                query = query.where(Position.account_id.in_(user_account_ids))
            else:
                raise HTTPException(status_code=404, detail="Position not found")

        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Can only update settings for open positions")

        # Get current config snapshot (or empty dict if none)
        config = position.strategy_config_snapshot or {}

        # Track what was updated
        updated_fields = []

        # Update only the fields that were provided
        if settings.take_profit_percentage is not None:
            old_value = config.get("take_profit_percentage")
            config["take_profit_percentage"] = settings.take_profit_percentage
            updated_fields.append(f"take_profit_percentage: {old_value} → {settings.take_profit_percentage}")

        if settings.max_safety_orders is not None:
            old_value = config.get("max_safety_orders")
            config["max_safety_orders"] = settings.max_safety_orders
            updated_fields.append(f"max_safety_orders: {old_value} → {settings.max_safety_orders}")

        if settings.trailing_take_profit is not None:
            old_value = config.get("trailing_take_profit")
            config["trailing_take_profit"] = settings.trailing_take_profit
            updated_fields.append(f"trailing_take_profit: {old_value} → {settings.trailing_take_profit}")

        if settings.trailing_tp_deviation is not None:
            old_value = config.get("trailing_tp_deviation")
            config["trailing_tp_deviation"] = settings.trailing_tp_deviation
            updated_fields.append(f"trailing_tp_deviation: {old_value} → {settings.trailing_tp_deviation}")

        if settings.stop_loss_enabled is not None:
            old_value = config.get("stop_loss_enabled")
            config["stop_loss_enabled"] = settings.stop_loss_enabled
            updated_fields.append(f"stop_loss_enabled: {old_value} → {settings.stop_loss_enabled}")

        if settings.stop_loss_percentage is not None:
            old_value = config.get("stop_loss_percentage")
            config["stop_loss_percentage"] = settings.stop_loss_percentage
            updated_fields.append(f"stop_loss_percentage: {old_value} → {settings.stop_loss_percentage}")

        if not updated_fields:
            raise HTTPException(status_code=400, detail="No settings provided to update")

        # Update the config snapshot
        position.strategy_config_snapshot = config

        await db.commit()

        logger.info(f"Updated position #{position_id} settings: {', '.join(updated_fields)}")

        return {
            "message": f"Position {position_id} settings updated successfully",
            "updated_fields": updated_fields,
            "new_config": config,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating position settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _compute_resize_budget(position: Position, bot: Optional[Bot]) -> float:
    """Compute the true max deal cost for a position from its config and trades."""
    config = position.strategy_config_snapshot or (bot.strategy_config if bot else {}) or {}

    # Try calculate_expected_position_budget first (works for fixed order configs)
    expected = calculate_expected_position_budget(config, 0)
    if expected > 0:
        return expected

    # Fallback: derive from position's first buy trade
    base_order_size = 0.0
    if position.trades:
        buy_trades = sorted(
            [t for t in position.trades if t.side == "buy"],
            key=lambda t: t.timestamp,
        )
        if buy_trades:
            base_order_size = buy_trades[0].quote_amount or 0.0

    # If still no base order size, try config values
    if base_order_size <= 0:
        base_order_size = config.get("base_order_btc", 0.0) or config.get("base_order_fixed", 0.0)

    if base_order_size <= 0:
        return 0.0

    return calculate_max_deal_cost(config, base_order_size)


@router.post("/{position_id}/resize-budget")
async def resize_position_budget(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Recalculate and update a position's max_quote_allowed to reflect true max deal cost."""
    try:
        from sqlalchemy.orm import selectinload

        query = select(Position).options(selectinload(Position.trades)).where(
            Position.id == position_id
        )

        if current_user:
            accounts_query = select(Account.id).where(Account.user_id == current_user.id)
            accounts_result = await db.execute(accounts_query)
            user_account_ids = [row[0] for row in accounts_result.fetchall()]
            if user_account_ids:
                query = query.where(Position.account_id.in_(user_account_ids))
            else:
                raise HTTPException(status_code=404, detail="Position not found")

        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        # Load bot for fallback config
        bot = None
        if position.bot_id:
            bot_result = await db.execute(select(Bot).where(Bot.id == position.bot_id))
            bot = bot_result.scalars().first()

        old_max = position.max_quote_allowed or 0.0
        new_max = _compute_resize_budget(position, bot)

        if new_max <= 0:
            raise HTTPException(
                status_code=400,
                detail="Could not compute max deal cost — no base order size found",
            )

        position.max_quote_allowed = new_max
        await db.commit()

        # Determine quote currency from product_id
        parts = position.product_id.split("-") if position.product_id else []
        quote_currency = parts[1] if len(parts) >= 2 else "BTC"

        logger.info(
            f"Resized position #{position_id} budget: {old_max:.8f} → {new_max:.8f} {quote_currency}"
        )

        return {
            "message": f"Position {position_id} budget resized",
            "position_id": position_id,
            "old_max": old_max,
            "new_max": new_max,
            "quote_currency": quote_currency,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resizing position budget: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resize-all-budgets")
async def resize_all_budgets(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Recalculate and update max_quote_allowed for all open positions."""
    try:
        from sqlalchemy.orm import selectinload

        query = select(Position).options(selectinload(Position.trades)).where(
            Position.status == "open"
        )

        if current_user:
            accounts_query = select(Account.id).where(Account.user_id == current_user.id)
            accounts_result = await db.execute(accounts_query)
            user_account_ids = [row[0] for row in accounts_result.fetchall()]
            if user_account_ids:
                query = query.where(Position.account_id.in_(user_account_ids))

        result = await db.execute(query)
        positions = result.scalars().all()

        # Pre-load bots for all positions
        bot_ids = {p.bot_id for p in positions if p.bot_id}
        bots_map = {}
        if bot_ids:
            bots_result = await db.execute(select(Bot).where(Bot.id.in_(bot_ids)))
            bots_map = {b.id: b for b in bots_result.scalars().all()}

        results = []
        updated_count = 0

        for position in positions:
            bot = bots_map.get(position.bot_id) if position.bot_id else None
            old_max = position.max_quote_allowed or 0.0
            new_max = _compute_resize_budget(position, bot)

            if new_max > 0:
                position.max_quote_allowed = new_max
                updated_count += 1
                results.append({
                    "id": position.id,
                    "pair": position.product_id,
                    "old_max": old_max,
                    "new_max": new_max,
                })
            else:
                results.append({
                    "id": position.id,
                    "pair": position.product_id,
                    "old_max": old_max,
                    "new_max": old_max,
                    "skipped": "Could not compute base order size",
                })

        await db.commit()

        logger.info(f"Resized budgets for {updated_count}/{len(positions)} open positions")

        return {
            "message": f"Resized {updated_count} of {len(positions)} open positions",
            "updated_count": updated_count,
            "total_count": len(positions),
            "results": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resizing all budgets: {e}")
        raise HTTPException(status_code=500, detail=str(e))
