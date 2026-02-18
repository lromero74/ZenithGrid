"""
Migration: Add user_content_seen_status table for tracking read/seen articles
and videos per user.

Idempotent — safe to re-run.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "trading.db"
)


def run_migration():
    """Create user_content_seen_status table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_content_seen_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL
                REFERENCES users(id) ON DELETE CASCADE,
            content_type TEXT NOT NULL,
            content_id INTEGER NOT NULL,
            seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, content_type, content_id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_content_seen_lookup
        ON user_content_seen_status(user_id, content_type)
    """)

    conn.commit()
    conn.close()
    logger.info("Migration complete: user_content_seen_status table ready")


if __name__ == "__main__":
    run_migration()
