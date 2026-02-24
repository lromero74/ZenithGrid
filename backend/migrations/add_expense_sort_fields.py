"""
Migration: Add expense sort fields

Adds expense_sort_mode to report_goals and sort_order to expense_items
for configurable waterfall sort order.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Add expense_sort_mode to report_goals (idempotent)
    try:
        cursor.execute(
            "ALTER TABLE report_goals ADD COLUMN expense_sort_mode TEXT DEFAULT 'amount_asc'"
        )
        logger.info("Added expense_sort_mode column to report_goals")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("expense_sort_mode column already exists")
        else:
            raise

    # Add sort_order to expense_items (idempotent)
    try:
        cursor.execute(
            "ALTER TABLE expense_items ADD COLUMN sort_order INTEGER DEFAULT 0"
        )
        logger.info("Added sort_order column to expense_items")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("sort_order column already exists")
        else:
            raise

    conn.commit()
    conn.close()
    logger.info("Expense sort fields migration complete")


if __name__ == "__main__":
    run()
