"""
Migration: Add percent-of-income columns to expense_items

Supports Donations category where amount is a percentage of income
rather than a fixed dollar amount.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    columns = [
        ("amount_mode", "TEXT DEFAULT 'fixed'"),
        ("percent_of_income", "REAL"),
        ("percent_basis", "TEXT"),
    ]

    for col_name, col_type in columns:
        try:
            cursor.execute(
                f"ALTER TABLE expense_items ADD COLUMN {col_name} {col_type}"
            )
            logger.info("Added %s column to expense_items", col_name)
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("%s column already exists, skipping", col_name)
            else:
                raise

    conn.commit()
    conn.close()
