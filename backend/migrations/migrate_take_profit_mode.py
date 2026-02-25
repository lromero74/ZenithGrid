"""
Migration: Convert legacy take profit fields to new take_profit_mode system.

Converts:
- trailing_take_profit: true → take_profit_mode: "trailing"
- min_profit_for_conditions set → take_profit_mode: "minimum"
- Neither → take_profit_mode: "fixed"
- take_profit_conditions configured → take_profit_mode: "minimum"

Also:
- Changes take_profit_order_type default from "limit" to "market"
- Adds base_execution_type: "market" and dca_execution_type: "market"

Updates both bot strategy_config AND open position strategy_config_snapshot.

Usage:
    cd backend && ./venv/bin/python3 migrations/migrate_take_profit_mode.py
"""

import json
import logging
import os
import sqlite3
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


def has_conditions(config):
    """Check if take_profit_conditions has actual conditions configured."""
    tp_conds = config.get("take_profit_conditions")
    if tp_conds is None:
        return False
    if isinstance(tp_conds, list):
        return len(tp_conds) > 0
    if isinstance(tp_conds, dict):
        groups = tp_conds.get("groups", [])
        return any(len(g.get("conditions", [])) > 0 for g in groups)
    return False


def migrate_config(config):
    """Migrate a strategy_config dict to the new take_profit_mode system.

    Returns (new_config, changed) tuple.
    """
    if not isinstance(config, dict):
        return config, False

    changed = False

    # Already migrated?
    if "take_profit_mode" in config:
        return config, False

    # Determine mode from legacy fields
    if config.get("trailing_take_profit", False):
        config["take_profit_mode"] = "trailing"
        changed = True
    elif config.get("min_profit_for_conditions") is not None:
        config["take_profit_mode"] = "minimum"
        changed = True
    elif has_conditions(config):
        config["take_profit_mode"] = "minimum"
        changed = True
    else:
        config["take_profit_mode"] = "fixed"
        changed = True

    # Remove legacy fields
    if "trailing_take_profit" in config:
        del config["trailing_take_profit"]
        changed = True
    if "min_profit_for_conditions" in config:
        # If min_profit was explicitly different from TP%, keep the lower value as TP%
        min_prof = config["min_profit_for_conditions"]
        tp_pct = config.get("take_profit_percentage", 3.0)
        if config["take_profit_mode"] == "minimum" and min_prof != tp_pct:
            config["take_profit_percentage"] = min_prof
        del config["min_profit_for_conditions"]
        changed = True

    # Change take_profit_order_type default from limit to market
    if config.get("take_profit_order_type") == "limit":
        config["take_profit_order_type"] = "market"
        changed = True

    # Add new execution type fields if missing
    if "base_execution_type" not in config:
        config["base_execution_type"] = "market"
        changed = True
    if "dca_execution_type" not in config:
        config["dca_execution_type"] = "market"
        changed = True

    return config, changed


def main():
    if not os.path.exists(DB_PATH):
        logger.info("Database not found, skipping migration")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Migrate bots
    cursor.execute("SELECT id, strategy_config FROM bots WHERE strategy_config IS NOT NULL")
    bot_rows = cursor.fetchall()
    bot_count = 0
    for bot_id, config_json in bot_rows:
        try:
            config = json.loads(config_json)
            new_config, changed = migrate_config(config)
            if changed:
                cursor.execute(
                    "UPDATE bots SET strategy_config = ? WHERE id = ?",
                    (json.dumps(new_config), bot_id),
                )
                bot_count += 1
        except (json.JSONDecodeError, TypeError):
            continue

    # Migrate open position snapshots
    cursor.execute(
        "SELECT id, strategy_config_snapshot FROM positions "
        "WHERE strategy_config_snapshot IS NOT NULL AND status = 'open'"
    )
    pos_rows = cursor.fetchall()
    pos_count = 0
    for pos_id, config_json in pos_rows:
        try:
            config = json.loads(config_json)
            new_config, changed = migrate_config(config)
            if changed:
                cursor.execute(
                    "UPDATE positions SET strategy_config_snapshot = ? WHERE id = ?",
                    (json.dumps(new_config), pos_id),
                )
                pos_count += 1
        except (json.JSONDecodeError, TypeError):
            continue

    conn.commit()
    conn.close()

    logger.info(f"Migration complete: {bot_count} bot(s), {pos_count} position(s) updated")


if __name__ == "__main__":
    main()
