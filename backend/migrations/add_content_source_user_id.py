"""
Migration: Add user_id column to content_sources for custom source ownership.

Before: Custom sources (is_system=False) have no owner — any user can delete any custom source.
After:  Custom sources have a user_id linking to their creator.

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
        # Add user_id column to content_sources (nullable, for system sources)
        try:
            await db.execute(
                "ALTER TABLE content_sources ADD COLUMN user_id INTEGER REFERENCES users(id)"
            )
            logger.info("Added user_id column to content_sources")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                logger.debug("user_id column already exists on content_sources")
            else:
                logger.warning(f"Could not add user_id to content_sources: {e}")

        # Add index for query performance
        try:
            await db.execute(
                "CREATE INDEX IF NOT EXISTS ix_content_sources_user_id ON content_sources(user_id)"
            )
            logger.info("Created index ix_content_sources_user_id")
        except Exception as e:
            logger.debug(f"Index may already exist: {e}")

        await db.commit()
        logger.info("Migration complete: content_sources now has user_id for custom source ownership")
