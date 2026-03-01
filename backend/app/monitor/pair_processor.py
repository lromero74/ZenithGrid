"""
Pair Processor for Multi-Bot Monitor

Handles processing of signals for a single bot/pair combination.
Extracted from MultiBotMonitor.process_bot_pair().
"""

import logging
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bot
from app.services.indicator_log_service import log_indicator_evaluation
from app.strategies import StrategyRegistry
from app.trading_engine_v2 import StrategyTradingEngine
from app.utils.candle_utils import get_timeframes_for_phases

logger = logging.getLogger(__name__)


async def process_bot_pair(
    monitor, db: AsyncSession, bot: Bot, product_id: str,
    pre_analyzed_signal=None, pair_data=None, commit=True,
    skip_ai_analysis: bool = False
) -> Dict[str, Any]:
    """
    Process signals for a single bot/pair combination

    Args:
        monitor: MultiBotMonitor instance (provides exchange, caching, logging methods)
        db: Database session
        bot: Bot instance to process
        product_id: Trading pair to evaluate (e.g., "ETH-BTC")
        pre_analyzed_signal: Pre-analyzed signal from batch analysis (optional)
        pair_data: Pre-fetched market data from batch analysis (optional)
        commit: Whether to commit the database session after processing (default: True)
                Set to False when processing in batch mode to avoid corrupting the session
        skip_ai_analysis: If True, skip AI analysis and check only technical conditions

    Returns:
        Result dictionary with action/signal info
    """
    try:
        logger.info(f"  Evaluating pair: {product_id}")

        # Get strategy instance for this bot
        try:
            # Get ALL open positions for this pair (supports simultaneous same-pair deals)
            from app.trading_engine.position_manager import (
                all_positions_exhausted_safety_orders,
                get_active_positions_for_pair,
            )

            all_pair_positions = await get_active_positions_for_pair(db, bot, product_id)
            existing_position = all_pair_positions[0] if all_pair_positions else None

            if existing_position and existing_position.strategy_config_snapshot:
                # Use frozen config from position (snapshot at creation time)
                strategy_config = existing_position.strategy_config_snapshot.copy()
                logger.info(f"    Using FROZEN strategy config from position #{existing_position.id}")
            else:
                # Use current bot config (for new positions or legacy positions without snapshot)
                strategy_config = bot.strategy_config.copy()
                logger.info("    Using CURRENT bot strategy config")

                # Adjust budget percentages if splitting across pairs (only for new positions)
                # Skip when auto_calculate is on — auto-calculate already receives per-position
                # budget from _calculate_budget() and computes order sizes from that balance.
                # Dividing percentages here would double-count the split.
                if bot.split_budget_across_pairs and not strategy_config.get("auto_calculate_order_sizes", False):
                    max_concurrent_deals = max(strategy_config.get("max_concurrent_deals", 1), 1)
                    logger.info(f"    Splitting budget across {max_concurrent_deals} max concurrent deals")

                    # Adjust percentage-based parameters
                    if "base_order_percentage" in strategy_config:
                        original = strategy_config["base_order_percentage"]
                        strategy_config["base_order_percentage"] = original / max_concurrent_deals
                        logger.info(
                            f"      Base order: {original}% → {strategy_config['base_order_percentage']:.2f}%"
                        )

                    if "safety_order_percentage" in strategy_config:
                        original = strategy_config["safety_order_percentage"]
                        strategy_config["safety_order_percentage"] = original / max_concurrent_deals
                        logger.info(
                            f"      Safety order: {original}% → {strategy_config['safety_order_percentage']:.2f}%"
                        )

                    if "max_btc_usage_percentage" in strategy_config:
                        original = strategy_config["max_btc_usage_percentage"]
                        strategy_config["max_btc_usage_percentage"] = original / max_concurrent_deals
                        logger.info(
                            f"      Max usage: {original}% → {strategy_config['max_btc_usage_percentage']:.2f}%"
                        )

            # Inject user_id into strategy config for per-user AI API key lookup
            strategy_config["user_id"] = bot.user_id
            strategy = StrategyRegistry.get_strategy(bot.strategy_type, strategy_config)
        except ValueError as e:
            logger.error(f"Unknown strategy: {bot.strategy_type}")
            return {"error": str(e)}

        # Use provided pair_data if available (from batch), otherwise fetch market data
        if pair_data:
            logger.info("    Using pre-fetched market data")
            current_price = pair_data.get("current_price", 0)
            candles = pair_data.get("candles", [])
            # Use candles_by_timeframe from pair_data if available (supports multiple timeframes for BB%)
            candles_by_timeframe = pair_data.get("candles_by_timeframe", {"FIVE_MINUTE": candles})
        else:
            # Initialize candles variables for later use
            candles = None
            candles_by_timeframe = {}

            # Fetch candles first to get reliable price
            temp_candles = await monitor.get_candles_cached(product_id, "FIVE_MINUTE", 100)
            if temp_candles and len(temp_candles) > 0:
                current_price = float(temp_candles[-1].get("close", 0))
                logger.info(f"    Current {product_id} price (from candles): {current_price:.8f}")
            else:
                logger.warning(f"    No candles available for {product_id}, using fallback ticker")
                current_price = await monitor.exchange.get_current_price(product_id)
                logger.info(f"    Current {product_id} price (from ticker): {current_price:.8f}")

        # Simultaneous same-pair deal settings (used for all strategy types)
        max_same_pair = strategy_config.get("max_simultaneous_same_pair", 1)
        max_safety = strategy_config.get("max_safety_orders", 5)
        same_pair_count = len(all_pair_positions)

        # For indicator-based strategies, extract timeframes from conditions
        if bot.strategy_type in ("conditional_dca", "indicator_based"):
            # Phase 3 Optimization: Lazy fetching - only fetch timeframes for current phase
            # Determine which phases we need to check based on position status
            if existing_position:
                # Check if a simultaneous deal might be possible (need entry phases too)
                if (same_pair_count < max_same_pair
                        and all_positions_exhausted_safety_orders(all_pair_positions, max_safety)):
                    # Need both DCA/exit for existing AND entry for potential new deal
                    phases_to_check = ["base_order_conditions", "safety_order_conditions", "take_profit_conditions"]
                    print(
                        f"  📊 {same_pair_count} position(s), all SOs exhausted"
                        " - checking entry + DCA + exit phases"
                    )
                else:
                    # Open position: check safety orders (DCA) + take profit (exit)
                    phases_to_check = ["safety_order_conditions", "take_profit_conditions"]
                    print("  📊 Open position detected - checking DCA + exit phases only")
            else:
                # No position: check base order (entry) conditions only
                phases_to_check = ["base_order_conditions"]
                print("  📊 No position - checking entry phase only")

            # Extract unique timeframes for the phases we actually need
            timeframes_needed = get_timeframes_for_phases(bot.strategy_config, phases_to_check)

            print(
                f"  📊 Fetching candles for timeframes: {timeframes_needed} "
                f"(phases: {phases_to_check})"
            )

            # Fetch candles for each unique timeframe
            # Use more lookback for longer timeframes to ensure we get enough data
            candles_by_timeframe = {}
            for timeframe in timeframes_needed:
                # Coinbase limits: ~300 candles max per request
                # Stay conservative to ensure we get data
                lookback_map = {
                    "ONE_MINUTE": 200,
                    "THREE_MINUTE": 200,
                    "FIVE_MINUTE": 200,
                    "TEN_MINUTE": 150,
                    "FIFTEEN_MINUTE": 150,
                    "THIRTY_MINUTE": 100,  # 100 candles = 50 hours
                    "ONE_HOUR": 100,  # 100 candles = 4 days
                    "TWO_HOUR": 100,
                    "FOUR_HOUR": 100,
                    "SIX_HOUR": 100,
                    "ONE_DAY": 100,
                }
                lookback = lookback_map.get(timeframe, 100)

                tf_candles = await monitor.get_candles_cached(
                    product_id=product_id, granularity=timeframe, lookback_candles=lookback
                )
                if tf_candles:
                    logger.info(f"    Got {len(tf_candles)} candles for {timeframe}")
                    candles_by_timeframe[timeframe] = tf_candles
                else:
                    logger.warning(f"    No candles returned for {timeframe}")

            if not candles_by_timeframe:
                logger.warning(f"    No candles available for {product_id}")
                return {"error": "No candles available"}

            # Use first timeframe's candles as default for backward compatibility
            candles = list(candles_by_timeframe.values())[0]
        else:
            # Legacy: Get bot's configured timeframe (default to FIVE_MINUTE if not set)
            timeframe = bot.strategy_config.get("timeframe", "FIVE_MINUTE")
            logger.info(f"  Using timeframe: {timeframe}")

            # Get historical candles for signal analysis (if not already provided via pair_data)
            if not candles:
                candles = await monitor.get_candles_cached(
                    product_id=product_id, granularity=timeframe, lookback_candles=100
                )

            if not candles:
                logger.warning(f"    No candles available for {product_id}")
                return {"error": "No candles available"}

            # Only set default candles_by_timeframe if not already populated from pair_data
            # This preserves THREE_MINUTE and other timeframes from batch mode
            if not candles_by_timeframe or len(candles_by_timeframe) == 0:
                candles_by_timeframe = {timeframe: candles}
            else:
                logger.info(
                    f"  📊 Using pre-fetched candles_by_timeframe with"
                    f" {len(candles_by_timeframe)} timeframes:"
                    f" {list(candles_by_timeframe.keys())}"
                )

        # Use pre-analyzed signal if provided (from batch analysis), otherwise analyze now
        if pre_analyzed_signal:
            logger.info("  Using pre-analyzed signal from batch")
            signal_data = pre_analyzed_signal
        elif skip_ai_analysis:
            # Skip AI analysis for technical-only check
            # Pass previous_indicators_cache for crossing detection on ALL strategies
            cache_key = (bot.id, product_id)
            previous_indicators_from_cache = monitor._previous_indicators_cache.get(cache_key)
            if bot.strategy_type in ("conditional_dca", "indicator_based"):
                print("  ⏭️  Technical check: Analyzing indicator-based signals")
                signal_data = await strategy.analyze_signal(
                    candles, current_price, candles_by_timeframe,
                    position=existing_position,
                    previous_indicators_cache=previous_indicators_from_cache,
                    db=db, user_id=bot.user_id, product_id=product_id
                )
            else:
                logger.info("  ⏭️  Technical check: Evaluating conditions with cached AI values")
                signal_data = await strategy.analyze_signal(
                    candles, current_price,
                    position=existing_position,
                    previous_indicators_cache=previous_indicators_from_cache,
                    db=db,
                    user_id=bot.user_id,
                    product_id=product_id,
                    use_cached_ai=True  # Use cached AI values, don't call LLM
                )
        else:
            # Analyze signal using strategy
            # Pass previous_indicators_cache for crossing detection on ALL strategies
            cache_key = (bot.id, product_id)
            previous_indicators_from_cache = monitor._previous_indicators_cache.get(cache_key)
            if bot.strategy_type in ("conditional_dca", "indicator_based"):
                print("  📊 Analyzing indicator-based signals...")
                signal_data = await strategy.analyze_signal(
                    candles, current_price, candles_by_timeframe,
                    position=existing_position,
                    previous_indicators_cache=previous_indicators_from_cache,
                    db=db, user_id=bot.user_id, product_id=product_id
                )
            else:
                signal_data = await strategy.analyze_signal(
                    candles, current_price,
                    position=existing_position,
                    previous_indicators_cache=previous_indicators_from_cache,
                    db=db,
                    user_id=bot.user_id,
                    product_id=product_id
                )

        # Update previous_indicators cache for ALL strategies (crossing detection)
        if signal_data and "indicators" in signal_data:
            cache_key = (bot.id, product_id)
            monitor._previous_indicators_cache[cache_key] = signal_data["indicators"].copy()
            logger.debug(f"    Updated previous_indicators cache for {cache_key}")

        # Check max_synthetic_pct threshold — skip pair if too many gap-filled candles
        max_synthetic_pct = strategy_config.get("max_synthetic_pct")
        if max_synthetic_pct is not None and signal_data and "indicators" in signal_data:
            indicators_snap = signal_data["indicators"]
            # Find gap_fill_pct from any timeframe (check with and without timeframe prefix)
            gap_fill = indicators_snap.get("gap_fill_pct")
            if gap_fill is None:
                for key, val in indicators_snap.items():
                    if key.endswith("_gap_fill_pct") and val is not None:
                        gap_fill = val
                        break
            if gap_fill is not None and gap_fill > max_synthetic_pct:
                logger.warning(
                    f"  Skipping {product_id}: gap_fill_pct={gap_fill:.1f}%"
                    f" > max_synthetic_pct={max_synthetic_pct}%"
                )
                return {
                    "action": "none",
                    "reason": f"Synthetic candle % too high ({gap_fill:.1f}% > {max_synthetic_pct}%)",
                }

        # Commit any position changes (e.g., previous_indicators for crossing detection)
        if existing_position is not None:
            await db.commit()

        if not signal_data:
            logger.warning("  No signal from strategy (returned None)")
            return {"action": "none", "reason": "No signal"}

        logger.info(
            f"  Signal data:"
            f" base_order={signal_data.get('base_order_signal')},"
            f" safety_order={signal_data.get('safety_order_signal')},"
            f" take_profit={signal_data.get('take_profit_signal')}"
        )

        signal_type = signal_data.get("signal_type")
        logger.info(f"  🔔 Signal detected: {signal_type}")

        # Log AI decision to database (only for actual AI analysis, not technical-only checks)
        # Handle both direct reasoning field (AI strategies) and indicator-based AI explanations
        reasoning = signal_data.get("reasoning")
        indicators = signal_data.get("indicators", {})
        ai_buy_explanation = indicators.get("ai_buy_explanation") if indicators else None
        ai_sell_explanation = indicators.get("ai_sell_explanation") if indicators else None

        should_log_ai = False
        log_signal_data = signal_data

        if reasoning and reasoning != "Technical-only check (no AI)":
            # Direct AI strategy with reasoning field
            should_log_ai = True
        elif ai_buy_explanation or ai_sell_explanation:
            # indicator_based strategy with AI conditions
            should_log_ai = True

            # Determine clear BUY/SELL/HOLD decision from signals
            base_order = signal_data.get("base_order_signal", False)
            safety_order = signal_data.get("safety_order_signal", False)
            take_profit = signal_data.get("take_profit_signal", False)

            ai_buy_score = indicators.get("ai_buy_score", 0) or 0
            ai_sell_score = indicators.get("ai_sell_score", 0) or 0

            # Determine decision and confidence based on which signal triggered
            # IMPORTANT: Only show SELL if there's actually a position to sell
            has_position = existing_position is not None
            if take_profit and has_position:
                decision = "sell"
                confidence = ai_sell_score
                reasoning = ai_sell_explanation or "Take profit conditions met"
            elif base_order or safety_order:
                decision = "buy"
                confidence = ai_buy_score
                reasoning = ai_buy_explanation or "Buy conditions met"
            else:
                # For pairs without positions, show AI_BUY analysis
                # For pairs with positions, show combined analysis
                decision = "hold"
                if has_position:
                    confidence = max(ai_buy_score, ai_sell_score)
                    combined_parts = []
                    if ai_buy_explanation:
                        combined_parts.append(f"AI Buy: {ai_buy_explanation}")
                    if ai_sell_explanation:
                        combined_parts.append(f"AI Sell: {ai_sell_explanation}")
                    reasoning = " | ".join(combined_parts) if combined_parts else "Conditions not met"
                else:
                    # No position - show only BUY analysis (what we need to enter)
                    confidence = ai_buy_score
                    reasoning = ai_buy_explanation or "Waiting for buy conditions"

            log_signal_data = {
                **signal_data,
                "signal_type": decision,
                "reasoning": reasoning,
                "confidence": confidence,
            }

        if should_log_ai:
            pair_info = {"current_price": current_price}
            # Get open positions for this bot to link logs to positions
            from app.models import Position
            open_pos_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
            open_pos_result = await db.execute(open_pos_query)
            open_positions_list = list(open_pos_result.scalars().all())
            await monitor.log_ai_decision(db, bot, product_id, log_signal_data, pair_info, open_positions_list)
            logger.info(f"  📝 Logged AI decision for {product_id}")

        # Log indicator condition evaluations for indicator-based bots
        # This includes bots with AI indicators - they get BOTH AI logs AND indicator logs
        # Only log when conditions MATCH to reduce noise:
        # - Entry (base_order): log only when entry conditions are met AND bot has capacity
        # - DCA (safety_order): log only when we have a position AND DCA slots available AND DCA conditions are met
        # - Exit (take_profit): log only when we have a position AND exit conditions are met
        condition_details = signal_data.get("condition_details")
        if condition_details:
            has_position = existing_position is not None
            logged_any = False

            # Check if position has DCA slots available (for safety_order logging)
            dca_slots_available = False
            if has_position and existing_position:
                # Get max safety orders from frozen config or current bot config
                config = existing_position.strategy_config_snapshot or bot.strategy_config or {}
                max_safety_orders = config.get("max_safety_orders", 5)
                # Count completed safety orders (buy trades - 1 for base order)
                buy_trades = (
                    [t for t in existing_position.trades if t.side == "buy"]
                    if existing_position.trades else []
                )
                safety_orders_completed = max(0, len(buy_trades) - 1)
                dca_slots_available = safety_orders_completed < max_safety_orders

            # Log each phase that has conditions
            for phase, details in condition_details.items():
                if not details:  # Skip if no conditions for this phase
                    continue
                phase_signal_key = f"{phase}_signal"
                conditions_met = signal_data.get(phase_signal_key, False)

                # Skip DCA/Exit phases when there's no position (irrelevant)
                if not has_position and phase in ("safety_order", "take_profit"):
                    continue
                # Skip Entry phase when we already have a position (can't enter twice)
                if has_position and phase == "base_order":
                    continue
                # Skip DCA phase when no DCA slots available
                if phase == "safety_order" and not dca_slots_available:
                    continue

                # Log ALL evaluations (both passing and failing) for debugging
                await log_indicator_evaluation(
                    db=db,
                    bot_id=bot.id,
                    product_id=product_id,
                    phase=phase,
                    conditions_met=conditions_met,
                    conditions_detail=details,
                    indicators_snapshot=indicators,
                    current_price=current_price,
                )
                logged_any = True
            if logged_any:
                logger.info(f"  📊 Logged indicator evaluation for {product_id}")

        # Process each existing position for DCA/sell
        result = {"action": "none", "reason": "No signal"}
        for pos in all_pair_positions:
            # For each position, use ITS frozen config if available
            pos_strategy_config = (
                pos.strategy_config_snapshot.copy()
                if pos.strategy_config_snapshot
                else bot.strategy_config.copy()
            )
            pos_strategy_config["user_id"] = bot.user_id
            pos_strategy = StrategyRegistry.get_strategy(bot.strategy_type, pos_strategy_config)

            pos_engine = StrategyTradingEngine(
                db=db, exchange=monitor.exchange, bot=bot, strategy=pos_strategy, product_id=product_id,
            )
            pos_result = await pos_engine.process_signal(
                candles, current_price, pre_analyzed_signal=signal_data,
                candles_by_timeframe=candles_by_timeframe, position_override=pos,
            )
            logger.info(f"  Position #{pos.id} result: {pos_result['action']} - {pos_result['reason']}")
            # Keep track of most interesting result
            if pos_result.get("action") not in ("none", "hold"):
                result = pos_result

        # Check if a new simultaneous deal can be opened
        if (bot.is_active
                and same_pair_count > 0
                and same_pair_count < max_same_pair
                and all_positions_exhausted_safety_orders(all_pair_positions, max_safety)):
            # Open new simultaneous deal - pass position=None
            logger.info(f"  🔄 All {same_pair_count} position(s) exhausted SOs — evaluating new simultaneous deal")
            new_engine = StrategyTradingEngine(
                db=db, exchange=monitor.exchange, bot=bot, strategy=strategy, product_id=product_id,
            )
            new_result = await new_engine.process_signal(
                candles, current_price, pre_analyzed_signal=signal_data,
                candles_by_timeframe=candles_by_timeframe, position_override=None,
            )
            logger.info(f"  New simultaneous deal result: {new_result['action']} - {new_result['reason']}")
            if new_result.get("action") not in ("none", "hold"):
                result = new_result
        elif same_pair_count == 0:
            # No existing positions - normal flow (process_signal handles base order check)
            engine = StrategyTradingEngine(
                db=db, exchange=monitor.exchange, bot=bot, strategy=strategy, product_id=product_id,
            )
            result = await engine.process_signal(
                candles, current_price, pre_analyzed_signal=signal_data,
                candles_by_timeframe=candles_by_timeframe,
            )

        logger.info(f"  Result: {result['action']} - {result['reason']}")

        # Note: bot.last_signal_check is updated BEFORE processing starts (in monitor_loop)
        # to prevent race conditions where the same bot gets processed twice
        # Only commit if not in batch mode (batch mode commits once at the end)
        if commit:
            await db.commit()

        return result

    except Exception as e:
        logger.error(f"Error processing bot {bot.name}: {e}", exc_info=True)
        return {"error": str(e)}
