"""
Pair Processor for Multi-Bot Monitor

Handles processing of signals for a single bot/pair combination.
Extracted from MultiBotMonitor.process_bot_pair().

Phases:
  1. _resolve_strategy() - Get positions, resolve config, create strategy instance
  2. _fetch_market_data() - Fetch candles by timeframe (or use pre-fetched data)
  3. _analyze_signal() - Run strategy analysis (pre-analyzed, technical-only, or full)
  4. _log_signal_decisions() - Log AI decisions and indicator evaluations
  5. _execute_trades() - Process existing positions and open new deals
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bot, Position
from app.services.indicator_log_service import log_indicator_evaluation
from app.strategies import StrategyRegistry
from app.trading_engine_v2 import StrategyTradingEngine
from app.utils.candle_utils import get_timeframes_for_phases

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 1: Strategy Resolution
# ---------------------------------------------------------------------------


async def _resolve_strategy(
    db: AsyncSession, bot: Bot, product_id: str
) -> Tuple[Any, List[Position], Optional[Position], dict]:
    """
    Resolve the strategy instance and fetch open positions.

    Returns (strategy, all_pair_positions, existing_position, strategy_config).
    Raises ValueError if strategy type is unknown.
    """
    from app.trading_engine.position_manager import get_active_positions_for_pair

    all_pair_positions = await get_active_positions_for_pair(db, bot, product_id)
    existing_position = all_pair_positions[0] if all_pair_positions else None

    if existing_position and existing_position.strategy_config_snapshot:
        strategy_config = existing_position.strategy_config_snapshot.copy()
        logger.info(f"    Using FROZEN strategy config from position #{existing_position.id}")
    else:
        strategy_config = bot.strategy_config.copy()
        logger.info("    Using CURRENT bot strategy config")

        # Adjust budget percentages if splitting across pairs (only for new positions)
        # Skip when auto_calculate is on — it already receives per-position budget.
        if bot.split_budget_across_pairs and not strategy_config.get("auto_calculate_order_sizes", False):
            max_concurrent_deals = max(strategy_config.get("max_concurrent_deals", 1), 1)
            logger.info(f"    Splitting budget across {max_concurrent_deals} max concurrent deals")

            for pct_key in ("base_order_percentage", "safety_order_percentage", "max_btc_usage_percentage"):
                if pct_key in strategy_config:
                    original = strategy_config[pct_key]
                    strategy_config[pct_key] = original / max_concurrent_deals
                    label = pct_key.replace("_", " ").title()
                    logger.info(f"      {label}: {original}% → {strategy_config[pct_key]:.2f}%")

    strategy_config["user_id"] = bot.user_id
    strategy = StrategyRegistry.get_strategy(bot.strategy_type, strategy_config)

    return strategy, all_pair_positions, existing_position, strategy_config


# ---------------------------------------------------------------------------
# Phase 2: Market Data Fetching
# ---------------------------------------------------------------------------


async def _fetch_market_data(
    monitor, bot: Bot, product_id: str,
    existing_position: Optional[Position],
    all_pair_positions: List[Position],
    strategy_config: dict,
    pair_data: Optional[dict],
) -> Tuple[float, list, dict]:
    """
    Fetch or reuse market data (candles) for the pair.

    Returns (current_price, candles, candles_by_timeframe).
    """
    if pair_data:
        logger.info("    Using pre-fetched market data")
        current_price = pair_data.get("current_price", 0)
        candles = pair_data.get("candles", [])
        candles_by_timeframe = pair_data.get("candles_by_timeframe", {"FIVE_MINUTE": candles})
        return current_price, candles, candles_by_timeframe

    # Fetch candles to get reliable price
    candles = None
    candles_by_timeframe = {}

    temp_candles = await monitor.get_candles_cached(product_id, "FIVE_MINUTE", 100)
    if temp_candles and len(temp_candles) > 0:
        current_price = float(temp_candles[-1].get("close", 0))
        logger.info(f"    Current {product_id} price (from candles): {current_price:.8f}")
    else:
        logger.warning(f"    No candles available for {product_id}, using fallback ticker")
        current_price = await monitor.exchange.get_current_price(product_id)
        logger.info(f"    Current {product_id} price (from ticker): {current_price:.8f}")

    # For indicator-based strategies, fetch candles per-timeframe based on needed phases
    if bot.strategy_type in ("conditional_dca", "indicator_based"):
        candles, candles_by_timeframe = await _fetch_indicator_candles(
            monitor, bot, product_id, existing_position, all_pair_positions, strategy_config,
        )
    else:
        candles, candles_by_timeframe = await _fetch_legacy_candles(
            monitor, bot, product_id, candles, candles_by_timeframe, pair_data,
        )

    return current_price, candles, candles_by_timeframe


async def _fetch_indicator_candles(
    monitor, bot: Bot, product_id: str,
    existing_position: Optional[Position],
    all_pair_positions: List[Position],
    strategy_config: dict,
) -> Tuple[list, dict]:
    """Fetch candles for indicator-based strategies using phase-aware timeframes."""
    from app.trading_engine.position_manager import all_positions_exhausted_safety_orders

    max_same_pair = strategy_config.get("max_simultaneous_same_pair", 1)
    max_safety = strategy_config.get("max_safety_orders", 5)
    same_pair_count = len(all_pair_positions)

    # Determine which phases to check based on position status
    if existing_position:
        if (same_pair_count < max_same_pair
                and all_positions_exhausted_safety_orders(all_pair_positions, max_safety)):
            phases_to_check = ["base_order_conditions", "safety_order_conditions", "take_profit_conditions"]
            print(f"  📊 {same_pair_count} position(s), all SOs exhausted - checking entry + DCA + exit phases")
        else:
            phases_to_check = ["safety_order_conditions", "take_profit_conditions"]
            print("  📊 Open position detected - checking DCA + exit phases only")
    else:
        phases_to_check = ["base_order_conditions"]
        print("  📊 No position - checking entry phase only")

    timeframes_needed = get_timeframes_for_phases(bot.strategy_config, phases_to_check)
    print(f"  📊 Fetching candles for timeframes: {timeframes_needed} (phases: {phases_to_check})")

    lookback_map = {
        "ONE_MINUTE": 200, "THREE_MINUTE": 200, "FIVE_MINUTE": 200,
        "TEN_MINUTE": 150, "FIFTEEN_MINUTE": 150, "THIRTY_MINUTE": 100,
        "ONE_HOUR": 100, "TWO_HOUR": 100, "FOUR_HOUR": 100,
        "SIX_HOUR": 100, "ONE_DAY": 100,
    }

    candles_by_timeframe = {}
    for timeframe in timeframes_needed:
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
        return [], {}

    candles = list(candles_by_timeframe.values())[0]
    return candles, candles_by_timeframe


async def _fetch_legacy_candles(
    monitor, bot: Bot, product_id: str,
    candles: Optional[list], candles_by_timeframe: dict,
    pair_data: Optional[dict],
) -> Tuple[list, dict]:
    """Fetch candles for legacy (non-indicator-based) strategies."""
    timeframe = bot.strategy_config.get("timeframe", "FIVE_MINUTE")
    logger.info(f"  Using timeframe: {timeframe}")

    if not candles:
        candles = await monitor.get_candles_cached(
            product_id=product_id, granularity=timeframe, lookback_candles=100
        )

    if not candles:
        logger.warning(f"    No candles available for {product_id}")
        return [], {}

    if not candles_by_timeframe or len(candles_by_timeframe) == 0:
        candles_by_timeframe = {timeframe: candles}
    else:
        logger.info(
            f"  📊 Using pre-fetched candles_by_timeframe with"
            f" {len(candles_by_timeframe)} timeframes:"
            f" {list(candles_by_timeframe.keys())}"
        )

    return candles, candles_by_timeframe


# ---------------------------------------------------------------------------
# Phase 3: Signal Analysis
# ---------------------------------------------------------------------------


async def _analyze_signal(
    monitor, bot: Bot, product_id: str, strategy: Any,
    candles: list, current_price: float, candles_by_timeframe: dict,
    existing_position: Optional[Position], strategy_config: dict,
    pre_analyzed_signal: Optional[dict], skip_ai_analysis: bool,
) -> Optional[dict]:
    """
    Analyze market signal using the strategy.

    Returns signal_data dict or None.
    """
    if pre_analyzed_signal:
        logger.info("  Using pre-analyzed signal from batch")
        return pre_analyzed_signal

    cache_key = (bot.id, product_id)
    previous_indicators_from_cache = monitor._previous_indicators_cache.get(cache_key)

    if skip_ai_analysis:
        if bot.strategy_type in ("conditional_dca", "indicator_based"):
            print("  ⏭️  Technical check: Analyzing indicator-based signals")
            return await strategy.analyze_signal(
                candles, current_price, candles_by_timeframe,
                position=existing_position,
                previous_indicators_cache=previous_indicators_from_cache,
                db=None, user_id=bot.user_id, product_id=product_id
            )
        else:
            logger.info("  ⏭️  Technical check: Evaluating conditions with cached AI values")
            return await strategy.analyze_signal(
                candles, current_price,
                position=existing_position,
                previous_indicators_cache=previous_indicators_from_cache,
                db=None, user_id=bot.user_id, product_id=product_id,
                use_cached_ai=True,
            )
    else:
        if bot.strategy_type in ("conditional_dca", "indicator_based"):
            print("  📊 Analyzing indicator-based signals...")
            return await strategy.analyze_signal(
                candles, current_price, candles_by_timeframe,
                position=existing_position,
                previous_indicators_cache=previous_indicators_from_cache,
                db=None, user_id=bot.user_id, product_id=product_id
            )
        else:
            return await strategy.analyze_signal(
                candles, current_price,
                position=existing_position,
                previous_indicators_cache=previous_indicators_from_cache,
                db=None, user_id=bot.user_id, product_id=product_id
            )


def _check_synthetic_candle_threshold(signal_data: dict, strategy_config: dict, product_id: str) -> Optional[dict]:
    """Check if gap-filled candle percentage exceeds threshold. Returns skip-result or None."""
    max_synthetic_pct = strategy_config.get("max_synthetic_pct")
    if max_synthetic_pct is None or not signal_data or "indicators" not in signal_data:
        return None

    indicators_snap = signal_data["indicators"]
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
    return None


# ---------------------------------------------------------------------------
# Phase 4: Signal Logging
# ---------------------------------------------------------------------------


async def _log_signal_decisions(
    monitor, db: AsyncSession, bot: Bot, product_id: str,
    signal_data: dict, current_price: float,
    existing_position: Optional[Position], indicators: dict,
):
    """Log AI decisions and indicator condition evaluations."""
    await _log_ai_decision(monitor, db, bot, product_id, signal_data, current_price, existing_position, indicators)
    await _log_indicator_evaluations(db, bot, product_id, signal_data, current_price, existing_position, indicators)


async def _log_ai_decision(
    monitor, db: AsyncSession, bot: Bot, product_id: str,
    signal_data: dict, current_price: float,
    existing_position: Optional[Position], indicators: dict,
):
    """Log AI-based trading decisions to the database."""
    reasoning = signal_data.get("reasoning")
    ai_buy_explanation = indicators.get("ai_buy_explanation") if indicators else None
    ai_sell_explanation = indicators.get("ai_sell_explanation") if indicators else None

    should_log_ai = False
    log_signal_data = signal_data

    if reasoning and reasoning != "Technical-only check (no AI)":
        should_log_ai = True
    elif ai_buy_explanation or ai_sell_explanation:
        should_log_ai = True
        log_signal_data = _build_indicator_ai_log(signal_data, indicators, existing_position,
                                                  ai_buy_explanation, ai_sell_explanation)

    if should_log_ai:
        pair_info = {"current_price": current_price}
        open_pos_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
        open_pos_result = await db.execute(open_pos_query)
        open_positions_list = list(open_pos_result.scalars().all())
        await monitor.log_ai_decision(db, bot, product_id, log_signal_data, pair_info, open_positions_list)
        logger.info(f"  📝 Logged AI decision for {product_id}")


def _build_indicator_ai_log(
    signal_data: dict, indicators: dict, existing_position: Optional[Position],
    ai_buy_explanation: Optional[str], ai_sell_explanation: Optional[str],
) -> dict:
    """Build enriched signal data for indicator-based AI logging."""
    base_order = signal_data.get("base_order_signal", False)
    safety_order = signal_data.get("safety_order_signal", False)
    take_profit = signal_data.get("take_profit_signal", False)

    ai_buy_score = indicators.get("ai_buy_score", 0) or 0
    ai_sell_score = indicators.get("ai_sell_score", 0) or 0

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
            confidence = ai_buy_score
            reasoning = ai_buy_explanation or "Waiting for buy conditions"

    return {
        **signal_data,
        "signal_type": decision,
        "reasoning": reasoning,
        "confidence": confidence,
    }


async def _log_indicator_evaluations(
    db: AsyncSession, bot: Bot, product_id: str,
    signal_data: dict, current_price: float,
    existing_position: Optional[Position], indicators: dict,
):
    """Log indicator condition evaluations for indicator-based bots."""
    condition_details = signal_data.get("condition_details")
    if not condition_details:
        return

    has_position = existing_position is not None

    # Check if position has DCA slots available
    dca_slots_available = False
    if has_position and existing_position:
        config = existing_position.strategy_config_snapshot or bot.strategy_config or {}
        max_safety_orders = config.get("max_safety_orders", 5)
        buy_trades = (
            [t for t in existing_position.trades if t.side == "buy"]
            if existing_position.trades else []
        )
        safety_orders_completed = max(0, len(buy_trades) - 1)
        dca_slots_available = safety_orders_completed < max_safety_orders

    logged_any = False
    for phase, details in condition_details.items():
        if not details:
            continue
        # Skip irrelevant phases
        if not has_position and phase in ("safety_order", "take_profit"):
            continue
        if has_position and phase == "base_order":
            continue
        if phase == "safety_order" and not dca_slots_available:
            continue

        phase_signal_key = f"{phase}_signal"
        conditions_met = signal_data.get(phase_signal_key, False)
        await log_indicator_evaluation(
            db=db, bot_id=bot.id, product_id=product_id,
            phase=phase, conditions_met=conditions_met,
            conditions_detail=details, indicators_snapshot=indicators,
            current_price=current_price,
        )
        logged_any = True

    if logged_any:
        logger.info(f"  📊 Logged indicator evaluation for {product_id}")


# ---------------------------------------------------------------------------
# Phase 5: Trade Execution
# ---------------------------------------------------------------------------


async def _execute_trades(
    monitor, db: AsyncSession, bot: Bot, product_id: str, strategy: Any,
    candles: list, current_price: float, candles_by_timeframe: dict,
    signal_data: dict, all_pair_positions: List[Position],
    strategy_config: dict,
) -> dict:
    """Process existing positions for DCA/sell and open new deals if eligible."""
    from app.trading_engine.position_manager import all_positions_exhausted_safety_orders

    max_same_pair = strategy_config.get("max_simultaneous_same_pair", 1)
    max_safety = strategy_config.get("max_safety_orders", 5)
    same_pair_count = len(all_pair_positions)

    # Process each existing position for DCA/sell
    result = {"action": "none", "reason": "No signal"}
    for pos in all_pair_positions:
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
        if pos_result.get("action") not in ("none", "hold"):
            result = pos_result

    # Check if a new simultaneous deal can be opened
    if (bot.is_active
            and same_pair_count > 0
            and same_pair_count < max_same_pair
            and all_positions_exhausted_safety_orders(all_pair_positions, max_safety)):
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
        # No existing positions — normal flow
        engine = StrategyTradingEngine(
            db=db, exchange=monitor.exchange, bot=bot, strategy=strategy, product_id=product_id,
        )
        result = await engine.process_signal(
            candles, current_price, pre_analyzed_signal=signal_data,
            candles_by_timeframe=candles_by_timeframe,
        )

    return result


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


async def process_bot_pair(
    monitor, db: AsyncSession, bot: Bot, product_id: str,
    pre_analyzed_signal=None, pair_data=None, commit=True,
    skip_ai_analysis: bool = False
) -> Dict[str, Any]:
    """
    Process signals for a single bot/pair combination.

    Orchestrates five phases:
      1. Resolve strategy and fetch positions
      2. Fetch or reuse market data
      3. Analyze signal using strategy
      4. Log AI decisions and indicator evaluations
      5. Execute trades (DCA, sell, new deals)

    Args:
        monitor: MultiBotMonitor instance (provides exchange, caching, logging methods)
        db: Database session
        bot: Bot instance to process
        product_id: Trading pair to evaluate (e.g., "ETH-BTC")
        pre_analyzed_signal: Pre-analyzed signal from batch analysis (optional)
        pair_data: Pre-fetched market data from batch analysis (optional)
        commit: Whether to commit the database session after processing (default: True)
        skip_ai_analysis: If True, skip AI analysis and check only technical conditions

    Returns:
        Result dictionary with action/signal info
    """
    try:
        logger.info(f"  Evaluating pair: {product_id}")

        # Phase 1: Resolve strategy
        try:
            strategy, all_pair_positions, existing_position, strategy_config = await _resolve_strategy(
                db, bot, product_id
            )
        except ValueError as e:
            logger.error(f"Unknown strategy: {bot.strategy_type}")
            return {"error": str(e)}

        # Phase 2: Fetch market data
        current_price, candles, candles_by_timeframe = await _fetch_market_data(
            monitor, bot, product_id, existing_position, all_pair_positions, strategy_config, pair_data,
        )
        # Only fail on missing candles when we actually needed to fetch them
        # (pair_data may provide empty candles intentionally when using pre-analyzed signals)
        if not candles and not pair_data:
            return {"error": "No candles available"}

        # Phase 3: Analyze signal
        signal_data = await _analyze_signal(
            monitor, bot, product_id, strategy,
            candles, current_price, candles_by_timeframe,
            existing_position, strategy_config,
            pre_analyzed_signal, skip_ai_analysis,
        )

        # Update previous_indicators cache
        if signal_data and "indicators" in signal_data:
            cache_key = (bot.id, product_id)
            monitor._previous_indicators_cache[cache_key] = signal_data["indicators"].copy()
            logger.debug(f"    Updated previous_indicators cache for {cache_key}")

        # Check synthetic candle threshold
        skip_result = _check_synthetic_candle_threshold(signal_data, strategy_config, product_id)
        if skip_result:
            return skip_result

        # Commit position changes (e.g., previous_indicators for crossing detection)
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
        logger.info(f"  🔔 Signal detected: {signal_data.get('signal_type')}")

        # Phase 4: Log signal decisions
        indicators = signal_data.get("indicators", {})
        await _log_signal_decisions(
            monitor, db, bot, product_id, signal_data, current_price, existing_position, indicators,
        )

        # Phase 5: Execute trades
        result = await _execute_trades(
            monitor, db, bot, product_id, strategy,
            candles, current_price, candles_by_timeframe,
            signal_data, all_pair_positions, strategy_config,
        )

        logger.info(f"  Result: {result['action']} - {result['reason']}")

        if commit:
            await db.commit()

        return result

    except Exception as e:
        logger.error(f"Error processing bot {bot.name}: {e}", exc_info=True)
        return {"error": str(e)}
