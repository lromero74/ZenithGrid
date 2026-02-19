"""
Database migration: Convert recipients from plain strings to objects

Converts report_schedules.recipients and reports.delivery_recipients
from plain email string arrays (["a@b.com"]) to object arrays
([{"email": "a@b.com", "level": "comfortable"}]).

Idempotent — skips rows that are already in object format.
"""

import json
import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")


def _convert_column(cursor, table, column):
    """Convert a JSON column from string arrays to object arrays."""
    cursor.execute(
        f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL"
    )
    rows = cursor.fetchall()
    updated = 0

    for row_id, raw in rows:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(data, list) or len(data) == 0:
            continue

        # Already converted — first item has an 'email' key
        if isinstance(data[0], dict) and "email" in data[0]:
            continue

        # Convert plain strings to objects
        converted = []
        for item in data:
            if isinstance(item, str):
                converted.append({
                    "email": item,
                    "level": "comfortable",
                })
            elif isinstance(item, dict) and "email" in item:
                converted.append(item)
            else:
                # Unknown shape — skip
                continue

        cursor.execute(
            f"UPDATE {table} SET {column} = ? WHERE id = ?",
            (json.dumps(converted), row_id),
        )
        updated += 1

    return updated


def run_migration():
    db_path = os.path.abspath(DB_PATH)
    if not os.path.exists(db_path):
        logger.info("Database not found at %s, skipping migration", db_path)
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        n1 = _convert_column(cursor, "report_schedules", "recipients")
        logger.info(
            "Converted %d report_schedules.recipients rows to object format",
            n1,
        )

        n2 = _convert_column(cursor, "reports", "delivery_recipients")
        logger.info(
            "Converted %d reports.delivery_recipients rows to object format",
            n2,
        )

        conn.commit()
        logger.info(
            "Migration complete: convert_recipients_to_objects (%d rows total)",
            n1 + n2,
        )
    except Exception as e:
        conn.rollback()
        logger.error("Migration failed: %s", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
