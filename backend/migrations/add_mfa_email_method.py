"""
Database migration: Add email-based MFA support

Adds to users table:
- mfa_email_enabled (BOOLEAN DEFAULT 0) - Whether email MFA is active

Reuses existing email_verification_tokens table with token_type="mfa_email"
for MFA email verification tokens.
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
    ("users", "mfa_email_enabled", "BOOLEAN DEFAULT 0"),
]


def migrate():
    """Run migration to add email MFA support"""
    logger.info("Starting email MFA support migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
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

        conn.commit()
        logger.info("Email MFA support migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration (informational only)"""
    logger.info(
        "Rollback: No destructive rollback for mfa_email_enabled column."
    )
    logger.info(
        "Column will remain but is unused if feature is disabled."
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
