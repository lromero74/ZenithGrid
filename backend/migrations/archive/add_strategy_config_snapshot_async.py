"""
Add strategy_config_snapshot column to positions table
This allows each position to freeze the bot's configuration at creation time
"""
import asyncio
import os
import sys

# Change to backend directory so database path resolves correctly
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from sqlalchemy import text
from app.database import engine

async def upgrade():
    """Add strategy_config_snapshot column"""
    async with engine.begin() as conn:
        # Check if column already exists
        result = await conn.execute(text("PRAGMA table_info(positions)"))
        columns = [row[1] for row in result]

        if 'strategy_config_snapshot' in columns:
            print("✅ Column strategy_config_snapshot already exists")
            return

        # Add column (nullable for existing positions)
        await conn.execute(text("""
            ALTER TABLE positions
            ADD COLUMN strategy_config_snapshot TEXT
        """))

        print("✅ Added strategy_config_snapshot column to positions table")

async def rollback():
    """Remove strategy_config_snapshot column"""
    print("⚠️  Manual rollback required for SQLite")
    print("To rollback, you would need to:")
    print("1. Create new table without strategy_config_snapshot column")
    print("2. Copy all data from old table to new table")
    print("3. Drop old table and rename new table")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        asyncio.run(rollback())
    else:
        asyncio.run(upgrade())
