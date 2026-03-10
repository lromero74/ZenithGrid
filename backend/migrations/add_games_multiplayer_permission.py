"""
Add games:multiplayer permission and assign to trader/paper_trader roles.

Demo users (Observers/viewer role) do NOT get this permission,
preventing them from playing multiplayer against real users.

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

MIGRATION_NAME = "add_games_multiplayer_permission"


def run(conn):
    cursor = conn.cursor()
    try:
        pg = is_postgres()

        # Add permission
        if pg:
            cursor.execute(
                "INSERT INTO permissions (name, description) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                ("games:multiplayer", "Play multiplayer games against other users"),
            )
        else:
            cursor.execute(
                "INSERT OR IGNORE INTO permissions (name, description) VALUES (?, ?)",
                ("games:multiplayer", "Play multiplayer games against other users"),
            )

        # Get permission id
        if pg:
            cursor.execute("SELECT id FROM permissions WHERE name = %s", ("games:multiplayer",))
        else:
            cursor.execute("SELECT id FROM permissions WHERE name = ?", ("games:multiplayer",))
        perm_row = cursor.fetchone()
        if not perm_row:
            logger.error("Failed to find games:multiplayer permission")
            return
        perm_id = perm_row[0]

        # Assign to trader and paper_trader roles
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
            logger.info(f"Assigned games:multiplayer to {role_name}")

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
