"""
Migration: Add user_category and retention_days columns to user_source_subscriptions.

user_category: Per-user category override for a source (nullable).
retention_days: Per-user visibility filter — how many days of articles to show (nullable, query-time only).

Idempotent: Safe to run multiple times.
"""

import logging
import os

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


async def run(db_session):
    """Run migration using async session (called by update.py)."""
    import aiosqlite

    db_path = DB_PATH
    async with aiosqlite.connect(db_path) as db:
        # Add user_category column
        try:
            await db.execute(
                "ALTER TABLE user_source_subscriptions ADD COLUMN user_category TEXT"
            )
            logger.info("Added user_category column to user_source_subscriptions")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                logger.debug("user_category column already exists on user_source_subscriptions")
            else:
                logger.warning(f"Could not add user_category to user_source_subscriptions: {e}")

        # Add retention_days column
        try:
            await db.execute(
                "ALTER TABLE user_source_subscriptions ADD COLUMN retention_days INTEGER"
            )
            logger.info("Added retention_days column to user_source_subscriptions")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                logger.debug("retention_days column already exists on user_source_subscriptions")
            else:
                logger.warning(f"Could not add retention_days to user_source_subscriptions: {e}")

        await db.commit()
        logger.info("Migration complete: user_source_subscriptions now has user_category and retention_days")
