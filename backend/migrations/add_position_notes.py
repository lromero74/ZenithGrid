#!/usr/bin/env python3
"""
Migration: Add notes field to positions table

Adds notes column to enable user notes on positions (like 3Commas).
"""

import sqlite3
import sys
from pathlib import Path

# Get database path
DB_PATH = Path(__file__).parent.parent / "trading.db"

def migrate():
    """Add notes column to positions table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print(f"Adding notes column to positions table...")

        # Add notes column
        cursor.execute("""
            ALTER TABLE positions
            ADD COLUMN notes TEXT
        """)
        print("✓ Added notes column")

        conn.commit()
        print("\n✅ Migration completed successfully!")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"⚠️  Column already exists - migration already applied")
        else:
            print(f"❌ Error: {e}")
            sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
