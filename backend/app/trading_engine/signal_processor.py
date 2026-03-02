"""
Signal processing and trading decision orchestration
Coordinates buy/sell decisions based on strategy analysis
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.currency_utils import format_with_usd, get_quote_currency
from app.exchange_clients.base import ExchangeClient
from app.indicator_calculator import IndicatorCalculator
from app.models import BlacklistedCoin, Bot, OrderHistory, Position, Signal
from app.services.indicator_log_service import log_indicator_evaluation
from app.strategies import TradingStrategy
from app.trading_client import TradingClient
from app.trading_engine.book_depth_guard import check_buy_slippage, check_sell_slippage
from app.trading_engine.buy_executor import execute_buy, execute_buy_close_short
from app.trading_engine.trade_context import TradeContext
from app.trading_engine.order_logger import log_order_to_history, save_ai_log, OrderLogEntry
from app.trading_engine.perps_executor import execute_perps_close, execute_perps_open
from app.trading_engine.position_manager import create_position, get_active_position, get_open_positions_count
from app.trading_engine.sell_executor import execute_sell, execute_sell_short

logger = logging.getLogger(__name__)


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

    calc = IndicatorCalculator()

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
    print(f"🔍 Bot budget_percentage: {bot.budget_percentage}%, quote_currency: {quote_currency}")
    if bot.budget_percentage > 0:
        # Bot uses percentage-based budgeting - calculate aggregate value
        # CRITICAL: Only considers assets in this bot's quote currency market
        # (e.g., USD bot gets 20% of USD only, not USDC or BTC)
        aggregate_value = await exchange.calculate_aggregate_quote_value(
            quote_currency, bypass_cache=True
        )
        print(f"🔍 Aggregate {quote_currency} value: {aggregate_value}")
        logger.info(f"  💰 Aggregate {quote_currency} value: {aggregate_value}")

    reserved_balance = bot.get_reserved_balance(aggregate_value)
    print(f"🔍 Reserved balance (total bot budget): {reserved_balance:.8f}")
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
        query = select(Position).where(
            Position.bot_id == bot.id, Position.status == "open", Position.product_id == product_id
        )
        result = await db.execute(query)
        open_positions = result.scalars().all()

        total_in_positions = sum(p.total_quote_spent for p in open_positions)
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


async def _decide_buy(
    ctx: TradeContext, signal_data: Dict[str, Any],
    position: Optional[Position], quote_balance: float,
    aggregate_value: Optional[float],
) -> tuple:
    """Decide whether to buy, including all checks (max deals, cooldown, blacklist).

    Returns (should_buy, quote_amount, buy_reason) tuple.
    """
    db, bot, strategy = ctx.db, ctx.bot, ctx.strategy
    product_id, current_price = ctx.product_id, ctx.current_price
    should_buy = False
    quote_amount = 0
    buy_reason = ""

    print(f"🔍 Bot active: {bot.is_active}, Position exists: {position is not None}")
    logger.info(f"  🤖 Bot active: {bot.is_active}, Position exists: {position is not None}")

    if bot.is_active:
        # Skip stable/pegged pairs (layer-2 safety check)
        if position is None:
            skip_stable = bot.strategy_config.get("skip_stable_pairs", True) if bot.strategy_config else True
            if skip_stable:
                from app.services.delisted_pair_monitor import is_stable_pair
                if is_stable_pair(product_id):
                    return False, 0, f"{product_id} is a stable/pegged pair (skipped)"

        # Check max concurrent deals limit
        if position is None:  # Only check when considering opening a NEW position
            open_positions_count = await get_open_positions_count(db, bot)
            max_deals = strategy.config.get("max_concurrent_deals", 1)
            print(f"🔍 Open positions: {open_positions_count}/{max_deals}")

            if open_positions_count >= max_deals:
                should_buy = False
                buy_reason = f"Max concurrent deals limit reached ({open_positions_count}/{max_deals})"
                print(f"🔍 Should buy: FALSE - {buy_reason}")
            else:
                # Check deal cooldown for this pair
                deal_cooldown = strategy.config.get("deal_cooldown_seconds", 0) or 0
                if deal_cooldown > 0:
                    cooldown_cutoff = datetime.utcnow() - timedelta(seconds=deal_cooldown)
                    recent_close_query = select(Position).where(
                        Position.bot_id == bot.id,
                        Position.product_id == product_id,
                        Position.status == "closed",
                        Position.closed_at >= cooldown_cutoff
                    )
                    recent_result = await db.execute(recent_close_query)
                    recently_closed = recent_result.scalars().first()
                    if recently_closed:
                        elapsed = (datetime.utcnow() - recently_closed.closed_at).total_seconds()
                        remaining = deal_cooldown - elapsed
                        should_buy = False
                        buy_reason = f"Deal cooldown active for {product_id} ({int(remaining)}s remaining)"
                        print(f"🔍 Should buy: FALSE - {buy_reason}")
                        logger.info(f"  ⏳ {buy_reason}")

                # Check if coin is blacklisted before considering a buy (skip if cooldown blocked)
                if not buy_reason:
                    base_symbol = product_id.split("-")[0]  # "ETH-BTC" -> "ETH"

                    # Check for user-specific override first, then fall back to global
                    user_override_query = select(BlacklistedCoin).where(
                        BlacklistedCoin.symbol == base_symbol,
                        BlacklistedCoin.user_id == bot.user_id,
                    )
                    user_override_result = await db.execute(user_override_query)
                    user_override_entry = user_override_result.scalars().first()

                    if user_override_entry:
                        blacklisted_entry = user_override_entry
                    else:
                        global_query = select(BlacklistedCoin).where(
                            BlacklistedCoin.symbol == base_symbol,
                            BlacklistedCoin.user_id.is_(None),
                        )
                        global_result = await db.execute(global_query)
                        blacklisted_entry = global_result.scalars().first()

                    if blacklisted_entry:
                        # Determine coin's category from reason prefix
                        reason = blacklisted_entry.reason or ''
                        if reason.startswith('[APPROVED]'):
                            coin_category = 'APPROVED'
                        elif reason.startswith('[BORDERLINE]'):
                            coin_category = 'BORDERLINE'
                        elif reason.startswith('[QUESTIONABLE]'):
                            coin_category = 'QUESTIONABLE'
                        elif reason.startswith('[MEME]'):
                            coin_category = 'MEME'
                        else:
                            coin_category = 'BLACKLISTED'

                        # Get allowed categories from bot's strategy_config (not global settings)
                        allowed_categories = ['APPROVED']  # Default
                        if bot.strategy_config and bot.strategy_config.get('allowed_categories'):
                            allowed_categories = bot.strategy_config['allowed_categories']

                        if coin_category in allowed_categories:
                            # Category is allowed to trade
                            print(f"🔍 {base_symbol} is {coin_category} (allowed): {reason}")
                            logger.info(f"  ✅ {coin_category}: {base_symbol} - allowed to trade")
                            agg_str = (
                                f"{aggregate_value:.8f}" if aggregate_value is not None else "None"
                            )
                            print(
                                f"🔍 Calling strategy.should_buy() with"
                                f" quote_balance={quote_balance:.8f}, aggregate={agg_str}"
                            )
                            should_buy, quote_amount, buy_reason = await strategy.should_buy(
                                signal_data, position, quote_balance,
                                aggregate_value=aggregate_value
                            )
                            amt = quote_amount if quote_amount else 0
                            print(
                                f"🔍 Should buy result: {should_buy},"
                                f" amount: {amt:.8f}, reason: {buy_reason}"
                            )
                        else:
                            should_buy = False
                            category_tag = f'[{coin_category}] '
                            buy_reason = (
                                f"{base_symbol} is {coin_category}:"
                                f" {reason.replace(category_tag, '')}"
                            )
                            print(f"🔍 Should buy: FALSE - {buy_reason}")
                            logger.info(f"  🚫 {coin_category} (blocked): {buy_reason}")
                    else:
                        agg_str = (
                            f"{aggregate_value:.8f}" if aggregate_value is not None else "None"
                        )
                        print(
                            f"🔍 Calling strategy.should_buy() with"
                            f" quote_balance={quote_balance:.8f}, aggregate={agg_str}"
                        )
                        should_buy, quote_amount, buy_reason = await strategy.should_buy(
                            signal_data, position, quote_balance,
                            aggregate_value=aggregate_value
                        )
                        amt = quote_amount if quote_amount else 0
                        print(
                            f"🔍 Should buy result: {should_buy},"
                            f" amount: {amt:.8f}, reason: {buy_reason}"
                        )

                        # Log budget blockers to indicator_logs so they show in GUI
                        if not should_buy and ("insufficient" in buy_reason.lower() or "budget" in buy_reason.lower()):
                            await log_indicator_evaluation(
                                db=db,
                                bot_id=bot.id,
                                product_id=product_id,
                                phase="budget_check",
                                conditions_met=False,
                                conditions_detail=[{
                                    "type": "budget",
                                    "indicator": "Available Balance",
                                    "operator": "sufficient_for",
                                    "threshold": quote_amount if quote_amount else 0,
                                    "actual_value": quote_balance,
                                    "result": False,
                                    "reason": buy_reason
                                }],
                                indicators_snapshot=signal_data.get("indicators", {}),
                                current_price=current_price
                            )
                            if not await _is_duplicate_failed_order(db, bot.id, product_id, "initial", buy_reason):
                                await log_order_to_history(
                                    db=db, bot=bot, position=None,
                                    entry=OrderLogEntry(
                                        product_id=product_id, side="BUY", order_type="MARKET",
                                        trade_type="initial", quote_amount=0.0,
                                        price=current_price, status="failed",
                                        error_message=buy_reason,
                                    ),
                                )
                                await db.commit()
        else:
            # Position already exists for this pair - check for DCA
            should_buy, quote_amount, buy_reason = await strategy.should_buy(
                signal_data, position, quote_balance,
                aggregate_value=aggregate_value
            )

            # Log budget blockers to indicator_logs so they show in GUI
            if not should_buy and ("insufficient" in buy_reason.lower() or "budget" in buy_reason.lower()):
                await log_indicator_evaluation(
                    db=db,
                    bot_id=bot.id,
                    product_id=product_id,
                    phase="budget_check_dca",
                    conditions_met=False,
                    conditions_detail=[{
                        "type": "budget",
                        "indicator": "Available Balance",
                        "operator": "sufficient_for",
                        "threshold": quote_amount if quote_amount else 0,
                        "actual_value": quote_balance,
                        "result": False,
                        "reason": buy_reason
                    }],
                    indicators_snapshot=signal_data.get("indicators", {}),
                    current_price=current_price
                )
                is_dup = await _is_duplicate_failed_order(
                    db, bot.id, product_id, "safety_order",
                    buy_reason, position
                )
                if not is_dup:
                    await log_order_to_history(
                        db=db, bot=bot, position=position,
                        entry=OrderLogEntry(
                            product_id=product_id, side="BUY", order_type="MARKET",
                            trade_type="safety_order", quote_amount=0.0,
                            price=current_price, status="failed",
                            error_message=buy_reason,
                        ),
                    )
                    await db.commit()
    else:
        # Bot is stopped - don't open new positions, but still check DCA for existing positions
        if position is None:
            buy_reason = "Bot is stopped - not opening new positions"
        else:
            # Still check DCA conditions for existing positions even when stopped
            should_buy, quote_amount, buy_reason = await strategy.should_buy(
                signal_data, position, quote_balance,
                aggregate_value=aggregate_value
            )
            if not should_buy:
                buy_reason = f"Bot stopped, DCA check: {buy_reason}"

                # Log budget blockers to indicator_logs so they show in GUI (even when bot stopped)
                if "insufficient" in buy_reason.lower() or "budget" in buy_reason.lower():
                    await log_indicator_evaluation(
                        db=db,
                        bot_id=bot.id,
                        product_id=product_id,
                        phase="budget_check_dca",
                        conditions_met=False,
                        conditions_detail=[{
                            "type": "budget",
                            "indicator": "Available Balance",
                            "operator": "sufficient_for",
                            "threshold": quote_amount if quote_amount else 0,
                            "actual_value": quote_balance,
                            "result": False,
                            "reason": buy_reason
                        }],
                        indicators_snapshot=signal_data.get("indicators", {}),
                        current_price=current_price
                    )
                    is_dup = await _is_duplicate_failed_order(
                        db, bot.id, product_id, "safety_order",
                        buy_reason, position
                    )
                    if not is_dup:
                        await log_order_to_history(
                            db=db, bot=bot, position=position,
                            entry=OrderLogEntry(
                                product_id=product_id, side="BUY", order_type="MARKET",
                                trade_type="safety_order", quote_amount=0.0,
                                price=current_price, status="failed",
                                error_message=buy_reason,
                            ),
                        )
                        await db.commit()

    return should_buy, quote_amount, buy_reason


async def _execute_buy_trade(
    ctx: TradeContext, position: Optional[Position],
    quote_amount: float, quote_balance: float,
    signal_data: Dict[str, Any], aggregate_value: Optional[float],
    buy_reason: str,
) -> Optional[Dict[str, Any]]:
    """Execute buy trade (initial or DCA), handling position creation and routing.

    Returns a result dict if a buy was executed (or failed), None should not happen
    since this is only called when should_buy is True.
    """
    db, exchange, trading_client = ctx.db, ctx.exchange, ctx.trading_client
    bot, product_id, current_price = ctx.bot, ctx.product_id, ctx.current_price
    # Get BTC/USD price for logging
    try:
        btc_usd_price = await exchange.get_btc_usd_price()
    except Exception:
        btc_usd_price = None

    quote_formatted = format_with_usd(quote_amount, product_id, btc_usd_price)
    logger.info(f"  💰 BUY DECISION: will buy {quote_formatted} worth of {product_id}")

    # Determine trade type
    is_new_position = position is None
    trade_type = "initial" if is_new_position else "dca"

    # Check if this is a short order (bidirectional DCA)
    direction = signal_data.get("direction", "long")
    is_short = direction == "short"

    if is_new_position:
        action_verb = "SELL" if is_short else "BUY"
        logger.info(
            f"  🔨 Executing {trade_type} {action_verb} order FIRST"
            " (position will be created after success)..."
        )
    else:
        action_verb = "sell" if is_short else "buy"
        logger.info(f"  🔨 Executing {trade_type} {action_verb} order for existing position...")

    # Execute order FIRST - don't create position until we know trade succeeds
    try:
        # For new positions, we need to create position for the trade to reference
        # BUT we do it in a transaction that will rollback if trade fails
        if is_new_position:
            logger.info("  📝 Creating position (will commit only if trade succeeds)...")

            # Extract bull_flag pattern data if present (for pattern-based TP/SL)
            pattern_data = None
            indicators = signal_data.get("indicators", {}) if signal_data else {}
            if indicators.get("bull_flag") == 1:
                pattern_data = {
                    "entry_price": indicators.get("bull_flag_entry"),
                    "stop_loss": indicators.get("bull_flag_stop"),
                    "take_profit_target": indicators.get("bull_flag_target"),
                    "pattern_type": "bull_flag",
                }
                logger.info(
                    f"  🎯 Bull flag pattern detected - using pattern targets:"
                    f" SL={pattern_data['stop_loss']:.4f},"
                    f" TP={pattern_data['take_profit_target']:.4f}"
                )

            position = await create_position(
                db, exchange, bot, product_id, quote_balance, quote_amount, aggregate_value,
                pattern_data=pattern_data,
                direction=direction  # Pass direction to position
            )
            logger.info(f"  ✅ Position created: ID={position.id} direction={direction} (pending trade execution)")

        # Route perps bots to perps executor
        if getattr(bot, 'market_type', 'spot') == 'perps':
            perps_config = bot.strategy_config or {}
            perps_leverage = perps_config.get("leverage", 1)
            perps_margin = perps_config.get("margin_type", "CROSS")
            perps_tp_pct = perps_config.get("default_tp_pct")
            perps_sl_pct = perps_config.get("default_sl_pct")
            perps_side = "SELL" if is_short else "BUY"

            # Get the underlying CoinbaseClient from the exchange adapter
            coinbase_client = getattr(exchange, '_client', None) or getattr(exchange, 'client', None)
            if coinbase_client is None:
                logger.error("Cannot get CoinbaseClient for perps order")
                raise RuntimeError("Perps trading requires CoinbaseClient")

            position, trade = await execute_perps_open(
                db=db,
                client=coinbase_client,
                bot=bot,
                product_id=product_id,
                side=perps_side,
                size_usdc=quote_amount,
                current_price=current_price,
                leverage=perps_leverage,
                margin_type=perps_margin,
                tp_pct=perps_tp_pct,
                sl_pct=perps_sl_pct,
                user_id=bot.user_id,
            )

            if position is None:
                raise RuntimeError("Perps order failed")

            logger.info(f"  ✅ Perps position opened: #{position.id}")

        # Execute the actual trade (direction-aware) — spot path
        elif is_short:
            # SHORT ORDER: Sell BTC for USD
            # Calculate how much BTC to sell based on quote_amount (USD value)
            base_amount = quote_amount / current_price
            logger.info(
                f"  📉 SHORT: Selling {base_amount:.8f} BTC"
                f" (${quote_amount:.2f} worth) @ ${current_price:.2f}"
            )

            # Execute short order using existing sell infrastructure
            # For base orders (trade_type="initial"), we execute market sell
            # For safety orders, we check config for limit vs market

            trade = await execute_sell_short(
                db=db,
                exchange=exchange,
                trading_client=trading_client,
                bot=bot,
                product_id=product_id,
                position=position,
                base_amount=base_amount,
                current_price=current_price,
                trade_type=trade_type,
                signal_data=signal_data,
                commit_on_error=not is_new_position,
            )
        else:
            # Slippage guard for market buy orders
            buy_config = bot.strategy_config or {}
            exec_key = "base_execution_type" if trade_type == "initial" else "dca_execution_type"
            if buy_config.get(exec_key, "market") == "market" and buy_config.get("slippage_guard", False):
                proceed, guard_reason = await check_buy_slippage(
                    exchange, product_id, quote_amount, buy_config
                )
                if not proceed:
                    logger.warning(f"  🛡️ Slippage guard blocked buy: {guard_reason}")
                    if is_new_position and position:
                        position.status = "failed"
                        position.last_error_message = f"Slippage guard: {guard_reason}"
                        position.last_error_timestamp = datetime.utcnow()
                        position.closed_at = datetime.utcnow()
                        await db.commit()
                    return {
                        "action": "hold",
                        "reason": f"Slippage guard: {guard_reason}",
                        "signal": signal_data,
                    }

            # LONG ORDER: Buy BTC with USD (existing logic)
            trade = await execute_buy(
                db=db,
                exchange=exchange,
                trading_client=trading_client,
                bot=bot,
                product_id=product_id,
                position=position,
                quote_amount=quote_amount,
                current_price=current_price,
                trade_type=trade_type,
                signal_data=signal_data,
                commit_on_error=not is_new_position,  # Don't commit errors for base orders
            )

        if trade is None:
            # Limit order was placed instead
            logger.info("  ✅ Limit order placed (pending fill)")
        else:
            # Market order executed immediately
            logger.info(f"  ✅ Trade executed: ID={trade.id}, Order={trade.order_id}")

    except Exception as e:
        logger.error(f"  ❌ Trade execution failed: {e}")
        # If this was a new position and trade failed, mark it as failed (don't leave orphaned)
        if is_new_position and position:
            logger.warning(f"  🗑️ Marking position {position.id} as failed (initial buy failed)")
            # Mark position as failed instead of expunging
            # This prevents orphaned positions showing as "open" with 0 trades
            position.status = "failed"
            position.last_error_message = f"Initial buy failed: {str(e)}"
            position.last_error_timestamp = datetime.utcnow()
            position.closed_at = datetime.utcnow()
            await db.commit()
            return {"action": "none", "reason": f"Buy failed: {str(e)}", "signal": signal_data}

        # CRITICAL FIX: For existing positions (DCA failures), DO NOT raise exception
        # Raising would abort the entire bot cycle and prevent sells on other positions!
        # Instead, log the error on the position and continue processing
        logger.error(f"  ❌ DCA buy failed for existing position: {e}")
        logger.warning("  ⚠️ Continuing bot cycle to check for sells on other positions")

        # The error is already recorded on the position by execute_buy() if commit_on_error=True
        # Just return and let the bot continue to check for sells
        return {"action": "none", "reason": f"DCA buy failed: {str(e)}", "signal": signal_data}

    # Record signal
    await _record_signal(
        db, position, signal_data.get("signal_type", "buy"), "buy",
        buy_reason, current_price, signal_data,
    )

    return {"action": "buy", "reason": buy_reason, "signal": signal_data, "trade": trade, "position": position}


async def _decide_and_execute_sell(
    ctx: TradeContext, position: Position,
    signal_data: Dict[str, Any],
    candles: List[Dict[str, Any]],
    candles_by_timeframe: Optional[Dict[str, List[Dict[str, Any]]]],
) -> Optional[Dict[str, Any]]:
    """Decide whether to sell and execute the sell if conditions are met.

    Returns a result dict if sell/hold action taken, None if no position.
    """
    db, exchange, trading_client = ctx.db, ctx.exchange, ctx.trading_client
    bot, strategy = ctx.bot, ctx.strategy
    product_id, current_price = ctx.product_id, ctx.current_price
    # Debug: Log timeframes available in candles_by_timeframe
    if candles_by_timeframe:
        for tf, tf_candles in candles_by_timeframe.items():
            logger.debug(f"  📊 candles_by_timeframe[{tf}]: {len(tf_candles) if tf_candles else 0} candles")
    else:
        logger.debug("  📊 candles_by_timeframe is None or empty")

    # Calculate market context with indicators for custom sell conditions
    market_context = _calculate_market_context_with_indicators(candles, current_price, candles_by_timeframe)

    # Add previous indicators for crossing detection
    cache_key = f"{bot.id}_{product_id}"
    previous_context = _previous_market_context.get(cache_key)
    market_context["_previous"] = previous_context
    # Update cache with current context (copy to avoid mutation issues)
    _previous_market_context[cache_key] = {k: v for k, v in market_context.items() if k != "_previous"}

    should_sell, sell_reason = await strategy.should_sell(signal_data, position, current_price, market_context)

    if should_sell:
        # CRITICAL FIX: For limit orders, verify profit at MARK PRICE meets threshold
        # should_sell checked profit at current_price (candle close), but limit orders
        # are placed at mark price (bid/ask midpoint) which can be significantly lower
        config = position.strategy_config_snapshot or {}
        take_profit_order_type = config.get("take_profit_order_type", "market")
        take_profit_mode = config.get("take_profit_mode")
        if take_profit_mode is None:
            # Legacy inference
            if config.get("trailing_take_profit", False):
                take_profit_mode = "trailing"
            elif config.get("min_profit_for_conditions") is not None:
                take_profit_mode = "minimum"
            else:
                take_profit_mode = "fixed"

        # For limit orders, verify profit at mark price meets threshold
        if take_profit_order_type == "limit":
            tp_pct = config.get("take_profit_percentage", 3.0)
            try:
                ticker = await exchange.get_ticker(product_id)
                best_bid = float(ticker.get("best_bid", 0))
                best_ask = float(ticker.get("best_ask", 0))
                mark_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else current_price

                mark_value = position.total_base_acquired * mark_price
                mark_profit = mark_value - position.total_quote_spent
                mark_profit_pct = (mark_profit / position.total_quote_spent) * 100

                if mark_profit_pct < tp_pct:
                    logger.info(
                        f"  ⚠️ Sell conditions met BUT mark price profit ({mark_profit_pct:.2f}%) "
                        f"< take_profit ({tp_pct}%) - HOLDING"
                    )
                    hold_reason = f"Conditions met but mark profit {mark_profit_pct:.2f}% < {tp_pct}%"
                    await _record_signal(
                        db, position, "hold", "hold", hold_reason,
                        current_price, signal_data,
                    )
                    return {
                        "action": "hold",
                        "reason": f"Sell blocked: mark profit {mark_profit_pct:.2f}% < {tp_pct}%",
                        "signal": signal_data,
                        "position": position,
                    }
                else:
                    logger.info(
                        f"  ✓ Mark price profit ({mark_profit_pct:.2f}%)"
                        f" >= take_profit ({tp_pct}%)"
                        " - proceeding"
                    )
            except Exception as e:
                logger.warning(f"Could not verify mark price profit, proceeding with sell: {e}")

        # Slippage guard for market sell orders
        if take_profit_order_type == "market" and config.get("slippage_guard", False):
            proceed, guard_reason = await check_sell_slippage(
                exchange, product_id, position, config
            )
            if not proceed:
                logger.info(f"  🛡️ Slippage guard blocked sell: {guard_reason}")
                await _record_signal(
                    db, position, "hold", "hold",
                    f"Slippage guard: {guard_reason}", current_price, signal_data,
                )
                return {
                    "action": "hold",
                    "reason": f"Slippage guard: {guard_reason}",
                    "signal": signal_data,
                    "position": position,
                }

        # Stop loss / trailing stop always execute at market (no limit orders)
        sell_reason_lower = sell_reason.lower()
        is_stop_loss = "stop loss" in sell_reason_lower or "tsl triggered" in sell_reason_lower

        # Check if limit close order already pending
        if position.closing_via_limit:
            logger.warning(
                f"  ⚠️ Position #{position.id} already has a pending limit close order, skipping sell signal"
            )
            await _record_signal(
                db, position, "hold", "hold",
                f"Limit close order already pending (order_id: {position.limit_close_order_id})",
                current_price, signal_data,
            )
            return {
                "action": "hold",
                "reason": "Limit close order already pending",
                "signal": signal_data,
                "position": position,
            }

        # Execute close order (direction-aware)
        # Route perps positions to perps executor
        if getattr(position, 'product_type', 'spot') == 'future':
            coinbase_client = getattr(exchange, '_client', None) or getattr(exchange, 'client', None)
            if coinbase_client is None:
                logger.error("Cannot get CoinbaseClient for perps close")
                raise RuntimeError("Perps trading requires CoinbaseClient")

            success, profit_quote, profit_pct = await execute_perps_close(
                db=db,
                client=coinbase_client,
                position=position,
                current_price=current_price,
                reason="signal",
            )
            if not success:
                raise RuntimeError("Perps close order failed")
            trade = None  # Trade record created inside execute_perps_close

        # For long positions: sell the BTC we bought
        # For short positions: buy back the BTC we sold
        elif position.direction == "short":
            # CLOSE SHORT: Buy back BTC (opposite of opening short)

            trade, profit_quote, profit_pct = await execute_buy_close_short(
                db=db,
                exchange=exchange,
                trading_client=trading_client,
                bot=bot,
                product_id=product_id,
                position=position,
                current_price=current_price,
                signal_data=signal_data,
            )
        else:
            # CLOSE LONG: Sell the BTC we bought (existing logic)
            trade, profit_quote, profit_pct = await execute_sell(
                db=db,
                exchange=exchange,
                trading_client=trading_client,
                bot=bot,
                product_id=product_id,
                position=position,
                current_price=current_price,
                signal_data=signal_data,
                force_market=is_stop_loss,
            )

        # If trade is None, a limit order was placed - position stays open
        if trade is None:
            logger.info(f"  📊 Limit close order placed for position #{position.id}, waiting for fill")
            return {
                "action": "limit_close_pending",
                "reason": sell_reason,
                "limit_order_placed": True,
                "position_id": position.id,
            }

        # Record signal for market sell
        await _record_signal(
            db, position, signal_data.get("signal_type", "sell"), "sell",
            sell_reason, current_price, signal_data,
        )

        # Log the SELL decision to AI logs (even if AI recommended something else)
        # This captures what the trading engine actually did, not just what AI suggested
        await save_ai_log(
            db=db,
            bot=bot,
            product_id=product_id,
            signal_data={
                **signal_data,
                "signal_type": "sell",
                "reasoning": f"SELL EXECUTED: {sell_reason}",
                "confidence": 100,  # Trading engine decision, not AI suggestion
            },
            decision="sell",
            current_price=current_price,
            position=position,
        )

        return {
            "action": "sell",
            "reason": sell_reason,
            "signal": signal_data,
            "trade": trade,
            "position": position,
            "profit_quote": profit_quote,
            "profit_percentage": profit_pct,
        }
    else:
        # Hold - record signal with no action
        await _record_signal(
            db, position, signal_data.get("signal_type", "hold"), "hold",
            sell_reason, current_price, signal_data,
        )

        return {"action": "hold", "reason": sell_reason, "signal": signal_data, "position": position}


async def process_signal(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    strategy: TradingStrategy,
    product_id: str,
    candles: List[Dict[str, Any]],
    current_price: float,
    pre_analyzed_signal: Optional[Dict[str, Any]] = None,
    candles_by_timeframe: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    position_override: Any = _POSITION_NOT_SET,
) -> Dict[str, Any]:
    """
    Process market data with bot's strategy — orchestrator function.

    Delegates to private helper functions for each phase:
    1. Get position + analyze signal
    2. AI failsafe (if no signal)
    3. Calculate budget
    4. Log AI thinking
    5. Decide buy
    6. Execute buy
    7. Sell decision + execution

    Args:
        db: Database session
        exchange: Exchange client instance (CEX or DEX)
        trading_client: TradingClient instance
        bot: Bot instance
        strategy: TradingStrategy instance
        product_id: Trading pair (e.g., 'ETH-BTC')
        candles: Recent candle data
        current_price: Current market price
        pre_analyzed_signal: Optional pre-analyzed signal from batch mode (prevents duplicate AI calls)
        candles_by_timeframe: Optional dict of {timeframe: candles} for multi-timeframe indicator calculation

    Returns:
        Dict with action taken and details
    """
    quote_currency = get_quote_currency(product_id)

    # Build shared context for internal trading functions
    ctx = TradeContext(
        db=db, exchange=exchange, trading_client=trading_client,
        bot=bot, product_id=product_id, current_price=current_price,
        strategy=strategy,
    )

    # 1. Get current state FIRST (needed for web search context)
    # If position_override is provided, use it (supports simultaneous same-pair deals)
    if position_override is not _POSITION_NOT_SET:
        position = position_override
    else:
        position = await get_active_position(db, bot, product_id)

    # Determine action context for web search
    action_context = "hold"  # Default for positions that exist
    if position is None:
        action_context = "open"  # Considering opening a new position

    # Use pre-analyzed signal if provided (from batch mode), otherwise analyze now
    if pre_analyzed_signal:
        signal_data = pre_analyzed_signal
        logger.info(f"  Using pre-analyzed signal from batch mode (confidence: {signal_data.get('confidence')}%)")
    else:
        signal_data = await strategy.analyze_signal(
            candles, current_price, position=position, action_context=action_context,
            db=db, user_id=bot.user_id
        )

    # 2. AI failsafe — handle case where signal analysis returned None
    if not signal_data:
        failsafe_result = await _handle_ai_failsafe(ctx, position)
        if failsafe_result:
            return failsafe_result
        return {"action": "none", "reason": "No signal detected", "signal": None}

    # 3. Calculate budget
    aggregate_value = None
    quote_balance, aggregate_value = await _calculate_budget(
        ctx, position, quote_currency, aggregate_value,
    )

    # 4. Log AI thinking immediately after analysis (if AI bot and not already logged in batch mode)
    if bot.strategy_type == "ai_autonomous" and not signal_data.get("_already_logged", False):
        import traceback
        stack = "".join(traceback.format_stack()[-5:-1])
        logger.warning(f"  ⚠️ save_ai_log called despite _already_logged check! Bot #{bot.id} {product_id}")
        logger.warning(f"  _already_logged={signal_data.get('_already_logged')}")
        logger.warning(f"  Call stack:\n{stack}")

        ai_signal = signal_data.get("signal_type", "none")
        if ai_signal == "buy":
            decision = "buy"
        elif ai_signal == "sell":
            decision = "sell"
        else:
            decision = "hold"
        await save_ai_log(db, bot, product_id, signal_data, decision, current_price, position)

    # 5. Decide buy
    should_buy, quote_amount, buy_reason = await _decide_buy(
        ctx, signal_data, position, quote_balance, aggregate_value,
    )

    # 6. Execute buy
    if should_buy:
        buy_result = await _execute_buy_trade(
            ctx, position, quote_amount, quote_balance,
            signal_data, aggregate_value, buy_reason,
        )
        if buy_result:
            return buy_result

    # 7. Sell decision + execution
    if position is not None:
        sell_result = await _decide_and_execute_sell(
            ctx, position, signal_data, candles, candles_by_timeframe,
        )
        if sell_result:
            return sell_result

    # Commit any pending changes (like AI logs)
    await db.commit()

    return {"action": "none", "reason": "Signal detected but no action criteria met", "signal": signal_data}
