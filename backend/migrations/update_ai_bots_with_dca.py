"""
Update existing AI autonomous bots with new DCA parameters
and backfill strategy_config_snapshot for existing positions
"""
import asyncio
import sys
import json
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Change to backend directory so database path resolves correctly
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from app.database import async_session_maker
from app.models import Bot, Position

# Default DCA parameters
DEFAULT_DCA_CONFIG = {
    "enable_dca": True,
    "max_safety_orders": 3,
    "safety_order_percentage": 5.0,
    "min_price_drop_for_dca": 2.0,
    "dca_confidence_threshold": 70,
    "profit_calculation_method": "cost_basis"
}

async def update_bots_and_snapshots():
    """Update AI bots with DCA config and backfill position snapshots"""
    async with async_session_maker() as db:
        # Get all AI autonomous bots
        query = select(Bot).where(Bot.strategy_type == "ai_autonomous")
        result = await db.execute(query)
        ai_bots = result.scalars().all()

        print(f"Found {len(ai_bots)} AI autonomous bots")

        # Check if migration already applied (all bots have all DCA keys)
        needs_update = False
        for bot in ai_bots:
            for key in DEFAULT_DCA_CONFIG.keys():
                if key not in bot.strategy_config:
                    needs_update = True
                    break
            if needs_update:
                break

        if not needs_update and len(ai_bots) > 0:
            print("⚠️  All AI bots already have DCA config - migration already applied")
            return

        for bot in ai_bots:
            print(f"\n📝 Updating bot #{bot.id}: {bot.name}")

            # Update bot's strategy_config with new DCA parameters
            updated_config = bot.strategy_config.copy()

            # Add new DCA parameters if they don't exist
            for key, default_value in DEFAULT_DCA_CONFIG.items():
                if key not in updated_config:
                    updated_config[key] = default_value
                    print(f"  ✅ Added {key}: {default_value}")

            bot.strategy_config = updated_config

            # Find all open positions for this bot
            pos_query = select(Position).where(
                Position.bot_id == bot.id,
                Position.status == "open"
            )
            pos_result = await db.execute(pos_query)
            positions = pos_result.scalars().all()

            print(f"  Found {len(positions)} open positions")

            # Backfill strategy_config_snapshot for positions without it
            for position in positions:
                if position.strategy_config_snapshot is None:
                    position.strategy_config_snapshot = updated_config.copy()
                    print(f"    ✅ Backfilled snapshot for position #{position.id} ({position.product_id})")
                else:
                    print(f"    ⏭️  Position #{position.id} already has snapshot")

        # Commit all changes
        await db.commit()
        print(f"\n✅ Successfully updated {len(ai_bots)} bots and their positions")

if __name__ == "__main__":
    asyncio.run(update_bots_and_snapshots())
