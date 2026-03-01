"""
Batch Analyzer for Multi-Bot Monitor

Handles batch analysis of multiple trading pairs using AI batch analysis
(single API call for all pairs). Extracted from MultiBotMonitor.process_bot_batch().
"""

import asyncio
import logging
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import PAIR_PROCESSING_DELAY_SECONDS
from app.models import Bot
from app.utils.candle_utils import prepare_market_context

logger = logging.getLogger(__name__)


async def _calculate_batch_budget(monitor, bot: Bot, open_positions: list) -> dict:
    """Calculate budget availability for new positions.

    Returns dict with: quote_currency, reserved_balance, budget_pct, available_budget,
    min_per_position, has_budget_for_new, max_concurrent_deals.
    """
    max_concurrent_deals = bot.strategy_config.get("max_concurrent_deals", 1)
    quote_currency = bot.get_quote_currency()

    try:
        aggregate_value = await monitor.exchange.calculate_aggregate_quote_value(
            quote_currency, bypass_cache=True
        )
    except Exception as e:
        logger.warning(f"  ⚠️  Failed to get aggregate balance (API error), using 0.001 BTC fallback: {e}")
        aggregate_value = 0.001

    try:
        if quote_currency == "BTC":
            actual_available = await monitor.exchange.get_btc_balance()
        else:
            actual_available = await monitor.exchange.get_usd_balance()
    except Exception as e:
        logger.warning(f"  ⚠️  Failed to get actual available balance: {e}")
        actual_available = 0.0

    if aggregate_value < 0.0001:
        logger.warning(
            f"  ⚠️  SUSPICIOUS: Aggregate {quote_currency} value is very low"
            f" ({aggregate_value:.8f}). This may indicate API issues."
        )
        logger.warning("  ⚠️  Bot may be unable to open new positions due to insufficient calculated balance.")

    reserved_balance = bot.get_reserved_balance(aggregate_value)
    budget_pct = bot.budget_percentage
    total_in_positions = sum(p.total_quote_spent for p in open_positions)
    available_budget = reserved_balance - total_in_positions
    min_per_position = reserved_balance / max(max_concurrent_deals, 1)

    has_allocation_room = available_budget >= min_per_position
    has_actual_balance = actual_available >= min_per_position
    has_budget_for_new = has_allocation_room and has_actual_balance

    logger.warning(
        f"  💰 Budget: {reserved_balance:.8f} {quote_currency} reserved ({budget_pct}% of {aggregate_value:.8f})"
    )
    logger.warning(
        f"  💰 In positions: {total_in_positions:.8f} {quote_currency},"
        f" Available allocation: {available_budget:.8f} {quote_currency}"
    )
    logger.warning(f"  💰 Actual {quote_currency} balance: {actual_available:.8f} {quote_currency}")
    logger.warning(f"  💰 Min per position: {min_per_position:.8f} {quote_currency}")
    logger.warning(
        f"  💰 Has allocation room: {has_allocation_room},"
        f" Has actual balance: {has_actual_balance},"
        f" Can open new: {has_budget_for_new}"
    )

    return {
        "quote_currency": quote_currency,
        "reserved_balance": reserved_balance,
        "available_budget": available_budget,
        "min_per_position": min_per_position,
        "has_budget_for_new": has_budget_for_new,
        "max_concurrent_deals": max_concurrent_deals,
    }


