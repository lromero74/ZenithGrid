#!/usr/bin/env python3
"""
Script to manually run cleanup jobs immediately.
This will actually DELETE old records from the database.
"""
import sqlite3
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# Database path
db_path = Path(__file__).parent.parent / "backend" / "trading.db"

def backup_database():
    """Create a backup before cleanup"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = db_path.parent / f"trading_backup_{timestamp}.db"
    print(f"📦 Creating backup: {backup_path.name}")
    shutil.copy2(db_path, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path

def run_cleanup():
    """Run the actual cleanup operations"""

    print("\n" + "=" * 60)
    print("RUNNING CLEANUP JOBS")
    print("=" * 60)
    print()

    # Create backup first
    backup_path = backup_database()
    print()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cutoff_time = (datetime.utcnow() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')

    try:
        # 1. Clean up failed condition logs (indicator_logs)
        print("1. Cleaning indicator logs (conditions_met=False)...")
        cursor.execute("""
            DELETE FROM indicator_logs
            WHERE timestamp < ? AND conditions_met = 0
        """, (cutoff_time,))
        indicator_deleted = cursor.rowcount
        print(f"   ✅ Deleted {indicator_deleted} indicator logs")

        # 2. Clean up low-confidence AI logs
        print("\n2. Cleaning AI logs (confidence <30%)...")
        cursor.execute("""
            DELETE FROM ai_bot_logs
            WHERE timestamp < ? AND confidence < 30
        """, (cutoff_time,))
        ai_deleted = cursor.rowcount
        print(f"   ✅ Deleted {ai_deleted} AI logs")

        # 3. Clean up failed orders
        print("\n3. Cleaning failed orders...")
        cursor.execute("""
            DELETE FROM order_history
            WHERE timestamp < ? AND status = 'failed'
        """, (cutoff_time,))
        failed_orders_deleted = cursor.rowcount
        print(f"   ✅ Deleted {failed_orders_deleted} failed orders")

        # Commit all changes
        conn.commit()

        # Summary
        total_deleted = indicator_deleted + ai_deleted + failed_orders_deleted
        print("\n" + "=" * 60)
        print("CLEANUP COMPLETE")
        print("=" * 60)
        print(f"Total records deleted: {total_deleted}")
        print(f"  - Indicator logs: {indicator_deleted}")
        print(f"  - AI logs: {ai_deleted}")
        print(f"  - Failed orders: {failed_orders_deleted}")
        print()
        print(f"✅ Database cleaned successfully!")
        print(f"📦 Backup saved at: {backup_path}")
        print()

        # VACUUM to reclaim space
        print("🗜️  Running VACUUM to reclaim disk space...")
        cursor.execute("VACUUM")
        print("✅ VACUUM complete - database optimized")
        print()

    except Exception as e:
        print(f"\n❌ Error during cleanup: {e}")
        conn.rollback()
        print(f"⚠️  Database rolled back - no changes made")
        print(f"📦 Backup preserved at: {backup_path}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("\n🧹 Manual Cleanup Job Execution\n")
    run_cleanup()
