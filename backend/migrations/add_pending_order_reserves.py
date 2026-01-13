"""
Migration: Add capital reservation tracking to pending_orders table

This migration adds two new columns to track capital reserved in pending orders,
which is critical for grid trading bots that place many simultaneous limit orders.

NEW COLUMNS:
- reserved_amount_quote: Capital reserved in quote currency (BTC, USD, etc.)
- reserved_amount_base: Capital reserved in base currency (ETH, ADA, etc.)

For buy orders:  reserved_amount_quote = size * limit_price
For sell orders: reserved_amount_base = size

These fields allow the system to calculate truly available balances by subtracting:
  1. Capital locked in open positions (total_quote_spent)
  2. Capital locked in pending orders (reserved_amount_quote/base)

This prevents grid bots from over-allocating capital and conflicting with other strategies.
"""

import sqlite3
import sys
import os

# Change to backend directory so database path resolves correctly
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

DB_PATH = "trading.db"


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("🔄 Starting migration: Add capital reservation to pending_orders...")

    try:
        # Check if migration already applied
        cursor.execute("PRAGMA table_info(pending_orders)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'reserved_amount_quote' in columns:
            print("✅ Migration already applied (pending_orders has reserved_amount_quote)")
            conn.close()
            return

        # Add reserved_amount_quote column (for buy orders)
        print("  Adding reserved_amount_quote column...")
        cursor.execute("""
            ALTER TABLE pending_orders
            ADD COLUMN reserved_amount_quote REAL DEFAULT 0.0
        """)

        # Add reserved_amount_base column (for sell orders)
        print("  Adding reserved_amount_base column...")
        cursor.execute("""
            ALTER TABLE pending_orders
            ADD COLUMN reserved_amount_base REAL DEFAULT 0.0
        """)

        # For existing pending buy orders, calculate reserved_amount_quote
        # reserved_amount_quote = quote_amount (which is already the reserved capital)
        print("  Populating reserved_amount_quote for existing buy orders...")
        cursor.execute("""
            UPDATE pending_orders
            SET reserved_amount_quote = quote_amount
            WHERE side = 'BUY' AND status = 'pending'
        """)

        # For existing pending sell orders, calculate reserved_amount_base
        # For sell orders, base_amount might be null, use quote_amount / limit_price as estimate
        print("  Populating reserved_amount_base for existing sell orders...")
        cursor.execute("""
            UPDATE pending_orders
            SET reserved_amount_base = CASE
                WHEN base_amount IS NOT NULL THEN base_amount
                WHEN limit_price > 0 THEN quote_amount / limit_price
                ELSE 0
            END
            WHERE side = 'SELL' AND status = 'pending'
        """)

        # Commit all changes
        conn.commit()
        print("✅ Migration completed successfully!")
        print("   - Added reserved_amount_quote column")
        print("   - Added reserved_amount_base column")
        print("   - Populated values for existing pending orders")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


def rollback():
    """
    Rollback migration by recreating pending_orders table without reserved columns.

    Note: SQLite doesn't support DROP COLUMN directly, so we need to recreate the table.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("🔄 Rolling back migration: Remove capital reservation columns...")

    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(pending_orders)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'reserved_amount_quote' not in columns:
            print("✅ Rollback not needed (columns don't exist)")
            conn.close()
            return

        # Step 1: Create new table without reserved columns
        print("  Creating pending_orders table without reserved columns...")
        cursor.execute("""
            CREATE TABLE pending_orders_old (
                id INTEGER NOT NULL PRIMARY KEY,
                position_id INTEGER NOT NULL,
                bot_id INTEGER NOT NULL,
                order_id VARCHAR NOT NULL UNIQUE,
                product_id VARCHAR NOT NULL,
                side VARCHAR NOT NULL,
                order_type VARCHAR NOT NULL,
                limit_price REAL NOT NULL,
                quote_amount REAL NOT NULL,
                base_amount REAL,
                trade_type VARCHAR NOT NULL,
                status VARCHAR NOT NULL DEFAULT 'pending',
                created_at DATETIME NOT NULL,
                filled_at DATETIME,
                canceled_at DATETIME,
                filled_price REAL,
                filled_quote_amount REAL,
                filled_base_amount REAL,
                fills JSON,
                remaining_base_amount REAL,
                time_in_force VARCHAR NOT NULL DEFAULT 'gtc',
                end_time DATETIME,
                is_manual INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(position_id) REFERENCES positions (id),
                FOREIGN KEY(bot_id) REFERENCES bots (id)
            )
        """)

        # Step 2: Copy data (excluding reserved columns)
        print("  Copying data...")
        cursor.execute("""
            INSERT INTO pending_orders_old (
                id, position_id, bot_id, order_id, product_id, side, order_type,
                limit_price, quote_amount, base_amount, trade_type, status,
                created_at, filled_at, canceled_at, filled_price, filled_quote_amount,
                filled_base_amount, fills, remaining_base_amount, time_in_force,
                end_time, is_manual
            )
            SELECT
                id, position_id, bot_id, order_id, product_id, side, order_type,
                limit_price, quote_amount, base_amount, trade_type, status,
                created_at, filled_at, canceled_at, filled_price, filled_quote_amount,
                filled_base_amount, fills, remaining_base_amount, time_in_force,
                end_time, is_manual
            FROM pending_orders
        """)

        # Step 3: Drop old table and rename
        print("  Replacing table...")
        cursor.execute("DROP TABLE pending_orders")
        cursor.execute("ALTER TABLE pending_orders_old RENAME TO pending_orders")

        # Step 4: Recreate indexes
        cursor.execute("CREATE INDEX ix_pending_orders_id ON pending_orders (id)")
        cursor.execute("CREATE UNIQUE INDEX ix_pending_orders_order_id ON pending_orders (order_id)")

        conn.commit()
        print("✅ Rollback completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Rollback failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
