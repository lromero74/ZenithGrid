"""
Database migration: Add flexible report scheduling columns

Adds 6 new columns to report_schedules:
- schedule_type: daily/weekly/monthly/quarterly/yearly
- schedule_days: JSON array of run days (meaning varies by type)
- quarter_start_month: which month starts quarterly cycle (1-12)
- period_window: full_prior/wtd/mtd/qtd/ytd/trailing
- lookback_value: N for trailing lookback
- lookback_unit: days/weeks/months/years for trailing lookback

Also migrates existing schedules from old periodicity to new fields.
"""

import json
import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")

NEW_COLUMNS = [
    ("schedule_type", "TEXT"),
    ("schedule_days", "TEXT"),
    ("quarter_start_month", "INTEGER"),
    ("period_window", "TEXT DEFAULT 'full_prior'"),
    ("lookback_value", "INTEGER"),
    ("lookback_unit", "TEXT"),
]

# Map old periodicity values to new flexible fields
MIGRATION_MAP = {
    "daily": {
        "schedule_type": "daily",
        "schedule_days": None,
        "quarter_start_month": None,
        "period_window": "full_prior",
        "lookback_value": None,
        "lookback_unit": None,
    },
    "weekly": {
        "schedule_type": "weekly",
        "schedule_days": json.dumps([0]),  # Monday
        "quarter_start_month": None,
        "period_window": "full_prior",
        "lookback_value": None,
        "lookback_unit": None,
    },
    "biweekly": {
        "schedule_type": "weekly",
        "schedule_days": json.dumps([0]),  # Monday
        "quarter_start_month": None,
        "period_window": "trailing",
        "lookback_value": 14,
        "lookback_unit": "days",
    },
    "monthly": {
        "schedule_type": "monthly",
        "schedule_days": json.dumps([1]),
        "quarter_start_month": None,
        "period_window": "full_prior",
        "lookback_value": None,
        "lookback_unit": None,
    },
    "quarterly": {
        "schedule_type": "quarterly",
        "schedule_days": json.dumps([1]),
        "quarter_start_month": 1,
        "period_window": "full_prior",
        "lookback_value": None,
        "lookback_unit": None,
    },
    "yearly": {
        "schedule_type": "yearly",
        "schedule_days": json.dumps([1, 1]),  # Jan 1
        "quarter_start_month": None,
        "period_window": "full_prior",
        "lookback_value": None,
        "lookback_unit": None,
    },
}


def migrate():
    """Run migration to add flexible scheduling columns."""
    logger.info("Starting flexible report scheduling migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Add new columns (idempotent)
        for col_name, col_type in NEW_COLUMNS:
            try:
                cursor.execute(
                    f"ALTER TABLE report_schedules ADD COLUMN "
                    f"{col_name} {col_type}"
                )
                logger.info(f"Added column: {col_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(
                        f"Column {col_name} already exists, skipping"
                    )
                else:
                    raise

        # Migrate existing data (only rows where schedule_type is NULL)
        cursor.execute(
            "SELECT id, periodicity FROM report_schedules "
            "WHERE schedule_type IS NULL"
        )
        rows = cursor.fetchall()

        for row_id, periodicity in rows:
            mapping = MIGRATION_MAP.get(periodicity)
            if not mapping:
                logger.warning(
                    f"Unknown periodicity '{periodicity}' for schedule "
                    f"{row_id}, defaulting to weekly"
                )
                mapping = MIGRATION_MAP["weekly"]

            cursor.execute(
                "UPDATE report_schedules SET "
                "schedule_type = ?, schedule_days = ?, "
                "quarter_start_month = ?, period_window = ?, "
                "lookback_value = ?, lookback_unit = ? "
                "WHERE id = ?",
                (
                    mapping["schedule_type"],
                    mapping["schedule_days"],
                    mapping["quarter_start_month"],
                    mapping["period_window"],
                    mapping["lookback_value"],
                    mapping["lookback_unit"],
                    row_id,
                ),
            )
            logger.info(
                f"Migrated schedule {row_id}: {periodicity} -> "
                f"{mapping['schedule_type']}"
            )

        conn.commit()
        logger.info(
            "Flexible report scheduling migration completed successfully!"
        )

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration — informational only."""
    logger.info(
        "Rollback: The new columns (schedule_type, schedule_days, "
        "quarter_start_month, period_window, lookback_value, lookback_unit) "
        "can be dropped from report_schedules if needed."
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
