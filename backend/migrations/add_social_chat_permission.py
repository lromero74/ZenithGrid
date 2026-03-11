"""
Add social:chat permission and assign to trader/paper_trader/super_admin roles.

Separates social features (chat, friends) from game features (multiplayer).
Users can message friends without needing games:multiplayer permission.

Demo users (Observers/viewer role) do NOT get this permission.

Idempotent: checks before inserting.
"""

import logging
import os
import sys

sys_path_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if sys_path_dir not in sys.path:
    sys.path.insert(0, sys_path_dir)

from migrations.db_utils import get_migration_connection, is_postgres  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MIGRATION_NAME = "add_social_chat_permission"


def run(conn):
    cursor = conn.cursor()
    try:
        pg = is_postgres()

        # Add permission
        if pg:
            cursor.execute(
                "INSERT INTO permissions (name, description) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                ("social:chat", "Access chat, friends, and social features"),
            )
        else:
            cursor.execute(
                "INSERT OR IGNORE INTO permissions (name, description) VALUES (?, ?)",
                ("social:chat", "Access chat, friends, and social features"),
            )

        # Get permission id
        if pg:
            cursor.execute("SELECT id FROM permissions WHERE name = %s", ("social:chat",))
        else:
            cursor.execute("SELECT id FROM permissions WHERE name = ?", ("social:chat",))
        perm_row = cursor.fetchone()
        if not perm_row:
            logger.error("Failed to find social:chat permission")
            return
        perm_id = perm_row[0]

        # Assign to trader, paper_trader, and super_admin roles (NOT viewer/Observers)
        for role_name in ("trader", "paper_trader", "super_admin"):
            if pg:
                cursor.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
            else:
                cursor.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
            role_row = cursor.fetchone()
            if not role_row:
                continue
            role_id = role_row[0]

            if pg:
                cursor.execute(
                    "INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (role_id, perm_id),
                )
            else:
                cursor.execute(
                    "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                    (role_id, perm_id),
                )
            logger.info(f"Assigned social:chat to {role_name}")

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
