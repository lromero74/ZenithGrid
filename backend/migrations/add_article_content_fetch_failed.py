"""
Add content_fetch_failed column to news_articles.

Tracks whether content extraction has been attempted and failed,
so we never re-fetch from the external source.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Add the column (idempotent)
        try:
            cursor.execute(
                "ALTER TABLE news_articles ADD COLUMN content_fetch_failed BOOLEAN DEFAULT 0"
            )
            logger.info("Added content_fetch_failed column to news_articles")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("content_fetch_failed column already exists")
            else:
                raise

        # Backfill: articles flagged as broken with no content have already failed
        cursor.execute(
            "UPDATE news_articles SET content_fetch_failed = 1 "
            "WHERE has_issue = 1 AND content IS NULL"
        )
        backfilled = cursor.rowcount
        if backfilled:
            logger.info(f"Backfilled content_fetch_failed=1 for {backfilled} articles")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
