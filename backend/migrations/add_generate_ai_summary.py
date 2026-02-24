"""
Migration: Add generate_ai_summary column to report_schedules

Allows users to toggle AI-powered insights on/off per schedule.
Defaults to enabled (1).
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "ALTER TABLE report_schedules ADD COLUMN "
            "generate_ai_summary INTEGER DEFAULT 1"
        )
        logger.info("Added generate_ai_summary column to report_schedules")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("generate_ai_summary column already exists, skipping")
        else:
            raise

    conn.commit()
    conn.close()
