"""
Migration: Add pending_orders table for limit order tracking

This adds support for tracking pending limit orders placed by DCA strategies.
"""

import sqlite3
from pathlib import Path

def run_migration():
    """Add pending_orders table to track unfilled limit orders"""
    db_path = Path(__file__).parent.parent / "trading.db"

    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Create pending_orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER NOT NULL,
                bot_id INTEGER NOT NULL,

                -- Order details
                order_id VARCHAR NOT NULL UNIQUE,
                product_id VARCHAR NOT NULL,
                side VARCHAR NOT NULL,
                order_type VARCHAR NOT NULL,

                -- Amounts
                limit_price FLOAT NOT NULL,
                quote_amount FLOAT NOT NULL,
                base_amount FLOAT,

                -- Order purpose
                trade_type VARCHAR NOT NULL,

                -- Status tracking
                status VARCHAR NOT NULL DEFAULT 'pending',
                created_at DATETIME NOT NULL,
                filled_at DATETIME,
                canceled_at DATETIME,

                -- Filled details
                filled_price FLOAT,
                filled_quote_amount FLOAT,
                filled_base_amount FLOAT,

                FOREIGN KEY (position_id) REFERENCES positions(id),
                FOREIGN KEY (bot_id) REFERENCES bots(id)
            )
        """)

        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_pending_orders_id ON pending_orders (id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_pending_orders_order_id ON pending_orders (order_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_pending_orders_position_id ON pending_orders (position_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_pending_orders_status ON pending_orders (status)")

        conn.commit()
        print("✅ Migration completed successfully!")
        print("   - Created pending_orders table")
        print("   - Added indexes for performance")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
