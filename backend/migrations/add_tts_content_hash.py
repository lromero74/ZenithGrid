"""
Migration: Add content_hash column to article_tts table.

Allows cache invalidation when article text changes (e.g., retry
fetches full content after initial summary-only TTS was cached).

Idempotent: Safe to run multiple times.
"""

import logging
import os

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "trading.db"
)


async def run(db_session):
    """Run migration using async session (called by update.py)."""
    import aiosqlite

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "ALTER TABLE article_tts ADD COLUMN content_hash TEXT"
            )
            await db.commit()
            logger.info(
                "Added content_hash column to article_tts"
            )
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                logger.debug(
                    "article_tts.content_hash already exists"
                )
            else:
                logger.warning(
                    f"Could not add content_hash to article_tts: {e}"
                )
