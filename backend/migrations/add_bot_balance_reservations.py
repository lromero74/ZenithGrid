"""
Add balance reservation columns to bots table so each bot has its own allocated balance
"""
import asyncio
import sys
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Change to backend directory so database path resolves correctly
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from app.database import async_session_maker
from app.models import Bot

async def migrate():
    """Add reserved_btc_balance and reserved_usd_balance columns to bots table"""
    async with async_session_maker() as db:
        print("🔧 Adding balance reservation columns to bots table...")

        # Add columns
        await db.execute(text("ALTER TABLE bots ADD COLUMN reserved_btc_balance REAL DEFAULT 0.0"))
        await db.execute(text("ALTER TABLE bots ADD COLUMN reserved_usd_balance REAL DEFAULT 0.0"))

        await db.commit()
        print("✅ Successfully added balance reservation columns")
        print("   - reserved_btc_balance (REAL, default 0.0)")
        print("   - reserved_usd_balance (REAL, default 0.0)")

async def rollback():
    """Remove balance reservation columns"""
    async with async_session_maker() as db:
        print("🔄 Rolling back: removing balance reservation columns...")

        # SQLite doesn't support DROP COLUMN directly, need to recreate table
        print("⚠️  SQLite requires table recreation for column removal")
        print("   Manual rollback required if needed")

        # For now, just set all values to 0
        await db.execute(text("UPDATE bots SET reserved_btc_balance = 0.0, reserved_usd_balance = 0.0"))
        await db.commit()
        print("✅ Reset all reserved balances to 0")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        asyncio.run(rollback())
    else:
        asyncio.run(migrate())
