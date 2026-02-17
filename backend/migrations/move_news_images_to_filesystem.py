"""
Migration: Move news article images from database to filesystem

Extracts base64 image_data from news_articles into individual WebP files
under backend/news_images/. Updates cached_thumbnail_path to point to
the file, then NULLs image_data to reclaim DB space.
"""

import base64
import os
import sqlite3
from pathlib import Path


def get_db_path():
    """Get database path relative to script location"""
    backend_dir = Path(__file__).parent.parent
    return backend_dir / "trading.db"


def get_images_dir():
    """Get news_images directory relative to script location"""
    backend_dir = Path(__file__).parent.parent
    return backend_dir / "news_images"


def run_migration():
    """Extract base64 image_data from DB to filesystem"""
    db_path = get_db_path()
    images_dir = get_images_dir()

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False

    # Create news_images directory
    images_dir.mkdir(exist_ok=True)
    print(f"Ensured news_images directory at {images_dir}")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Get all articles with image_data
        cursor.execute(
            "SELECT id, image_data FROM news_articles WHERE image_data IS NOT NULL AND image_data != ''"
        )
        articles = cursor.fetchall()

        if not articles:
            print("No articles with embedded image_data found")
            return True

        print(f"Found {len(articles)} articles with embedded images to migrate")

        migrated = 0
        errors = 0

        for article_id, image_data in articles:
            try:
                # Parse the data URI: data:image/webp;base64,/9j/4AAQ...
                if image_data.startswith("data:"):
                    header, b64_data = image_data.split(",", 1)
                    mime_type = header.split(":")[1].split(";")[0]
                else:
                    b64_data = image_data
                    mime_type = "image/jpeg"

                # Determine file extension from MIME type
                ext_map = {
                    "image/webp": ".webp",
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/gif": ".gif",
                }
                ext = ext_map.get(mime_type, ".webp")

                # Decode and write to file
                image_bytes = base64.b64decode(b64_data)
                filename = f"{article_id}{ext}"
                filepath = images_dir / filename

                with open(filepath, "wb") as f:
                    f.write(image_bytes)

                # Update database: set cached_thumbnail_path, clear image_data
                cursor.execute(
                    "UPDATE news_articles SET cached_thumbnail_path = ?, image_data = NULL WHERE id = ?",
                    (filename, article_id)
                )

                migrated += 1

            except Exception as e:
                print(f"  Error migrating article {article_id}: {e}")
                errors += 1

        conn.commit()
        print(f"Migration complete: {migrated} images extracted, {errors} errors")

        # Report space savings
        db_size_bytes = os.path.getsize(db_path)
        print(f"Database size after migration: {db_size_bytes / 1024 / 1024:.1f} MB")
        print("Run VACUUM on the database to reclaim freed space")

        return True

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    print("Running migration: move_news_images_to_filesystem")
    success = run_migration()
    exit(0 if success else 1)
