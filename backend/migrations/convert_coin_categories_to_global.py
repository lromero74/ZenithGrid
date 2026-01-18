"""
Database migration: Convert user-specific coin categorizations to global entries

Problem: Early versions of setup.py incorrectly created coin categorizations
with user_id set to the first admin user's ID. The /api/blacklist/ endpoint
only returns global entries (user_id IS NULL), causing Settings page to show
empty categorizations even though data exists in database.

Fix: Convert all user-specific coin categorizations to global entries (user_id = NULL)
so they're visible to all users and manageable by admins.
"""

import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database path relative to this migration file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")


def migrate():
    """Convert user-specific coin categorizations to global entries"""
    logger.info("🔄 Starting coin categorization global conversion migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check how many user-specific categorizations exist
        cursor.execute("""
            SELECT COUNT(*) FROM blacklisted_coins
            WHERE user_id IS NOT NULL
        """)
        user_specific_count = cursor.fetchone()[0]

        if user_specific_count == 0:
            logger.info("✅ No user-specific categorizations found - all entries are already global")
            conn.close()
            return

        logger.info(f"Found {user_specific_count} user-specific coin categorizations to convert")

        # Check if there are any global categorizations (to avoid duplicates)
        cursor.execute("""
            SELECT COUNT(*) FROM blacklisted_coins
            WHERE user_id IS NULL
        """)
        global_count = cursor.fetchone()[0]

        if global_count > 0:
            logger.warning(f"⚠️ Found {global_count} existing global categorizations")
            logger.info("Will preserve global entries and delete user-specific duplicates")

            # Delete user-specific entries that would conflict with global ones
            cursor.execute("""
                DELETE FROM blacklisted_coins
                WHERE user_id IS NOT NULL
                AND symbol IN (
                    SELECT symbol FROM blacklisted_coins WHERE user_id IS NULL
                )
            """)
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                logger.info(f"✅ Deleted {deleted_count} duplicate user-specific entries")

        # Convert remaining user-specific entries to global
        cursor.execute("""
            UPDATE blacklisted_coins
            SET user_id = NULL
            WHERE user_id IS NOT NULL
        """)
        converted_count = cursor.rowcount

        if converted_count > 0:
            logger.info(f"✅ Converted {converted_count} user-specific categorizations to global entries")
        else:
            logger.info("No conversions needed (entries were duplicates)")

        # Verify final state
        cursor.execute("SELECT COUNT(*) FROM blacklisted_coins WHERE user_id IS NULL")
        final_global_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM blacklisted_coins WHERE user_id IS NOT NULL")
        final_user_count = cursor.fetchone()[0]

        logger.info(f"📊 Final state: {final_global_count} global entries, {final_user_count} user-specific entries")

        conn.commit()
        logger.info("✅ Coin categorization global conversion migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration (not applicable - cannot restore original user_id values)"""
    logger.warning("⚠️ This migration cannot be rolled back")
    logger.warning("Original user_id values were not preserved during conversion")
    logger.warning("If you need to undo this, restore from a backup taken before migration")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
