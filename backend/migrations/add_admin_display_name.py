"""
Add admin_display_name column to users table.
"""
import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

MIGRATION_NAME = "add_admin_display_name"


async def run_migration(db):
    """Add admin_display_name column to users table."""
    try:
        await db.execute(text(
            "ALTER TABLE users ADD COLUMN admin_display_name VARCHAR(50)"
        ))
        logger.info("Added admin_display_name column to users")
    except Exception as e:
        if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
            raise
        logger.info("admin_display_name column already exists")
