#!/usr/bin/env python3
"""
Add user_attempt_number to positions table

This migration implements dual numbering:
- user_attempt_number: Sequential counter for ALL position attempts (success + failed)
- user_deal_number: Sequential counter for SUCCESSFUL deals only (like 3Commas)

This allows:
- Clean deal numbers that only count successful positions
- Full tracking of failed attempts for debugging
- Better alignment with 3Commas behavior

Run with: python migrations/add_user_attempt_number.py
"""

import os
import sqlite3
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_migration(db_path: str):
    """Add user_attempt_number column and backfill with chronological numbering"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("=" * 80)
        print("ADD USER_ATTEMPT_NUMBER MIGRATION")
        print("=" * 80)
        print()

        # Step 1: Check if column already exists
        cursor.execute("PRAGMA table_info(positions)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'user_attempt_number' in columns:
            print("✓ user_attempt_number column already exists, skipping migration")
            return

        # Step 2: Add user_attempt_number column
        print("Step 1: Adding user_attempt_number column to positions table...")
        cursor.execute("""
            ALTER TABLE positions
            ADD COLUMN user_attempt_number INTEGER
        """)
        print("  ✓ Column added")

        # Step 3: Backfill attempt numbers
        print("\nStep 2: Backfilling attempt numbers for existing positions...")
        print("  (Assigning sequential numbers based on position creation order)")

        # Get all users
        cursor.execute("SELECT DISTINCT user_id FROM positions WHERE user_id IS NOT NULL")
        users = cursor.fetchall()

        total_updated = 0
        for (user_id,) in users:
            # Get positions for this user in chronological order
            cursor.execute("""
                SELECT id FROM positions
                WHERE user_id = ?
                ORDER BY opened_at, id
            """, (user_id,))
            position_ids = [row[0] for row in cursor.fetchall()]

            # Assign sequential attempt numbers
            for attempt_num, pos_id in enumerate(position_ids, start=1):
                cursor.execute("""
                    UPDATE positions
                    SET user_attempt_number = ?
                    WHERE id = ?
                """, (attempt_num, pos_id))
                total_updated += 1

            print(f"    User {user_id}: Assigned attempt numbers 1-{len(position_ids)}")

        # Handle positions without user_id (legacy)
        cursor.execute("""
            SELECT COUNT(*) FROM positions WHERE user_id IS NULL
        """)
        legacy_count = cursor.fetchone()[0]

        if legacy_count > 0:
            print(f"\n  Handling {legacy_count} legacy positions (user_id IS NULL)...")
            cursor.execute("""
                SELECT id FROM positions
                WHERE user_id IS NULL
                ORDER BY opened_at, id
            """)
            position_ids = [row[0] for row in cursor.fetchall()]

            for attempt_num, pos_id in enumerate(position_ids, start=1):
                cursor.execute("""
                    UPDATE positions
                    SET user_attempt_number = ?
                    WHERE id = ?
                """, (attempt_num, pos_id))
                total_updated += 1

            print(f"    Legacy: Assigned attempt numbers 1-{len(position_ids)}")

        print(f"\n  ✓ Updated {total_updated} positions with attempt numbers")

        # Step 4: Create index for performance
        print("\nStep 3: Creating index on user_attempt_number...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_positions_user_attempt_number
            ON positions(user_attempt_number)
        """)
        print("  ✓ Index created")

        # Step 5: Show statistics
        print("\nStep 4: Analyzing current state...")

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN user_deal_number IS NOT NULL THEN 1 END) as with_deal_number,
                COUNT(CASE WHEN user_deal_number IS NULL THEN 1 END) as without_deal_number,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
            FROM positions
            WHERE user_id IS NOT NULL
        """)
        row = cursor.fetchone()
        total, with_deal, without_deal, failed = row

        print(f"  Total positions: {total}")
        print(f"    With deal numbers: {with_deal}")
        print(f"    Without deal numbers: {without_deal}")
        print(f"    Failed: {failed}")
        print()
        print(f"  📊 Failure rate: {failed}/{total} = {(failed/total*100):.1f}%")

        # Commit changes
        conn.commit()
        print("\n✅ Migration completed successfully!")
        print()
        print("Next steps:")
        print("  1. Update Position model to include user_attempt_number")
        print("  2. Modify create_position() to assign attempt_number first")
        print("  3. Modify base order execution to assign deal_number only on success")
        print()

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    # Get database path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(script_dir)
    db_path = os.path.join(backend_dir, "trading.db")

    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    # Confirm before running
    print("⚠️  This migration will:")
    print("   1. Add user_attempt_number column to positions table")
    print("   2. Backfill attempt numbers for all existing positions")
    print("   3. Create index for performance")
    print()
    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        print("Migration cancelled")
        sys.exit(0)

    run_migration(db_path)
