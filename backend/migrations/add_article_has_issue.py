"""
Migration: Add has_issue column to news_articles table for flagging
articles that fail TTS playback (content extraction failure, etc.).

Idempotent — safe to re-run.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "trading.db"
)


def run_migration():
    """Add has_issue boolean column to news_articles."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "ALTER TABLE news_articles ADD COLUMN has_issue BOOLEAN DEFAULT 0"
        )
        conn.commit()
        logger.info("Added has_issue column to news_articles")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("has_issue column already exists — skipping")
        else:
            raise
    finally:
        conn.close()
