"""
Database migration: Add perpetual futures (INTX) support

Adds:
- Account: perps_portfolio_uuid, default_leverage, margin_type
- Bot: market_type
- Position: product_type, leverage, perps_margin_type, liquidation_price,
  funding_fees_total, tp/sl order IDs, tp/sl prices, unrealized_pnl
"""

import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database path relative to this migration file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")


# Column definitions: (table, column_name, column_type_and_default)
COLUMNS_TO_ADD = [
    # Account table - perpetual futures configuration
    ("accounts", "perps_portfolio_uuid", "TEXT DEFAULT NULL"),
    ("accounts", "default_leverage", "INTEGER DEFAULT 1"),
    ("accounts", "margin_type", "TEXT DEFAULT 'CROSS'"),

    # Bot table - market type
    ("bots", "market_type", "TEXT DEFAULT 'spot'"),

    # Position table - perpetual futures fields
    ("positions", "product_type", "TEXT DEFAULT 'spot'"),
    ("positions", "leverage", "INTEGER DEFAULT NULL"),
    ("positions", "perps_margin_type", "TEXT DEFAULT NULL"),
    ("positions", "liquidation_price", "REAL DEFAULT NULL"),
    ("positions", "funding_fees_total", "REAL DEFAULT 0.0"),
    ("positions", "tp_order_id", "TEXT DEFAULT NULL"),
    ("positions", "sl_order_id", "TEXT DEFAULT NULL"),
    ("positions", "tp_price", "REAL DEFAULT NULL"),
    ("positions", "sl_price", "REAL DEFAULT NULL"),
    ("positions", "unrealized_pnl", "REAL DEFAULT NULL"),
]


def migrate():
    """Run migration to add perpetual futures support"""
    logger.info("Starting perpetual futures migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        for table, column, col_type in COLUMNS_TO_ADD:
            logger.info(f"Adding {column} to {table}...")
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                logger.info(f"  Added {column}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"  Column {column} already exists, skipping")
                else:
                    raise

        conn.commit()
        logger.info("Perpetual futures migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration (SQLite doesn't support DROP COLUMN easily)"""
    logger.info("Rollback: No destructive rollback for perpetual futures columns.")
    logger.info("Columns will remain but are unused if feature is disabled.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
