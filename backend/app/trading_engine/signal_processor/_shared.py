"""Shared helpers for the signal_processor package.

Internal module — consumers should import through app.trading_engine.signal_processor.
Split out of the original monolithic signal_processor.py as part of
code-quality Phase 5.1.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.indicator_calculator import IndicatorCalculator
from app.models import OrderHistory, Position, Signal
from app.trading_engine.sell_executor import execute_sell
from app.trading_engine.trade_context import TradeContext

logger = logging.getLogger(__name__)

# Module-level singleton — IndicatorCalculator is stateless, no need to re-instantiate per call
_indicator_calc = IndicatorCalculator()


async def _record_signal(
    db: AsyncSession,
    position: "Position",
    signal_type: str,
    action_taken: str,
    reason: str,
    current_price: float,
    signal_data: Optional[Dict[str, Any]] = None,
) -> Signal:
    """Create and persist a Signal record.

    Deduplicates the repeated Signal-creation pattern found throughout
    the buy/sell decision functions.
    """
    signal = Signal(
        position_id=position.id,
        timestamp=datetime.utcnow(),
        signal_type=signal_type,
        macd_value=(signal_data or {}).get("macd_value", 0),
        macd_signal=(signal_data or {}).get("macd_signal", 0),
        macd_histogram=(signal_data or {}).get("macd_histogram", 0),
        price=current_price,
        action_taken=action_taken,
        reason=reason,
    )
    db.add(signal)
    await db.commit()
    return signal


async def _is_duplicate_failed_order(
    db: AsyncSession, bot_id: int, product_id: str, trade_type: str,
    error_message: str, position: Optional["Position"] = None,
) -> bool:
    """Check if the most recent failed order for this deal+trade_type has the same error."""
    query = (
        select(OrderHistory.error_message)
        .where(
            OrderHistory.bot_id == bot_id,
            OrderHistory.product_id == product_id,
            OrderHistory.trade_type == trade_type,
            OrderHistory.status == "failed",
        )
    )
    if position is not None:
        query = query.where(OrderHistory.position_id == position.id)
    else:
        query = query.where(OrderHistory.position_id.is_(None))
    result = await db.execute(query.order_by(OrderHistory.timestamp.desc()).limit(1))
    last_error = result.scalar_one_or_none()
    return last_error == error_message

# Cache previous market context for crossing detection (bot_id_product_id -> context)
_previous_market_context: Dict[str, Dict[str, Any]] = {}


def _calculate_market_context_with_indicators(
    candles: List[Dict[str, Any]],
    current_price: float,
    candles_by_timeframe: Optional[Dict[str, List[Dict[str, Any]]]] = None
) -> Dict[str, Any]:
    """
    Calculate market context with technical indicators for custom sell conditions

    Args:
        candles: Default candles (FIVE_MINUTE) for backward compatibility
        current_price: Current market price
        candles_by_timeframe: Optional dict of {timeframe: candles} for multi-timeframe support

    Returns a dict with timeframe-prefixed keys like:
    - THREE_MINUTE_bb_percent, THREE_MINUTE_bb_upper_20_2, etc.
    - FIVE_MINUTE_bb_percent, FIVE_MINUTE_bb_upper_20_2, etc.
    """
    result = {
        "price": current_price,
        "rsi": 50.0,
        "rsi_14": 50.0,
        "macd": 0.0,
        "macd_signal": 0.0,
        "macd_histogram": 0.0,
        "macd_12_26_9": 0.0,
        "macd_signal_12_26_9": 0.0,
        "macd_histogram_12_26_9": 0.0,
        "bb_percent": 50.0,
    }

    calc = _indicator_calc

    # Build candles_by_timeframe if not provided (backward compatibility)
    if candles_by_timeframe is None:
        candles_by_timeframe = {"FIVE_MINUTE": candles} if candles else {}

    # Calculate indicators for each timeframe
    for timeframe, tf_candles in candles_by_timeframe.items():
        if not tf_candles or len(tf_candles) < 20:
            # Not enough data - set neutral defaults for this timeframe
            candle_count = len(tf_candles) if tf_candles else 0
            logger.debug(
                f"  📊 {timeframe}: Not enough candles ({candle_count} < 20), using defaults"
            )
            result[f"{timeframe}_bb_percent"] = 50.0
            result[f"{timeframe}_bb_upper_20_2"] = current_price
            result[f"{timeframe}_bb_lower_20_2"] = current_price
            result[f"{timeframe}_bb_middle_20_2"] = current_price
            result[f"{timeframe}_price"] = current_price
            continue

        try:
            prices = [float(c.get("close", c.get("price", 0))) for c in tf_candles]

            # Calculate Bollinger Bands (20 period, 2 std dev)
            bb_upper, bb_middle, bb_lower = calc.calculate_bollinger_bands(prices, period=20, std_dev=2.0)

            # Calculate BB% = (price - lower) / (upper - lower) * 100
            if bb_upper and bb_lower and bb_upper != bb_lower:
                bb_percent = ((current_price - bb_lower) / (bb_upper - bb_lower)) * 100
            else:
                bb_percent = 50.0

            # Use defaults if calculation failed
            if bb_upper is None:
                bb_upper, bb_middle, bb_lower = current_price, current_price, current_price
                bb_percent = 50.0

            # Add timeframe-prefixed keys
            result[f"{timeframe}_bb_percent"] = bb_percent
            result[f"{timeframe}_bb_upper_20_2"] = bb_upper
            result[f"{timeframe}_bb_lower_20_2"] = bb_lower
            result[f"{timeframe}_bb_middle_20_2"] = bb_middle
            result[f"{timeframe}_price"] = current_price
            logger.debug(f"  📊 {timeframe}: BB%={bb_percent:.1f}%, upper={bb_upper:.8f}, lower={bb_lower:.8f}")

            # Also set non-prefixed bb_percent from the primary timeframe (first one)
            if "bb_percent" not in result or result["bb_percent"] == 50.0:
                result["bb_percent"] = bb_percent
                result["bb_upper_20_2"] = bb_upper
                result["bb_lower_20_2"] = bb_lower
                result["bb_middle_20_2"] = bb_middle

            # Calculate RSI and MACD from this timeframe (use first available)
            if result["rsi"] == 50.0 and len(prices) >= 15:
                rsi = calc.calculate_rsi(prices, period=14)
                if rsi is not None:
                    result["rsi"] = rsi
                    result["rsi_14"] = rsi

            if result["macd"] == 0.0:
                macd_line, signal_line, histogram = calc.calculate_macd(prices, 12, 26, 9)
                if macd_line is not None:
                    result["macd"] = macd_line
                    result["macd_signal"] = signal_line
                    result["macd_histogram"] = histogram
                    result["macd_12_26_9"] = macd_line
                    result["macd_signal_12_26_9"] = signal_line
                    result["macd_histogram_12_26_9"] = histogram

        except Exception as e:
            logger.warning(f"Error calculating {timeframe} indicators: {e}")
            result[f"{timeframe}_bb_percent"] = 50.0
            result[f"{timeframe}_bb_upper_20_2"] = current_price
            result[f"{timeframe}_bb_lower_20_2"] = current_price
            result[f"{timeframe}_bb_middle_20_2"] = current_price
            result[f"{timeframe}_price"] = current_price

    return result


_POSITION_NOT_SET = object()  # sentinel to distinguish None from not-provided


async def _handle_ai_failsafe(
    ctx: TradeContext, position: Position,
) -> Optional[Dict[str, Any]]:
    """Handle AI failsafe sell when signal analysis returned None.

    Only applies to ai_autonomous bots with an existing position.
    Returns a result dict if failsafe was triggered, None otherwise.
    """
    db, exchange, trading_client = ctx.db, ctx.exchange, ctx.trading_client
    bot, product_id, current_price, strategy = ctx.bot, ctx.product_id, ctx.current_price, ctx.strategy
    if bot.strategy_type != "ai_autonomous" or position is None:
        return None

    logger.warning(f"  🛡️ AI analysis failed for {product_id} - checking failsafe for position #{position.id}")

    # Check if failsafe should sell to protect profit
    should_sell_failsafe, failsafe_reason = await strategy.should_sell_failsafe(position, current_price)

    if not should_sell_failsafe:
        logger.info(f"  Failsafe checked but not triggered: {failsafe_reason}")
        return None

    logger.warning(f"  🛡️ FAILSAFE ACTIVATED: {failsafe_reason}")

    # Check if limit close order already pending
    if position.closing_via_limit:
        logger.warning(
            f"  ⚠️ Position #{position.id} already has a pending limit close order, skipping failsafe sell"
        )
        return {
            "action": "failsafe_limit_close_already_pending",
            "reason": f"Limit order already pending (order_id: {position.limit_close_order_id})",
            "position_id": position.id,
        }

    # Execute sell with limit order (mark price → bid fallback after 60s)
    # This uses the existing execute_sell function which handles limit orders
    trade, profit_quote, profit_pct = await execute_sell(
        db=db,
        exchange=exchange,
        trading_client=trading_client,
        bot=bot,
        product_id=product_id,
        position=position,
        current_price=current_price,
        signal_data={
            "signal_type": "sell",
            "confidence": 100,
            "reasoning": failsafe_reason,
        },
    )

    # If trade is None, a limit order was placed - position stays open
    if trade is None:
        logger.warning(
            f"  🛡️ Failsafe limit close order placed for position #{position.id},"
            " waiting for fill"
        )
        return {
            "action": "failsafe_limit_close_pending",
            "reason": failsafe_reason,
            "limit_order_placed": True,
            "position_id": position.id,
        }

    # Record signal for market sell
    await _record_signal(db, position, "sell", "sell", failsafe_reason, current_price)

    logger.warning(f"  🛡️ FAILSAFE SELL COMPLETED: Profit protected at {profit_pct:.2f}%")

    return {
        "action": "failsafe_sell",
        "reason": failsafe_reason,
        "signal": None,
        "trade": trade,
        "position": position,
        "profit_quote": profit_quote,
        "profit_percentage": profit_pct,
    }


async def _calculate_budget(
    ctx: TradeContext, position: Optional[Position],
    quote_currency: str, aggregate_value: Optional[float],
) -> tuple:
    """Calculate budget allocation for the bot.

    Returns (quote_balance, aggregate_value) tuple.
    """
    db, exchange, trading_client = ctx.db, ctx.exchange, ctx.trading_client
    bot, product_id = ctx.bot, ctx.product_id
    logger.debug(f"Bot budget_percentage: {bot.budget_percentage}%, quote_currency: {quote_currency}")
    if bot.budget_percentage > 0:
        # Bot uses percentage-based budgeting - calculate aggregate value
        # CRITICAL: Only considers assets in this bot's quote currency market
        # (e.g., USD bot gets 20% of USD only, not USDC or BTC)
        aggregate_value = await exchange.calculate_market_budget(
            quote_currency, bypass_cache=True
        )
        logger.debug(f"Aggregate {quote_currency} value: {aggregate_value}")
        logger.info(f"  💰 Aggregate {quote_currency} value: {aggregate_value}")

    reserved_balance = bot.get_reserved_balance(aggregate_value)
    logger.debug(f"Reserved balance (total bot budget): {reserved_balance:.8f}")
    if reserved_balance > 0:
        # Check if budget should be split across concurrent deals
        max_concurrent_deals = max(bot.strategy_config.get("max_concurrent_deals", 1), 1)

        # Only split budget if split_budget_across_pairs is enabled
        # (deal-based: each deal gets full budget by default)
        if bot.split_budget_across_pairs:
            per_position_budget = reserved_balance / max_concurrent_deals
        else:
            per_position_budget = reserved_balance

        # Calculate how much is available for THIS position (per-position budget - already spent in this position)
        from sqlalchemy import func as sa_func
        sum_result = await db.execute(
            select(sa_func.coalesce(sa_func.sum(Position.total_quote_spent), 0.0)).where(
                Position.bot_id == bot.id, Position.status == "open", Position.product_id == product_id
            )
        )
        total_in_positions = sum_result.scalar()
        quote_balance = per_position_budget - total_in_positions

        # For safety orders (position already exists), use the position's own allocated budget
        # instead of pair-level budget which can over-subtract when multiple positions share a pair
        if position and position.max_quote_allowed:
            quote_balance = position.max_quote_allowed - position.total_quote_spent

        split_mode = "SPLIT" if bot.split_budget_across_pairs else "FULL"
        if bot.budget_percentage > 0:
            logger.info(
                f"  💰 Bot budget ({split_mode}):"
                f" {bot.budget_percentage}% of aggregate ({reserved_balance:.8f}),"
                f" Max deals: {max_concurrent_deals},"
                f" Per-position: {per_position_budget:.8f},"
                f" In positions: {total_in_positions:.8f},"
                f" Available: {quote_balance:.8f}"
            )
        else:
            logger.info(
                f"  💰 Bot reserved balance ({split_mode}): {reserved_balance},"
                f" Max deals: {max_concurrent_deals},"
                f" Per-position: {per_position_budget:.8f},"
                f" In positions: {total_in_positions},"
                f" Available: {quote_balance}"
            )
    else:
        # No reserved balance - use total portfolio balance (backward compatibility)
        quote_balance = await trading_client.get_quote_balance(product_id)
        logger.info(f"  💰 Using total portfolio balance: {quote_balance}")

    return quote_balance, aggregate_value


async def calculate_soft_ceiling(
    ctx: TradeContext, aggregate_value: float,
) -> int:
    """Calculate the 'soft ceiling' for concurrent deals based on budget.

    Determines how many deals the bot can safely open while ensuring every deal
    (including all safety orders) can meet the exchange's minimum order size
    for the 'most expensive' coin in the bot's selected pairs.
    """
    bot, strategy, exchange = ctx.bot, ctx.strategy, ctx.exchange
    if not bot.strategy_config.get("enable_soft_ceiling", False):
        return strategy.config.get("max_concurrent_deals", 1)

    # 1. Total bot budget
    total_budget = bot.get_reserved_balance(aggregate_value)
    if total_budget <= 0:
        return 1

    # 2. Get DCA multiplier (total capital needed for 1 full deal cycle relative to base order)
    from app.strategies.safety_order_calculator import get_total_multiplier
    multiplier = get_total_multiplier(strategy.config)

    # 3. Find the largest minimum order size among ALL selected pairs
    # (The 'worst case' coin that dictates our ceiling)
    from app.order_validation import get_product_minimums
    max_min_quote = 0.0
    product_ids = bot.product_ids or [bot.product_id]

    for pid in product_ids:
        try:
            min_info = await get_product_minimums(exchange, pid)
            min_quote = float(min_info.get("quote_min_size", 0.0001))
            if min_quote > max_min_quote:
                max_min_quote = min_quote
        except Exception as e:
            logger.warning(f"Failed to get minimums for {pid} during soft ceiling calc: {e}")

    if max_min_quote <= 0:
        max_min_quote = 1.0  # Fallback for USD pairs

    # 4. Calculate required budget for ONE deal of the 'worst case' coin
    # Each base/safety order must be at least max_min_quote.
    # In auto-calculate mode, they are roughly equal if scales are 1.0.
    # Safe estimate: 1 deal needs (max_min_quote * multiplier)
    required_per_deal = max_min_quote * multiplier

    # 5. Effective max deals = Total Budget / Required per deal
    import math
    soft_max = math.floor(total_budget / required_per_deal)

    # 6. Clamp between 1 and user-specified max
    user_max = strategy.config.get("max_concurrent_deals", 1)
    effective_max = max(1, min(soft_max, user_max))

    logger.info(
        f"  🏠 Soft Ceiling: budget={total_budget:.2f}, "
        f"min_req={max_min_quote:.2f}, mult={multiplier:.1f}, "
        f"calc_max={soft_max}, user_max={user_max} -> result={effective_max}"
    )

    return effective_max
