"""
Bot Control Router

Handles bot activation, deactivation, and force-run operations.
Respects seasonality restrictions when enabled.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bot, Position, Settings, User
from app.routers.auth_dependencies import get_current_user
from app.services.season_detector import get_seasonality_status

logger = logging.getLogger(__name__)
router = APIRouter()


async def check_seasonality_allows_bot(db: AsyncSession, bot: Bot) -> tuple[bool, str | None]:
    """
    Check if seasonality restrictions allow this bot to be enabled.

    Returns (allowed, reason) tuple.
    """
    # Check if seasonality is enabled
    result = await db.execute(select(Settings).where(Settings.key == "seasonality_enabled"))
    setting = result.scalars().first()
    enabled = setting and setting.value == "true"

    if not enabled:
        return True, None

    # Grid bots are exempt from seasonality restrictions
    if bot.strategy_type == "grid_trading":
        return True, None

    # Get current seasonality status
    status = await get_seasonality_status()
    quote_currency = bot.get_quote_currency()

    if quote_currency == "BTC" and not status.btc_bots_allowed:
        mode_str = status.mode.replace('_', '-')
        return False, f"BTC bots blocked during {mode_str} mode ({status.season_info.name})"

    if quote_currency == "USD" and not status.usd_bots_allowed:
        mode_str = status.mode.replace('_', '-')
        return False, f"USD bots blocked during {mode_str} mode ({status.season_info.name})"

    return True, None


@router.post("/{bot_id}/start")
async def start_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Activate a bot to start trading (respects seasonality restrictions)"""
    query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
    query = query.where(Bot.user_id == current_user.id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    if bot.is_active:
        return {"message": f"Bot '{bot.name}' is already active"}

    # Check seasonality restrictions
    allowed, reason = await check_seasonality_allows_bot(db, bot)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot start bot: {reason}. Disable seasonality tracking to override."
        )

    bot.is_active = True
    bot.updated_at = datetime.utcnow()

    await db.commit()

    return {"message": f"Bot '{bot.name}' started successfully"}


@router.post("/{bot_id}/stop")
async def stop_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Deactivate a bot to stop trading"""
    query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
    query = query.where(Bot.user_id == current_user.id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    if not bot.is_active:
        return {"message": f"Bot '{bot.name}' is already inactive"}

    bot.is_active = False
    bot.updated_at = datetime.utcnow()

    await db.commit()

    return {"message": f"Bot '{bot.name}' stopped successfully"}


@router.post("/{bot_id}/force-run")
async def force_run_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Force bot to run immediately on next monitor cycle"""
    query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
    query = query.where(Bot.user_id == current_user.id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    if not bot.is_active:
        raise HTTPException(status_code=400, detail="Cannot force run an inactive bot. Start the bot first.")

    # Get bot's check interval (default to 300 seconds if not set)
    check_interval = getattr(bot, "check_interval_seconds", 300) or 300

    # Set last_signal_check to a time that's past the interval
    # This ensures the bot will be processed on the next monitor cycle
    force_time = datetime.utcnow() - timedelta(seconds=check_interval + 60)
    bot.last_signal_check = force_time
    bot.updated_at = datetime.utcnow()

    await db.commit()

    logger.info(
        f"🚀 Force run triggered for bot '{bot.name}' (ID: {bot_id}). Will execute on next monitor cycle (~10 seconds)."
    )

    return {
        "message": f"Bot '{bot.name}' will run on next monitor cycle",
        "note": "Bot will execute within ~10 seconds",
    }


@router.post("/{bot_id}/cancel-all-positions")
async def cancel_all_positions(
    bot_id: int,
    confirm: bool = Query(False, description="Must be true to execute"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel all open positions for a bot without selling"""
    if not confirm:
        raise HTTPException(status_code=400, detail="Must confirm with confirm=true")

    # Get bot with user filtering
    query = select(Bot).where(Bot.id == bot_id)
    query = query.where(Bot.user_id == current_user.id)
    result = await db.execute(query)
    bot = result.scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Get all open positions for this bot
    positions_query = select(Position).where(
        Position.bot_id == bot_id,
        Position.status == "open"
    )
    positions_result = await db.execute(positions_query)
    positions = positions_result.scalars().all()

    if not positions:
        raise HTTPException(status_code=400, detail="No open positions to cancel")

    # Cancel each position
    cancelled_count = 0
    failed_count = 0
    errors = []

    for position in positions:
        try:
            position.status = "cancelled"
            position.closed_at = datetime.utcnow()
            cancelled_count += 1
        except Exception as e:
            failed_count += 1
            errors.append(f"{position.product_id} (#{position.id}): {str(e)}")

    await db.commit()

    logger.info(f"Cancelled {cancelled_count} positions for bot '{bot.name}' (ID: {bot_id})")

    return {
        "message": f"Cancelled {cancelled_count} position(s)",
        "cancelled_count": cancelled_count,
        "failed_count": failed_count,
        "errors": errors
    }


@router.post("/{bot_id}/sell-all-positions")
async def sell_all_positions(
    bot_id: int,
    confirm: bool = Query(False, description="Must be true to execute"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Sell all open positions for a bot at market price (realize P&L)"""
    if not confirm:
        raise HTTPException(status_code=400, detail="Must confirm with confirm=true")

    # Get bot with user filtering
    query = select(Bot).where(Bot.id == bot_id)
    query = query.where(Bot.user_id == current_user.id)
    result = await db.execute(query)
    bot = result.scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Get exchange client for this bot's account
    from app.services.exchange_service import get_exchange_client_for_account
    from app.strategies import StrategyRegistry
    from app.trading_engine_v2 import StrategyTradingEngine

    exchange = await get_exchange_client_for_account(db, bot.account_id)
    strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)

    # Get all open positions for this bot
    positions_query = select(Position).where(
        Position.bot_id == bot_id,
        Position.status == "open"
    )
    positions_result = await db.execute(positions_query)
    positions = positions_result.scalars().all()

    if not positions:
        raise HTTPException(status_code=400, detail="No open positions to sell")

    # Sell each position
    sold_count = 0
    failed_count = 0
    total_profit_quote = 0.0
    errors = []

    for position in positions:
        try:
            # Get current price
            current_price = await exchange.get_current_price(position.product_id)

            # Execute sell using trading engine
            engine = StrategyTradingEngine(
                db=db, exchange=exchange, bot=bot, strategy=strategy, product_id=position.product_id
            )
            trade, profit_quote, profit_pct = await engine.execute_sell(
                position=position, current_price=current_price, signal_data=None
            )

            sold_count += 1
            total_profit_quote += profit_quote

        except Exception as e:
            failed_count += 1
            errors.append(f"{position.product_id} (#{position.id}): {str(e)}")

    logger.warning(
        f"🚨 SELL ALL executed for bot '{bot.name}': "
        f"{sold_count} sold, {failed_count} failed, "
        f"total profit: {total_profit_quote:.8f}"
    )

    return {
        "message": f"Sold {sold_count} position(s)",
        "sold_count": sold_count,
        "failed_count": failed_count,
        "total_profit_quote": total_profit_quote,
        "errors": errors
    }
