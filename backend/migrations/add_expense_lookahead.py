"""
Migration: Add show_expense_lookahead column to report_schedules

Enables the expense goal lookahead feature that shows upcoming expenses
from the first ~15 days of the next period as a greyed-out preview.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "ALTER TABLE report_schedules ADD COLUMN "
            "show_expense_lookahead INTEGER DEFAULT 1"
        )
        logger.info("Added show_expense_lookahead column to report_schedules")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("show_expense_lookahead column already exists, skipping")
        else:
            raise

    conn.commit()
    conn.close()
