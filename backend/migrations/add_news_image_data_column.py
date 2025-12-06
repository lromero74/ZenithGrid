"""
Migration: Add image_data column to news_articles table

This adds a TEXT column to store base64-encoded image data URIs directly
in the database. This eliminates the need for file-based image caching
and avoids path/proxy issues with SSH tunneling.
"""

import sqlite3
from pathlib import Path


def run_migration():
    """Add image_data column to news_articles table for base64 image storage"""
    db_path = Path(__file__).parent.parent / "trading.db"

    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(news_articles)")
        columns = [col[1] for col in cursor.fetchall()]

        if "image_data" in columns:
            print("Column 'image_data' already exists, skipping...")
            return

        # Add image_data column (TEXT to store base64 data URIs)
        cursor.execute("""
            ALTER TABLE news_articles
            ADD COLUMN image_data TEXT
        """)

        conn.commit()
        print("Migration completed successfully!")
        print("   - Added 'image_data' column (TEXT) to news_articles table")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
