"""
Database migration: Add original_type column to account_transfers

Preserves the Coinbase transaction type (cardspend, fiat_withdrawal, etc.)
so reports can show descriptive labels instead of generic "Deposit"/"Withdrawal".

Also backfills existing records with heuristic mapping.
"""

import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")


def migrate():
    """Add original_type column and backfill existing records."""
    logger.info("Starting add_transfer_original_type migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Add the column
        try:
            cursor.execute(
                "ALTER TABLE account_transfers ADD COLUMN original_type TEXT"
            )
            logger.info("Added original_type column to account_transfers")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("original_type column already exists, skipping ALTER")
            else:
                raise

        # Backfill existing coinbase_api records with heuristic mapping:
        # Card spends: BTC withdrawals with small USD amounts (all recent cardspend txns)
        # Plus the one USD cardspend on Feb 19
        cursor.execute("""
            UPDATE account_transfers
            SET original_type = 'cardspend'
            WHERE source = 'coinbase_api'
              AND transfer_type = 'withdrawal'
              AND currency = 'BTC'
              AND original_type IS NULL
              AND amount_usd < 200
        """)
        cardspend_btc = cursor.rowcount
        logger.info(f"Backfilled {cardspend_btc} BTC card spend records")

        # USD card spend (Feb 19 small withdrawal)
        cursor.execute("""
            UPDATE account_transfers
            SET original_type = 'cardspend'
            WHERE source = 'coinbase_api'
              AND transfer_type = 'withdrawal'
              AND currency = 'USD'
              AND original_type IS NULL
              AND amount_usd < 200
              AND occurred_at >= '2026-02-01'
        """)
        cardspend_usd = cursor.rowcount
        logger.info(f"Backfilled {cardspend_usd} USD card spend records")

        # Fiat deposits (USD deposits)
        cursor.execute("""
            UPDATE account_transfers
            SET original_type = 'fiat_deposit'
            WHERE source = 'coinbase_api'
              AND transfer_type = 'deposit'
              AND currency = 'USD'
              AND original_type IS NULL
        """)
        fiat_dep = cursor.rowcount
        logger.info(f"Backfilled {fiat_dep} fiat deposit records")

        # Fiat withdrawals (USD withdrawals >= $100, not card spends)
        cursor.execute("""
            UPDATE account_transfers
            SET original_type = 'fiat_withdrawal'
            WHERE source = 'coinbase_api'
              AND transfer_type = 'withdrawal'
              AND currency = 'USD'
              AND original_type IS NULL
              AND amount_usd >= 100
        """)
        fiat_wth = cursor.rowcount
        logger.info(f"Backfilled {fiat_wth} fiat withdrawal records")

        # Crypto deposits (BTC deposits = staking rewards / incoming sends)
        cursor.execute("""
            UPDATE account_transfers
            SET original_type = 'send'
            WHERE source = 'coinbase_api'
              AND transfer_type = 'deposit'
              AND currency = 'BTC'
              AND original_type IS NULL
        """)
        crypto_dep = cursor.rowcount
        logger.info(f"Backfilled {crypto_dep} crypto deposit records")

        conn.commit()
        total = cardspend_btc + cardspend_usd + fiat_dep + fiat_wth + crypto_dep
        logger.info(
            f"add_transfer_original_type migration completed! "
            f"Backfilled {total} records."
        )

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback — SQLite can't drop columns, but we can clear the data."""
    logger.info("Rollback: clearing original_type values")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE account_transfers SET original_type = NULL")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
