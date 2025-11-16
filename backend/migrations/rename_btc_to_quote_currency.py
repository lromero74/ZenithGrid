"""
Migration: Rename BTC-specific columns to quote-currency agnostic names

This migration renames columns in positions and trades tables to support
both BTC and USD (or any other) quote currencies.

OLD NAME                  -> NEW NAME
--------------------------------------
initial_btc_balance       -> initial_quote_balance
max_btc_allowed           -> max_quote_allowed
total_btc_spent           -> total_quote_spent
total_eth_acquired        -> total_base_acquired
total_btc_received        -> total_quote_received
profit_btc                -> profit_quote

Trade table:
btc_amount                -> quote_amount
eth_amount                -> base_amount
"""

import sqlite3
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = "backend/trading.db"


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("🔄 Starting migration: Rename BTC-specific columns to quote currency...")

    try:
        # Step 1: Create new positions table with renamed columns
        print("  Creating new positions table...")
        cursor.execute("""
            CREATE TABLE positions_new (
                id INTEGER NOT NULL PRIMARY KEY,
                bot_id INTEGER,
                status VARCHAR,
                opened_at DATETIME,
                closed_at DATETIME,
                initial_quote_balance FLOAT,
                max_quote_allowed FLOAT,
                total_quote_spent FLOAT,
                total_base_acquired FLOAT,
                average_buy_price FLOAT,
                sell_price FLOAT,
                total_quote_received FLOAT,
                profit_quote FLOAT,
                profit_percentage FLOAT,
                btc_usd_price_at_open FLOAT,
                btc_usd_price_at_close FLOAT,
                profit_usd FLOAT,
                product_id TEXT DEFAULT "ETH-BTC",
                highest_price_since_tp REAL,
                trailing_tp_active INTEGER DEFAULT 0,
                highest_price_since_entry REAL,
                FOREIGN KEY(bot_id) REFERENCES bots (id)
            )
        """)

        # Step 2: Copy data from old table to new table
        print("  Copying positions data...")
        cursor.execute("""
            INSERT INTO positions_new (
                id, bot_id, status, opened_at, closed_at,
                initial_quote_balance, max_quote_allowed, total_quote_spent,
                total_base_acquired, average_buy_price, sell_price,
                total_quote_received, profit_quote, profit_percentage,
                btc_usd_price_at_open, btc_usd_price_at_close, profit_usd,
                product_id, highest_price_since_tp, trailing_tp_active,
                highest_price_since_entry
            )
            SELECT
                id, bot_id, status, opened_at, closed_at,
                initial_btc_balance, max_btc_allowed, total_btc_spent,
                total_eth_acquired, average_buy_price, sell_price,
                total_btc_received, profit_btc, profit_percentage,
                btc_usd_price_at_open, btc_usd_price_at_close, profit_usd,
                product_id, highest_price_since_tp, trailing_tp_active,
                highest_price_since_entry
            FROM positions
        """)

        # Step 3: Drop old table and rename new table
        print("  Replacing old positions table...")
        cursor.execute("DROP TABLE positions")
        cursor.execute("ALTER TABLE positions_new RENAME TO positions")
        cursor.execute("CREATE INDEX ix_positions_id ON positions (id)")

        # Step 4: Create new trades table with renamed columns
        print("  Creating new trades table...")
        cursor.execute("""
            CREATE TABLE trades_new (
                id INTEGER NOT NULL PRIMARY KEY,
                position_id INTEGER,
                timestamp DATETIME,
                side VARCHAR,
                quote_amount FLOAT,
                base_amount FLOAT,
                price FLOAT,
                trade_type VARCHAR,
                order_id VARCHAR,
                macd_value FLOAT,
                macd_signal FLOAT,
                macd_histogram FLOAT,
                FOREIGN KEY(position_id) REFERENCES positions (id)
            )
        """)

        # Step 5: Copy data from old trades table
        print("  Copying trades data...")
        cursor.execute("""
            INSERT INTO trades_new (
                id, position_id, timestamp, side, quote_amount, base_amount,
                price, trade_type, order_id, macd_value, macd_signal, macd_histogram
            )
            SELECT
                id, position_id, timestamp, side, btc_amount, eth_amount,
                price, trade_type, order_id, macd_value, macd_signal, macd_histogram
            FROM trades
        """)

        # Step 6: Drop old table and rename new table
        print("  Replacing old trades table...")
        cursor.execute("DROP TABLE trades")
        cursor.execute("ALTER TABLE trades_new RENAME TO trades")
        cursor.execute("CREATE INDEX ix_trades_id ON trades (id)")

        # Commit all changes
        conn.commit()
        print("✅ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


def rollback():
    """Rollback migration by renaming columns back to original names"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("🔄 Rolling back migration...")

    try:
        # Rollback positions table
        print("  Creating old positions table...")
        cursor.execute("""
            CREATE TABLE positions_old (
                id INTEGER NOT NULL PRIMARY KEY,
                bot_id INTEGER,
                status VARCHAR,
                opened_at DATETIME,
                closed_at DATETIME,
                initial_btc_balance FLOAT,
                max_btc_allowed FLOAT,
                total_btc_spent FLOAT,
                total_eth_acquired FLOAT,
                average_buy_price FLOAT,
                sell_price FLOAT,
                total_btc_received FLOAT,
                profit_btc FLOAT,
                profit_percentage FLOAT,
                btc_usd_price_at_open FLOAT,
                btc_usd_price_at_close FLOAT,
                profit_usd FLOAT,
                product_id TEXT DEFAULT "ETH-BTC",
                highest_price_since_tp REAL,
                trailing_tp_active INTEGER DEFAULT 0,
                highest_price_since_entry REAL,
                FOREIGN KEY(bot_id) REFERENCES bots (id)
            )
        """)

        cursor.execute("""
            INSERT INTO positions_old SELECT
                id, bot_id, status, opened_at, closed_at,
                initial_quote_balance, max_quote_allowed, total_quote_spent,
                total_base_acquired, average_buy_price, sell_price,
                total_quote_received, profit_quote, profit_percentage,
                btc_usd_price_at_open, btc_usd_price_at_close, profit_usd,
                product_id, highest_price_since_tp, trailing_tp_active,
                highest_price_since_entry
            FROM positions
        """)

        cursor.execute("DROP TABLE positions")
        cursor.execute("ALTER TABLE positions_old RENAME TO positions")
        cursor.execute("CREATE INDEX ix_positions_id ON positions (id)")

        # Rollback trades table
        print("  Creating old trades table...")
        cursor.execute("""
            CREATE TABLE trades_old (
                id INTEGER NOT NULL PRIMARY KEY,
                position_id INTEGER,
                timestamp DATETIME,
                side VARCHAR,
                btc_amount FLOAT,
                eth_amount FLOAT,
                price FLOAT,
                trade_type VARCHAR,
                order_id VARCHAR,
                macd_value FLOAT,
                macd_signal FLOAT,
                macd_histogram FLOAT,
                FOREIGN KEY(position_id) REFERENCES positions (id)
            )
        """)

        cursor.execute("""
            INSERT INTO trades_old SELECT * FROM trades
        """)

        cursor.execute("DROP TABLE trades")
        cursor.execute("ALTER TABLE trades_old RENAME TO trades")
        cursor.execute("CREATE INDEX ix_trades_id ON trades (id)")

        conn.commit()
        print("✅ Rollback completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Rollback failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
