"""
Database migration: Add reporting & goals tables

Creates four new tables:
- report_goals: User financial targets
- report_schedules: Report delivery configuration
- report_schedule_goals: Junction table (schedules ↔ goals)
- reports: Generated report instances with HTML, PDF, AI summary
"""

import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database path relative to this migration file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")

REPORT_GOALS_TABLE = """
CREATE TABLE IF NOT EXISTS report_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_currency TEXT NOT NULL DEFAULT 'USD',
    target_value REAL NOT NULL,
    target_balance_value REAL,
    target_profit_value REAL,
    time_horizon_months INTEGER NOT NULL,
    start_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    target_date DATETIME NOT NULL,
    is_active INTEGER DEFAULT 1,
    achieved_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

REPORT_SCHEDULES_TABLE = """
CREATE TABLE IF NOT EXISTS report_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id INTEGER REFERENCES accounts(id),
    name TEXT NOT NULL,
    periodicity TEXT NOT NULL,
    is_enabled INTEGER DEFAULT 1,
    recipients TEXT,
    ai_provider TEXT,
    last_run_at DATETIME,
    next_run_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

REPORT_SCHEDULE_GOALS_TABLE = """
CREATE TABLE IF NOT EXISTS report_schedule_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL REFERENCES report_schedules(id) ON DELETE CASCADE,
    goal_id INTEGER NOT NULL REFERENCES report_goals(id) ON DELETE CASCADE,
    UNIQUE(schedule_id, goal_id)
)
"""

REPORTS_TABLE = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    schedule_id INTEGER REFERENCES report_schedules(id) ON DELETE SET NULL,
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,
    periodicity TEXT NOT NULL,
    report_data TEXT,
    html_content TEXT,
    pdf_content BLOB,
    ai_summary TEXT,
    ai_provider_used TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending',
    delivered_at DATETIME,
    delivery_recipients TEXT,
    delivery_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_report_goals_user_id ON report_goals(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_report_schedules_user_id ON report_schedules(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_report_schedule_goals_schedule_id ON report_schedule_goals(schedule_id)",
    "CREATE INDEX IF NOT EXISTS ix_report_schedule_goals_goal_id ON report_schedule_goals(goal_id)",
    "CREATE INDEX IF NOT EXISTS ix_reports_user_id ON reports(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_reports_schedule_id ON reports(schedule_id)",
    "CREATE INDEX IF NOT EXISTS ix_reports_period_end ON reports(period_end)",
]


def migrate():
    """Run migration to add reporting & goals tables."""
    logger.info("Starting reports and goals migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Create tables (idempotent via IF NOT EXISTS)
        logger.info("Creating report_goals table...")
        cursor.execute(REPORT_GOALS_TABLE)

        logger.info("Creating report_schedules table...")
        cursor.execute(REPORT_SCHEDULES_TABLE)

        logger.info("Creating report_schedule_goals table...")
        cursor.execute(REPORT_SCHEDULE_GOALS_TABLE)

        logger.info("Creating reports table...")
        cursor.execute(REPORTS_TABLE)

        # Create indexes
        logger.info("Creating indexes...")
        for idx_sql in INDEXES:
            cursor.execute(idx_sql)

        conn.commit()
        logger.info("Reports and goals migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration — informational only."""
    logger.info(
        "Rollback: To undo, drop tables: reports, report_schedule_goals, "
        "report_schedules, report_goals (in that order due to FK constraints)"
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
