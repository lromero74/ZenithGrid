"""
Add simulate_slippage=true to strategy_config for all paper trading bots.

Paper trading bots should use order book VWAP fills by default for
realistic slippage simulation.
"""
import json
import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")


def migrate():
    """Set simulate_slippage: true in strategy_config for all paper trading bots."""
    logger.info("Starting simulate_slippage migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT b.id, b.strategy_config FROM bots b "
            "JOIN accounts a ON b.account_id = a.id "
            "WHERE a.is_paper_trading = 1"
        )
        rows = cursor.fetchall()
        updated = 0

        for row in rows:
            bot_id = row[0]
            config_raw = row[1]

            try:
                config = json.loads(config_raw) if config_raw else {}
            except (json.JSONDecodeError, TypeError):
                config = {}

            if "simulate_slippage" not in config:
                config["simulate_slippage"] = True
                cursor.execute(
                    "UPDATE bots SET strategy_config = ? WHERE id = ?",
                    (json.dumps(config), bot_id),
                )
                updated += 1

        conn.commit()

        if updated:
            logger.info(f"Set simulate_slippage=true for {updated} paper trading bots")
        else:
            logger.info("All paper trading bots already have simulate_slippage configured")

        logger.info("Migration completed successfully")

    except Exception as e:
        conn.rollback()
        if "no such column" in str(e).lower() or "no such table" in str(e).lower():
            logger.info(f"Skipping migration (table/column not ready): {e}")
        else:
            raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
