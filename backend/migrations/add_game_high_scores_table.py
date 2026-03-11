"""
Migration: Add game_high_scores table for per-user best scores.

Stores the highest score each user has achieved in each game,
replacing localStorage-based score storage.

Idempotent: checks for table existence before creating.
"""

import logging
import os
import sys

sys_path_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if sys_path_dir not in sys.path:
    sys.path.insert(0, sys_path_dir)

from migrations.db_utils import get_migration_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MIGRATION_NAME = "add_game_high_scores_table"


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

        if table_exists("game_high_scores"):
            logger.info("game_high_scores table already exists — skipping")
            return

        cursor.execute("""
            CREATE TABLE game_high_scores (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                game_id VARCHAR NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_user_game_score UNIQUE (user_id, game_id)
            )
        """ if is_pg else """
            CREATE TABLE game_high_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                game_id VARCHAR NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_user_game_score UNIQUE (user_id, game_id)
            )
        """)

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_game_high_scores_user_id ON game_high_scores(user_id)"
        )

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
