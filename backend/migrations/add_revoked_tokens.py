"""
Database migration: Add token revocation support

Creates revoked_tokens table:
- Stores JTIs of revoked JWT tokens (from logout, password change, etc.)
- Indexed for fast lookup on every authenticated request
- Expired entries cleaned up by periodic background task

Adds to users table:
- tokens_valid_after (DATETIME) — bulk revocation timestamp
  When set, any token with iat < tokens_valid_after is rejected.
  Used by password change / reset to invalidate all sessions at once.
"""

import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database path relative to this migration file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")

REVOKED_TOKENS_TABLE = """
CREATE TABLE IF NOT EXISTS revoked_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jti TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    revoked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL
)
"""

REVOKED_TOKENS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_revoked_tokens_jti ON revoked_tokens(jti)",
    "CREATE INDEX IF NOT EXISTS ix_revoked_tokens_user_id ON revoked_tokens(user_id)",
]

USER_COLUMNS = [
    ("users", "tokens_valid_after", "DATETIME DEFAULT NULL"),
]


def migrate():
    """Run migration to add token revocation support."""
    logger.info("Starting token revocation migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Create revoked_tokens table
        logger.info("Creating revoked_tokens table...")
        cursor.execute(REVOKED_TOKENS_TABLE)
        for idx_sql in REVOKED_TOKENS_INDEXES:
            cursor.execute(idx_sql)
        logger.info("  revoked_tokens table ready")

        # Add tokens_valid_after column to users
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
        logger.info("Token revocation migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration (informational only)."""
    logger.info(
        "Rollback: DROP TABLE revoked_tokens; "
        "ALTER TABLE users DROP COLUMN tokens_valid_after"
    )
