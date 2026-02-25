"""
Migration: Add unrealized_pnl_usd, unrealized_pnl_btc, btc_usd_price
to account_value_snapshots.

Enables native-currency accounting for report deposits/withdrawals.
Historical snapshots will have NULL values.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for col in (
        "unrealized_pnl_usd REAL",
        "unrealized_pnl_btc REAL",
        "btc_usd_price REAL",
    ):
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
