"""
Database migration: Add prop firm support (HyroTrader / FTMO)

Adds to accounts table:
- prop_firm, prop_firm_config, prop_daily_drawdown_pct,
  prop_total_drawdown_pct, prop_initial_deposit

Creates new table:
- prop_firm_state (kill switch, equity tracking, daily reset)
"""

import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database path relative to this migration file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")

# Account table columns to add
ACCOUNT_COLUMNS = [
    ("accounts", "prop_firm", "TEXT DEFAULT NULL"),
    ("accounts", "prop_firm_config", "TEXT DEFAULT NULL"),
    ("accounts", "prop_daily_drawdown_pct", "REAL DEFAULT NULL"),
    ("accounts", "prop_total_drawdown_pct", "REAL DEFAULT NULL"),
    ("accounts", "prop_initial_deposit", "REAL DEFAULT NULL"),
]

# SQL for prop_firm_state table
CREATE_PROP_FIRM_STATE = """
CREATE TABLE IF NOT EXISTS prop_firm_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL UNIQUE,
    initial_deposit REAL NOT NULL DEFAULT 0.0,
    daily_start_equity REAL,
    daily_start_timestamp DATETIME,
    current_equity REAL,
    current_equity_timestamp DATETIME,
    is_killed BOOLEAN DEFAULT 0,
    kill_reason TEXT,
    kill_timestamp DATETIME,
    daily_pnl REAL DEFAULT 0.0,
    total_pnl REAL DEFAULT 0.0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
)
"""

# SQL for prop_firm_equity_snapshots table (time-series)
CREATE_EQUITY_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS prop_firm_equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    equity REAL NOT NULL,
    daily_drawdown_pct REAL DEFAULT 0.0,
    total_drawdown_pct REAL DEFAULT 0.0,
    daily_pnl REAL DEFAULT 0.0,
    is_killed BOOLEAN DEFAULT 0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
)
"""


def migrate():
    """Run migration to add prop firm support"""
    logger.info("Starting prop firm support migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Add columns to accounts table
        for table, column, col_type in ACCOUNT_COLUMNS:
            logger.info(f"Adding {column} to {table}...")
            try:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                )
                logger.info(f"  Added {column}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"  Column {column} already exists, skipping")
                else:
                    raise

        # Create prop_firm_state table
        logger.info("Creating prop_firm_state table...")
        cursor.execute(CREATE_PROP_FIRM_STATE)
        logger.info("  Created prop_firm_state table")

        # Create prop_firm_equity_snapshots table
        logger.info("Creating prop_firm_equity_snapshots table...")
        cursor.execute(CREATE_EQUITY_SNAPSHOTS)
        logger.info("  Created prop_firm_equity_snapshots table")

        # Create indexes
        try:
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_prop_firm_state_account_id "
                "ON prop_firm_state (account_id)"
            )
            logger.info("  Created index on prop_firm_state.account_id")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_prop_equity_snap_account_ts "
                "ON prop_firm_equity_snapshots (account_id, timestamp)"
            )
            logger.info("  Created index on equity_snapshots(account_id, timestamp)")
        except sqlite3.OperationalError:
            pass

        conn.commit()
        logger.info("Prop firm support migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration (informational only)"""
    logger.info(
        "Rollback: No destructive rollback for prop firm columns."
    )
    logger.info(
        "Columns will remain but are unused if feature is disabled."
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
