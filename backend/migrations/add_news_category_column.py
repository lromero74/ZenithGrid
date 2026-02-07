"""
Migration: Add category column to news tables

Adds a 'category' column to news_articles, video_articles, and content_sources tables.
All existing content defaults to 'CryptoCurrency' category.
Enables filtering news by category (World, Nation, Business, Technology, etc.)
"""

import sqlite3
from pathlib import Path


def get_db_path():
    """Get database path relative to script location"""
    backend_dir = Path(__file__).parent.parent
    return backend_dir / "trading.db"


def run_migration():
    """Add category column to news tables"""
    db_path = get_db_path()

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check and add category to news_articles
        cursor.execute("PRAGMA table_info(news_articles)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'category' not in columns:
            cursor.execute("""
                ALTER TABLE news_articles
                ADD COLUMN category TEXT NOT NULL DEFAULT 'CryptoCurrency'
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_news_articles_category
                ON news_articles(category)
            """)
            print("Added category column to news_articles")
        else:
            print("news_articles.category already exists")

        # Check and add category to video_articles
        cursor.execute("PRAGMA table_info(video_articles)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'category' not in columns:
            cursor.execute("""
                ALTER TABLE video_articles
                ADD COLUMN category TEXT NOT NULL DEFAULT 'CryptoCurrency'
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_video_articles_category
                ON video_articles(category)
            """)
            print("Added category column to video_articles")
        else:
            print("video_articles.category already exists")

        # Check and add category to content_sources
        cursor.execute("PRAGMA table_info(content_sources)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'category' not in columns:
            cursor.execute("""
                ALTER TABLE content_sources
                ADD COLUMN category TEXT NOT NULL DEFAULT 'CryptoCurrency'
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_content_sources_category
                ON content_sources(category)
            """)
            print("Added category column to content_sources")
        else:
            print("content_sources.category already exists")

        conn.commit()
        print("Migration completed successfully")
        return True

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    print("Running migration: add_news_category_column")
    success = run_migration()
    exit(0 if success else 1)
