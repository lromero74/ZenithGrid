"""
Remove medicalxpress source and its articles.

medicalxpress.com blocked our EC2 IP after repeated content fetches.
This migration cleans up all related data.
"""

import logging
import os
import shutil
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")
TTS_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tts_cache")


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Find medicalxpress article IDs for TTS cache cleanup
        cursor.execute(
            "SELECT id FROM news_articles WHERE url LIKE '%medicalxpress.com%'"
        )
        article_ids = [row[0] for row in cursor.fetchall()]

        # Delete TTS cache directories for these articles
        if article_ids and os.path.isdir(TTS_CACHE_DIR):
            cleaned = 0
            for aid in article_ids:
                cache_dir = os.path.join(TTS_CACHE_DIR, str(aid))
                if os.path.isdir(cache_dir):
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    cleaned += 1
            if cleaned:
                logger.info(f"Cleaned {cleaned} TTS cache dirs for medicalxpress articles")

        # Delete related records (CASCADE handles article_tts, history, seen_status)
        # But be explicit for tables that might not have CASCADE
        if article_ids:
            placeholders = ",".join("?" * len(article_ids))
            cursor.execute(
                f"DELETE FROM article_tts WHERE article_id IN ({placeholders})",
                article_ids,
            )
            cursor.execute(
                f"DELETE FROM user_article_tts_history WHERE article_id IN ({placeholders})",
                article_ids,
            )
            cursor.execute(
                f"DELETE FROM user_content_seen_status WHERE content_type = 'article' "
                f"AND content_id IN ({placeholders})",
                article_ids,
            )

        # Delete articles
        cursor.execute(
            "DELETE FROM news_articles WHERE url LIKE '%medicalxpress.com%'"
        )
        deleted_articles = cursor.rowcount
        if deleted_articles:
            logger.info(f"Deleted {deleted_articles} medicalxpress articles")

        # Delete content source
        cursor.execute(
            "DELETE FROM content_sources WHERE source_key = 'medical_xpress'"
        )
        deleted_source = cursor.rowcount
        if deleted_source:
            logger.info("Deleted medical_xpress content source")

        if not deleted_articles and not deleted_source:
            logger.info("No medicalxpress data found to clean up")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
