#!/usr/bin/env python3
"""
Daily database cleanup script - removes old logs and vacuums the database.

This script is designed to run as a scheduled job (via systemd timer) to prevent
database bloat from accumulated log entries.

Tables cleaned:
- indicator_logs: Entries older than 1 day are deleted
- ai_bot_logs: Entries older than 7 days are deleted

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


def log(message: str, log_file: str) -> None:
    """Log message to both stdout and log file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    formatted = f'[{timestamp}] {message}'
    print(formatted)
    with open(log_file, 'a') as f:
        f.write(formatted + '\n')


def get_db_size_mb(cursor) -> float:
    """Get current database size in MB."""
    cursor.execute('SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()')
    return cursor.fetchone()[0] / 1024 / 1024


def main():
    parser = argparse.ArgumentParser(description='Clean up old database logs')
    parser.add_argument('--db-path', default=DEFAULT_DB_PATH, help='Path to SQLite database')
    parser.add_argument('--log-path', default=DEFAULT_LOG_PATH, help='Path to log file')
    args = parser.parse_args()

    log('Starting database cleanup...', args.log_path)

    if not os.path.exists(args.db_path):
        log(f'Database not found: {args.db_path}', args.log_path)
        return 1

    conn = sqlite3.connect(args.db_path)
    cursor = conn.cursor()

    try:
        # Delete old indicator logs (older than 1 day)
        cursor.execute("SELECT COUNT(*) FROM indicator_logs WHERE timestamp < datetime('now', '-1 day')")
        indicator_count = cursor.fetchone()[0]
        cursor.execute("DELETE FROM indicator_logs WHERE timestamp < datetime('now', '-1 day')")

        # Delete old ai_bot_logs (older than 7 days)
        cursor.execute("SELECT COUNT(*) FROM ai_bot_logs WHERE timestamp < datetime('now', '-7 days')")
        ai_log_count = cursor.fetchone()[0]
        cursor.execute("DELETE FROM ai_bot_logs WHERE timestamp < datetime('now', '-7 days')")

        conn.commit()

        # Get size before vacuum
        size_before = get_db_size_mb(cursor)

        # Vacuum to reclaim space
        cursor.execute('VACUUM')

        # Get size after vacuum
        size_after = get_db_size_mb(cursor)

        log(f'Deleted {indicator_count} indicator_logs, {ai_log_count} ai_bot_logs', args.log_path)
        log(f'Database size: {size_before:.1f}MB -> {size_after:.1f}MB', args.log_path)
        log('Cleanup complete', args.log_path)

        return 0

    except Exception as e:
        log(f'Error during cleanup: {e}', args.log_path)
        return 1

    finally:
        conn.close()


if __name__ == '__main__':
    exit(main())
