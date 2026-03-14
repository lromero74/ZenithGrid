"""
Extend game_high_scores with score_type and difficulty columns.
Updates unique constraint to allow multiple score types per game.
"""
import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

MIGRATION_NAME = "extend_game_high_scores"


async def run_migration(db):
    """Add score_type and difficulty columns to game_high_scores."""

    # Add score_type column
    try:
        await db.execute(text(
            "ALTER TABLE game_high_scores ADD COLUMN score_type VARCHAR(20) NOT NULL DEFAULT 'high_score'"
        ))
        logger.info("Added score_type column to game_high_scores")
    except Exception as e:
        if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
            raise
        logger.info("score_type column already exists")

    # Add difficulty column
    try:
        await db.execute(text(
            "ALTER TABLE game_high_scores ADD COLUMN difficulty VARCHAR(20)"
        ))
        logger.info("Added difficulty column to game_high_scores")
    except Exception as e:
        if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
            raise
        logger.info("difficulty column already exists")

    # Update unique constraint to include score_type
    try:
        await db.execute(text(
            "ALTER TABLE game_high_scores DROP CONSTRAINT IF EXISTS uq_user_game_score"
        ))
        await db.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_game_score_type "
            "ON game_high_scores(user_id, game_id, score_type)"
        ))
        logger.info("Updated unique constraint to include score_type")
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise
        logger.info("Unique constraint already updated")
