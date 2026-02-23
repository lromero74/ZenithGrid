"""
Migration: Add due_month column to expense_items

Stores the month (1-12) when an expense is due, for frequencies
that span multiple months (quarterly, semi_annual, yearly).
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
        cursor.execute("ALTER TABLE expense_items ADD COLUMN due_month INTEGER")
        logger.info("Added due_month column to expense_items")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("due_month column already exists, skipping")
        else:
            raise

    conn.commit()
    conn.close()
