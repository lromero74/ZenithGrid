"""
Database migration: Add email verification + password reset tokens

Adds to users table:
- email_verified (BOOLEAN) - Whether user's email is verified
- email_verified_at (TIMESTAMP) - When email was verified

Creates email_verification_tokens table:
- Stores tokens for email verification and password reset
- Single table with token_type to distinguish purpose

Marks all existing users as email_verified=1 (they were admin-created).
"""

import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database path relative to this migration file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")

# Columns to add to users table
USER_COLUMNS = [
    ("users", "email_verified", "BOOLEAN DEFAULT 0"),
    ("users", "email_verified_at", "TIMESTAMP DEFAULT NULL"),
]

# Email verification tokens table DDL
EMAIL_VERIFICATION_TOKENS_TABLE = """
CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    verification_code TEXT DEFAULT NULL,
    token_type TEXT NOT NULL DEFAULT 'email_verify',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP DEFAULT NULL
)
"""

EMAIL_VERIFICATION_TOKENS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_evt_user_id ON email_verification_tokens(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_evt_token ON email_verification_tokens(token)",
]


def migrate():
    """Run migration to add email verification support"""
    logger.info("Starting email verification migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Add email verification columns to users table
        for table, column, col_type in USER_COLUMNS:
            logger.info(f"Adding {column} to {table}...")
            try:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                )
                logger.info(f"  Added {column}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"  Column {column} already exists, skipping")
                else:
                    raise

        # Mark all existing users as email_verified
        cursor.execute("UPDATE users SET email_verified = 1 WHERE email_verified = 0 OR email_verified IS NULL")
        updated = cursor.rowcount
        if updated > 0:
            logger.info(f"  Marked {updated} existing user(s) as email_verified")

        # Create email_verification_tokens table
        logger.info("Creating email_verification_tokens table...")
        cursor.execute(EMAIL_VERIFICATION_TOKENS_TABLE)
        for idx_sql in EMAIL_VERIFICATION_TOKENS_INDEXES:
            cursor.execute(idx_sql)
        logger.info("  email_verification_tokens table ready")

        conn.commit()
        logger.info("Email verification migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration (informational only)"""
    logger.info(
        "Rollback: No destructive rollback for email verification columns."
    )
    logger.info(
        "Columns will remain but are unused if feature is disabled."
    )
    logger.info(
        "email_verification_tokens table can be dropped manually if needed."
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
