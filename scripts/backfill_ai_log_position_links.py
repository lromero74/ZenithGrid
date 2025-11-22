"""
Backfill missing position_id links in AI bot logs.

This script finds AI logs with position_id = NULL and links them to their
corresponding positions based on matching criteria:
- Same bot_id
- Same product_id
- Decision = 'buy'
- Timestamp within 10 seconds of position.opened_at

Usage:
    python scripts/backfill_ai_log_position_links.py [--dry-run]
"""
import sqlite3
import sys
from datetime import datetime, timedelta

def backfill_position_links(db_path='backend/trading.db', dry_run=False):
    """Link orphaned AI logs to their positions"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Find all AI logs without position_id that have decision='buy'
    cursor.execute('''
        SELECT id, bot_id, product_id, timestamp, thinking
        FROM ai_bot_logs
        WHERE position_id IS NULL AND decision = 'buy'
        ORDER BY timestamp DESC
    ''')

    orphaned_logs = cursor.fetchall()
    print('=' * 80)
    print('BACKFILLING AI LOG POSITION LINKS')
    print('=' * 80)
    print(f'Found {len(orphaned_logs)} orphaned AI logs with decision="buy"')
    print()

    linked_count = 0
    skipped_count = 0

    for log_id, bot_id, product_id, log_timestamp, thinking in orphaned_logs:
        # Parse timestamp
        log_time = datetime.fromisoformat(log_timestamp.replace(' ', 'T') if ' ' in log_timestamp else log_timestamp)

        # Find matching position: same bot, same product, opened within 10 seconds of log
        cursor.execute('''
            SELECT id, opened_at
            FROM positions
            WHERE bot_id = ? AND product_id = ? AND status = 'open'
            ORDER BY ABS(julianday(opened_at) - julianday(?))
            LIMIT 1
        ''', (bot_id, product_id, log_timestamp))

        match = cursor.fetchone()
        if match:
            position_id, position_opened_at = match
            position_time = datetime.fromisoformat(position_opened_at.replace(' ', 'T') if ' ' in position_opened_at else position_opened_at)
            time_diff = abs((position_time - log_time).total_seconds())

            # Only link if timestamps are within 10 seconds
            if time_diff <= 10:
                thinking_preview = thinking[:100] + '...' if len(thinking) > 100 else thinking
                print(f'✓ Linking AI log {log_id} → position {position_id} ({product_id})')
                print(f'  Time diff: {time_diff:.2f}s')
                print(f'  Reasoning: {thinking_preview}')

                if not dry_run:
                    cursor.execute('''
                        UPDATE ai_bot_logs
                        SET position_id = ?
                        WHERE id = ?
                    ''', (position_id, log_id))

                linked_count += 1
            else:
                print(f'⚠  Skipping AI log {log_id} ({product_id}) - time diff too large ({time_diff:.2f}s)')
                skipped_count += 1
        else:
            print(f'⚠  No matching position found for AI log {log_id} ({product_id})')
            skipped_count += 1

    if not dry_run:
        conn.commit()

    print()
    print('=' * 80)
    print('BACKFILL COMPLETE')
    print('=' * 80)
    print(f'Linked: {linked_count}')
    print(f'Skipped: {skipped_count}')
    if dry_run:
        print('\n⚠️  DRY RUN - No changes were made to the database')
    else:
        print('\n✅ Changes committed to database')

    conn.close()
    return linked_count, skipped_count

if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        print('🔍 Running in DRY RUN mode\n')

    backfill_position_links(dry_run=dry_run)
