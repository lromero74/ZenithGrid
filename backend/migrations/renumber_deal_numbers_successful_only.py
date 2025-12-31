#!/usr/bin/env python3
"""
Renumber Deal Numbers - Successful Positions Only

This migration renumbers user_deal_number so that ONLY positions with
successful base orders (positions that have trades) get deal numbers.

Failed positions (no trades) will have:
- user_attempt_number: Set (tracks all attempts)
- user_deal_number: NULL (no successful deal)

This aligns with 3Commas behavior where deal numbers only count successful deals.

Run with: python migrations/renumber_deal_numbers_successful_only.py
"""

import os
import sqlite3
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_migration(db_path: str):
    """Renumber deal numbers for successful positions only"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("=" * 80)
        print("RENUMBER DEAL NUMBERS - SUCCESSFUL POSITIONS ONLY")
        print("=" * 80)
        print()

        # Step 1: Analyze current state
        print("Step 1: Analyzing current state...")
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN user_deal_number IS NOT NULL THEN 1 END) as with_deal_num,
                COUNT(CASE WHEN EXISTS (
                    SELECT 1 FROM trades t WHERE t.position_id = positions.id
                ) THEN 1 END) as with_trades,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
            FROM positions
            WHERE user_id IS NOT NULL
        """)
        total, with_deal, with_trades, failed = cursor.fetchone()

        print(f"  Total positions: {total}")
        print(f"    Currently have deal numbers: {with_deal}")
        print(f"    Have successful trades: {with_trades}")
        print(f"    Failed (no trades): {failed}")
        print()

        # Step 2: Clear deal numbers for positions without trades
        print("Step 2: Clearing deal numbers from failed positions (no trades)...")
        cursor.execute("""
            UPDATE positions
            SET user_deal_number = NULL
            WHERE user_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM trades t WHERE t.position_id = positions.id
              )
        """)
        cleared_count = cursor.rowcount
        print(f"  ✓ Cleared {cleared_count} deal numbers from positions without trades")

        # Step 3: Renumber successful positions
        print("\nStep 3: Renumbering successful positions (with trades)...")

        # Get all users
        cursor.execute("SELECT DISTINCT user_id FROM positions WHERE user_id IS NOT NULL")
        users = cursor.fetchall()

        total_renumbered = 0
        for (user_id,) in users:
            # Get successful positions for this user (positions with trades), in chronological order
            cursor.execute("""
                SELECT DISTINCT p.id
                FROM positions p
                WHERE p.user_id = ?
                  AND EXISTS (SELECT 1 FROM trades t WHERE t.position_id = p.id)
                ORDER BY p.opened_at, p.id
            """, (user_id,))
            position_ids = [row[0] for row in cursor.fetchall()]

            # Assign sequential deal numbers (1, 2, 3, ...)
            for deal_num, pos_id in enumerate(position_ids, start=1):
                cursor.execute("""
                    UPDATE positions
                    SET user_deal_number = ?
                    WHERE id = ?
                """, (deal_num, pos_id))
                total_renumbered += 1

            if position_ids:
                print(f"    User {user_id}: Assigned deal numbers 1-{len(position_ids)} to successful positions")

        print(f"\n  ✓ Renumbered {total_renumbered} successful positions")

        # Step 4: Verify final state
        print("\nStep 4: Verifying final state...")
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN user_deal_number IS NOT NULL THEN 1 END) as with_deal_num,
                COUNT(CASE WHEN user_deal_number IS NULL THEN 1 END) as without_deal_num
            FROM positions
            WHERE user_id IS NOT NULL
        """)
        total, with_deal, without_deal = cursor.fetchone()

        print(f"  Total positions: {total}")
        print(f"    With deal numbers (successful): {with_deal}")
        print(f"    Without deal numbers (failed): {without_deal}")

        # Show examples
        print("\n  Examples of renumbered successful positions:")
        cursor.execute("""
            SELECT id, user_attempt_number, user_deal_number, product_id, status
            FROM positions
            WHERE user_id IS NOT NULL
              AND user_deal_number IS NOT NULL
            ORDER BY user_deal_number DESC
            LIMIT 5
        """)
        for row in cursor.fetchall():
            print(f"    Position {row[0]}: Attempt #{row[1]} → Deal #{row[2]} ({row[3]}, {row[4]})")

        print("\n  Examples of failed positions (no deal number):")
        cursor.execute("""
            SELECT id, user_attempt_number, user_deal_number, product_id, status
            FROM positions
            WHERE user_id IS NOT NULL
              AND user_deal_number IS NULL
            ORDER BY id DESC
            LIMIT 5
        """)
        for row in cursor.fetchall():
            print(f"    Position {row[0]}: Attempt #{row[1]} → Deal #None ({row[3]}, {row[4]})")

        # Commit changes
        conn.commit()
        print("\n✅ Migration completed successfully!")
        print()
        print("Result:")
        print(f"  - Successful positions (with trades): {with_deal} deal numbers assigned")
        print(f"  - Failed positions (no trades): {without_deal} have NO deal numbers")
        print(f"  - Deal numbers now count ONLY successful deals (like 3Commas)")
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
    print("   1. Clear deal numbers from failed positions (no trades)")
    print("   2. Renumber successful positions sequentially (1, 2, 3, ...)")
    print("   3. Align deal numbering with 3Commas (successful deals only)")
    print()
    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        print("Migration cancelled")
        sys.exit(0)

    run_migration(db_path)
