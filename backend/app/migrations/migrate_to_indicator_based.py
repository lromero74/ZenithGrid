"""
Migration Script: Convert Legacy Strategies to indicator_based

Migrates all existing bots from pre-baked strategies to the unified
indicator_based strategy format.

Strategy Mappings:
- ai_autonomous → indicator_based with AI_BUY/AI_SELL conditions
- bull_flag → indicator_based with BULL_FLAG condition
- conditional_dca → indicator_based (conditions preserved)
- macd_dca → indicator_based with MACD conditions
- simple_dca → indicator_based (no entry conditions)
- advanced_dca → indicator_based (conditions converted)
- bollinger → indicator_based with BB conditions
- rsi → indicator_based with RSI conditions

Usage:
    python -m app.migrations.migrate_to_indicator_based --dry-run
    python -m app.migrations.migrate_to_indicator_based --apply
"""

import argparse
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import Bot, Position

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Migration converters for each strategy type
def convert_ai_autonomous(config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert ai_autonomous strategy to indicator_based format."""
    new_config = {}

    # Map risk tolerance to AI preset
    risk_tolerance = config.get("risk_tolerance", "moderate")
    if risk_tolerance == "aggressive":
        new_config["ai_risk_preset"] = "aggressive"
        new_config["ai_min_confluence_score"] = 50
    elif risk_tolerance == "conservative":
        new_config["ai_risk_preset"] = "conservative"
        new_config["ai_min_confluence_score"] = 80
    else:
        new_config["ai_risk_preset"] = "moderate"
        new_config["ai_min_confluence_score"] = 65

    # Copy budget and deal management settings
    new_config["max_concurrent_deals"] = config.get("max_concurrent_deals", 3)

    # DCA settings from AI autonomous
    if config.get("enable_dca", True):
        new_config["max_safety_orders"] = config.get("max_safety_orders", 3)
        new_config["safety_order_percentage"] = config.get("safety_order_percentage", 20.0)
        new_config["price_deviation"] = config.get("min_dca_drop_pct", 2.0)
    else:
        new_config["max_safety_orders"] = 0

    # Take profit settings
    new_config["take_profit_percentage"] = config.get("target_profit_percentage", 3.0)
    new_config["trailing_take_profit"] = config.get("use_trailing_profit", False)
    new_config["trailing_deviation"] = config.get("trailing_deviation", 1.0)

    # Stop loss settings
    if config.get("stop_loss_percentage"):
        new_config["stop_loss_enabled"] = True
        new_config["stop_loss_percentage"] = config.get("stop_loss_percentage", -10.0)
    else:
        new_config["stop_loss_enabled"] = False

    # Create AI_BUY condition for entry
    new_config["base_order_conditions"] = [
        {
            "id": "ai_buy_entry",
            "indicator": "ai_buy",
            "operator": "equal",
            "value_type": "static",
            "static_value": 1,
            "timeframe": "FIFTEEN_MINUTE",
        }
    ]
    new_config["base_order_logic"] = "and"

    # Create AI_SELL condition for exit
    new_config["take_profit_conditions"] = [
        {
            "id": "ai_sell_exit",
            "indicator": "ai_sell",
            "operator": "equal",
            "value_type": "static",
            "static_value": 1,
            "timeframe": "FIFTEEN_MINUTE",
        }
    ]
    new_config["take_profit_logic"] = "and"

    # No safety order conditions - uses price deviation
    new_config["safety_order_conditions"] = []
    new_config["safety_order_logic"] = "and"

    return new_config


def convert_bull_flag(config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert bull_flag strategy to indicator_based format."""
    new_config = {}

    # Bull flag specific settings
    new_config["bull_flag_timeframe"] = config.get("timeframe", "FIFTEEN_MINUTE")
    new_config["bull_flag_min_pole_gain"] = config.get("min_pole_gain_pct", 3.0)

    # Budget settings
    new_config["max_concurrent_deals"] = config.get("max_concurrent_positions", 5)

    if config.get("budget_mode") == "fixed_usd":
        new_config["base_order_type"] = "fixed_usd"
        new_config["base_order_fixed"] = config.get("fixed_usd_amount", 100.0)
    else:
        new_config["base_order_type"] = "percentage"
        new_config["base_order_percentage"] = config.get("budget_percentage", 5.0)

    # Bull flag doesn't DCA
    new_config["max_safety_orders"] = 0

    # Take profit from reward/risk ratio
    reward_risk = config.get("reward_risk_ratio", 2.0)
    new_config["take_profit_percentage"] = reward_risk * 2  # Approximate

    # Create BULL_FLAG condition for entry
    new_config["base_order_conditions"] = [
        {
            "id": "bull_flag_entry",
            "indicator": "bull_flag",
            "operator": "equal",
            "value_type": "static",
            "static_value": 1,
            "timeframe": config.get("timeframe", "FIFTEEN_MINUTE"),
        }
    ]
    new_config["base_order_logic"] = "and"

    # No conditions for exit - use TP percentage
    new_config["take_profit_conditions"] = []
    new_config["take_profit_logic"] = "and"
    new_config["safety_order_conditions"] = []
    new_config["safety_order_logic"] = "and"

    return new_config


def convert_conditional_dca(config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert conditional_dca - mostly a direct copy since format is similar."""
    new_config = {}

    # Direct copy of most settings
    new_config["max_concurrent_deals"] = config.get("max_concurrent_deals", 1)

    # Base order settings
    new_config["base_order_type"] = config.get("base_order_type", "percentage")
    new_config["base_order_percentage"] = config.get("base_order_percentage", 10.0)
    new_config["base_order_fixed"] = config.get("base_order_btc", 0.001)

    # Safety order settings
    new_config["max_safety_orders"] = config.get("max_safety_orders", 5)
    new_config["safety_order_type"] = config.get("safety_order_type", "percentage_of_base")
    new_config["safety_order_percentage"] = config.get("safety_order_percentage", 50.0)
    new_config["safety_order_fixed"] = config.get("safety_order_btc", 0.0005)
    new_config["price_deviation"] = config.get("price_deviation", 2.0)
    new_config["safety_order_step_scale"] = config.get("safety_order_step_scale", 1.0)
    new_config["safety_order_volume_scale"] = config.get("safety_order_volume_scale", 1.0)

    # Take profit settings
    new_config["take_profit_percentage"] = config.get("take_profit_percentage", 3.0)
    new_config["take_profit_order_type"] = config.get("take_profit_order_type", "limit")
    new_config["min_profit_for_conditions"] = config.get("min_profit_for_conditions", 0.0)
    new_config["trailing_take_profit"] = config.get("trailing_take_profit", False)
    new_config["trailing_deviation"] = config.get("trailing_deviation", 1.0)

    # Stop loss settings
    new_config["stop_loss_enabled"] = config.get("stop_loss_enabled", False)
    new_config["stop_loss_percentage"] = config.get("stop_loss_percentage", -10.0)
    new_config["trailing_stop_loss"] = config.get("trailing_stop_loss", False)
    new_config["trailing_stop_deviation"] = config.get("trailing_stop_deviation", 5.0)

    # Preserve phase conditions as-is
    new_config["base_order_conditions"] = config.get("base_order_conditions", [])
    new_config["base_order_logic"] = config.get("base_order_logic", "and")
    new_config["safety_order_conditions"] = config.get("safety_order_conditions", [])
    new_config["safety_order_logic"] = config.get("safety_order_logic", "and")
    new_config["take_profit_conditions"] = config.get("take_profit_conditions", [])
    new_config["take_profit_logic"] = config.get("take_profit_logic", "and")

    return new_config


def convert_macd_dca(config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert macd_dca strategy to indicator_based format."""
    new_config = {}

    # Copy DCA settings
    new_config["max_concurrent_deals"] = config.get("max_concurrent_deals", 1)
    new_config["base_order_type"] = "percentage"
    new_config["base_order_percentage"] = config.get("initial_btc_percentage", 10.0)
    new_config["max_safety_orders"] = config.get("max_dca_orders", 5)
    new_config["safety_order_percentage"] = config.get("dca_percentage", 50.0)
    new_config["take_profit_percentage"] = config.get("min_profit_percentage", 3.0)

    # MACD parameters
    fast = config.get("macd_fast_period", 12)
    slow = config.get("macd_slow_period", 26)
    signal = config.get("macd_signal_period", 9)
    timeframe = config.get("candle_interval", "FIVE_MINUTE")

    # Create MACD crossing above signal condition for entry
    new_config["base_order_conditions"] = [
        {
            "id": "macd_cross_above",
            "indicator": "macd",
            "operator": "crossing_above",
            "value_type": "indicator",
            "compare_indicator": "macd_signal",
            "timeframe": timeframe,
            "indicator_params": {
                "fast_period": fast,
                "slow_period": slow,
                "signal_period": signal,
            },
            "compare_indicator_params": {
                "fast_period": fast,
                "slow_period": slow,
                "signal_period": signal,
            },
        }
    ]
    new_config["base_order_logic"] = "and"

    # No special exit conditions - use TP %
    new_config["take_profit_conditions"] = []
    new_config["take_profit_logic"] = "and"
    new_config["safety_order_conditions"] = []
    new_config["safety_order_logic"] = "and"

    return new_config


def convert_simple_dca(config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert simple_dca strategy - immediate entry, DCA on drop."""
    new_config = {}

    new_config["max_concurrent_deals"] = config.get("max_concurrent_deals", 1)
    new_config["base_order_type"] = "percentage"
    new_config["base_order_percentage"] = config.get("initial_btc_percentage", 10.0)
    new_config["max_safety_orders"] = config.get("max_dca_orders", 5)
    new_config["safety_order_percentage"] = config.get("dca_percentage", 50.0)
    new_config["price_deviation"] = config.get("dca_threshold_percentage", 2.0)
    new_config["take_profit_percentage"] = config.get("min_profit_percentage", 3.0)

    # No conditions - enter immediately when no position exists
    new_config["base_order_conditions"] = []
    new_config["base_order_logic"] = "and"
    new_config["take_profit_conditions"] = []
    new_config["take_profit_logic"] = "and"
    new_config["safety_order_conditions"] = []
    new_config["safety_order_logic"] = "and"

    return new_config


def convert_bollinger(config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert bollinger strategy to indicator_based format."""
    new_config = {}

    new_config["max_concurrent_deals"] = config.get("max_concurrent_deals", 1)
    new_config["base_order_type"] = "percentage"
    new_config["base_order_percentage"] = config.get("initial_btc_percentage", 10.0)
    new_config["max_safety_orders"] = config.get("max_dca_orders", 5)
    new_config["safety_order_percentage"] = config.get("dca_percentage", 50.0)
    new_config["take_profit_percentage"] = config.get("min_profit_percentage", 3.0)

    period = config.get("bb_period", 20)
    std_dev = config.get("bb_std_dev", 2)
    timeframe = config.get("candle_interval", "FIVE_MINUTE")

    # Create BB condition: price < lower band
    new_config["base_order_conditions"] = [
        {
            "id": "price_below_bb_lower",
            "indicator": "price",
            "operator": "less_than",
            "value_type": "indicator",
            "compare_indicator": "bollinger_lower",
            "timeframe": timeframe,
            "compare_indicator_params": {
                "period": period,
                "std_dev": std_dev,
            },
        }
    ]
    new_config["base_order_logic"] = "and"

    # Exit when price > upper band
    new_config["take_profit_conditions"] = [
        {
            "id": "price_above_bb_upper",
            "indicator": "price",
            "operator": "greater_than",
            "value_type": "indicator",
            "compare_indicator": "bollinger_upper",
            "timeframe": timeframe,
            "compare_indicator_params": {
                "period": period,
                "std_dev": std_dev,
            },
        }
    ]
    new_config["take_profit_logic"] = "and"
    new_config["safety_order_conditions"] = []
    new_config["safety_order_logic"] = "and"

    return new_config


def convert_rsi(config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert rsi strategy to indicator_based format."""
    new_config = {}

    new_config["max_concurrent_deals"] = config.get("max_concurrent_deals", 1)
    new_config["base_order_type"] = "percentage"
    new_config["base_order_percentage"] = config.get("initial_btc_percentage", 10.0)
    new_config["max_safety_orders"] = config.get("max_dca_orders", 5)
    new_config["safety_order_percentage"] = config.get("dca_percentage", 50.0)
    new_config["take_profit_percentage"] = config.get("min_profit_percentage", 3.0)

    period = config.get("rsi_period", 14)
    oversold = config.get("rsi_oversold", 30)
    overbought = config.get("rsi_overbought", 70)
    timeframe = config.get("candle_interval", "FIVE_MINUTE")

    # Create RSI condition: RSI < oversold
    new_config["base_order_conditions"] = [
        {
            "id": "rsi_oversold",
            "indicator": "rsi",
            "operator": "less_than",
            "value_type": "static",
            "static_value": oversold,
            "timeframe": timeframe,
            "indicator_params": {"period": period},
        }
    ]
    new_config["base_order_logic"] = "and"

    # Exit when RSI > overbought
    new_config["take_profit_conditions"] = [
        {
            "id": "rsi_overbought",
            "indicator": "rsi",
            "operator": "greater_than",
            "value_type": "static",
            "static_value": overbought,
            "timeframe": timeframe,
            "indicator_params": {"period": period},
        }
    ]
    new_config["take_profit_logic"] = "and"
    new_config["safety_order_conditions"] = []
    new_config["safety_order_logic"] = "and"

    return new_config


def convert_advanced_dca(config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert advanced_dca - similar to conditional_dca."""
    return convert_conditional_dca(config)


# Strategy converter mapping
STRATEGY_CONVERTERS = {
    "ai_autonomous": convert_ai_autonomous,
    "bull_flag": convert_bull_flag,
    "conditional_dca": convert_conditional_dca,
    "macd_dca": convert_macd_dca,
    "simple_dca": convert_simple_dca,
    "advanced_dca": convert_advanced_dca,
    "bollinger": convert_bollinger,
    "rsi": convert_rsi,
}

# Strategies to skip (arbitrage strategies)
SKIP_STRATEGIES = {
    "spatial_arbitrage",
    "triangular_arbitrage",
    "statistical_arbitrage",
    "indicator_based",  # Already migrated
}


def migrate_bot_config(bot: Bot) -> Tuple[str, Dict[str, Any], bool]:
    """
    Migrate a single bot's configuration.

    Returns:
        Tuple of (new_strategy_type, new_config, was_changed)
    """
    old_strategy = bot.strategy_type

    if old_strategy in SKIP_STRATEGIES:
        return old_strategy, bot.strategy_config, False

    if old_strategy not in STRATEGY_CONVERTERS:
        logger.warning(f"Bot {bot.id} ({bot.name}): Unknown strategy '{old_strategy}', skipping")
        return old_strategy, bot.strategy_config, False

    converter = STRATEGY_CONVERTERS[old_strategy]
    new_config = converter(bot.strategy_config or {})

    # Preserve any extra fields not handled by converter
    for key, value in (bot.strategy_config or {}).items():
        if key not in new_config:
            new_config[f"_migrated_{key}"] = value

    return "indicator_based", new_config, True


async def migrate_all_bots(db: AsyncSession, dry_run: bool = True) -> Dict[str, int]:
    """
    Migrate all bots to indicator_based strategy.

    Args:
        db: Database session
        dry_run: If True, don't actually save changes

    Returns:
        Dict with counts: {migrated, skipped, errors}
    """
    stats = {"migrated": 0, "skipped": 0, "errors": 0}

    result = await db.execute(select(Bot))
    bots = result.scalars().all()

    logger.info(f"Found {len(bots)} bots to process")

    for bot in bots:
        try:
            new_strategy, new_config, was_changed = migrate_bot_config(bot)

            if not was_changed:
                logger.info(f"Bot {bot.id} ({bot.name}): Skipped - {bot.strategy_type}")
                stats["skipped"] += 1
                continue

            logger.info(
                f"Bot {bot.id} ({bot.name}): {bot.strategy_type} → {new_strategy}"
            )

            if not dry_run:
                # Store original config for reference
                if bot.strategy_config:
                    new_config["_original_strategy"] = bot.strategy_type
                    new_config["_original_config"] = bot.strategy_config

                bot.strategy_type = new_strategy
                bot.strategy_config = new_config
                bot.updated_at = datetime.utcnow()

            stats["migrated"] += 1

        except Exception as e:
            logger.error(f"Bot {bot.id} ({bot.name}): Error - {e}")
            stats["errors"] += 1

    if not dry_run:
        await db.commit()
        logger.info("Changes committed to database")

    return stats


async def migrate_position_snapshots(db: AsyncSession, dry_run: bool = True) -> Dict[str, int]:
    """
    Update position bot_config snapshots to reflect migration.

    Args:
        db: Database session
        dry_run: If True, don't actually save changes

    Returns:
        Dict with counts: {updated, skipped, errors}
    """
    stats = {"updated": 0, "skipped": 0, "errors": 0}

    result = await db.execute(select(Position))
    positions = result.scalars().all()

    logger.info(f"Found {len(positions)} positions to process")

    for position in positions:
        try:
            if not position.bot_config:
                stats["skipped"] += 1
                continue

            old_strategy = position.bot_config.get("strategy_type")
            if not old_strategy or old_strategy in SKIP_STRATEGIES:
                stats["skipped"] += 1
                continue

            if old_strategy not in STRATEGY_CONVERTERS:
                stats["skipped"] += 1
                continue

            # Create a mock bot object to use the converter
            class MockBot:
                pass

            mock = MockBot()
            mock.id = position.id
            mock.name = f"Position {position.id}"
            mock.strategy_type = old_strategy
            mock.strategy_config = position.bot_config.get("strategy_config", {})

            new_strategy, new_config, was_changed = migrate_bot_config(mock)

            if not was_changed:
                stats["skipped"] += 1
                continue

            logger.info(
                f"Position {position.id}: {old_strategy} → {new_strategy}"
            )

            if not dry_run:
                position.bot_config["strategy_type"] = new_strategy
                position.bot_config["strategy_config"] = new_config
                position.bot_config["_migrated_at"] = datetime.utcnow().isoformat()

            stats["updated"] += 1

        except Exception as e:
            logger.error(f"Position {position.id}: Error - {e}")
            stats["errors"] += 1

    if not dry_run:
        await db.commit()
        logger.info("Position snapshot changes committed")

    return stats


async def main(dry_run: bool = True, migrate_positions: bool = False):
    """Main migration function."""
    logger.info(f"Starting migration (dry_run={dry_run})")

    async with async_session_maker() as db:
        # Migrate bots
        bot_stats = await migrate_all_bots(db, dry_run)
        logger.info(
            f"Bot migration complete: {bot_stats['migrated']} migrated, "
            f"{bot_stats['skipped']} skipped, {bot_stats['errors']} errors"
        )

        # Optionally migrate position snapshots
        if migrate_positions:
            pos_stats = await migrate_position_snapshots(db, dry_run)
            logger.info(
                f"Position migration complete: {pos_stats['updated']} updated, "
                f"{pos_stats['skipped']} skipped, {pos_stats['errors']} errors"
            )

    if dry_run:
        logger.info("Dry run complete - no changes were made")
    else:
        logger.info("Migration complete - changes have been applied")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate bots to indicator_based strategy")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default is dry-run)",
    )
    parser.add_argument(
        "--positions",
        action="store_true",
        help="Also migrate position bot_config snapshots",
    )
    args = parser.parse_args()

    asyncio.run(main(dry_run=not args.apply, migrate_positions=args.positions))
