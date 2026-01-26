#!/usr/bin/env python3
"""
Compress existing news article images in the database.

This script:
1. Reads all news articles with image_data
2. Decompresses base64 images
3. Resizes to 400px width max
4. Converts to WebP format (85% quality)
5. Re-encodes as base64 and updates database

Expected savings: 60-80% reduction in image storage size.
"""
import sqlite3
import base64
import io
import shutil
from datetime import datetime
from pathlib import Path
from PIL import Image

# Configuration
DB_PATH = Path(__file__).parent.parent / "backend" / "trading.db"
THUMBNAIL_MAX_WIDTH = 400
WEBP_QUALITY = 85
BATCH_SIZE = 100  # Process in batches to avoid memory issues


def compress_image_from_base64(data_uri: str) -> tuple[str, int, int]:
    """
    Decompress a base64 data URI, compress the image, and return new data URI.

    Returns:
        Tuple of (new_data_uri, original_size, compressed_size)
    """
    try:
        # Extract base64 data from data URI
        if ';base64,' not in data_uri:
            return (data_uri, 0, 0)  # Not a base64 image, skip

        header, b64_data = data_uri.split(';base64,', 1)
        original_size = len(b64_data)

        # Decode base64 to bytes
        image_bytes = base64.b64decode(b64_data)

        # Open image
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if needed
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Resize if needed
        if img.width > THUMBNAIL_MAX_WIDTH:
            ratio = THUMBNAIL_MAX_WIDTH / img.width
            new_height = int(img.height * ratio)
            img = img.resize((THUMBNAIL_MAX_WIDTH, new_height), Image.Resampling.LANCZOS)

        # Save as WebP
        output = io.BytesIO()
        img.save(output, format='WEBP', quality=WEBP_QUALITY, method=6)
        compressed_bytes = output.getvalue()

        # Convert back to base64 data URI
        compressed_b64 = base64.b64encode(compressed_bytes).decode('ascii')
        new_data_uri = f"data:image/webp;base64,{compressed_b64}"

        compressed_size = len(compressed_b64)

        return (new_data_uri, original_size, compressed_size)

    except Exception as e:
        print(f"    ERROR compressing image: {e}")
        return (data_uri, 0, 0)  # Return original on error


def compress_all_images():
    """Compress all images in the database."""
    print("=" * 80)
    print("NEWS IMAGE COMPRESSION")
    print("=" * 80)
    print(f"Database: {DB_PATH}")
    print()

    # Create backup first
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = DB_PATH.parent / f"trading_backup_precompress_{timestamp}.db"
    print(f"📦 Creating backup: {backup_path.name}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ Backup created")
    print()

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        # Get count of images to compress
        cursor.execute("SELECT COUNT(*) FROM news_articles WHERE image_data IS NOT NULL")
        total_images = cursor.fetchone()[0]

        if total_images == 0:
            print("No images to compress!")
            return

        print(f"Found {total_images:,} images to compress")
        print()

        # Process in batches
        compressed_count = 0
        skipped_count = 0
        total_original_size = 0
        total_compressed_size = 0

        offset = 0
        while offset < total_images:
            cursor.execute("""
                SELECT id, image_data
                FROM news_articles
                WHERE image_data IS NOT NULL
                LIMIT ? OFFSET ?
            """, (BATCH_SIZE, offset))

            batch = cursor.fetchall()
            if not batch:
                break

            print(f"Processing batch {offset + 1}-{offset + len(batch)} of {total_images}...")

            for article_id, image_data in batch:
                if not image_data or not image_data.startswith('data:image'):
                    skipped_count += 1
                    continue

                # Compress the image
                new_data_uri, original_size, compressed_size = compress_image_from_base64(image_data)

                if compressed_size > 0 and compressed_size < original_size:
                    # Update database
                    cursor.execute("""
                        UPDATE news_articles
                        SET image_data = ?
                        WHERE id = ?
                    """, (new_data_uri, article_id))

                    compressed_count += 1
                    total_original_size += original_size
                    total_compressed_size += compressed_size

                    savings = (1 - compressed_size / original_size) * 100
                    if compressed_count % 50 == 0:
                        print(f"  Compressed {compressed_count}/{total_images} images ({savings:.1f}% savings)")
                else:
                    skipped_count += 1

            # Commit batch
            conn.commit()
            offset += BATCH_SIZE

        print()
        print("=" * 80)
        print("COMPRESSION SUMMARY")
        print("=" * 80)
        print(f"Total images processed: {total_images:,}")
        print(f"Successfully compressed: {compressed_count:,}")
        print(f"Skipped: {skipped_count:,}")
        print()

        if total_original_size > 0:
            total_savings = (1 - total_compressed_size / total_original_size) * 100
            original_mb = total_original_size / (1024 * 1024)
            compressed_mb = total_compressed_size / (1024 * 1024)
            saved_mb = original_mb - compressed_mb

            print(f"Original size: {original_mb:.2f} MB")
            print(f"Compressed size: {compressed_mb:.2f} MB")
            print(f"Savings: {saved_mb:.2f} MB ({total_savings:.1f}%)")
        print()

        # VACUUM to reclaim space
        print("🗜️  Running VACUUM to reclaim disk space...")
        cursor.execute("VACUUM")
        print("✅ VACUUM complete")
        print()

        print(f"📦 Backup saved at: {backup_path}")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error during compression: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("\n🗜️  Compressing News Article Images\n")
    compress_all_images()
