"""
Migration: Add video_articles table for database-backed video caching

This adds support for storing video articles in the database with deduplication.
Replaces the previous JSON file-based caching for videos.
"""

import sqlite3
from pathlib import Path


def run_migration():
    """Add video_articles table for caching videos with deduplication"""
    db_path = Path(__file__).parent.parent / "trading.db"

    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='video_articles'")
        if cursor.fetchone():
            print("Warning: Table video_articles already exists - migration already applied")
            return

        # Create video_articles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                video_id TEXT NOT NULL,
                source TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                published_at DATETIME,
                description TEXT,
                thumbnail_url TEXT,
                fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_video_articles_url ON video_articles (url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_video_articles_video_id ON video_articles (video_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_video_articles_published_at ON video_articles (published_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_video_articles_fetched_at ON video_articles (fetched_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_video_articles_source ON video_articles (source)")

        conn.commit()
        print("Migration completed successfully!")
        print("   - Created video_articles table")
        print("   - Added indexes for url, video_id, published_at, fetched_at, source")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
