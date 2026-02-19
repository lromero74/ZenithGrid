"""
Add content and content_fetched_at columns to news_articles for persistent
article content caching. Eliminates redundant re-fetches across users.
"""

import logging
import sqlite3
import os

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'trading.db')


def run_migration():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for col, col_type in [
        ("content", "TEXT"),
        ("content_fetched_at", "DATETIME"),
    ]:
        try:
            cursor.execute(
                f"ALTER TABLE news_articles ADD COLUMN {col} {col_type}"
            )
            logger.info(f"Added column {col} to news_articles")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info(f"Column {col} already exists in news_articles")
            else:
                raise

    conn.commit()
    conn.close()


if __name__ == "__main__":
    run_migration()
