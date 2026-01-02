#!/usr/bin/env python3
"""
Fix Orphaned Trades and Position ID Reuse

This migration fixes critical database integrity issues:
1. Deletes orphaned trades (trades pointing to deleted positions)
2. Deletes trades created BEFORE their position was opened (data corruption)
3. Adds AUTOINCREMENT to positions.id to prevent ID reuse
4. Adds CASCADE DELETE to trades.position_id FK so trades are deleted with positions

Background:
- When bots are deleted, positions are cascade deleted but trades remain orphaned
- Without AUTOINCREMENT, SQLite reuses deleted position IDs
- New positions "inherit" orphaned trades, causing incorrect totals and "phantom" safety orders

Run with: python migrations/fix_orphaned_trades_and_id_reuse.py
"""

import os
import sqlite3
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_migration(db_path: str, dry_run: bool = False):
    """Run the migration to fix orphaned trades and add AUTOINCREMENT"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("=" * 80)
        print("ORPHANED TRADES & POSITION ID REUSE FIX")
        print("=" * 80)
        print()

        if dry_run:
            print("🔍 DRY RUN MODE - No changes will be made\n")

        # Step 1: Find and delete orphaned trades (position_id doesn't exist)
        print("Step 1: Finding orphaned trades (position_id doesn't exist)...")
        cursor.execute("""
            SELECT COUNT(*) FROM trades
            WHERE position_id NOT IN (SELECT id FROM positions)
        """)
        orphaned_count = cursor.fetchone()[0]
        print(f"  Found {orphaned_count} orphaned trades")

        if orphaned_count > 0 and not dry_run:
            cursor.execute("""
                DELETE FROM trades
                WHERE position_id NOT IN (SELECT id FROM positions)
            """)
            print(f"  ✓ Deleted {orphaned_count} orphaned trades")

        # Step 2: Find and delete trades created BEFORE their position opened
        print("\nStep 2: Finding trades created before position opened (data corruption)...")
        cursor.execute("""
            SELECT COUNT(*) FROM trades t
            JOIN positions p ON t.position_id = p.id
            WHERE t.timestamp < p.opened_at
        """)
        corrupt_count = cursor.fetchone()[0]
        print(f"  Found {corrupt_count} corrupted trades (timestamp < position.opened_at)")

        if corrupt_count > 0:
            # Show examples
            cursor.execute("""
                SELECT p.id, p.user_deal_number, p.product_id, p.opened_at,
                       t.id, t.trade_type, t.timestamp
                FROM trades t
                JOIN positions p ON t.position_id = p.id
                WHERE t.timestamp < p.opened_at
                ORDER BY p.id, t.timestamp
                LIMIT 10
            """)
            print("  Examples:")
            for row in cursor.fetchall():
                print(f"    Position {row[0]} (Deal #{row[1]}, {row[2]}) opened {row[3]}")
                print(f"      → Trade {row[4]} ({row[5]}) from {row[6]} (BEFORE opening!)")

            if not dry_run:
                cursor.execute("""
                    DELETE FROM trades
                    WHERE rowid IN (
                        SELECT t.rowid FROM trades t
                        JOIN positions p ON t.position_id = p.id
                        WHERE t.timestamp < p.opened_at
                    )
                """)
                print(f"  ✓ Deleted {corrupt_count} corrupted trades")

        # Step 3: Recalculate position totals for open positions
        print("\nStep 3: Recalculating position totals for open positions...")
        cursor.execute("""
            SELECT id, product_id FROM positions WHERE status = 'open'
        """)
        open_positions = cursor.fetchall()
        print(f"  Found {len(open_positions)} open positions")

        for pos_id, product_id in open_positions:
            # Sum up actual trades
            cursor.execute("""
                SELECT
                    COALESCE(SUM(quote_amount), 0) as total_quote,
                    COALESCE(SUM(base_amount), 0) as total_base
                FROM trades
                WHERE position_id = ? AND side = 'BUY'
            """, (pos_id,))
            total_quote, total_base = cursor.fetchone()

            # Calculate average price
            avg_price = total_quote / total_base if total_base > 0 else 0

            if not dry_run:
                cursor.execute("""
                    UPDATE positions
                    SET total_quote_spent = ?,
                        total_base_acquired = ?,
                        average_buy_price = ?
                    WHERE id = ?
                """, (total_quote, total_base, avg_price, pos_id))

            print(f"    Position {pos_id} ({product_id}): {total_base:.8f} for {total_quote:.10f} BTC @ {avg_price:.8f}")

        # Step 4: Add AUTOINCREMENT to positions table
        print("\nStep 4: Adding AUTOINCREMENT to positions.id...")
        print("  (Requires recreating table)")

        if not dry_run:
            # Get current schema
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='positions'")
            old_schema = cursor.fetchone()[0]

            # Check if already has AUTOINCREMENT
            if 'AUTOINCREMENT' in old_schema:
                print("  ℹ️  positions.id already has AUTOINCREMENT, skipping")
            else:
                # Create new table with AUTOINCREMENT
                # Note: We'll preserve all columns and data
                cursor.execute("""
                    CREATE TABLE positions_new (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        bot_id INTEGER,
                        account_id INTEGER REFERENCES accounts(id),
                        user_id INTEGER REFERENCES users(id),
                        user_deal_number INTEGER,
                        product_id TEXT DEFAULT "ETH-BTC",
                        status VARCHAR DEFAULT "open",
                        opened_at DATETIME,
                        closed_at DATETIME,
                        exchange_type VARCHAR DEFAULT 'cex' NOT NULL,
                        chain_id INTEGER,
                        dex_router VARCHAR,
                        wallet_address VARCHAR,
                        strategy_config_snapshot TEXT,
                        initial_quote_balance FLOAT,
                        max_quote_allowed FLOAT,
                        total_quote_spent FLOAT DEFAULT 0.0,
                        total_base_acquired FLOAT DEFAULT 0.0,
                        average_buy_price FLOAT DEFAULT 0.0,
                        sell_price FLOAT,
                        total_quote_received FLOAT,
                        profit_quote FLOAT,
                        profit_percentage FLOAT,
                        btc_usd_price_at_open FLOAT,
                        btc_usd_price_at_close FLOAT,
                        profit_usd FLOAT,
                        highest_price_since_tp REAL,
                        trailing_tp_active INTEGER DEFAULT 0,
                        highest_price_since_entry REAL,
                        last_error_message TEXT,
                        last_error_timestamp DATETIME,
                        notes TEXT,
                        closing_via_limit BOOLEAN DEFAULT 0,
                        limit_close_order_id TEXT,
                        trailing_stop_loss_price REAL,
                        trailing_stop_loss_active BOOLEAN DEFAULT 0,
                        entry_stop_loss REAL,
                        entry_take_profit_target REAL,
                        pattern_data TEXT,
                        exit_reason TEXT,
                        previous_indicators TEXT,
                        FOREIGN KEY(bot_id) REFERENCES bots (id)
                    )
                """)

                # Copy data with explicit column mapping
                cursor.execute("""
                    INSERT INTO positions_new (
                        id, bot_id, account_id, user_id, user_deal_number, product_id, status,
                        opened_at, closed_at, exchange_type, chain_id, dex_router, wallet_address,
                        strategy_config_snapshot, initial_quote_balance, max_quote_allowed,
                        total_quote_spent, total_base_acquired, average_buy_price,
                        sell_price, total_quote_received, profit_quote, profit_percentage,
                        btc_usd_price_at_open, btc_usd_price_at_close, profit_usd,
                        highest_price_since_tp, trailing_tp_active, highest_price_since_entry,
                        last_error_message, last_error_timestamp, notes,
                        closing_via_limit, limit_close_order_id,
                        trailing_stop_loss_price, trailing_stop_loss_active,
                        entry_stop_loss, entry_take_profit_target, pattern_data,
                        exit_reason, previous_indicators
                    )
                    SELECT
                        id, bot_id, account_id, user_id, user_deal_number, product_id, status,
                        opened_at, closed_at, exchange_type, chain_id, dex_router, wallet_address,
                        strategy_config_snapshot, initial_quote_balance, max_quote_allowed,
                        total_quote_spent, total_base_acquired, average_buy_price,
                        sell_price, total_quote_received, profit_quote, profit_percentage,
                        btc_usd_price_at_open, btc_usd_price_at_close, profit_usd,
                        highest_price_since_tp, trailing_tp_active, highest_price_since_entry,
                        last_error_message, last_error_timestamp, notes,
                        closing_via_limit, limit_close_order_id,
                        trailing_stop_loss_price, trailing_stop_loss_active,
                        entry_stop_loss, entry_take_profit_target, pattern_data,
                        exit_reason, previous_indicators
                    FROM positions
                """)

                # Drop old table and rename
                cursor.execute("DROP TABLE positions")
                cursor.execute("ALTER TABLE positions_new RENAME TO positions")

                # Recreate indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_positions_user_id ON positions(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_positions_user_deal_number ON positions(user_deal_number)")

                print("  ✓ Added AUTOINCREMENT to positions.id")

        # Step 5: Add CASCADE DELETE to trades.position_id FK
        print("\nStep 5: Adding CASCADE DELETE to trades.position_id FK...")
        print("  (Requires recreating table)")

        if not dry_run:
            # Create new trades table with CASCADE DELETE
            cursor.execute("""
                CREATE TABLE trades_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    position_id INTEGER NOT NULL,
                    timestamp DATETIME NOT NULL,
                    side VARCHAR NOT NULL,
                    quote_amount FLOAT NOT NULL,
                    base_amount FLOAT NOT NULL,
                    price FLOAT NOT NULL,
                    trade_type VARCHAR NOT NULL,
                    order_id VARCHAR,
                    macd_value FLOAT,
                    macd_signal FLOAT,
                    macd_histogram FLOAT,
                    FOREIGN KEY(position_id) REFERENCES positions(id) ON DELETE CASCADE
                )
            """)

            # Copy data with explicit column mapping
            cursor.execute("""
                INSERT INTO trades_new (
                    id, position_id, timestamp, side, quote_amount, base_amount,
                    price, trade_type, order_id, macd_value, macd_signal, macd_histogram
                )
                SELECT
                    id, position_id, timestamp, side, quote_amount, base_amount,
                    price, trade_type, order_id, macd_value, macd_signal, macd_histogram
                FROM trades
            """)

            # Drop old table and rename
            cursor.execute("DROP TABLE trades")
            cursor.execute("ALTER TABLE trades_new RENAME TO trades")

            print("  ✓ Added CASCADE DELETE to trades.position_id")

        # Commit if not dry run
        if not dry_run:
            conn.commit()
            print("\n✅ Migration completed successfully!")
        else:
            print("\n🔍 Dry run completed - no changes made")

        print()
        print("Summary:")
        print(f"  - Orphaned trades deleted: {orphaned_count}")
        print(f"  - Corrupted trades deleted: {corrupt_count}")
        print(f"  - Open positions recalculated: {len(open_positions)}")
        print(f"  - positions.id: AUTOINCREMENT {'would be added' if dry_run else 'added'}")
        print(f"  - trades.position_id: CASCADE DELETE {'would be added' if dry_run else 'added'}")
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

    # Check if dry run
    dry_run = "--dry-run" in sys.argv

    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    # Confirm before running
    if not dry_run:
        print("⚠️  This migration will:")
        print("   1. Delete orphaned and corrupted trades")
        print("   2. Recreate positions table with AUTOINCREMENT")
        print("   3. Recreate trades table with CASCADE DELETE")
        print()
        response = input("Continue? (yes/no): ")
        if response.lower() != "yes":
            print("Migration cancelled")
            sys.exit(0)

    run_migration(db_path, dry_run=dry_run)
