"""
Position Actions Router

Handles basic position actions: cancel, force-close, and update settings.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account, Bot, Position, User
from app.position_routers.helpers import compute_resize_budget
from app.auth.dependencies import get_current_user
from app.schemas.position import UpdatePositionSettingsRequest
from app.services.exchange_service import get_exchange_client_for_account

from app.trading_engine_v2 import StrategyTradingEngine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{position_id}/cancel")
async def cancel_position(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel a position without selling (leave balances as-is)"""
    try:
        query = select(Position).where(Position.id == position_id)

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
    except Exception:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/{position_id}/force-close")
async def force_close_position(
    position_id: int,
    skip_slippage_guard: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Force close a position at current market price"""
    try:
        query = select(Position).where(Position.id == position_id)

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

        # Get the correct exchange client for this position's account
        # (paper trading positions need PaperTradingClient, not the real Coinbase client)
        exchange = await get_exchange_client_for_account(db, position.account_id)
        if not exchange:
            raise HTTPException(
                status_code=503,
                detail="Could not create exchange client for this position's account."
            )

        # Get current price for the position's product
        current_price = await exchange.get_current_price(position.product_id)

        # Slippage guard — warn user if slippage will erode profit
        config = position.strategy_config_snapshot or {}
        if config.get("slippage_guard", False) and not skip_slippage_guard:
            from app.trading_engine.book_depth_guard import check_sell_slippage
            proceed, guard_reason = await check_sell_slippage(
                exchange, position.product_id, position, config
            )
            if not proceed:
                return {
                    "slippage_warning": guard_reason,
                    "requires_confirmation": True,
                }

        # Create strategy instance for this bot
        from app.strategies import StrategyRegistry

        strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)

        # Execute sell using trading engine
        engine = StrategyTradingEngine(
            db=db, exchange=exchange, bot=bot, strategy=strategy, product_id=position.product_id
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
        logger.error(f"Error force-closing position {position_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.patch("/{position_id}/settings")
async def update_position_settings(
    position_id: int,
    settings: UpdatePositionSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update position settings (deal editing).

    This updates the strategy_config_snapshot for an open position,
    allowing users to modify take profit, max safety orders, etc.
    without affecting the bot's default configuration.
    """
    try:
        query = select(Position).where(Position.id == position_id)

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
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/{position_id}/resize-budget")
async def resize_position_budget(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recalculate and update a position's max_quote_allowed to reflect true max deal cost."""
    try:
        from sqlalchemy.orm import selectinload

        query = select(Position).options(selectinload(Position.trades)).where(
            Position.id == position_id
        )

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
        new_max = compute_resize_budget(position, bot)

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
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/resize-all-budgets")
async def resize_all_budgets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recalculate and update max_quote_allowed for all open positions."""
    try:
        from sqlalchemy.orm import selectinload

        query = select(Position).options(selectinload(Position.trades)).where(
            Position.status == "open"
        )

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
            new_max = compute_resize_budget(position, bot)

            if new_max > 0:
                # Skip if budget is effectively unchanged (within 1 satoshi)
                if abs(old_max - new_max) < 0.000000015:
                    continue
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

        if updated_count == 0 and not results:
            message = f"All {len(positions)} positions already have correct budgets"
        else:
            message = f"Resized {updated_count} of {len(positions)} open positions"

        return {
            "message": message,
            "updated_count": updated_count,
            "total_count": len(positions),
            "results": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resizing all budgets: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")
