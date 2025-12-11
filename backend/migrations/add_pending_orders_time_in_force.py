"""
Migration: Add time_in_force support to pending_orders table

Adds:
- time_in_force: "gtc" (Good 'til Cancelled) or "gtd" (Good 'til Date)
- end_time: DateTime for GTD orders to expire
- is_manual: Boolean to distinguish manual limit close from automated bot orders
"""

import sqlite3
from pathlib import Path


def run_migration():
    """Add time_in_force columns to pending_orders table"""
    db_path = Path(__file__).parent.parent / "trading.db"

    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if time_in_force column already exists
        cursor.execute("PRAGMA table_info(pending_orders)")
        columns = [col[1] for col in cursor.fetchall()]

        if "time_in_force" in columns:
            print("⚠️  Column time_in_force already exists - migration already applied")
            return

        # Add time_in_force column (default gtc for existing orders)
        cursor.execute("""
            ALTER TABLE pending_orders
            ADD COLUMN time_in_force VARCHAR NOT NULL DEFAULT 'gtc'
        """)
        print("   - Added time_in_force column")

        # Add end_time column for GTD orders
        cursor.execute("""
            ALTER TABLE pending_orders
            ADD COLUMN end_time DATETIME
        """)
        print("   - Added end_time column")

        # Add is_manual column (default False for existing orders - they're automated)
        cursor.execute("""
            ALTER TABLE pending_orders
            ADD COLUMN is_manual BOOLEAN NOT NULL DEFAULT 0
        """)
        print("   - Added is_manual column")

        conn.commit()
        print("✅ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
