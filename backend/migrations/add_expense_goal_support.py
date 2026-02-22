"""
Migration: Add expense goal support

Creates expense_items table and adds expense_period/tax_withholding_pct
columns to report_goals.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create expense_items table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expense_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL REFERENCES report_goals(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            frequency TEXT NOT NULL,
            frequency_n INTEGER,
            frequency_anchor TEXT,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_expense_items_goal_id "
        "ON expense_items(goal_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_expense_items_user_id "
        "ON expense_items(user_id)"
    )

    # Add expense_period to report_goals (idempotent)
    try:
        cursor.execute(
            "ALTER TABLE report_goals ADD COLUMN expense_period TEXT"
        )
        logger.info("Added expense_period column to report_goals")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("expense_period column already exists")
        else:
            raise

    # Add tax_withholding_pct to report_goals (idempotent)
    try:
        cursor.execute(
            "ALTER TABLE report_goals ADD COLUMN tax_withholding_pct REAL DEFAULT 0"
        )
        logger.info("Added tax_withholding_pct column to report_goals")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("tax_withholding_pct column already exists")
        else:
            raise

    conn.commit()
    conn.close()
    logger.info("Expense goal support migration complete")


if __name__ == "__main__":
    run()