async def _determine_pairs_to_analyze(
    monitor, bot: Bot, trading_pairs: List[str], open_positions: list,
    strategy: Any, budget_info: dict,
) -> List[str]:
    """Determine which pairs to analyze based on bot state, capacity, and budget.

    Returns filtered list of pairs, or empty list if nothing to analyze.
    May return a special skip result via exception if bot should skip entirely.
    """
    open_count = len(open_positions)
    max_concurrent_deals = budget_info["max_concurrent_deals"]
    has_budget_for_new = budget_info["has_budget_for_new"]
    quote_currency = budget_info["quote_currency"]
    available_budget = budget_info["available_budget"]
    min_per_position = budget_info["min_per_position"]

    pairs_to_analyze = list(trading_pairs)

    if not bot.is_active:
        pairs_with_positions = {p.product_id for p in open_positions if p.product_id}
        pairs_to_analyze = [p for p in trading_pairs if p in pairs_with_positions]
        logger.info(
            f"  ⏸️  Bot is STOPPED - analyzing only {len(pairs_to_analyze)}"
            " pairs with open positions for DCA/exit"
        )
    elif open_count >= max_concurrent_deals:
        pairs_with_positions = {p.product_id for p in open_positions if p.product_id}
        pairs_to_analyze = [p for p in trading_pairs if p in pairs_with_positions]
        if len(pairs_to_analyze) < len(trading_pairs):
            logger.info(f"  📊 Bot at max capacity ({open_count}/{max_concurrent_deals} positions)")
            logger.info(
                f"  🎯 Analyzing only {len(pairs_to_analyze)} pairs with open positions: {pairs_to_analyze}"
            )
            logger.info(f"  ⏭️  Skipping {len(trading_pairs) - len(pairs_to_analyze)} pairs without positions")
    elif not has_budget_for_new:
        pairs_with_positions = {p.product_id for p in open_positions if p.product_id}
        pairs_to_analyze = [p for p in trading_pairs if p in pairs_with_positions]
        logger.warning(
            f"  ⚠️  INSUFFICIENT FUNDS: Only {available_budget:.8f}"
            f" {quote_currency} available, need {min_per_position:.8f}"
        )
        logger.info(
            f"  💰 Skipping new position analysis - analyzing only"
            f" {len(pairs_to_analyze)} pairs with open positions for sell signals"
        )
        logger.info("  ℹ️  Will resume looking for new opportunities once funds are available")
    else:
        logger.info(f"  📊 Bot below capacity ({open_count}/{max_concurrent_deals} positions)")
        logger.info(f"  🔍 Analyzing all {len(trading_pairs)} pairs for opportunities")

        min_daily_volume = strategy.config.get("min_daily_volume", 0.0)
        if min_daily_volume > 0:
            pairs_to_analyze = await _filter_by_volume(
                monitor, pairs_to_analyze, open_positions, min_daily_volume,
            )

    return pairs_to_analyze


async def _filter_by_volume(
    monitor, pairs: List[str], open_positions: list, min_daily_volume: float,
) -> List[str]:
    """Filter pairs by minimum 24h volume, always keeping pairs with open positions."""
    logger.info(f"  📊 Filtering pairs by minimum 24h volume: {min_daily_volume}")
    pairs_with_existing_positions = {p.product_id for p in open_positions if p.product_id}
    filtered_pairs = []

    for product_id in pairs:
        if product_id in pairs_with_existing_positions:
            filtered_pairs.append(product_id)
            logger.info(f"    🔒 {product_id}: Has open position (bypassing volume filter)")
            continue
        try:
            stats = await monitor.exchange.get_product_stats(product_id)
            volume_24h = stats.get("volume_24h", 0.0)
            if volume_24h >= min_daily_volume:
                filtered_pairs.append(product_id)
                logger.info(f"    ✅ {product_id}: Volume {volume_24h:.2f} (meets threshold)")
            else:
                logger.info(f"    ⏭️  {product_id}: Volume {volume_24h:.2f} (below {min_daily_volume})")
        except Exception as e:
            logger.warning(f"    ⚠️  {product_id}: Could not fetch volume stats ({e}), including anyway")
            filtered_pairs.append(product_id)

    logger.info(f"  📊 After volume filter: {len(filtered_pairs)} pairs remain")
    return filtered_pairs


async def _fetch_batch_market_data(
    monitor, pairs_to_analyze: List[str], open_positions: list,
) -> tuple:
    """Fetch market data for all pairs to analyze.

    Returns (pairs_data, failed_pairs, successful_pairs).
    """
    pairs_data = {}
    failed_pairs = {}
    successful_pairs = set()

    pairs_with_positions = {p.product_id for p in open_positions if p.product_id}
    logger.info(f"  Fetching market data for {len(pairs_to_analyze)} pairs...")

    for product_id in pairs_to_analyze:
        has_open_position = product_id in pairs_with_positions
        max_retries = 3 if has_open_position else 1

        success = False
        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"  🔄 Retry {attempt}/{max_retries-1} for {product_id}")
                    await asyncio.sleep(0.5 * attempt)

                candles = await monitor.get_candles_cached(product_id, "FIVE_MINUTE", 100)
                one_min_candles = await monitor.get_candles_cached(product_id, "ONE_MINUTE", 300)
                three_min_candles = await monitor.get_candles_cached(product_id, "THREE_MINUTE", 100)
                ten_min_candles = await monitor.get_candles_cached(product_id, "TEN_MINUTE", 100)
                one_hour_candles = await monitor.get_candles_cached(product_id, "ONE_HOUR", 100)
                fifteen_min_candles = await monitor.get_candles_cached(product_id, "FIFTEEN_MINUTE", 100)
                four_hour_candles = await monitor.get_candles_cached(product_id, "FOUR_HOUR", 100)

                if not candles or len(candles) == 0:
                    last_error = "No candles available from API"
                    if attempt < max_retries - 1:
                        continue
                    logger.warning(f"  ⚠️  {product_id}: {last_error} after {max_retries} attempts")
                    break

                current_price = float(candles[-1].get("close", 0))
                if current_price is None or current_price <= 0:
                    last_error = f"Invalid price: {current_price}"
                    if attempt < max_retries - 1:
                        continue
                    logger.warning(f"  ⚠️  {product_id}: {last_error} after {max_retries} attempts")
                    break

                candles_by_timeframe = _build_candles_by_timeframe(
                    product_id, candles, one_min_candles, three_min_candles,
                    ten_min_candles, one_hour_candles, fifteen_min_candles, four_hour_candles,
                )

                market_context = prepare_market_context(candles, current_price)
                pairs_data[product_id] = {
                    "current_price": current_price,
                    "candles": candles,
                    "candles_by_timeframe": candles_by_timeframe,
                    "market_context": market_context,
                }
                success = True
                break

            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    logger.warning(f"  ⚠️  {product_id}: Error on attempt {attempt+1}: {e}, retrying...")
                    continue
                logger.error(f"  ❌ {product_id}: Error after {max_retries} attempts: {e}")

        if not success and has_open_position:
            failed_pairs[product_id] = last_error
            logger.error(f"  🚨 CRITICAL: Failed to fetch data for open position {product_id}: {last_error}")
        elif success and has_open_position:
            successful_pairs.add(product_id)

        await asyncio.sleep(PAIR_PROCESSING_DELAY_SECONDS)

    return pairs_data, failed_pairs, successful_pairs


