"""
User-Specific Deal Numbers Migration

This migration:
1. Adds user_id column to positions table (links to owner via bot.user_id)
2. Adds user_deal_number column (user-specific sequential deal number)
3. Backfills user_id from bots table (position -> bot -> user)
4. DOES NOT backfill user_deal_number (assigned by trading engine on successful trades)

Deal numbers are assigned by the trading engine when base orders execute successfully.
This aligns with 3Commas behavior where only successful deals get deal numbers.

For existing databases with positions, run the renumbering migration separately:
  ./venv/bin/python migrations/renumber_deal_numbers_successful_only.py

Run with: cd backend && ./venv/bin/python migrations/add_user_deal_numbers.py
"""

import sqlite3

DATABASE_PATH = "trading.db"


def run_migration():
    """Run the user deal numbers migration."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # Step 1: Add user_id column to positions
        print("Adding user_id column to positions...")
        try:
            cursor.execute("ALTER TABLE positions ADD COLUMN user_id INTEGER REFERENCES users(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_positions_user_id ON positions(user_id)")
            print("  - user_id column added to positions")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  - user_id column already exists in positions")
            else:
                raise

        # Step 2: Add user_deal_number column to positions
        print("Adding user_deal_number column to positions...")
        try:
            cursor.execute("ALTER TABLE positions ADD COLUMN user_deal_number INTEGER")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_positions_user_deal_number ON positions(user_deal_number)")
            print("  - user_deal_number column added to positions")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  - user_deal_number column already exists in positions")
            else:
                raise

        # Step 3: Backfill user_id from bots table (position -> bot -> user)
        print("Backfilling user_id from bots table...")
        cursor.execute("""
            UPDATE positions
            SET user_id = (
                SELECT bots.user_id
                FROM bots
                WHERE bots.id = positions.bot_id
            )
            WHERE user_id IS NULL AND bot_id IS NOT NULL
        """)
        positions_updated = cursor.rowcount
        print(f"  - Updated {positions_updated} positions with user_id from bots")

        # Step 4: SKIP backfill - deal numbers should only be assigned to SUCCESSFUL positions
        # Deal numbers will be assigned by the trading engine when base orders execute successfully
        # For existing databases, run migrations/renumber_deal_numbers_successful_only.py separately
        print("Skipping user_deal_number backfill...")
        print("  - Deal numbers will be assigned when positions execute successfully")
        print("  - For existing databases with positions, run:")
        print("    ./venv/bin/python migrations/renumber_deal_numbers_successful_only.py")

        conn.commit()
        print("\nMigration completed successfully!")
        print("\nNote: New positions will automatically get user_id and user_deal_number")
        print("when created via the trading engine.")

    except Exception as e:
        conn.rollback()
        print(f"\nMigration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
