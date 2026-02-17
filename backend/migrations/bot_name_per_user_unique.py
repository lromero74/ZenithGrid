"""
Migration: Change bot name uniqueness from global to per-user.

Before: Bot names must be unique across ALL users (global UNIQUE constraint on 'name').
After:  Bot names must be unique per-user (composite UNIQUE on 'user_id' + 'name').

This allows different users to create bots with the same name.

Idempotent: Safe to run multiple times.
"""

import logging
import os

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


async def run(db_session):
    """Run migration using async session (called by update.py)."""
    import aiosqlite

    db_path = DB_PATH
    async with aiosqlite.connect(db_path) as db:
        # Step 1: Drop the old global unique index on bots.name (if it exists)
        # SQLite auto-creates an index named 'ix_bots_name' for indexed columns
        # and a separate unique index for unique=True
        try:
            await db.execute("DROP INDEX IF EXISTS ix_bots_name")
            logger.info("Dropped old ix_bots_name index")
        except Exception as e:
            logger.debug(f"Could not drop ix_bots_name: {e}")

        # SQLite may also create a unique index with a sqlite_autoindex name
        # We need to check for any unique index on just (name)
        cursor = await db.execute("PRAGMA index_list('bots')")
        indexes = await cursor.fetchall()
        for idx in indexes:
            idx_name = idx[1]
            is_unique = idx[2]
            if is_unique:
                cursor2 = await db.execute(f"PRAGMA index_info('{idx_name}')")
                cols = await cursor2.fetchall()
                col_names = [c[2] for c in cols]
                # Drop any unique index that's ONLY on 'name' (not the composite one)
                if col_names == ["name"]:
                    try:
                        await db.execute(f"DROP INDEX IF EXISTS \"{idx_name}\"")
                        logger.info(f"Dropped old unique index '{idx_name}' on bots(name)")
                    except Exception as e:
                        logger.debug(f"Could not drop {idx_name}: {e}")

        # Step 2: Create composite unique index (user_id, name) — idempotent
        try:
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_bot_user_name ON bots(user_id, name)"
            )
            logger.info("Created composite unique index uq_bot_user_name on bots(user_id, name)")
        except Exception as e:
            logger.debug(f"Composite unique index may already exist: {e}")

        # Step 3: Re-create a non-unique index on name for query performance
        try:
            await db.execute(
                "CREATE INDEX IF NOT EXISTS ix_bots_name ON bots(name)"
            )
            logger.info("Created non-unique index ix_bots_name on bots(name)")
        except Exception as e:
            logger.debug(f"Name index may already exist: {e}")

        await db.commit()
        logger.info("Migration complete: bot name uniqueness is now per-user")
