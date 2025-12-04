"""
Multi-User Support Migration

This migration:
1. Creates the 'users' table
2. Adds user_id column to accounts, bots, bot_templates, blacklisted_coins
3. Creates an initial user (louis_romero@outlook.com / pass1234)
4. Migrates all existing data to that user

Run with: cd backend && ./venv/bin/python migrations/add_multi_user_support.py
"""

import sqlite3
from datetime import datetime
import bcrypt

DATABASE_PATH = "trading.db"

# Initial user credentials
INITIAL_USER_EMAIL = "louis_romero@outlook.com"
INITIAL_USER_PASSWORD = "pass1234"


def run_migration():
    """Run the multi-user support migration."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # Step 1: Create users table
        print("Creating users table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                hashed_password TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                is_superuser INTEGER DEFAULT 0,
                display_name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login_at DATETIME
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)")
        print("  - users table created")

        # Step 2: Add user_id column to accounts
        print("Adding user_id to accounts...")
        try:
            cursor.execute("ALTER TABLE accounts ADD COLUMN user_id INTEGER REFERENCES users(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_accounts_user_id ON accounts(user_id)")
            print("  - user_id column added to accounts")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  - user_id column already exists in accounts")
            else:
                raise

        # Step 3: Add user_id column to bots
        print("Adding user_id to bots...")
        try:
            cursor.execute("ALTER TABLE bots ADD COLUMN user_id INTEGER REFERENCES users(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_bots_user_id ON bots(user_id)")
            print("  - user_id column added to bots")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  - user_id column already exists in bots")
            else:
                raise

        # Step 4: Add user_id column to bot_templates
        print("Adding user_id to bot_templates...")
        try:
            cursor.execute("ALTER TABLE bot_templates ADD COLUMN user_id INTEGER REFERENCES users(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_bot_templates_user_id ON bot_templates(user_id)")
            print("  - user_id column added to bot_templates")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  - user_id column already exists in bot_templates")
            else:
                raise

        # Step 5: Add user_id column to blacklisted_coins
        print("Adding user_id to blacklisted_coins...")
        try:
            cursor.execute("ALTER TABLE blacklisted_coins ADD COLUMN user_id INTEGER REFERENCES users(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_blacklisted_coins_user_id ON blacklisted_coins(user_id)")
            print("  - user_id column added to blacklisted_coins")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  - user_id column already exists in blacklisted_coins")
            else:
                raise

        # Step 6: Create initial user
        print(f"Creating initial user ({INITIAL_USER_EMAIL})...")
        hashed_password = bcrypt.hashpw(INITIAL_USER_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Check if user already exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (INITIAL_USER_EMAIL,))
        existing_user = cursor.fetchone()

        if existing_user:
            user_id = existing_user[0]
            print(f"  - User already exists with id {user_id}")
        else:
            cursor.execute("""
                INSERT INTO users (email, hashed_password, is_active, is_superuser, display_name, created_at, updated_at)
                VALUES (?, ?, 1, 1, 'Louis Romero', ?, ?)
            """, (INITIAL_USER_EMAIL, hashed_password, datetime.utcnow(), datetime.utcnow()))
            user_id = cursor.lastrowid
            print(f"  - Created user with id {user_id}")

        # Step 7: Migrate existing data to the initial user
        print("Migrating existing data to initial user...")

        # Update accounts
        cursor.execute("UPDATE accounts SET user_id = ? WHERE user_id IS NULL", (user_id,))
        accounts_updated = cursor.rowcount
        print(f"  - Updated {accounts_updated} accounts")

        # Update bots
        cursor.execute("UPDATE bots SET user_id = ? WHERE user_id IS NULL", (user_id,))
        bots_updated = cursor.rowcount
        print(f"  - Updated {bots_updated} bots")

        # Update bot_templates
        cursor.execute("UPDATE bot_templates SET user_id = ? WHERE user_id IS NULL", (user_id,))
        templates_updated = cursor.rowcount
        print(f"  - Updated {templates_updated} bot_templates")

        # Update blacklisted_coins
        cursor.execute("UPDATE blacklisted_coins SET user_id = ? WHERE user_id IS NULL", (user_id,))
        coins_updated = cursor.rowcount
        print(f"  - Updated {coins_updated} blacklisted_coins")

        conn.commit()
        print("\nMigration completed successfully!")
        print(f"Initial user: {INITIAL_USER_EMAIL}")
        print(f"Initial password: {INITIAL_USER_PASSWORD}")
        print("\nIMPORTANT: Please change the password after first login!")

    except Exception as e:
        conn.rollback()
        print(f"\nMigration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
