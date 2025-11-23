"""
Bot Control Router

Handles bot activation, deactivation, and force-run operations.
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="")


@router.post("/{bot_id}/start")
async def start_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    """Activate a bot to start trading"""
    query = select(Bot).where(Bot.id == bot_id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    if bot.is_active:
        return {"message": f"Bot '{bot.name}' is already active"}

    bot.is_active = True
    bot.updated_at = datetime.utcnow()

    await db.commit()

    return {"message": f"Bot '{bot.name}' started successfully"}


@router.post("/{bot_id}/stop")
async def stop_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    """Deactivate a bot to stop trading"""
    query = select(Bot).where(Bot.id == bot_id)
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
async def force_run_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    """Force bot to run immediately on next monitor cycle"""
    query = select(Bot).where(Bot.id == bot_id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    if not bot.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot force run an inactive bot. Start the bot first."
        )

    # Get bot's check interval (default to 300 seconds if not set)
    check_interval = getattr(bot, 'check_interval_seconds', 300) or 300

    # Set last_signal_check to a time that's past the interval
    # This ensures the bot will be processed on the next monitor cycle
    force_time = datetime.utcnow() - timedelta(seconds=check_interval + 60)
    bot.last_signal_check = force_time
    bot.updated_at = datetime.utcnow()

    await db.commit()

    logger.info(f"🚀 Force run triggered for bot '{bot.name}' (ID: {bot_id}). Will execute on next monitor cycle (~10 seconds).")

    return {
        "message": f"Bot '{bot.name}' will run on next monitor cycle",
        "note": "Bot will execute within ~10 seconds"
    }
