"""
Add auto-buy BTC settings to accounts table

Adds per-account auto-buy settings for automatically converting stablecoins (USD, USDC, USDT)
to BTC when balances exceed configurable minimums.

Fields added:
- auto_buy_enabled: Master toggle (default: False)
- auto_buy_check_interval_minutes: Shared check interval (default: 5)
- auto_buy_usd_enabled, auto_buy_usd_min: USD settings (default: False, $10)
- auto_buy_usdc_enabled, auto_buy_usdc_min: USDC settings (default: False, $10)
- auto_buy_usdt_enabled, auto_buy_usdt_min: USDT settings (default: False, $10)
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
    """Add auto-buy BTC settings columns to accounts table"""
    async with engine.begin() as conn:
        # Check which columns already exist
        result = await conn.execute(text("PRAGMA table_info(accounts)"))
        existing_columns = [row[1] for row in result]

        columns_to_add = {
            'auto_buy_enabled': 'BOOLEAN DEFAULT 0',
            'auto_buy_check_interval_minutes': 'INTEGER DEFAULT 5',
            'auto_buy_order_type': 'TEXT DEFAULT "market"',
            'auto_buy_usd_enabled': 'BOOLEAN DEFAULT 0',
            'auto_buy_usd_min': 'REAL DEFAULT 10.0',
            'auto_buy_usdc_enabled': 'BOOLEAN DEFAULT 0',
            'auto_buy_usdc_min': 'REAL DEFAULT 10.0',
            'auto_buy_usdt_enabled': 'BOOLEAN DEFAULT 0',
            'auto_buy_usdt_min': 'REAL DEFAULT 10.0',
        }

        added_count = 0
        for column_name, column_type in columns_to_add.items():
            if column_name in existing_columns:
                print(f"⏭️  Column {column_name} already exists")
            else:
                await conn.execute(text(f"""
                    ALTER TABLE accounts
                    ADD COLUMN {column_name} {column_type}
                """))
                print(f"✅ Added {column_name} column to accounts table")
                added_count += 1

        if added_count == 0:
            print("✅ All auto-buy BTC settings columns already exist")
        else:
            print(f"✅ Added {added_count} auto-buy BTC settings columns to accounts table")

async def rollback():
    """Remove auto-buy BTC settings columns"""
    print("⚠️  Manual rollback required for SQLite")
    print("To rollback, you would need to:")
    print("1. Create new accounts table without auto-buy columns")
    print("2. Copy all data from old table to new table (excluding auto-buy columns)")
    print("3. Drop old table and rename new table")
    print("\nColumns to remove:")
    print("  - auto_buy_enabled")
    print("  - auto_buy_check_interval_minutes")
    print("  - auto_buy_usd_enabled")
    print("  - auto_buy_usd_min")
    print("  - auto_buy_usdc_enabled")
    print("  - auto_buy_usdc_min")
    print("  - auto_buy_usdt_enabled")
    print("  - auto_buy_usdt_min")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        asyncio.run(rollback())
    else:
        asyncio.run(upgrade())
