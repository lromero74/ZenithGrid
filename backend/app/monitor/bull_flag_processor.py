"""
Bull Flag Processor for Multi-Bot Monitor

Handles processing of bull flag strategy bots, which scan for volume spikes
and bull flag patterns, enter positions, and manage trailing stops.
Extracted from MultiBotMonitor.process_bull_flag_bot().
"""

import logging
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bot
from app.strategies.bull_flag_scanner import log_scanner_decision, scan_for_bull_flag_opportunities
from app.trading_engine.trailing_stops import (
    check_bull_flag_exit_conditions,
    setup_bull_flag_position_stops,
)

logger = logging.getLogger(__name__)


async def process_bull_flag_bot(monitor, db: AsyncSession, bot: Bot) -> Dict[str, Any]:
    """
    Process a bull flag strategy bot.

    Bull flag bots work differently from other strategies:
    1. Scan allowed USD coins for volume spikes and bull flag patterns
    2. Enter positions when patterns are detected (with TSL at pullback low, TTP at 2x risk)
    3. Monitor existing positions for TSL/TTP exit conditions

    Args:
        monitor: MultiBotMonitor instance (provides exchange client access)
        db: Database session
        bot: Bot instance with bull_flag strategy

    Returns:
        Result dictionary with actions taken
    """
    from app.models import Position

    try:
        logger.info(f"Processing bull flag bot: {bot.name}")
        results = {"scanned": 0, "opportunities": 0, "entries": [], "exits": [], "errors": []}

        # Step 1: Get open positions for this bot
        open_positions_query = select(Position).where(
            Position.bot_id == bot.id,
            Position.status == "open"
        )
        open_positions_result = await db.execute(open_positions_query)
        open_positions = list(open_positions_result.scalars().all())

        # Step 2: Check trailing stops on existing positions
        for position in open_positions:
            try:
                # Get current price
                current_price = await monitor.exchange.get_current_price(position.product_id)
                if not current_price or current_price <= 0:
                    logger.warning(f"  Could not get price for {position.product_id}")
                    continue

                # Check exit conditions (TSL/TTP)
                should_sell, reason = await check_bull_flag_exit_conditions(
                    position, current_price, db
                )

                # Log exit signal check
                await log_scanner_decision(
                    db=db,
                    bot_id=bot.id,
                    product_id=position.product_id,
                    scan_type="exit_signal",
                    decision="triggered" if should_sell else "hold",
                    reason=reason,
                    current_price=current_price,
                )

                if should_sell:
                    logger.info(f"  🔔 Exit signal for {position.product_id}: {reason}")

                    # Execute sell order
                    try:
                        order = await monitor.exchange.create_market_sell_order(
                            product_id=position.product_id,
                            quantity=position.total_quantity
                        )

                        if order:
                            # Update position
                            position.status = "closed"
                            position.closed_at = datetime.utcnow()
                            position.close_price = current_price
                            await db.commit()

                            results["exits"].append({
                                "product_id": position.product_id,
                                "reason": reason,
                                "price": current_price,
                                "quantity": position.total_quantity,
                            })
                            logger.info(f"  ✅ Sold {position.product_id}: {reason}")
                    except Exception as e:
                        logger.error(f"  Error executing sell for {position.product_id}: {e}")
                        results["errors"].append(f"Sell error {position.product_id}: {e}")

            except Exception as e:
                logger.error(f"  Error checking position {position.product_id}: {e}")
                results["errors"].append(f"Position check error: {e}")

        # Step 3: Check if we can open new positions
        max_concurrent = bot.strategy_config.get("max_concurrent_positions", 5)
        if len(open_positions) >= max_concurrent:
            logger.info(f"  At max positions ({len(open_positions)}/{max_concurrent}), skipping scan")
            # Commit any exit signal logs before returning
            await db.commit()
            return results

        # Step 4: Scan for new opportunities
        # max_scan_coins: configurable limit for rate limiting, defaults to 200 (covers 151 approved)
        max_scan_coins = bot.strategy_config.get("max_scan_coins", 200)
        opportunities = await scan_for_bull_flag_opportunities(
            db=db,
            exchange_client=monitor.exchange,
            config=bot.strategy_config,
            max_coins=max_scan_coins,
            bot_id=bot.id,  # Pass bot_id for scanner logging
            user_id=bot.user_id,  # Scope blacklist query to this user
        )

        # Commit scanner logs immediately after scan completes
        await db.commit()

        results["scanned"] = len(opportunities)
        results["opportunities"] = len([o for o in opportunities if o.get("pattern")])

        # Filter opportunities by allowed categories
        # Deferred import to avoid circular dependency (multi_bot_monitor imports this module)
        from app.multi_bot_monitor import filter_pairs_by_allowed_categories

        allowed_categories = bot.strategy_config.get("allowed_categories") if bot.strategy_config else None
        if allowed_categories and opportunities:
            # Extract pairs from opportunities
            opportunity_pairs = [o.get("product_id") for o in opportunities if o.get("product_id")]
            filtered_pairs = await filter_pairs_by_allowed_categories(
                db, opportunity_pairs, allowed_categories, user_id=bot.user_id
            )
            filtered_pairs_set = set(filtered_pairs)
            # Filter opportunities to only include allowed pairs
            opportunities = [o for o in opportunities if o.get("product_id") in filtered_pairs_set]
            logger.info(f"  Category filtered: {len(opportunities)} opportunities remain")

        # Step 5: Enter positions for valid opportunities
        # Skip coins we already have positions in
        existing_product_ids = {p.product_id for p in open_positions}
        available_slots = max_concurrent - len(open_positions)

        for opportunity in opportunities[:available_slots]:
            product_id = opportunity.get("product_id")
            pattern = opportunity.get("pattern")

            if not product_id or not pattern:
                continue

            if product_id in existing_product_ids:
                logger.info(f"  Skipping {product_id} - already have position")
                continue

            try:
                # Calculate position size
                budget_mode = bot.strategy_config.get("budget_mode", "percentage")
                if budget_mode == "fixed_usd":
                    usd_amount = bot.strategy_config.get("fixed_usd_amount", 100.0)
                else:
                    # Get aggregate USD value
                    aggregate_usd = await monitor.exchange.calculate_aggregate_usd_value()
                    budget_pct = bot.strategy_config.get("budget_percentage", 5.0)
                    usd_amount = aggregate_usd * (budget_pct / 100.0)

                # Check minimum
                if usd_amount < 10.0:
                    logger.warning(f"  Position size ${usd_amount:.2f} below minimum for {product_id}")
                    continue

                # Get current price
                current_price = pattern.get("entry_price", 0)
                if current_price <= 0:
                    current_price = await monitor.exchange.get_current_price(product_id)

                if not current_price or current_price <= 0:
                    logger.warning(f"  Could not get entry price for {product_id}")
                    continue

                # Calculate quantity
                quantity = usd_amount / current_price

                # Execute buy order
                order = await monitor.exchange.create_market_buy_order(
                    product_id=product_id,
                    quantity=quantity
                )

                if order:
                    # Create position
                    position = Position(
                        bot_id=bot.id,
                        account_id=bot.account_id,
                        product_id=product_id,
                        status="open",
                        opened_at=datetime.utcnow(),
                        average_buy_price=current_price,
                        total_quantity=quantity,
                        total_quote_spent=usd_amount,
                        strategy_type="bull_flag",
                        strategy_config_snapshot=bot.strategy_config.copy(),
                    )

                    # Set up trailing stops using pattern data
                    setup_bull_flag_position_stops(position, pattern)

                    db.add(position)
                    await db.commit()

                    results["entries"].append({
                        "product_id": product_id,
                        "price": current_price,
                        "quantity": quantity,
                        "usd_amount": usd_amount,
                        "stop_loss": pattern.get("stop_loss"),
                        "take_profit_target": pattern.get("take_profit_target"),
                    })

                    logger.info(
                        f"  ✅ Entered {product_id}: ${usd_amount:.2f} at ${current_price:.4f}, "
                        f"SL=${pattern.get('stop_loss'):.4f}, TP=${pattern.get('take_profit_target'):.4f}"
                    )

                    # Update existing_product_ids to prevent duplicate entries
                    existing_product_ids.add(product_id)

            except Exception as e:
                logger.error(f"  Error entering {product_id}: {e}")
                results["errors"].append(f"Entry error {product_id}: {e}")

        await db.commit()
        return results

    except Exception as e:
        logger.error(f"Error processing bull flag bot {bot.name}: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
