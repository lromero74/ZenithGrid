"""
Database migration: Add goal_progress_snapshots table

Stores daily progress data points for goal trend line visualization.
One row per goal per day, captured during the daily account snapshot cycle.
"""

import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")

GOAL_PROGRESS_SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS goal_progress_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES report_goals(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot_date DATETIME NOT NULL,
    current_value REAL NOT NULL DEFAULT 0.0,
    target_value REAL NOT NULL DEFAULT 0.0,
    progress_pct REAL NOT NULL DEFAULT 0.0,
    on_track INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_goal_progress_snapshots_goal_id ON goal_progress_snapshots(goal_id)",
    "CREATE INDEX IF NOT EXISTS ix_goal_progress_snapshots_user_id ON goal_progress_snapshots(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_goal_progress_snapshots_date ON goal_progress_snapshots(snapshot_date)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_goal_snapshot_date ON goal_progress_snapshots(goal_id, snapshot_date)",
]


def migrate():
    """Run migration to add goal_progress_snapshots table."""
    logger.info("Starting goal progress snapshots migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        logger.info("Creating goal_progress_snapshots table...")
        cursor.execute(GOAL_PROGRESS_SNAPSHOTS_TABLE)

        logger.info("Creating indexes...")
        for idx_sql in INDEXES:
            cursor.execute(idx_sql)

        conn.commit()
        logger.info("Goal progress snapshots migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration -- informational only."""
    logger.info("Rollback: DROP TABLE goal_progress_snapshots")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
