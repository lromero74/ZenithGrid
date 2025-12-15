#!/usr/bin/env python3
"""
Daily Database Cleanup Script

Runs via systemd timer to keep database size manageable.
- News articles/videos: 14 days retention
- Signals, scanner_logs, ai_bot_logs: 7 days retention
"""

import asyncio
import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Retention periods
NEWS_RETENTION_DAYS = 14
LOGS_RETENTION_DAYS = 7

# Database path
DB_PATH = Path(__file__).parent.parent / "trading.db"


def get_db_size_mb() -> float:
    """Get database file size in MB."""
    if DB_PATH.exists():
        return DB_PATH.stat().st_size / (1024 * 1024)
    return 0


def cleanup_table(conn: sqlite3.Connection, table: str, timestamp_col: str, days: int) -> int:
    """Delete rows older than specified days. Returns count deleted."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    cursor = conn.cursor()

    # Get count first
    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {timestamp_col} < ?", (cutoff_str,))
    count = cursor.fetchone()[0]

    if count > 0:
        cursor.execute(f"DELETE FROM {table} WHERE {timestamp_col} < ?", (cutoff_str,))
        conn.commit()
        logger.info(f"  {table}: deleted {count:,} rows older than {days} days")
    else:
        logger.info(f"  {table}: no rows to delete")

    return count


def run_cleanup():
    """Run all cleanup tasks."""
    logger.info("=" * 60)
    logger.info(f"Starting daily cleanup at {datetime.utcnow().isoformat()}")
    logger.info("=" * 60)

    size_before = get_db_size_mb()
    logger.info(f"Database size before: {size_before:.1f} MB")

    if not DB_PATH.exists():
        logger.error(f"Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    total_deleted = 0

    try:
        # News and videos - 14 day retention
        logger.info(f"\nCleaning news/videos (>{NEWS_RETENTION_DAYS} days old):")
        total_deleted += cleanup_table(conn, "news_articles", "published_at", NEWS_RETENTION_DAYS)
        total_deleted += cleanup_table(conn, "video_articles", "published_at", NEWS_RETENTION_DAYS)

        # Logs - 7 day retention
        logger.info(f"\nCleaning logs (>{LOGS_RETENTION_DAYS} days old):")
        total_deleted += cleanup_table(conn, "signals", "timestamp", LOGS_RETENTION_DAYS)
        total_deleted += cleanup_table(conn, "scanner_logs", "timestamp", LOGS_RETENTION_DAYS)
        total_deleted += cleanup_table(conn, "ai_bot_logs", "timestamp", LOGS_RETENTION_DAYS)
        total_deleted += cleanup_table(conn, "indicator_logs", "timestamp", LOGS_RETENTION_DAYS)

        # Vacuum to reclaim space
        if total_deleted > 0:
            logger.info("\nRunning VACUUM to reclaim disk space...")
            conn.execute("VACUUM")
            logger.info("VACUUM complete")

    finally:
        conn.close()

    size_after = get_db_size_mb()
    saved = size_before - size_after

    logger.info("\n" + "=" * 60)
    logger.info("Cleanup Summary:")
    logger.info(f"  Total rows deleted: {total_deleted:,}")
    logger.info(f"  Size before: {size_before:.1f} MB")
    logger.info(f"  Size after:  {size_after:.1f} MB")
    logger.info(f"  Space saved: {saved:.1f} MB ({(saved/size_before*100) if size_before > 0 else 0:.1f}%)")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_cleanup()