def _build_candles_by_timeframe(
    product_id: str, candles: list,
    one_min: list, three_min: list, ten_min: list,
    one_hour: list, fifteen_min: list, four_hour: list,
) -> Dict[str, list]:
    """Assemble candles_by_timeframe dict, validating minimum counts per timeframe."""
    result = {"FIVE_MINUTE": candles}

    if one_min and len(one_min) > 0:
        result["ONE_MINUTE"] = one_min

    if three_min and len(three_min) >= 20:
        result["THREE_MINUTE"] = three_min
        logger.debug(f"  ✅ THREE_MINUTE OK for {product_id}: {len(three_min)} candles")
    else:
        count = len(three_min) if three_min else 0
        logger.warning(
            f"  ⚠️ THREE_MINUTE insufficient for {product_id}: "
            f"have {count}/20 candles after gap-filling (very low volume pair)"
        )

    for tf_name, tf_candles, min_count in [
        ("TEN_MINUTE", ten_min, 36),
        ("ONE_HOUR", one_hour, 36),
        ("FIFTEEN_MINUTE", fifteen_min, 36),
        ("FOUR_HOUR", four_hour, 36),
    ]:
        if tf_candles and len(tf_candles) >= min_count:
            result[tf_name] = tf_candles
            logger.debug(f"  ✅ {tf_name} OK for {product_id}: {len(tf_candles)} candles")

    return result


async def _execute_batch_analysis(
    monitor, db: AsyncSession, bot: Bot, pairs_data: Dict[str, Any],
    strategy: Any, open_positions: list, skip_ai_analysis: bool,
) -> Dict[str, Any]:
    """Run AI batch analysis and execute trading logic for each pair.

    Returns results dict keyed by product_id.
    """
    # Calculate per-position budget for AI analysis
    max_concurrent_deals = bot.strategy_config.get("max_concurrent_deals", 1)
    quote_currency = bot.get_quote_currency()
    aggregate_value = await monitor.exchange.calculate_aggregate_quote_value(quote_currency)
    total_bot_budget = bot.get_reserved_balance(aggregate_value)

    if bot.split_budget_across_pairs and max_concurrent_deals > 0:
        per_position_budget = total_bot_budget / max_concurrent_deals
        print(
            f"💰 Budget calculation (SPLIT): Total={total_bot_budget:.8f},"
            f" MaxDeals={max_concurrent_deals}, PerPosition={per_position_budget:.8f}"
        )
    else:
        per_position_budget = total_bot_budget
        print(
            f"💰 Budget calculation (FULL): Total={total_bot_budget:.8f},"
            f" MaxDeals={max_concurrent_deals}, PerPosition={per_position_budget:.8f}"
            " (each deal gets full budget)"
        )

    # AI analysis (or technical-only fallback)
    if skip_ai_analysis:
        logger.info(f"  ⏭️  SKIPPING AI: Technical-only check for {len(pairs_data)} pairs")
        batch_analyses = {
            pid: {"signal_type": "hold", "confidence": 0, "reasoning": "Technical-only check (no AI)"}
            for pid in pairs_data.keys()
        }
    else:
        logger.info(f"  🧠 Calling AI for batch analysis of {len(pairs_data)} pairs...")
        batch_analyses = await strategy.analyze_multiple_pairs_batch(pairs_data, per_position_budget)
        logger.info(f"  ✅ Received {len(batch_analyses)} analyses from AI")

    # Process each pair's result
    results = {}
    logger.info(f"  📋 Processing {len(pairs_data)} pairs from batch analysis...")
    for product_id in pairs_data.keys():
        try:
            signal_data = batch_analyses.get(
                product_id, {"signal_type": "hold", "confidence": 0, "reasoning": "No analysis result"}
            )
            logger.info(
                f"    Processing {product_id}: {signal_data.get('signal_type')}"
                f" ({signal_data.get('confidence')}%)"
            )

            pair_info = pairs_data.get(product_id, {})
            signal_data["current_price"] = pair_info.get("current_price", 0)

            # Log AI analysis (skip for technical-only checks to reduce UI noise)
            ai_log_entry = None
            if signal_data.get("reasoning") != "Technical-only check (no AI)":
                ai_log_entry = await monitor.log_ai_decision(
                    db, bot, product_id, signal_data, pair_info, open_positions
                )
            signal_data["_already_logged"] = True

            result = await monitor.execute_trading_logic(db, bot, product_id, signal_data, pair_info)
            results[product_id] = result

            await asyncio.sleep(PAIR_PROCESSING_DELAY_SECONDS)

            # Link AI log to newly created position
            if ai_log_entry and result.get("position") and not ai_log_entry.position_id:
                position = result["position"]
                ai_log_entry.position_id = position.id
                ai_log_entry.position_status = "open"
                logger.info(f"  🔗 Linked AI log to new position #{position.id} for {product_id}")

        except Exception as e:
            logger.error(f"  Error processing {product_id} result: {e}")
            results[product_id] = {"error": str(e)}

    return results


