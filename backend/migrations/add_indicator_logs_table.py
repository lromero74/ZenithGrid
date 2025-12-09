"""
Migration: Add indicator_logs table for indicator condition evaluation logging

This adds support for logging indicator-based condition evaluations,
similar to ai_bot_logs but for traditional indicators (RSI, MACD, BB%, etc.)
"""

import sqlite3
from pathlib import Path


def run_migration():
    """Add indicator_logs table for logging condition evaluations"""
    db_path = Path(__file__).parent.parent / "trading.db"

    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='indicator_logs'")
        if cursor.fetchone():
            print("Table indicator_logs already exists - migration already applied")
            return

        # Create indicator_logs table
        cursor.execute("""
            CREATE TABLE indicator_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

                -- What was evaluated
                product_id VARCHAR NOT NULL,
                phase VARCHAR NOT NULL,

                -- Overall result
                conditions_met BOOLEAN NOT NULL,

                -- Detailed condition results (JSON)
                conditions_detail JSON NOT NULL,

                -- Indicator snapshot (JSON)
                indicators_snapshot JSON,

                -- Current price
                current_price FLOAT,

                FOREIGN KEY (bot_id) REFERENCES bots(id)
            )
        """)

        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_indicator_logs_bot_id ON indicator_logs (bot_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_indicator_logs_timestamp ON indicator_logs (timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_indicator_logs_product_id ON indicator_logs (product_id)")

        conn.commit()
        print("Migration completed successfully!")
        print("   - Created indicator_logs table")
        print("   - Added indexes for bot_id, timestamp, product_id")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
