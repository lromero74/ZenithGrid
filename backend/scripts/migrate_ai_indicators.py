#!/usr/bin/env python3
"""
Migration Script: AI_BUY/AI_SELL → ai_opinion/ai_confidence

Migrates existing bots from old AI indicator format to new unified AI spot opinion format.

Old format:
  - indicator: "AI_BUY" == 1
  - indicator: "AI_SELL" == 1

New format:
  - indicator: "ai_opinion" == "buy" AND "ai_confidence" >= 60
  - indicator: "ai_opinion" == "sell" AND "ai_confidence" >= 60

Usage:
  # Dry run (shows what would change):
  python scripts/migrate_ai_indicators.py

  # Apply changes:
  python scripts/migrate_ai_indicators.py --apply
"""

import sys
import os
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Any, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def get_db_path():
    """Get path to trading database."""
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "trading.db"
    )


def backup_database():
    """Create backup of database before migration."""
    import shutil
    db_path = get_db_path()
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    print(f"✅ Database backed up to: {backup_path}")
    return backup_path


def find_ai_indicator_in_conditions(conditions: Any) -> bool:
    """Recursively search for AI_BUY or AI_SELL in conditions."""
    if not conditions:
        return False

    # Handle list of conditions
    if isinstance(conditions, list):
        for condition in conditions:
            if find_ai_indicator_in_conditions(condition):
                return True
        return False

    # Handle dict (single condition or grouped)
    if isinstance(conditions, dict):
        # Check if this is a condition with an indicator
        indicator = (conditions.get("type") or conditions.get("indicator") or "").lower()
        if indicator in ["ai_buy", "ai_sell"]:
            return True

        # Check nested structures
        if "groups" in conditions:
            return find_ai_indicator_in_conditions(conditions["groups"])
        if "AND" in conditions:
            return find_ai_indicator_in_conditions(conditions["AND"])
        if "OR" in conditions:
            return find_ai_indicator_in_conditions(conditions["OR"])

    return False


def migrate_condition(condition: Dict[str, Any], is_entry: bool = True) -> Dict[str, Any]:
    """
    Migrate a single condition from AI_BUY/AI_SELL to ai_opinion.

    Args:
        condition: The condition dict to migrate
        is_entry: True if this is an entry condition (buy), False for exit (sell)

    Returns:
        Migrated condition dict
    """
    indicator = (condition.get("type") or condition.get("indicator") or "").lower()

    # Check if this needs migration
    if indicator == "ai_buy":
        # Convert AI_BUY == 1 to ai_opinion == "buy" AND ai_confidence >= 60
        return {
            "indicator": "ai_opinion",
            "operator": "==",
            "value": "buy",
            "AND": {
                "indicator": "ai_confidence",
                "operator": ">=",
                "value": 60  # Default minimum confidence
            }
        }
    elif indicator == "ai_sell":
        # Convert AI_SELL == 1 to ai_opinion == "sell" AND ai_confidence >= 60
        return {
            "indicator": "ai_opinion",
            "operator": "==",
            "value": "sell",
            "AND": {
                "indicator": "ai_confidence",
                "operator": ">=",
                "value": 60
            }
        }

    # Not an AI indicator - check for nested structures
    migrated = condition.copy()

    if "AND" in migrated:
        migrated["AND"] = migrate_condition(migrated["AND"], is_entry)
    if "OR" in migrated:
        migrated["OR"] = migrate_condition(migrated["OR"], is_entry)

    return migrated


def migrate_conditions_list(conditions: Any, is_entry: bool = True) -> Any:
    """Migrate a list or dict of conditions."""
    if not conditions:
        return conditions

    # Handle list of conditions
    if isinstance(conditions, list):
        return [migrate_conditions_list(c, is_entry) for c in conditions]

    # Handle dict
    if isinstance(conditions, dict):
        # Check if this has groups (new grouped format)
        if "groups" in conditions:
            migrated = conditions.copy()
            migrated["groups"] = [
                migrate_conditions_list(group, is_entry)
                for group in conditions["groups"]
            ]
            return migrated

        # Single condition - migrate it
        return migrate_condition(conditions, is_entry)

    return conditions


def migrate_bot_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate bot strategy config to use new AI parameters.

    Old params:
      - ai_risk_preset
      - ai_min_confluence_score
      - ai_entry_timeframe
      - ai_trend_timeframe

    New params:
      - ai_model (default: "claude")
      - ai_timeframe (default: "15m")
      - ai_min_confidence (default: 60)
      - enable_buy_prefilter (default: true)
    """
    migrated = config.copy()

    # Remove old AI params
    old_params = ["ai_risk_preset", "ai_min_confluence_score", "ai_entry_timeframe", "ai_trend_timeframe"]
    for param in old_params:
        migrated.pop(param, None)

    # Add new AI params if not present
    if "ai_model" not in migrated:
        migrated["ai_model"] = "claude"
    if "ai_timeframe" not in migrated:
        migrated["ai_timeframe"] = "15m"
    if "ai_min_confidence" not in migrated:
        # Try to map from old confluence score if available
        old_score = config.get("ai_min_confluence_score", 60)
        migrated["ai_min_confidence"] = max(0, min(100, int(old_score * 1.5)))  # Rough mapping
    if "enable_buy_prefilter" not in migrated:
        migrated["enable_buy_prefilter"] = True

    return migrated


def analyze_bots() -> List[Tuple[int, str, Dict[str, Any]]]:
    """
    Analyze all bots and find those using AI indicators.

    Returns:
        List of (bot_id, bot_name, migration_info) tuples
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, strategy_config FROM bots")
    bots = cursor.fetchall()

    bots_to_migrate = []

    for bot in bots:
        bot_id = bot["id"]
        bot_name = bot["name"]
        config = json.loads(bot["strategy_config"]) if bot["strategy_config"] else {}

        # Check if any conditions use AI indicators
        base_order_conditions = config.get("base_order_conditions")
        safety_order_conditions = config.get("safety_order_conditions")
        take_profit_conditions = config.get("take_profit_conditions")

        uses_ai = (
            find_ai_indicator_in_conditions(base_order_conditions) or
            find_ai_indicator_in_conditions(safety_order_conditions) or
            find_ai_indicator_in_conditions(take_profit_conditions)
        )

        if uses_ai:
            migration_info = {
                "base_order": base_order_conditions,
                "safety_order": safety_order_conditions,
                "take_profit": take_profit_conditions,
                "config": config
            }
            bots_to_migrate.append((bot_id, bot_name, migration_info))

    conn.close()
    return bots_to_migrate


