#!/usr/bin/env python3
"""
Migration: Add previous_indicators field to positions table

Adds previous_indicators column to enable crossing detection
(crossing_above, crossing_below) between check cycles.
"""

import sqlite3
import sys
from pathlib import Path

# Get database path
DB_PATH = Path(__file__).parent.parent / "trading.db"

def migrate():
    """Add previous_indicators column to positions table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print(f"Adding previous_indicators column to positions table...")

        # Add previous_indicators column (JSON stored as TEXT in SQLite)
        cursor.execute("""
            ALTER TABLE positions
            ADD COLUMN previous_indicators TEXT
        """)
        print("✓ Added previous_indicators column")

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
