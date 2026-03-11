"""
Create chat tables for DMs, group chats, and channels.

Tables created:
- chat_channels (dm/group/channel containers)
- chat_channel_members (membership with role and read tracking)
- chat_messages (messages with edit/soft-delete support)

Also adds chat_retention_days to settings table.

Idempotent: checks for table existence before creating.
"""

import logging
import sys
import os

sys_path_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if sys_path_dir not in sys.path:
    sys.path.insert(0, sys_path_dir)

from migrations.db_utils import get_migration_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MIGRATION_NAME = "create_chat_tables"


def run(conn):
    cursor = conn.cursor()

    try:
        # Detect database type
        try:
            cursor.execute("SELECT version()")
            is_pg = True
        except Exception:
            conn.rollback()
            is_pg = False

        def table_exists(name):
            if is_pg:
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                    (name,)
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (name,)
                )
            return cursor.fetchone() is not None

        # --- chat_channels ---
        if not table_exists("chat_channels"):
            cursor.execute("""
                CREATE TABLE chat_channels (
                    id SERIAL PRIMARY KEY,
                    type VARCHAR NOT NULL,
                    name VARCHAR,
                    created_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """ if is_pg else """
                CREATE TABLE chat_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type VARCHAR NOT NULL,
                    name VARCHAR,
                    created_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("Created chat_channels table")

        # --- chat_channel_members ---
        if not table_exists("chat_channel_members"):
            cursor.execute("""
                CREATE TABLE chat_channel_members (
                    id SERIAL PRIMARY KEY,
                    channel_id INTEGER NOT NULL REFERENCES chat_channels(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    role VARCHAR DEFAULT 'member',
                    last_read_at TIMESTAMP,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_chat_channel_member UNIQUE (channel_id, user_id)
                )
            """ if is_pg else """
                CREATE TABLE chat_channel_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL REFERENCES chat_channels(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    role VARCHAR DEFAULT 'member',
                    last_read_at TIMESTAMP,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_chat_channel_member UNIQUE (channel_id, user_id)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_chat_channel_members_channel "
                "ON chat_channel_members(channel_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_chat_channel_members_user "
                "ON chat_channel_members(user_id)"
            )
            logger.info("Created chat_channel_members table")

        # --- chat_messages ---
        if not table_exists("chat_messages"):
            cursor.execute("""
                CREATE TABLE chat_messages (
                    id SERIAL PRIMARY KEY,
                    channel_id INTEGER NOT NULL REFERENCES chat_channels(id) ON DELETE CASCADE,
                    sender_id INTEGER NOT NULL REFERENCES users(id),
                    content VARCHAR(2000) NOT NULL,
                    edited_at TIMESTAMP,
                    deleted_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """ if is_pg else """
                CREATE TABLE chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL REFERENCES chat_channels(id) ON DELETE CASCADE,
                    sender_id INTEGER NOT NULL REFERENCES users(id),
                    content VARCHAR(2000) NOT NULL,
                    edited_at TIMESTAMP,
                    deleted_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_channel_created "
                "ON chat_messages(channel_id, created_at)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_sender "
                "ON chat_messages(sender_id)"
            )
            logger.info("Created chat_messages table")

        # --- Seed chat_retention_days setting (0 = keep forever) ---
        if table_exists("settings"):
            param = "%s" if is_pg else "?"
            cursor.execute(
                f"SELECT 1 FROM settings WHERE key = {param}",
                ("chat_retention_days",)
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"INSERT INTO settings (key, value, value_type, description) "
                    f"VALUES ({param}, {param}, {param}, {param})",
                    ("chat_retention_days", "0", "int",
                     "Days to retain chat messages. 0 = keep forever.")
                )
                logger.info("Seeded chat_retention_days setting")

        conn.commit()
        logger.info(f"Migration {MIGRATION_NAME} completed successfully")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration {MIGRATION_NAME} failed: {e}")
        raise
    finally:
        cursor.close()


if __name__ == "__main__":
    conn = get_migration_connection()
    try:
        run(conn)
    finally:
        conn.close()
