"""
Migration: Add source_id FK to news_articles and video_articles.

Links articles/videos to their ContentSource via a proper foreign key,
replacing the string-only source field. Backfills existing rows by
matching source string to content_sources.source_key.

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
        # Add source_id column to news_articles
        try:
            await db.execute(
                "ALTER TABLE news_articles ADD COLUMN source_id INTEGER REFERENCES content_sources(id)"
            )
            logger.info("Added source_id column to news_articles")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                logger.debug("source_id column already exists on news_articles")
            else:
                logger.warning(f"Could not add source_id to news_articles: {e}")

        # Add index on news_articles.source_id
        try:
            await db.execute(
                "CREATE INDEX IF NOT EXISTS ix_news_articles_source_id ON news_articles(source_id)"
            )
            logger.info("Created index ix_news_articles_source_id")
        except Exception as e:
            logger.debug(f"Index may already exist: {e}")

        # Add source_id column to video_articles
        try:
            await db.execute(
                "ALTER TABLE video_articles ADD COLUMN source_id INTEGER REFERENCES content_sources(id)"
            )
            logger.info("Added source_id column to video_articles")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                logger.debug("source_id column already exists on video_articles")
            else:
                logger.warning(f"Could not add source_id to video_articles: {e}")

        # Add index on video_articles.source_id
        try:
            await db.execute(
                "CREATE INDEX IF NOT EXISTS ix_video_articles_source_id ON video_articles(source_id)"
            )
            logger.info("Created index ix_video_articles_source_id")
        except Exception as e:
            logger.debug(f"Index may already exist: {e}")

        # Backfill news_articles.source_id from content_sources.source_key
        try:
            cursor = await db.execute(
                """UPDATE news_articles SET source_id = (
                    SELECT id FROM content_sources WHERE source_key = news_articles.source
                ) WHERE source_id IS NULL"""
            )
            news_backfilled = cursor.rowcount
            if news_backfilled > 0:
                logger.info(f"Backfilled source_id for {news_backfilled} news articles")
        except Exception as e:
            logger.warning(f"Could not backfill news_articles.source_id: {e}")

        # Backfill video_articles.source_id from content_sources.source_key
        try:
            cursor = await db.execute(
                """UPDATE video_articles SET source_id = (
                    SELECT id FROM content_sources WHERE source_key = video_articles.source
                ) WHERE source_id IS NULL"""
            )
            videos_backfilled = cursor.rowcount
            if videos_backfilled > 0:
                logger.info(f"Backfilled source_id for {videos_backfilled} video articles")
        except Exception as e:
            logger.warning(f"Could not backfill video_articles.source_id: {e}")

        await db.commit()
        logger.info("Migration complete: news_articles and video_articles now have source_id FK")
