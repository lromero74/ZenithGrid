"""
Migration: Add usd_portion_usd and btc_portion_btc to account_value_snapshots

Enables split-view charting of USD-portion vs BTC-portion capital deployment.
Historical snapshots will have NULL values (cannot reconstruct breakdowns).
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for col in ("usd_portion_usd REAL", "btc_portion_btc REAL"):
        col_name = col.split()[0]
        try:
            cursor.execute(
                f"ALTER TABLE account_value_snapshots ADD COLUMN {col}"
            )
            logger.info(f"Added {col_name} column to account_value_snapshots")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info(f"{col_name} column already exists, skipping")
            else:
                raise

    conn.commit()
    conn.close()
