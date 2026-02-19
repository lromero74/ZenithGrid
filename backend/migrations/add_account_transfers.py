"""
Database migration: Add account_transfers table

Tracks deposits and withdrawals from Coinbase for accurate P&L calculation.
Distinguishes real trading gains from capital injections/withdrawals.
"""

import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database path relative to this migration file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")


def migrate():
    """Run migration to create account_transfers table."""
    logger.info("Starting account_transfers migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account_transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                external_id TEXT UNIQUE,
                transfer_type TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                amount_usd REAL,
                occurred_at DATETIME NOT NULL,
                source TEXT DEFAULT 'coinbase_api',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
        """)
        logger.info("Created account_transfers table (or already exists)")

        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_account_transfers_user_id
            ON account_transfers(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_account_transfers_account_id
            ON account_transfers(account_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_account_transfers_occurred_at
            ON account_transfers(occurred_at)
        """)
        logger.info("Created indexes on account_transfers")

        conn.commit()
        logger.info("account_transfers migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration — drop the table."""
    logger.info("Rollback: DROP TABLE account_transfers")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DROP TABLE IF EXISTS account_transfers")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
