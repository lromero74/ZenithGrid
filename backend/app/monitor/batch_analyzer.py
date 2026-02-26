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
        print("🔍 process_bot_batch() ENTERED")
        from app.models import Position

        print("🔍 Checking open positions...")
        # Check how many open positions this bot has
        open_positions_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
        open_positions_result = await db.execute(open_positions_query)
        open_positions = list(open_positions_result.scalars().all())
        open_count = len(open_positions)
        print(f"🔍 Found {open_count} open positions")

        # Refresh bot from database to get latest config (in case max_concurrent_deals changed)
        await db.refresh(bot)

        # Get max concurrent deals from strategy config
        max_concurrent_deals = bot.strategy_config.get("max_concurrent_deals", 1)
        print(f"🔍 Max concurrent deals: {max_concurrent_deals}")

        # Calculate available budget for new positions
        # Bypass cache for position creation to ensure accurate budget allocation
        quote_currency = bot.get_quote_currency()
        try:
            if quote_currency == "BTC":
                aggregate_value = await monitor.exchange.calculate_aggregate_btc_value(bypass_cache=True)
            else:  # USD
                aggregate_value = await monitor.exchange.calculate_aggregate_usd_value()
        except Exception as e:
            # If portfolio API fails (403/rate limit), use a conservative fallback
            logger.warning(f"  ⚠️  Failed to get aggregate balance (API error), using 0.001 BTC fallback: {e}")
            aggregate_value = 0.001  # Conservative fallback - allows ~3 positions at 30% budget

        # Get actual available balance (what's spendable right now)
        try:
            if quote_currency == "BTC":
                actual_available = await monitor.exchange.get_btc_balance()
            else:  # USD
                actual_available = await monitor.exchange.get_usd_balance()
        except Exception as e:
            logger.warning(f"  ⚠️  Failed to get actual available balance: {e}")
            actual_available = 0.0

        # Defensive logging: Warn if aggregate value is suspiciously low
        if aggregate_value < 0.0001:
            logger.warning(
                f"  ⚠️  SUSPICIOUS: Aggregate {quote_currency} value is very low"
                f" ({aggregate_value:.8f}). This may indicate API issues."
            )
            logger.warning("  ⚠️  Bot may be unable to open new positions due to insufficient calculated balance.")

        # Calculate bot's reserved balance (percentage of total account value from bot config)
        reserved_balance = bot.get_reserved_balance(aggregate_value)
        budget_pct = bot.budget_percentage

        # Calculate how much budget is already used by this bot's positions
        total_in_positions = sum(p.total_quote_spent for p in open_positions)

        # Available budget = max allowed - already in use
        available_budget = reserved_balance - total_in_positions

        # Calculate minimum required per new position (budget / max_deals)
        min_per_position = reserved_balance / max(max_concurrent_deals, 1)

        # Determine if we have enough budget for new positions or DCA
        # Must pass TWO checks:
        # 1. Has room in allocation (available_budget >= min_per_position)
        # 2. Has actual spendable balance (actual_available >= min_per_position)
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
        logger.warning(
            f"  💰 Actual {quote_currency} balance: {actual_available:.8f} {quote_currency}"
        )
        logger.warning(
            f"  💰 Min per position: {min_per_position:.8f} {quote_currency}"
        )
        logger.warning(
            f"  💰 Has allocation room: {has_allocation_room},"
            f" Has actual balance: {has_actual_balance},"
            f" Can open new: {has_budget_for_new}"
        )

        # Determine which pairs to analyze
        pairs_to_analyze = trading_pairs

        # If bot is stopped, only analyze pairs with open positions (for DCA/exit signals)
        if not bot.is_active:
            pairs_with_positions = {p.product_id for p in open_positions if p.product_id}
            pairs_to_analyze = [p for p in trading_pairs if p in pairs_with_positions]
            logger.info(
                f"  ⏸️  Bot is STOPPED - analyzing only {len(pairs_to_analyze)}"
                " pairs with open positions for DCA/exit"
            )
            if len(pairs_to_analyze) == 0:
                logger.info("  ℹ️  No open positions to manage - skipping analysis")
                return {"action": "skip", "reason": "Bot stopped with no open positions"}

        elif open_count >= max_concurrent_deals:
            # At capacity - only analyze pairs with open positions (for sell signals)
            pairs_with_positions = {p.product_id for p in open_positions if p.product_id}
            pairs_to_analyze = [p for p in trading_pairs if p in pairs_with_positions]

            if len(pairs_to_analyze) < len(trading_pairs):
                logger.info(f"  📊 Bot at max capacity ({open_count}/{max_concurrent_deals} positions)")
                logger.info(
                    f"  🎯 Analyzing only {len(pairs_to_analyze)} pairs with open positions: {pairs_to_analyze}"
                )
                logger.info(f"  ⏭️  Skipping {len(trading_pairs) - len(pairs_to_analyze)} pairs without positions")
        elif not has_budget_for_new:
            # Insufficient budget - only analyze pairs with open positions (for sell signals, no new buys/DCA)
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
            # Below capacity AND has budget - analyze all configured pairs (looking for buy + sell signals)
            logger.info(f"  📊 Bot below capacity ({open_count}/{max_concurrent_deals} positions)")
            logger.info(f"  🔍 Analyzing all {len(trading_pairs)} pairs for opportunities")

            # Filter by minimum daily volume (only for NEW positions, not existing ones)
            # Pairs with open positions are ALWAYS analyzed so AI can recommend sells
            min_daily_volume = strategy.config.get("min_daily_volume", 0.0)
            if min_daily_volume > 0:
                logger.info(f"  📊 Filtering pairs by minimum 24h volume: {min_daily_volume}")
                # Get pairs that have existing positions - these bypass volume filter
                pairs_with_existing_positions = {p.product_id for p in open_positions if p.product_id}
                filtered_pairs = []
                for product_id in pairs_to_analyze:
                    # Always include pairs with existing positions (for sell analysis)
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
                        logger.warning(
                            f"    ⚠️  {product_id}: Could not fetch volume"
                            f" stats ({e}), including anyway"
                        )
                        filtered_pairs.append(product_id)  # Include pairs where we can't get stats

                pairs_to_analyze = filtered_pairs
                logger.info(f"  📊 After volume filter: {len(pairs_to_analyze)} pairs remain")

        if not pairs_to_analyze:
            logger.info("  ⏭️  No pairs to analyze")
            return {}

        # Collect market data for pairs we're analyzing
        pairs_data = {}
        failed_pairs = {}  # Track pairs that failed to load data
        successful_pairs = set()  # Track pairs that succeeded (to clear stale errors)
        print(f"🔍 Fetching market data for {len(pairs_to_analyze)} pairs...")
        logger.info(f"  Fetching market data for {len(pairs_to_analyze)} pairs...")

        # Check which pairs have open positions (critical to retry)
        pairs_with_positions = {p.product_id for p in open_positions if p.product_id}

        for product_id in pairs_to_analyze:
            print(f"🔍 Fetching data for {product_id}...")
            has_open_position = product_id in pairs_with_positions
            max_retries = 3 if has_open_position else 1  # Retry more for open positions

            success = False
            last_error = None

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        logger.info(f"  🔄 Retry {attempt}/{max_retries-1} for {product_id}")
                        await asyncio.sleep(0.5 * attempt)  # Brief backoff

                    # Get candles for multiple timeframes (for BB%, MACD crossing, etc.)
                    candles = await monitor.get_candles_cached(product_id, "FIVE_MINUTE", 100)
                    # Fetch 300 ONE_MINUTE candles (max allowed by Coinbase API per request)
                    # This allows up to 100 THREE_MINUTE candles (300/3 = 100)
                    one_min_candles = await monitor.get_candles_cached(product_id, "ONE_MINUTE", 300)
                    # THREE_MINUTE is synthetic (aggregated from 1-min) but now supported
                    three_min_candles = await monitor.get_candles_cached(product_id, "THREE_MINUTE", 100)
                    # TEN_MINUTE is synthetic (aggregated from 5-min)
                    ten_min_candles = await monitor.get_candles_cached(product_id, "TEN_MINUTE", 100)
                    # ONE_HOUR candles for hourly MACD/RSI conditions
                    one_hour_candles = await monitor.get_candles_cached(product_id, "ONE_HOUR", 100)
                    # Higher timeframes for multi-timeframe indicator conditions
                    fifteen_min_candles = await monitor.get_candles_cached(product_id, "FIFTEEN_MINUTE", 100)
                    four_hour_candles = await monitor.get_candles_cached(product_id, "FOUR_HOUR", 100)

                    # Get current price from most recent candle (more reliable than ticker!)
                    if not candles or len(candles) == 0:
                        last_error = "No candles available from API"
                        if attempt < max_retries - 1:
                            continue  # Retry
                        logger.warning(f"  ⚠️  {product_id}: {last_error} after {max_retries} attempts")
                        break

                    current_price = float(candles[-1].get("close", 0))

                    # Validate price
                    if current_price is None or current_price <= 0:
                        last_error = f"Invalid price: {current_price}"
                        if attempt < max_retries - 1:
                            continue  # Retry
                        logger.warning(f"  ⚠️  {product_id}: {last_error} after {max_retries} attempts")
                        break

                    # Build candles_by_timeframe for multi-timeframe indicator calculation
                    candles_by_timeframe = {"FIVE_MINUTE": candles}
                    if one_min_candles and len(one_min_candles) > 0:
                        candles_by_timeframe["ONE_MINUTE"] = one_min_candles
                    if three_min_candles and len(three_min_candles) >= 20:
                        # Need at least 20 THREE_MINUTE candles for reliable BB% calculation
                        candles_by_timeframe["THREE_MINUTE"] = three_min_candles
                        logger.debug(
                            f"  ✅ THREE_MINUTE OK for {product_id}: {len(three_min_candles)} candles"
                        )
                    else:
                        # Log why THREE_MINUTE is insufficient
                        # Note: three_min_candles already went through gap-filling in get_candles_cached
                        three_min_count = len(three_min_candles) if three_min_candles else 0
                        logger.warning(
                            f"  ⚠️ THREE_MINUTE insufficient for {product_id}: "
                            f"have {three_min_count}/20 candles after gap-filling (very low volume pair)"
                        )
                    # Add TEN_MINUTE candles for multi-timeframe conditions
                    if ten_min_candles and len(ten_min_candles) >= 36:
                        candles_by_timeframe["TEN_MINUTE"] = ten_min_candles
                        logger.debug(
                            f"  ✅ TEN_MINUTE OK for {product_id}: {len(ten_min_candles)} candles"
                        )
                    # Add ONE_HOUR candles for hourly MACD/RSI conditions
                    if one_hour_candles and len(one_hour_candles) >= 36:
                        # Need at least 36 candles for MACD (26 slow + 9 signal + buffer for crossing)
                        candles_by_timeframe["ONE_HOUR"] = one_hour_candles
                        logger.debug(
                            f"  ✅ ONE_HOUR OK for {product_id}: {len(one_hour_candles)} candles"
                        )
                    # Add FIFTEEN_MINUTE candles for multi-timeframe conditions
                    if fifteen_min_candles and len(fifteen_min_candles) >= 36:
                        candles_by_timeframe["FIFTEEN_MINUTE"] = fifteen_min_candles
                        logger.debug(
                            f"  ✅ FIFTEEN_MINUTE OK for {product_id}: {len(fifteen_min_candles)} candles"
                        )
                    # Add FOUR_HOUR candles for longer timeframe conditions
                    if four_hour_candles and len(four_hour_candles) >= 36:
                        candles_by_timeframe["FOUR_HOUR"] = four_hour_candles
                        logger.debug(
                            f"  ✅ FOUR_HOUR OK for {product_id}: {len(four_hour_candles)} candles"
                        )

                    # Prepare market context (for AI batch analysis)
                    market_context = prepare_market_context(candles, current_price)

                    pairs_data[product_id] = {
                        "current_price": current_price,
                        "candles": candles,
                        "candles_by_timeframe": candles_by_timeframe,
                        "market_context": market_context,
                    }
                    success = True
                    break  # Success, exit retry loop

                except Exception as e:
                    last_error = str(e)
                    if attempt < max_retries - 1:
                        logger.warning(f"  ⚠️  {product_id}: Error on attempt {attempt+1}: {e}, retrying...")
                        continue  # Retry
                    logger.error(f"  ❌ {product_id}: Error after {max_retries} attempts: {e}")

            # Track failures and successes for open positions
            if not success and has_open_position:
                failed_pairs[product_id] = last_error
                logger.error(f"  🚨 CRITICAL: Failed to fetch data for open position {product_id}: {last_error}")
            elif success and has_open_position:
                # Track successful fetches so we can clear any stale errors
                successful_pairs.add(product_id)

            # Throttle between pairs to reduce CPU burst (t2.micro friendly)
            await asyncio.sleep(PAIR_PROCESSING_DELAY_SECONDS)

        # Calculate per-position budget (total budget / max concurrent deals)
        max_concurrent_deals = bot.strategy_config.get("max_concurrent_deals", 1)
        # Get total bot budget using Bot's get_reserved_balance method
        quote_currency = bot.get_quote_currency()
        if quote_currency == "BTC":
            # Calculate aggregate BTC value if needed
            aggregate_btc = await monitor.exchange.calculate_aggregate_btc_value()
            total_bot_budget = bot.get_reserved_balance(aggregate_btc)
        else:
            # USD bots - get balance directly (no aggregation needed)
            total_bot_budget = bot.get_reserved_balance()

        # Only split budget if split_budget_across_pairs is enabled
        # Otherwise each deal gets the full budget (deal-based allocation)
        if bot.split_budget_across_pairs and max_concurrent_deals > 0:
            per_position_budget = total_bot_budget / max_concurrent_deals
            print(
                f"💰 Budget calculation (SPLIT): Total={total_bot_budget:.8f},"
                f" MaxDeals={max_concurrent_deals},"
                f" PerPosition={per_position_budget:.8f}"
            )
        else:
            per_position_budget = total_bot_budget
            print(
                f"💰 Budget calculation (FULL): Total={total_bot_budget:.8f},"
                f" MaxDeals={max_concurrent_deals},"
                f" PerPosition={per_position_budget:.8f}"
                " (each deal gets full budget)"
            )

        # Call batch AI analysis (1 API call for ALL pairs!) - or skip if technical-only check
        if skip_ai_analysis:
            print("⏭️  Skipping AI analysis (technical-only check)")
            logger.info(f"  ⏭️  SKIPPING AI: Technical-only check for {len(pairs_data)} pairs")
            # When skipping AI, we only check existing positions (DCA, TP logic)
            # Don't open new positions without fresh AI analysis
            batch_analyses = {
                product_id: {"signal_type": "hold", "confidence": 0, "reasoning": "Technical-only check (no AI)"}
                for product_id in pairs_data.keys()
            }
        else:
            print(f"🔍 About to call AI batch analysis for {len(pairs_data)} pairs...")
            logger.info(f"  🧠 Calling AI for batch analysis of {len(pairs_data)} pairs...")
            batch_analyses = await strategy.analyze_multiple_pairs_batch(pairs_data, per_position_budget)
            print(f"✅ AI batch analysis returned with {len(batch_analyses)} results")
            logger.info(f"  ✅ Received {len(batch_analyses)} analyses from AI")

        # Process each pair's analysis result
        results = {}
        print(f"🔍 Processing {len(pairs_data)} pairs from batch analysis...")
        logger.info(f"  📋 Processing {len(pairs_data)} pairs from batch analysis...")
        for product_id in pairs_data.keys():
            try:
                print(f"🔍 Processing result for {product_id}...")
                signal_data = batch_analyses.get(
                    product_id, {"signal_type": "hold", "confidence": 0, "reasoning": "No analysis result"}
                )

                # Debug logging to track duplicate opinions
                logger.info(
                    f"    Processing {product_id}:"
                    f" {signal_data.get('signal_type')}"
                    f" ({signal_data.get('confidence')}%)"
                )

                # Add current_price to signal_data for DCA logic (AI response doesn't include it)
                pair_info = pairs_data.get(product_id, {})
                signal_data["current_price"] = pair_info.get("current_price", 0)

                # Only log actual AI analysis, not technical-only checks (reduces UI noise)
                ai_log_entry = None
                if signal_data.get("reasoning") != "Technical-only check (no AI)":
                    print(f"🔍 Logging AI decision for {product_id}...")
                    # Log AI decision with position info if one exists
                    ai_log_entry = await monitor.log_ai_decision(
                        db, bot, product_id, signal_data, pair_info, open_positions
                    )
                    print(f"✅ Logged AI decision for {product_id}")

                    # Mark signal as already logged to prevent duplicate logging in trading_engine_v2.py
                    signal_data["_already_logged"] = True
                else:
                    # Technical-only check - still mark as logged to skip duplicate logging
                    signal_data["_already_logged"] = True

                print(f"🔍 Executing trading logic for {product_id}...")
                # Execute trading logic based on signal
                result = await monitor.execute_trading_logic(db, bot, product_id, signal_data, pair_info)
                print(f"✅ Trading logic complete for {product_id}")
                results[product_id] = result

                # Rate limit between order attempts to avoid Coinbase 403 throttling
                # Coinbase returns 403 (not 429) when requests are too rapid
                await asyncio.sleep(PAIR_PROCESSING_DELAY_SECONDS)

                # Update AI log with position_id if a NEW position was created (not existing)
                if ai_log_entry and result.get("position") and not ai_log_entry.position_id:
                    position = result["position"]
                    ai_log_entry.position_id = position.id
                    ai_log_entry.position_status = "open"  # New position just opened
                    logger.info(f"  🔗 Linked AI log to new position #{position.id} for {product_id}")

            except Exception as e:
                logger.error(f"  Error processing {product_id} result: {e}")
                results[product_id] = {"error": str(e)}

        # Log errors to positions that failed to load market data
        if failed_pairs:
            from datetime import datetime

            logger.info(f"  💾 Logging {len(failed_pairs)} market data errors to positions...")
            for product_id, error_msg in failed_pairs.items():
                # Find the position for this product
                position = next((p for p in open_positions if p.product_id == product_id), None)
                if position:
                    position.last_error_message = f"Market data fetch failed: {error_msg}"
                    position.last_error_timestamp = datetime.utcnow()
                    logger.info(f"    📝 Position #{position.id} ({product_id}): Error logged")

        # Clear stale errors for positions that succeeded this cycle
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

        # Note: bot.last_signal_check is updated BEFORE processing starts (in monitor_loop)
        # to prevent race conditions where the same bot gets processed twice
        print("🔍 Committing database changes...")
        await db.commit()
        print("✅ Database committed, returning results")

        return results

    except Exception as e:
        logger.error(f"Error in batch processing: {e}")
        import traceback

        traceback.print_exc()
        return {"error": str(e)}
