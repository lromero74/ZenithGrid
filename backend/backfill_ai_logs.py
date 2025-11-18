"""
Backfill position_id for existing AI bot logs.

This script matches AI logs to positions based on:
- bot_id
- product_id
- timestamp (between position opened_at and closed_at, or 30s before opened_at)
"""
import asyncio
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker, init_db
from app.models import AIBotLog, Position


async def backfill_ai_logs():
    """Backfill position_id for AI logs that match positions"""
    await init_db()

    async with async_session_maker() as db:
        # Get all positions
        positions_query = select(Position).order_by(Position.opened_at)
        result = await db.execute(positions_query)
        positions = result.scalars().all()

        print(f"Found {len(positions)} positions")

        updated_count = 0

        for position in positions:
            if not position.bot_id or not position.product_id:
                continue

            # Calculate time window (30s before open to close time)
            time_before = position.opened_at - timedelta(seconds=30)
            time_after = position.closed_at if position.closed_at else position.opened_at + timedelta(days=365)

            # Find AI logs for this bot/product in the time window
            logs_query = select(AIBotLog).where(
                AIBotLog.bot_id == position.bot_id,
                AIBotLog.product_id == position.product_id,
                AIBotLog.timestamp >= time_before,
                AIBotLog.timestamp <= time_after,
                AIBotLog.position_id == None  # Only update logs that don't have position_id
            )

            logs_result = await db.execute(logs_query)
            logs = logs_result.scalars().all()

            if logs:
                print(f"Position #{position.id} ({position.product_id}): "
                      f"Found {len(logs)} AI logs from {position.opened_at} to {position.closed_at or 'now'}")

                for log in logs:
                    log.position_id = position.id
                    updated_count += 1

        await db.commit()

        print(f"\n✅ Updated {updated_count} AI logs with position_id")


if __name__ == "__main__":
    asyncio.run(backfill_ai_logs())
