#!/usr/bin/env python3
"""
Daily database cleanup script - removes old data and vacuums the database.

This script is designed to run as a scheduled job (via systemd timer) to prevent
database bloat from accumulated log entries and old news articles.

Retention policies:
- news_articles: 14 days (we share articles up to 14 days old)
- video_articles: 14 days
- signals: 7 days
- scanner_logs: 7 days
- ai_bot_logs: 7 days
- indicator_logs: 7 days

After deletion, VACUUM is run to reclaim disk space.

Usage:
    python3 cleanup_database.py [--db-path PATH] [--log-path PATH]

Defaults:
    --db-path:  /home/ec2-user/GetRidOf3CommasBecauseTheyGoDownTooOften/backend/trading.db
    --log-path: /home/ec2-user/cleanup-database.log
"""

import sqlite3
import os
import argparse
from datetime import datetime

DEFAULT_DB_PATH = "/home/ec2-user/GetRidOf3CommasBecauseTheyGoDownTooOften/backend/trading.db"
DEFAULT_LOG_PATH = "/home/ec2-user/cleanup-database.log"

# Retention periods in days
NEWS_RETENTION_DAYS = 14
LOGS_RETENTION_DAYS = 7


def log(message: str, log_file: str) -> None:
    """Log message to both stdout and log file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    formatted = f'[{timestamp}] {message}'
    print(formatted)
    with open(log_file, 'a') as f:
        f.write(formatted + '\n')


def get_db_size_mb(db_path: str) -> float:
    """Get database file size in MB."""
    if os.path.exists(db_path):
        return os.path.getsize(db_path) / (1024 * 1024)
    return 0


def cleanup_table(cursor, table: str, timestamp_col: str, days: int, log_file: str) -> int:
    """Delete rows older than specified days. Returns count deleted."""
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {timestamp_col} < datetime('now', '-{days} days')")
        count = cursor.fetchone()[0]

        if count > 0:
            cursor.execute(f"DELETE FROM {table} WHERE {timestamp_col} < datetime('now', '-{days} days')")
            log(f'  {table}: deleted {count:,} rows older than {days} days', log_file)
        else:
            log(f'  {table}: no rows to delete', log_file)

        return count
    except sqlite3.OperationalError as e:
        # Table might not exist in all installations
        log(f'  {table}: skipped ({e})', log_file)
        return 0


def main():
    parser = argparse.ArgumentParser(description='Clean up old database logs and news')
    parser.add_argument('--db-path', default=DEFAULT_DB_PATH, help='Path to SQLite database')
    parser.add_argument('--log-path', default=DEFAULT_LOG_PATH, help='Path to log file')
    args = parser.parse_args()

    log('=' * 60, args.log_path)
    log('Starting database cleanup...', args.log_path)
    log('=' * 60, args.log_path)

    if not os.path.exists(args.db_path):
        log(f'Database not found: {args.db_path}', args.log_path)
        return 1

    size_before = get_db_size_mb(args.db_path)
    log(f'Database size before: {size_before:.1f} MB', args.log_path)

    conn = sqlite3.connect(args.db_path)
    cursor = conn.cursor()
    total_deleted = 0

    try:
        # News and videos - 14 day retention
        log(f'Cleaning news/videos (>{NEWS_RETENTION_DAYS} days old):', args.log_path)
        total_deleted += cleanup_table(cursor, 'news_articles', 'published_at', NEWS_RETENTION_DAYS, args.log_path)
        total_deleted += cleanup_table(cursor, 'video_articles', 'published_at', NEWS_RETENTION_DAYS, args.log_path)

        # Logs - 7 day retention
        log(f'Cleaning logs (>{LOGS_RETENTION_DAYS} days old):', args.log_path)
        total_deleted += cleanup_table(cursor, 'signals', 'timestamp', LOGS_RETENTION_DAYS, args.log_path)
        total_deleted += cleanup_table(cursor, 'scanner_logs', 'timestamp', LOGS_RETENTION_DAYS, args.log_path)
        total_deleted += cleanup_table(cursor, 'ai_bot_logs', 'timestamp', LOGS_RETENTION_DAYS, args.log_path)
        total_deleted += cleanup_table(cursor, 'indicator_logs', 'timestamp', LOGS_RETENTION_DAYS, args.log_path)

        conn.commit()

        # Vacuum to reclaim space
        if total_deleted > 0:
            log('Running VACUUM to reclaim disk space...', args.log_path)
            cursor.execute('VACUUM')
            log('VACUUM complete', args.log_path)

    except Exception as e:
        log(f'Error during cleanup: {e}', args.log_path)
        return 1

    finally:
        conn.close()

    size_after = get_db_size_mb(args.db_path)
    saved = size_before - size_after

    log('=' * 60, args.log_path)
    log('Cleanup Summary:', args.log_path)
    log(f'  Total rows deleted: {total_deleted:,}', args.log_path)
    log(f'  Size before: {size_before:.1f} MB', args.log_path)
    log(f'  Size after:  {size_after:.1f} MB', args.log_path)
    log(f'  Space saved: {saved:.1f} MB ({(saved/size_before*100) if size_before > 0 else 0:.1f}%)', args.log_path)
    log('=' * 60, args.log_path)

    return 0


if __name__ == '__main__':
    exit(main())
