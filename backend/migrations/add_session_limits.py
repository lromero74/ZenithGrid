"""
Add session limits: active_sessions table, group session_policy, user session_policy_override.
Also seeds the Observers group with demo session defaults.
"""
import json
import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

MIGRATION_NAME = "add_session_limits"


async def run_migration(db):
    """Add session tracking and limits support."""

    # Create active_sessions table
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS active_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                session_id VARCHAR(36) NOT NULL UNIQUE,
                ip_address VARCHAR(45),
                user_agent VARCHAR(512),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                ended_at DATETIME,
                is_active BOOLEAN DEFAULT 1
            )
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_active_sessions_user_id ON active_sessions(user_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_active_sessions_session_id ON active_sessions(session_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_active_sessions_is_active ON active_sessions(is_active)"
        ))
        logger.info("Created active_sessions table")
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise
        logger.info("active_sessions table already exists")

    # Add session_policy to groups
    try:
        await db.execute(text("ALTER TABLE groups ADD COLUMN session_policy JSON"))
        logger.info("Added session_policy column to groups")
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise
        logger.info("session_policy column already exists on groups")

    # Add session_policy_override to users
    try:
        await db.execute(text("ALTER TABLE users ADD COLUMN session_policy_override JSON"))
        logger.info("Added session_policy_override column to users")
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise
        logger.info("session_policy_override column already exists on users")

    # Seed Observers group with demo defaults
    try:
        result = await db.execute(
            text("SELECT id, session_policy FROM groups WHERE name = 'Observers'")
        )
        row = result.fetchone()
        if row and not row[1]:
            demo_policy = json.dumps({
                "session_timeout_minutes": 30,
                "auto_logout": True,
                "max_simultaneous_sessions": 15,
                "max_sessions_per_ip": 2,
                "relogin_cooldown_minutes": 5,
            })
            await db.execute(
                text("UPDATE groups SET session_policy = :policy WHERE name = 'Observers'"),
                {"policy": demo_policy},
            )
            logger.info("Seeded Observers group with demo session policy")
    except Exception as e:
        logger.warning(f"Could not seed Observers session policy: {e}")

    await db.commit()
