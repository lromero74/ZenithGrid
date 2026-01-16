"""
Migration: Add account_value_snapshots table for historical account value tracking

Creates a new table to store daily snapshots of account values (BTC and USD).
Used for displaying account value chart over time.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path


def get_db_path():
    """Get database path relative to script location"""
    backend_dir = Path(__file__).parent.parent
    return backend_dir / "trading.db"


def run_migration():
    """Add account_value_snapshots table"""
    db_path = get_db_path()

    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return False

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='account_value_snapshots'
        """)
        if cursor.fetchone():
            print("✓ account_value_snapshots table already exists")
            return True

        # Create account_value_snapshots table
        cursor.execute("""
            CREATE TABLE account_value_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                snapshot_date DATETIME NOT NULL,
                total_value_btc REAL NOT NULL DEFAULT 0.0,
                total_value_usd REAL NOT NULL DEFAULT 0.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE (account_id, snapshot_date)
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX idx_account_value_snapshots_account_id
            ON account_value_snapshots(account_id)
        """)
        cursor.execute("""
            CREATE INDEX idx_account_value_snapshots_user_id
            ON account_value_snapshots(user_id)
        """)
        cursor.execute("""
            CREATE INDEX idx_account_value_snapshots_date
            ON account_value_snapshots(snapshot_date)
        """)

        conn.commit()
        print("✓ Created account_value_snapshots table with indexes")
        return True

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    print("Running migration: add_account_value_snapshots")
    success = run_migration()
    exit(0 if success else 1)
