"""
Create social/multiplayer tables and add unique constraint to display_name.

Tables created:
- friendships (bidirectional friend relationships)
- friend_requests (pending requests)
- blocked_users (user blocks)
- game_results (completed game records)
- game_result_players (per-player game outcomes)
- game_history_visibility (privacy controls)
- tournaments (multi-game competitions)
- tournament_players (tournament enrollment)
- tournament_delete_votes (committee vote deletion)

Also:
- Auto-generate display names for users with NULL display_name
- Add unique index on display_name (case-insensitive for PostgreSQL)

Idempotent: checks for table/column existence before creating.
"""

import logging
import random
import string
import sys

import os
sys_path_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if sys_path_dir not in sys.path:
    sys.path.insert(0, sys_path_dir)

from migrations.db_utils import get_migration_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MIGRATION_NAME = "create_social_tables"


def _random_suffix(length=4):
    return "".join(random.choices(string.digits, k=length))


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

        def index_exists(name):
            if is_pg:
                cursor.execute(
                    "SELECT 1 FROM pg_indexes WHERE indexname = %s",
                    (name,)
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                    (name,)
                )
            return cursor.fetchone() is not None

        # --- Create tables ---

        if not table_exists("friendships"):
            cursor.execute("""
                CREATE TABLE friendships (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    friend_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_friendship UNIQUE (user_id, friend_id)
                )
            """ if is_pg else """
                CREATE TABLE friendships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    friend_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_friendship UNIQUE (user_id, friend_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_friendships_user_id ON friendships(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_friendships_friend_id ON friendships(friend_id)")
            logger.info("Created friendships table")

        if not table_exists("friend_requests"):
            cursor.execute("""
                CREATE TABLE friend_requests (
                    id SERIAL PRIMARY KEY,
                    from_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    to_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_friend_request UNIQUE (from_user_id, to_user_id)
                )
            """ if is_pg else """
                CREATE TABLE friend_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    to_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_friend_request UNIQUE (from_user_id, to_user_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_friend_requests_from ON friend_requests(from_user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_friend_requests_to ON friend_requests(to_user_id)")
            logger.info("Created friend_requests table")

        if not table_exists("blocked_users"):
            cursor.execute("""
                CREATE TABLE blocked_users (
                    id SERIAL PRIMARY KEY,
                    blocker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_blocked_user UNIQUE (blocker_id, blocked_id)
                )
            """ if is_pg else """
                CREATE TABLE blocked_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    blocker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_blocked_user UNIQUE (blocker_id, blocked_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_blocked_users_blocker ON blocked_users(blocker_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_blocked_users_blocked ON blocked_users(blocked_id)")
            logger.info("Created blocked_users table")

        # Tournaments must be created BEFORE game_results (FK dependency)
        if not table_exists("tournaments"):
            cursor.execute("""
                CREATE TABLE tournaments (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    creator_id INTEGER NOT NULL REFERENCES users(id),
                    game_ids JSON NOT NULL,
                    config JSON,
                    status VARCHAR DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP
                )
            """ if is_pg else """
                CREATE TABLE tournaments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL,
                    creator_id INTEGER NOT NULL REFERENCES users(id),
                    game_ids JSON NOT NULL,
                    config JSON,
                    status VARCHAR DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_tournaments_creator ON tournaments(creator_id)")
            logger.info("Created tournaments table")

        if not table_exists("tournament_players"):
            cursor.execute("""
                CREATE TABLE tournament_players (
                    id SERIAL PRIMARY KEY,
                    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    total_score INTEGER DEFAULT 0,
                    placement INTEGER,
                    archived BOOLEAN DEFAULT FALSE,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_tournament_player UNIQUE (tournament_id, user_id)
                )
            """ if is_pg else """
                CREATE TABLE tournament_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    total_score INTEGER DEFAULT 0,
                    placement INTEGER,
                    archived BOOLEAN DEFAULT 0,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_tournament_player UNIQUE (tournament_id, user_id)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_tournament_players_tournament ON tournament_players(tournament_id)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_tournament_players_user ON tournament_players(user_id)")
            logger.info("Created tournament_players table")

        if not table_exists("tournament_delete_votes"):
            cursor.execute("""
                CREATE TABLE tournament_delete_votes (
                    id SERIAL PRIMARY KEY,
                    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_tournament_delete_vote UNIQUE (tournament_id, user_id)
                )
            """ if is_pg else """
                CREATE TABLE tournament_delete_votes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_tournament_delete_vote UNIQUE (tournament_id, user_id)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_tournament_delete_votes_tournament "
                "ON tournament_delete_votes(tournament_id)"
            )
            logger.info("Created tournament_delete_votes table")

        if not table_exists("game_results"):
            cursor.execute("""
                CREATE TABLE game_results (
                    id SERIAL PRIMARY KEY,
                    room_id VARCHAR NOT NULL,
                    game_id VARCHAR NOT NULL,
                    mode VARCHAR NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    result_data JSON,
                    tournament_id INTEGER REFERENCES tournaments(id)
                )
            """ if is_pg else """
                CREATE TABLE game_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id VARCHAR NOT NULL,
                    game_id VARCHAR NOT NULL,
                    mode VARCHAR NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    result_data JSON,
                    tournament_id INTEGER REFERENCES tournaments(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_game_results_room ON game_results(room_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_game_results_game ON game_results(game_id)")
            logger.info("Created game_results table")

        if not table_exists("game_result_players"):
            cursor.execute("""
                CREATE TABLE game_result_players (
                    id SERIAL PRIMARY KEY,
                    game_result_id INTEGER NOT NULL REFERENCES game_results(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    placement INTEGER,
                    score INTEGER,
                    is_winner BOOLEAN DEFAULT FALSE,
                    stats JSON
                )
            """ if is_pg else """
                CREATE TABLE game_result_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_result_id INTEGER NOT NULL REFERENCES game_results(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    placement INTEGER,
                    score INTEGER,
                    is_winner BOOLEAN DEFAULT 0,
                    stats JSON
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_game_result_players_result ON game_result_players(game_result_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_game_result_players_user ON game_result_players(user_id)"
            )
            logger.info("Created game_result_players table")

        if not table_exists("game_history_visibility"):
            cursor.execute("""
                CREATE TABLE game_history_visibility (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    default_visibility VARCHAR DEFAULT 'all_friends',
                    game_overrides JSON
                )
            """ if is_pg else """
                CREATE TABLE game_history_visibility (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    default_visibility VARCHAR DEFAULT 'all_friends',
                    game_overrides JSON
                )
            """)
            logger.info("Created game_history_visibility table")

        # --- Display name uniqueness ---

        # Auto-generate display names for users with NULL display_name
        if is_pg:
            cursor.execute("SELECT id, email FROM users WHERE display_name IS NULL OR display_name = ''")
        else:
            cursor.execute("SELECT id, email FROM users WHERE display_name IS NULL OR display_name = ''")

        null_users = cursor.fetchall()
        for user_id, email in null_users:
            prefix = email.split("@")[0][:12] if email else "Player"
            # Clean prefix to alphanumeric + underscore
            clean = "".join(c if c.isalnum() or c == "_" else "" for c in prefix)
            if len(clean) < 3:
                clean = "Player"
            name = f"{clean}_{_random_suffix()}"
            if is_pg:
                cursor.execute("UPDATE users SET display_name = %s WHERE id = %s", (name, user_id))
            else:
                cursor.execute("UPDATE users SET display_name = ? WHERE id = ?", (name, user_id))
            logger.info(f"Auto-generated display_name '{name}' for user {user_id}")

        # Add unique index on display_name (case-insensitive for PG)
        if not index_exists("uq_users_display_name_lower"):
            if is_pg:
                cursor.execute(
                    "CREATE UNIQUE INDEX uq_users_display_name_lower ON users (LOWER(display_name))"
                )
            else:
                # SQLite doesn't have function-based indexes, use COLLATE NOCASE
                cursor.execute(
                    "CREATE UNIQUE INDEX uq_users_display_name_lower ON users (display_name COLLATE NOCASE)"
                )
            logger.info("Added unique index on users.display_name (case-insensitive)")

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
