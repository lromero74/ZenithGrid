"""
Database migration: Add income goal fields to report_goals

Adds two new columns:
- income_period: "daily"/"weekly"/"monthly"/"yearly" (for income-type goals)
- lookback_days: Number of days to look back for income calculation (null=all-time)
"""

import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database path relative to this migration file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")

COLUMNS = [
    ("income_period", "TEXT"),
    ("lookback_days", "INTEGER"),
]


def migrate():
    """Run migration to add income goal fields."""
    logger.info("Starting income goal fields migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        for col_name, col_type in COLUMNS:
            try:
                cursor.execute(
                    f"ALTER TABLE report_goals ADD COLUMN {col_name} {col_type}"
                )
                logger.info(f"Added column {col_name} to report_goals")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"Column {col_name} already exists, skipping")
                else:
                    raise

        conn.commit()
        logger.info("Income goal fields migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration — informational only."""
    logger.info(
        "Rollback: SQLite does not support DROP COLUMN easily. "
        "To undo, recreate report_goals table without income_period/lookback_days."
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
