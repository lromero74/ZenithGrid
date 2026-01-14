"""
Database migration: Add paper trading account support

Adds:
- is_paper_trading flag to accounts table
- Virtual balance tracking for paper accounts
- Auto-creation of paper accounts for existing users
"""

import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database path relative to this migration file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")


def migrate():
    """Run migration to add paper trading support"""
    logger.info("🔄 Starting paper trading accounts migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Add is_paper_trading column to accounts table
        logger.info("Adding is_paper_trading column to accounts table...")
        try:
            cursor.execute("""
                ALTER TABLE accounts
                ADD COLUMN is_paper_trading BOOLEAN DEFAULT 0
            """)
            logger.info("✅ Added is_paper_trading column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⚠️ Column is_paper_trading already exists, skipping")
            else:
                raise

        # 2. Add paper_balances column (JSON) for virtual balances
        logger.info("Adding paper_balances column to accounts table...")
        try:
            cursor.execute("""
                ALTER TABLE accounts
                ADD COLUMN paper_balances TEXT DEFAULT NULL
            """)
            logger.info("✅ Added paper_balances column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("⚠️ Column paper_balances already exists, skipping")
            else:
                raise

        # 3. Auto-create paper trading accounts for existing users
        logger.info("Creating paper trading accounts for existing users...")

        # Get all users who don't have a paper trading account yet
        cursor.execute("""
            SELECT DISTINCT u.id, u.email
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM accounts a
                WHERE a.user_id = u.id
                AND a.is_paper_trading = 1
            )
        """)
        users_without_paper_account = cursor.fetchall()

        if users_without_paper_account:
            logger.info(f"Found {len(users_without_paper_account)} users without paper trading accounts")

            for user_id, email in users_without_paper_account:
                # Create paper trading account
                cursor.execute("""
                    INSERT INTO accounts (
                        user_id,
                        name,
                        type,
                        is_default,
                        is_active,
                        is_paper_trading,
                        exchange,
                        paper_balances
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    "Paper Trading",
                    "cex",
                    0,  # Not default
                    1,  # Active
                    1,  # Paper trading
                    "paper",
                    '{"BTC": 1.0, "ETH": 10.0, "USD": 100000.0, "USDC": 0.0, "USDT": 0.0}'
                ))

                logger.info(f"✅ Created paper trading account for user {user_id} ({email})")
        else:
            logger.info("No users need paper trading accounts")

        conn.commit()
        logger.info("✅ Paper trading migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration (remove columns)"""
    logger.info("🔄 Rolling back paper trading migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Note: SQLite doesn't support DROP COLUMN directly
        # We'd need to recreate the table to remove columns
        # For now, just mark paper accounts as inactive

        cursor.execute("""
            UPDATE accounts
            SET is_active = 0
            WHERE is_paper_trading = 1
        """)

        conn.commit()
        logger.info("✅ Deactivated all paper trading accounts")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Rollback failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
