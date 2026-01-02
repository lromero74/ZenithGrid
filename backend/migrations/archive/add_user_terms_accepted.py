"""
Add terms_accepted_at to users table

This migration adds a column to track when users accepted the risk disclaimer/terms.
Users must accept terms before accessing the dashboard.

Run with: cd backend && ./venv/bin/python migrations/add_user_terms_accepted.py
"""

import sqlite3

DATABASE_PATH = "trading.db"


def run_migration():
    """Add terms_accepted_at column to users table."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]

        if "terms_accepted_at" in columns:
            print("Column 'terms_accepted_at' already exists in users table")
            return

        # Add the column
        print("Adding terms_accepted_at column to users table...")
        cursor.execute("""
            ALTER TABLE users ADD COLUMN terms_accepted_at DATETIME
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
