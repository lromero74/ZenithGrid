#!/usr/bin/env python3
"""
Migration: Add bull flag position tracking fields

Adds fields to support bull flag trading strategy with trailing stop loss
and trailing take profit management.
"""

import sqlite3
import sys
from pathlib import Path

# Get database path
DB_PATH = Path(__file__).parent.parent / "trading.db"


def migrate():
    """Add bull flag tracking fields to positions table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("Adding bull flag position tracking fields...")

        # Add trailing stop loss fields
        print("\nAdding trailing stop loss fields...")
        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN trailing_stop_loss_price REAL
            """)
            print("✓ Added trailing_stop_loss_price column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  trailing_stop_loss_price column already exists")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN trailing_stop_loss_active BOOLEAN DEFAULT 0
            """)
            print("✓ Added trailing_stop_loss_active column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  trailing_stop_loss_active column already exists")
            else:
                raise

        # Add entry-time stop loss and take profit targets
        print("\nAdding entry-time stop/target fields...")
        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN entry_stop_loss REAL
            """)
            print("✓ Added entry_stop_loss column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  entry_stop_loss column already exists")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN entry_take_profit_target REAL
            """)
            print("✓ Added entry_take_profit_target column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  entry_take_profit_target column already exists")
            else:
                raise

        # Add pattern data storage (JSON)
        print("\nAdding pattern data field...")
        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN pattern_data TEXT
            """)
            print("✓ Added pattern_data column (JSON)")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  pattern_data column already exists")
            else:
                raise

        # Add exit reason tracking
        print("\nAdding exit reason field...")
        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN exit_reason TEXT
            """)
            print("✓ Added exit_reason column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  exit_reason column already exists")
            else:
                raise

        conn.commit()
        print("\n✅ Migration completed successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
