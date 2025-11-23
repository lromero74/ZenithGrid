#!/usr/bin/env python3
"""
Migration: Add limit order close tracking fields

Adds fields to support closing positions via limit orders with partial fill tracking.
"""

import sqlite3
import sys
from pathlib import Path

# Get database path
DB_PATH = Path(__file__).parent.parent / "trading.db"

def migrate():
    """Add limit close tracking fields to positions and pending_orders tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("Adding limit close tracking fields...")

        # Add fields to positions table
        print("\nUpdating positions table...")
        cursor.execute("""
            ALTER TABLE positions
            ADD COLUMN closing_via_limit BOOLEAN DEFAULT 0
        """)
        print("✓ Added closing_via_limit column")

        cursor.execute("""
            ALTER TABLE positions
            ADD COLUMN limit_close_order_id TEXT
        """)
        print("✓ Added limit_close_order_id column")

        # Add partial fill tracking fields to pending_orders table
        print("\nUpdating pending_orders table...")
        cursor.execute("""
            ALTER TABLE pending_orders
            ADD COLUMN fills TEXT
        """)
        print("✓ Added fills column (JSON array)")

        cursor.execute("""
            ALTER TABLE pending_orders
            ADD COLUMN remaining_base_amount REAL
        """)
        print("✓ Added remaining_base_amount column")

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
