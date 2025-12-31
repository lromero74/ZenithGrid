#!/usr/bin/env python3
"""
Cleanup Old Failed Records

Deletes failed positions and order history older than N days.
This removes noise from configuration issues while keeping recent failures for debugging.

Run with: python migrations/cleanup_old_failed_records.py
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_cleanup(db_path: str, days_to_keep: int = 7, dry_run: bool = False):
    """Delete failed positions and order history older than N days"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Initialize counts for VACUUM check in finally block
    failed_positions_count = 0
    failed_orders_count = 0

    try:
        print("=" * 80)
        print("CLEANUP OLD FAILED RECORDS")
        print("=" * 80)
        print()

        if dry_run:
            print("🔍 DRY RUN MODE - No changes will be made\n")

        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        print(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"(Keeping failures from last {days_to_keep} days)\n")

        # Step 1: Analyze what will be deleted
        print("Step 1: Analyzing failed records...")

        # Count failed positions to delete
        cursor.execute("""
            SELECT COUNT(*) FROM positions
            WHERE status = 'failed' AND opened_at < ?
        """, (cutoff_date,))
        failed_positions_count = cursor.fetchone()[0]

        # Count recent failed positions to keep
        cursor.execute("""
            SELECT COUNT(*) FROM positions
            WHERE status = 'failed' AND opened_at >= ?
        """, (cutoff_date,))
        kept_positions_count = cursor.fetchone()[0]

        # Show distribution by date
        cursor.execute("""
            SELECT DATE(opened_at) as date, COUNT(*) as count
            FROM positions
            WHERE status = 'failed' AND opened_at < ?
            GROUP BY DATE(opened_at)
            ORDER BY DATE(opened_at) DESC
        """, (cutoff_date,))

        print(f"\n  Failed positions to delete: {failed_positions_count}")
        print(f"  Failed positions to keep (recent): {kept_positions_count}")
        print(f"\n  Breakdown by date:")
        for row in cursor.fetchall():
            print(f"    {row[0]}: {row[1]} positions")

        # Count order_history records to delete
        cursor.execute("""
            SELECT COUNT(*) FROM order_history
            WHERE status = 'failed' AND timestamp < ?
        """, (cutoff_date,))
        failed_orders_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM order_history
            WHERE status = 'failed' AND timestamp >= ?
        """, (cutoff_date,))
        kept_orders_count = cursor.fetchone()[0]

        print(f"\n  Failed order_history to delete: {failed_orders_count}")
        print(f"  Failed order_history to keep (recent): {kept_orders_count}")

        # Step 2: Delete old failed positions
        if failed_positions_count > 0:
            print(f"\nStep 2: Deleting {failed_positions_count} old failed positions...")

            if not dry_run:
                # Get IDs first for logging
                cursor.execute("""
                    SELECT id, product_id, opened_at FROM positions
                    WHERE status = 'failed' AND opened_at < ?
                    ORDER BY opened_at
                    LIMIT 10
                """, (cutoff_date,))
                examples = cursor.fetchall()

                print(f"  Examples of positions to delete:")
                for pos_id, product, opened in examples:
                    print(f"    Position {pos_id}: {product}, opened {opened}")

                # Delete (CASCADE will handle trades automatically)
                cursor.execute("""
                    DELETE FROM positions
                    WHERE status = 'failed' AND opened_at < ?
                """, (cutoff_date,))
                deleted = cursor.rowcount
                print(f"  ✓ Deleted {deleted} failed positions")
            else:
                print(f"  Would delete {failed_positions_count} positions")
        else:
            print(f"\nStep 2: No old failed positions to delete")

        # Step 3: Delete old failed order_history
        if failed_orders_count > 0:
            print(f"\nStep 3: Deleting {failed_orders_count} old failed order_history records...")

            if not dry_run:
                cursor.execute("""
                    DELETE FROM order_history
                    WHERE status = 'failed' AND timestamp < ?
                """, (cutoff_date,))
                deleted = cursor.rowcount
                print(f"  ✓ Deleted {deleted} failed order_history records")
            else:
                print(f"  Would delete {failed_orders_count} order_history records")
        else:
            print(f"\nStep 3: No old failed order_history to delete")

        # Step 4: Show final stats BEFORE commit
        print(f"\nStep 4: Final statistics...")
        cursor.execute("SELECT COUNT(*), status FROM positions GROUP BY status")
        print(f"\n  Positions remaining:")
        for row in cursor.fetchall():
            print(f"    {row[1]}: {row[0]}")

        cursor.execute("SELECT COUNT(*) FROM order_history WHERE status = 'failed'")
        remaining_failed_orders = cursor.fetchone()[0]
        print(f"\n  Failed order_history remaining: {remaining_failed_orders}")

        # Commit deletions if not dry run
        if not dry_run:
            conn.commit()
            print("\n✅ Cleanup deletions committed successfully!")
        else:
            print("\n🔍 Dry run completed - no changes made")

        print()
        print("Summary:")
        print(f"  - Failed positions deleted: {failed_positions_count if not dry_run else f'{failed_positions_count} (would delete)'}")
        print(f"  - Failed order_history deleted: {failed_orders_count if not dry_run else f'{failed_orders_count} (would delete)'}")
        print(f"  - Recent failures kept: {kept_positions_count} positions, {kept_orders_count} orders")
        print()

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Cleanup failed: {e}")
        raise
    finally:
        # VACUUM must run outside transaction
        if not dry_run and (failed_positions_count > 0 or failed_orders_count > 0):
            try:
                print(f"\nStep 5: Vacuuming database to reclaim space...")
                conn.execute("VACUUM")
                print(f"  ✓ Database vacuumed")
            except Exception as vacuum_error:
                print(f"  ⚠️  VACUUM warning: {vacuum_error}")
                print(f"  (Deletions were still committed successfully)")

        conn.close()


if __name__ == "__main__":
    # Get database path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(script_dir)
    db_path = os.path.join(backend_dir, "trading.db")

    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    # Check for dry run flag
    dry_run = "--dry-run" in sys.argv

    # Get days to keep from args or use default
    days_to_keep = 7
    for arg in sys.argv:
        if arg.startswith("--days="):
            days_to_keep = int(arg.split("=")[1])

    if not dry_run:
        # Confirm before running
        print("⚠️  This cleanup will:")
        print(f"   1. Delete failed positions older than {days_to_keep} days")
        print(f"   2. Delete failed order_history older than {days_to_keep} days")
        print("   3. Keep recent failures for debugging")
        print()
        response = input("Continue? (yes/no): ")
        if response.lower() != "yes":
            print("Cleanup cancelled")
            sys.exit(0)

    run_cleanup(db_path, days_to_keep=days_to_keep, dry_run=dry_run)