def _update_position_errors(open_positions: list, failed_pairs: dict, successful_pairs: set):
    """Log errors to positions that failed market data fetch and clear stale errors."""
    if failed_pairs:
        from datetime import datetime
        logger.info(f"  💾 Logging {len(failed_pairs)} market data errors to positions...")
        for product_id, error_msg in failed_pairs.items():
            position = next((p for p in open_positions if p.product_id == product_id), None)
            if position:
                position.last_error_message = f"Market data fetch failed: {error_msg}"
                position.last_error_timestamp = datetime.utcnow()
                logger.info(f"    📝 Position #{position.id} ({product_id}): Error logged")

    if successful_pairs:
        cleared_count = 0
        for product_id in successful_pairs:
            position = next((p for p in open_positions if p.product_id == product_id), None)
            if position and position.last_error_message:
                position.last_error_message = None
                position.last_error_timestamp = None
                cleared_count += 1
                logger.debug(f"    ✅ Position #{position.id} ({product_id}): Stale error cleared")
        if cleared_count > 0:
            logger.info(f"  🧹 Cleared {cleared_count} stale error(s) from positions")


async def process_bot_batch(
    monitor, db: AsyncSession, bot: Bot, trading_pairs: List[str], strategy: Any, skip_ai_analysis: bool = False
) -> Dict[str, Any]:
    """
    Process multiple trading pairs using AI batch analysis (single API call for all pairs)

    Args:
        monitor: MultiBotMonitor instance (provides exchange, caching, logging methods)
        db: Database session
        bot: Bot instance
        trading_pairs: List of product IDs to analyze
        strategy: Strategy instance that supports batch analysis
        skip_ai_analysis: If True, skip AI analysis and check only technical conditions

    Returns:
        Result dictionary with action/signal info for all pairs
    """
    try:
        from app.models import Position

        # Phase 1: Get open positions and refresh bot config
        open_positions_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
        open_positions_result = await db.execute(open_positions_query)
        open_positions = list(open_positions_result.scalars().all())
        await db.refresh(bot)

        # Phase 2: Calculate budget availability
        budget_info = await _calculate_batch_budget(monitor, bot, open_positions)

        # Phase 3: Determine which pairs to analyze
        pairs_to_analyze = await _determine_pairs_to_analyze(
            monitor, bot, trading_pairs, open_positions, strategy, budget_info,
        )
        if not bot.is_active and not pairs_to_analyze:
            return {"action": "skip", "reason": "Bot stopped with no open positions"}
        if not pairs_to_analyze:
            logger.info("  ⏭️  No pairs to analyze")
            return {}

        # Phase 4: Fetch market data
        pairs_data, failed_pairs, successful_pairs = await _fetch_batch_market_data(
            monitor, pairs_to_analyze, open_positions,
        )

        if not pairs_data:
            _update_position_errors(open_positions, failed_pairs, successful_pairs)
            await db.commit()
            return {}

        # Phase 5: Run AI analysis + execute trades
        results = await _execute_batch_analysis(
            monitor, db, bot, pairs_data, strategy, open_positions, skip_ai_analysis,
        )

        # Phase 6: Update position error tracking
        _update_position_errors(open_positions, failed_pairs, successful_pairs)

        await db.commit()
        return results

    except Exception as e:
        logger.error(f"Error in batch processing: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
