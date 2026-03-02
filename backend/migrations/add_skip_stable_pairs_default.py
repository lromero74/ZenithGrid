"""
Add skip_stable_pairs=true default to all existing bots' strategy_config.
"""
import json
import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

MIGRATION_NAME = "add_skip_stable_pairs_default"


async def run_migration(db):
    """Set skip_stable_pairs: true in strategy_config for all existing bots."""

    try:
        result = await db.execute(text("SELECT id, strategy_config FROM bots"))
        rows = result.fetchall()
        updated = 0

        for row in rows:
            bot_id = row[0]
            config_raw = row[1]

            try:
                config = json.loads(config_raw) if config_raw else {}
            except (json.JSONDecodeError, TypeError):
                config = {}

            if "skip_stable_pairs" not in config:
                config["skip_stable_pairs"] = True
                await db.execute(
                    text("UPDATE bots SET strategy_config = :config WHERE id = :id"),
                    {"config": json.dumps(config), "id": bot_id},
                )
                updated += 1

        if updated:
            logger.info(f"Set skip_stable_pairs=true for {updated} bots")
        else:
            logger.info("All bots already have skip_stable_pairs configured")

    except Exception as e:
        if "no such column" in str(e).lower() or "no such table" in str(e).lower():
            logger.info(f"Skipping migration (table/column not ready): {e}")
        else:
            raise
