"""
Migration: Add login_url column to expense_items

Stores an optional URL to the payment/login page for the expense.
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
        cursor.execute("ALTER TABLE expense_items ADD COLUMN login_url TEXT")
        logger.info("Added login_url column to expense_items")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("login_url column already exists, skipping")
        else:
            raise

    conn.commit()
    conn.close()
