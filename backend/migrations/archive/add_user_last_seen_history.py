"""
Add last_seen_history_count to users table

This migration adds a column to track the last seen history count per user,
enabling the "new items" badge in the History tab to persist across sessions.

Run with: cd backend && ./venv/bin/python migrations/add_user_last_seen_history.py
"""

import sqlite3

DATABASE_PATH = "trading.db"


def run_migration():
    """Add last_seen_history_count column to users table."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]

        if "last_seen_history_count" in columns:
            print("Column 'last_seen_history_count' already exists in users table")
            return

        # Add the column
        print("Adding last_seen_history_count column to users table...")
        cursor.execute("""
            ALTER TABLE users ADD COLUMN last_seen_history_count INTEGER DEFAULT 0
        """)

        conn.commit()
        print("Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
