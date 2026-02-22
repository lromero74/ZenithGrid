"""
Migration: Add due_day column to expense_items

Stores the day of month (1-31) when an expense is due.
-1 means last day of month.
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
        cursor.execute("ALTER TABLE expense_items ADD COLUMN due_day INTEGER")
        logger.info("Added due_day column to expense_items")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("due_day column already exists, skipping")
        else:
            raise

    conn.commit()
    conn.close()