def migrate_bot(bot_id: int, bot_name: str, current_config: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """Migrate a single bot and return the new config."""
    print(f"\n{'='*60}")
    print(f"Bot #{bot_id}: {bot_name}")
    print(f"{'='*60}")

    new_config = current_config.copy()

    # Migrate conditions
    if current_config.get("base_order_conditions"):
        old = current_config["base_order_conditions"]
        new = migrate_conditions_list(old, is_entry=True)
        new_config["base_order_conditions"] = new
        print(f"\n📝 Base Order Conditions:")
        print(f"  Old: {json.dumps(old, indent=2)}")
        print(f"  New: {json.dumps(new, indent=2)}")

    if current_config.get("safety_order_conditions"):
        old = current_config["safety_order_conditions"]
        new = migrate_conditions_list(old, is_entry=True)
        new_config["safety_order_conditions"] = new
        print(f"\n📝 Safety Order Conditions:")
        print(f"  Old: {json.dumps(old, indent=2)}")
        print(f"  New: {json.dumps(new, indent=2)}")

    if current_config.get("take_profit_conditions"):
        old = current_config["take_profit_conditions"]
        new = migrate_conditions_list(old, is_entry=False)
        new_config["take_profit_conditions"] = new
        print(f"\n📝 Take Profit Conditions:")
        print(f"  Old: {json.dumps(old, indent=2)}")
        print(f"  New: {json.dumps(new, indent=2)}")

    # Migrate config params
    new_config = migrate_bot_config(new_config)
    print(f"\n⚙️  AI Configuration:")
    print(f"  ai_model: {new_config.get('ai_model')}")
    print(f"  ai_timeframe: {new_config.get('ai_timeframe')}")
    print(f"  ai_min_confidence: {new_config.get('ai_min_confidence')}")
    print(f"  enable_buy_prefilter: {new_config.get('enable_buy_prefilter')}")

    return new_config


def apply_migration(bot_id: int, new_config: Dict[str, Any]):
    """Apply migration to database."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE bots SET strategy_config = ?, updated_at = ? WHERE id = ?",
        (json.dumps(new_config), datetime.utcnow().isoformat(), bot_id)
    )

    conn.commit()
    conn.close()


def main():
    """Main migration script."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate AI indicators to new format")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompts")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("AI INDICATOR MIGRATION SCRIPT")
    print("AI_BUY/AI_SELL → ai_opinion/ai_confidence")
    print("="*60)

    # Analyze bots
    print("\n🔍 Analyzing bots...")
    bots_to_migrate = analyze_bots()

    if not bots_to_migrate:
        print("✅ No bots found using AI_BUY or AI_SELL indicators")
        print("   All bots are already up to date!")
        return

    print(f"\n📊 Found {len(bots_to_migrate)} bot(s) using old AI indicators:")
    for bot_id, bot_name, _ in bots_to_migrate:
        print(f"  - Bot #{bot_id}: {bot_name}")

    # Dry run or apply?
    if not args.apply:
        print("\n⚠️  DRY RUN MODE - No changes will be made")
        print("   Run with --apply to actually migrate bots")

    # Process each bot
    migrations = []
    for bot_id, bot_name, info in bots_to_migrate:
        new_config = migrate_bot(bot_id, bot_name, info["config"], dry_run=not args.apply)
        migrations.append((bot_id, bot_name, new_config))

    # Apply if requested
    if args.apply:
        print("\n" + "="*60)
        if not args.yes:
            confirm = input("\n⚠️  Apply these changes? (yes/no): ")
            if confirm.lower() not in ["yes", "y"]:
                print("❌ Migration cancelled")
                return

        # Backup database
        backup_path = backup_database()

        # Apply migrations
        print(f"\n🔄 Migrating {len(migrations)} bot(s)...")
        for bot_id, bot_name, new_config in migrations:
            apply_migration(bot_id, new_config)
            print(f"  ✅ Migrated Bot #{bot_id}: {bot_name}")

        print(f"\n✅ Migration complete!")
        print(f"   Backup saved to: {backup_path}")
        print(f"   {len(migrations)} bot(s) migrated successfully")
    else:
        print("\n💡 To apply these changes, run:")
        print("   python scripts/migrate_ai_indicators.py --apply")


if __name__ == "__main__":
    main()
