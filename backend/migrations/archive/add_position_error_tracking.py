#!/usr/bin/env python3
"""
Migration: Add error tracking fields to positions table

Adds last_error_message and last_error_timestamp columns to enable
error display in UI (like 3Commas).
"""

import sqlite3
import sys
from pathlib import Path

# Get database path
DB_PATH = Path(__file__).parent.parent / "trading.db"

def migrate():
    """Add error tracking columns to positions table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print(f"Adding error tracking columns to positions table...")

        # Add last_error_message column
        cursor.execute("""
            ALTER TABLE positions
            ADD COLUMN last_error_message TEXT
        """)
        print("✓ Added last_error_message column")

        # Add last_error_timestamp column
        cursor.execute("""
            ALTER TABLE positions
            ADD COLUMN last_error_timestamp DATETIME
        """)
        print("✓ Added last_error_timestamp column")

        conn.commit()
        print("\n✅ Migration completed successfully!")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"⚠️  Columns already exist - migration already applied")
        else:
            print(f"❌ Error: {e}")
            sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
