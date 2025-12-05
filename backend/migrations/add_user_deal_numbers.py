"""
User-Specific Deal Numbers Migration

This migration:
1. Adds user_id column to positions table (links to owner via bot.user_id)
2. Adds user_deal_number column (user-specific sequential deal number)
3. Backfills user_id from bots table (position -> bot -> user)
4. Backfills user_deal_number by ordering positions by opened_at per user

The user_deal_number starts at 1 for each user and increments for each new position.
This provides user-friendly deal numbers instead of global auto-increment IDs.

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

        # Step 4: Backfill user_deal_number
        # For each user, assign sequential numbers ordered by opened_at
        print("Backfilling user_deal_number...")

        # Get all distinct user_ids from positions
        cursor.execute("SELECT DISTINCT user_id FROM positions WHERE user_id IS NOT NULL")
        user_ids = [row[0] for row in cursor.fetchall()]

        total_updated = 0
        for user_id in user_ids:
            # Get all positions for this user ordered by opened_at
            cursor.execute("""
                SELECT id FROM positions
                WHERE user_id = ?
                ORDER BY opened_at ASC
            """, (user_id,))
            position_ids = [row[0] for row in cursor.fetchall()]

            # Assign sequential deal numbers
            for deal_number, position_id in enumerate(position_ids, start=1):
                cursor.execute("""
                    UPDATE positions
                    SET user_deal_number = ?
                    WHERE id = ?
                """, (deal_number, position_id))
                total_updated += 1

            print(f"  - User {user_id}: assigned deal numbers 1-{len(position_ids)}")

        print(f"  - Total positions with user_deal_number: {total_updated}")

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
