#!/usr/bin/env python3
"""
Simple test script to check what cleanup jobs would clean up.
Uses direct SQL queries instead of ORM to avoid path issues.
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Database path
db_path = Path(__file__).parent.parent / "backend" / "trading.db"

def test_cleanup_jobs():
    """Test cleanup jobs by showing what would be cleaned up"""

    print("=" * 60)
    print("CLEANUP JOB TEST REPORT")
    print("=" * 60)
    print(f"Database: {db_path}")
    print()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cutoff_time = (datetime.utcnow() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')

    try:
        # Check failed condition logs (IndicatorLog)
        print("1. Failed Condition Logs (indicator_logs)")
        print("-" * 60)
        cursor.execute("""
            SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
            FROM indicator_logs
            WHERE timestamp < ? AND conditions_met = 0
        """, (cutoff_time,))
        count, oldest, newest = cursor.fetchone()
        print(f"   Found {count} indicator logs with conditions_met=False older than 24h")
        if count > 0:
            print(f"   Oldest: {oldest}")
            print(f"   Newest: {newest}")
        print()

        # Check low-confidence AI logs
        print("2. Low-Confidence AI Logs (ai_bot_logs)")
        print("-" * 60)
        cursor.execute("""
            SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
            FROM ai_bot_logs
            WHERE timestamp < ? AND confidence < 30
        """, (cutoff_time,))
        count, oldest, newest = cursor.fetchone()
        print(f"   Found {count} AI logs with confidence <30% older than 24h")
        if count > 0:
            print(f"   Oldest: {oldest}")
            print(f"   Newest: {newest}")
        print()

        # Check failed orders
        print("3. Failed Orders (order_history)")
        print("-" * 60)
        cursor.execute("""
            SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
            FROM order_history
            WHERE timestamp < ? AND status = 'failed'
        """, (cutoff_time,))
        count, oldest, newest = cursor.fetchone()
        print(f"   Found {count} failed orders older than 24h")
        if count > 0:
            print(f"   Oldest: {oldest}")
            print(f"   Newest: {newest}")
            print()
            print("   Sample failed orders to be cleaned:")
            cursor.execute("""
                SELECT timestamp, product_id, side, error_message
                FROM order_history
                WHERE timestamp < ? AND status = 'failed'
                ORDER BY timestamp DESC
                LIMIT 5
            """, (cutoff_time,))
            for i, (ts, product, side, error) in enumerate(cursor.fetchall(), 1):
                error_short = error[:50] + "..." if error and len(error) > 50 else error
                print(f"      {i}. {ts} - {product} {side} - {error_short}")
        print()

        # Summary
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)

        # Get totals
        cursor.execute("""
            SELECT COUNT(*) FROM indicator_logs
            WHERE timestamp < ? AND conditions_met = 0
        """, (cutoff_time,))
        indicator_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM ai_bot_logs
            WHERE timestamp < ? AND confidence < 30
        """, (cutoff_time,))
        ai_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM order_history
            WHERE timestamp < ? AND status = 'failed'
        """, (cutoff_time,))
        failed_orders_count = cursor.fetchone()[0]

        total_to_clean = indicator_count + ai_count + failed_orders_count

        print(f"Total records that would be cleaned: {total_to_clean}")
        print(f"  - Indicator logs (conditions not met): {indicator_count}")
        print(f"  - AI logs (confidence <30%): {ai_count}")
        print(f"  - Failed orders: {failed_orders_count}")
        print()

        if total_to_clean > 0:
            print("✅ Cleanup jobs have work to do!")
        else:
            print("✅ No old records to clean (database is clean)")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    print("\n🔍 Testing Cleanup Jobs\n")
    test_cleanup_jobs()
