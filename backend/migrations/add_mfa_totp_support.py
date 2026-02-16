"""
Database migration: Add MFA TOTP support + Trusted Devices

Adds to users table:
- totp_secret (TEXT) - Fernet-encrypted TOTP secret key
- mfa_enabled (BOOLEAN) - Whether MFA is active for the user

Creates trusted_devices table:
- Stores 30-day "remember this device" tokens for MFA bypass
- Users can view and revoke trusted devices from Settings
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
    ("users", "totp_secret", "TEXT DEFAULT NULL"),
    ("users", "mfa_enabled", "BOOLEAN DEFAULT 0"),
]

# Trusted devices table DDL
TRUSTED_DEVICES_TABLE = """
CREATE TABLE IF NOT EXISTS trusted_devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id TEXT UNIQUE NOT NULL,
    device_name TEXT,
    ip_address TEXT,
    location TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
)
"""

TRUSTED_DEVICES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_trusted_devices_user_id ON trusted_devices(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_trusted_devices_device_id ON trusted_devices(device_id)",
]


def migrate():
    """Run migration to add MFA TOTP support and trusted devices"""
    logger.info("Starting MFA TOTP support migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Add MFA columns to users table
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

        # Create trusted_devices table
        logger.info("Creating trusted_devices table...")
        cursor.execute(TRUSTED_DEVICES_TABLE)
        for idx_sql in TRUSTED_DEVICES_INDEXES:
            cursor.execute(idx_sql)
        logger.info("  trusted_devices table ready")

        conn.commit()
        logger.info("MFA TOTP support migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration (informational only)"""
    logger.info(
        "Rollback: No destructive rollback for MFA columns."
    )
    logger.info(
        "Columns will remain but are unused if feature is disabled."
    )
    logger.info(
        "trusted_devices table can be dropped manually if needed."
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
