"""
Simple script to run the DEX fields migration
"""

import sys
import asyncio
from sqlalchemy import text
from app.database import engine, async_session_maker


async def run_migration():
    """Run the DEX fields migration manually"""
    print("🔄 Running DEX fields migration...")

    async with engine.begin() as conn:
        # Add DEX fields to bots table (SQLite requires separate ALTER TABLE statements)
        print("  📊 Adding DEX fields to bots table...")

        # Check if columns already exist
        result = await conn.execute(text("""
            SELECT name FROM pragma_table_info('bots') WHERE name IN ('exchange_type', 'chain_id', 'dex_router', 'wallet_address')
        """))
        existing_cols = {row[0] for row in result.fetchall()}

        if 'exchange_type' not in existing_cols:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN exchange_type VARCHAR DEFAULT 'cex' NOT NULL"))
        if 'chain_id' not in existing_cols:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN chain_id INTEGER"))
        if 'dex_router' not in existing_cols:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN dex_router VARCHAR"))
        if 'wallet_address' not in existing_cols:
            await conn.execute(text("ALTER TABLE bots ADD COLUMN wallet_address VARCHAR"))

        # Add DEX fields to positions table
        print("  📊 Adding DEX fields to positions table...")

        result = await conn.execute(text("""
            SELECT name FROM pragma_table_info('positions') WHERE name IN ('exchange_type', 'chain_id', 'dex_router', 'wallet_address')
        """))
        existing_cols = {row[0] for row in result.fetchall()}

        if 'exchange_type' not in existing_cols:
            await conn.execute(text("ALTER TABLE positions ADD COLUMN exchange_type VARCHAR DEFAULT 'cex' NOT NULL"))
        if 'chain_id' not in existing_cols:
            await conn.execute(text("ALTER TABLE positions ADD COLUMN chain_id INTEGER"))
        if 'dex_router' not in existing_cols:
            await conn.execute(text("ALTER TABLE positions ADD COLUMN dex_router VARCHAR"))
        if 'wallet_address' not in existing_cols:
            await conn.execute(text("ALTER TABLE positions ADD COLUMN wallet_address VARCHAR"))

    print("✅ Migration completed successfully!")

    # Verify the migration
    print("\n🔍 Verifying migration...")
    async with async_session_maker() as db:
        result = await db.execute(text("""
            SELECT name FROM pragma_table_info('bots')
            WHERE name IN ('exchange_type', 'chain_id', 'dex_router', 'wallet_address')
            ORDER BY name
        """))
        bot_cols = [row[0] for row in result.fetchall()]
        print(f"  Bots table new columns: {bot_cols}")

        result = await db.execute(text("""
            SELECT name FROM pragma_table_info('positions')
            WHERE name IN ('exchange_type', 'chain_id', 'dex_router', 'wallet_address')
            ORDER BY name
        """))
        pos_cols = [row[0] for row in result.fetchall()]
        print(f"  Positions table new columns: {pos_cols}")

        if len(bot_cols) == 4 and len(pos_cols) == 4:
            print("\n✅ All DEX fields added successfully!")
            return True
        else:
            print("\n❌ Migration verification failed!")
            return False


if __name__ == "__main__":
    try:
        success = asyncio.run(run_migration())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Migration failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
