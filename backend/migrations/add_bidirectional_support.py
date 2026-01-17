"""
Database migration: Add bidirectional DCA grid bot support

Adds:
- Bot table: reserved_usd_for_longs, reserved_btc_for_shorts columns
- Position table: direction column and short position tracking fields
- Index on positions.direction for faster queries
"""

import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database path relative to this migration file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")


def migrate():
    """Run migration to add bidirectional DCA support"""
    logger.info("🔄 Starting bidirectional DCA grid bot migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # ===== BOT TABLE CHANGES =====
        logger.info("Adding budget reservation columns to bots table...")

        # Add reserved_usd_for_longs column
        try:
            cursor.execute("""
                ALTER TABLE bots
                ADD COLUMN reserved_usd_for_longs REAL DEFAULT 0.0
            """)
            logger.info("✅ Added reserved_usd_for_longs column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⚠️ Column reserved_usd_for_longs already exists, skipping")
            else:
                raise

        # Add reserved_btc_for_shorts column
        try:
            cursor.execute("""
                ALTER TABLE bots
                ADD COLUMN reserved_btc_for_shorts REAL DEFAULT 0.0
            """)
            logger.info("✅ Added reserved_btc_for_shorts column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⚠️ Column reserved_btc_for_shorts already exists, skipping")
            else:
                raise

        # ===== POSITION TABLE CHANGES =====
        logger.info("Adding direction and short tracking columns to positions table...")

        # Add direction column (default "long" for backward compatibility)
        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN direction TEXT DEFAULT 'long'
            """)
            logger.info("✅ Added direction column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⚠️ Column direction already exists, skipping")
            else:
                raise

        # Add entry_price column (used for both long and short)
        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN entry_price REAL DEFAULT NULL
            """)
            logger.info("✅ Added entry_price column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⚠️ Column entry_price already exists, skipping")
            else:
                raise

        # Add short position tracking columns
        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN short_entry_price REAL DEFAULT NULL
            """)
            logger.info("✅ Added short_entry_price column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⚠️ Column short_entry_price already exists, skipping")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN short_average_sell_price REAL DEFAULT NULL
            """)
            logger.info("✅ Added short_average_sell_price column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⚠️ Column short_average_sell_price already exists, skipping")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN short_total_sold_quote REAL DEFAULT NULL
            """)
            logger.info("✅ Added short_total_sold_quote column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⚠️ Column short_total_sold_quote already exists, skipping")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE positions
                ADD COLUMN short_total_sold_base REAL DEFAULT NULL
            """)
            logger.info("✅ Added short_total_sold_base column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⚠️ Column short_total_sold_base already exists, skipping")
            else:
                raise

        # Create index on direction for faster queries
        logger.info("Creating index on positions.direction...")
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_positions_direction
                ON positions(direction)
            """)
            logger.info("✅ Created index on positions.direction")
        except sqlite3.OperationalError as e:
            logger.info(f"⚠️ Index creation warning: {e}")

        conn.commit()
        logger.info("✅ Bidirectional DCA migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration (reset reservations and direction)"""
    logger.info("🔄 Rolling back bidirectional DCA migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Note: SQLite doesn't support DROP COLUMN directly
        # We can only reset values, not remove columns

        # Reset bot reservations to 0
        cursor.execute("""
            UPDATE bots
            SET reserved_usd_for_longs = 0.0,
                reserved_btc_for_shorts = 0.0
        """)
        logger.info("✅ Reset bot budget reservations to 0")

        # Reset all positions to "long" direction
        cursor.execute("""
            UPDATE positions
            SET direction = 'long'
        """)
        logger.info("✅ Reset all positions to 'long' direction")

        conn.commit()
        logger.info("✅ Bidirectional DCA rollback completed")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Rollback failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
