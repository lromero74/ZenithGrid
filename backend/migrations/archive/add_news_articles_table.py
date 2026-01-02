"""
Migration: Add news_articles table for database-backed news caching

This adds support for storing news articles in the database with locally
cached thumbnail images. Replaces the previous JSON file-based caching.
"""

import sqlite3
from pathlib import Path


def run_migration():
    """Add news_articles table for caching news with local image storage"""
    db_path = Path(__file__).parent.parent / "trading.db"

    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='news_articles'")
        if cursor.fetchone():
            print("⚠️  Table news_articles already exists - migration already applied")
            return

        # Create news_articles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                published_at DATETIME,
                summary TEXT,
                author TEXT,
                original_thumbnail_url TEXT,
                cached_thumbnail_path TEXT,
                fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_news_articles_url ON news_articles (url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_news_articles_published_at ON news_articles (published_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_news_articles_fetched_at ON news_articles (fetched_at)")

        conn.commit()
        print("Migration completed successfully!")
        print("   - Created news_articles table")
        print("   - Added indexes for url, published_at, fetched_at")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
