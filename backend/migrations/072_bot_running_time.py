"""
Migration 072: Add running-time tracking columns to trading.bots

Adds:
  total_running_seconds FLOAT DEFAULT 0  -- accumulated active time across all start/stop cycles
  last_started_at       TIMESTAMP NULL   -- when the current (or most recent) run session began

These two fields allow computing aggregate_running_days = (total_running_seconds + current_session) / 86400.
"""

import logging
from migrations.db_utils import safe_add_column

logger = logging.getLogger(__name__)


def run(conn):
    safe_add_column(conn, "trading.bots", "total_running_seconds FLOAT DEFAULT 0.0")
    safe_add_column(conn, "trading.bots", "last_started_at TIMESTAMP NULL")
    logger.info("Migration 072: added total_running_seconds and last_started_at to trading.bots")
