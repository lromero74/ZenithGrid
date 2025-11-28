"""
Signal processing and trading decision orchestration
Coordinates buy/sell decisions based on strategy analysis
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.currency_utils import format_with_usd, get_quote_currency
from app.exchange_clients.base import ExchangeClient
from app.models import BlacklistedCoin, Bot, Position, Signal
from app.strategies import TradingStrategy
from app.trading_client import TradingClient
from app.trading_engine.position_manager import get_active_position, get_open_positions_count, create_position
from app.trading_engine.order_logger import save_ai_log
from app.trading_engine.buy_executor import execute_buy
from app.trading_engine.sell_executor import execute_sell
from app.indicator_calculator import IndicatorCalculator

logger = logging.getLogger(__name__)

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
) -> Dict[str, Any]:
    """
    Process market data with bot's strategy

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

    # Get current state FIRST (needed for web search context)
    position = await get_active_position(db, bot, product_id)

    # Determine action context for web search
    action_context = "hold"  # Default for positions that exist
    if position is None:
        action_context = "open"  # Considering opening a new position
    # (We'll update to "close" or "dca" later based on actual decision)

    # Use pre-analyzed signal if provided (from batch mode), otherwise analyze now
    if pre_analyzed_signal:
        signal_data = pre_analyzed_signal
        logger.info(f"  Using pre-analyzed signal from batch mode (confidence: {signal_data.get('confidence')}%)")
    else:
        # Analyze signal using strategy (with position and context for web search)
        signal_data = await strategy.analyze_signal(
            candles, current_price, position=position, action_context=action_context
        )

    if not signal_data:
        # AI FAILSAFE: If AI analysis failed and we have a position in profit, auto-sell to protect it
        if bot.strategy_type == "ai_autonomous" and position is not None:
            logger.warning(f"  🛡️ AI analysis failed for {product_id} - checking failsafe for position #{position.id}")

            # Check if failsafe should sell to protect profit
            should_sell_failsafe, failsafe_reason = await strategy.should_sell_failsafe(position, current_price)

            if should_sell_failsafe:
                logger.warning(f"  🛡️ FAILSAFE ACTIVATED: {failsafe_reason}")

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
                    logger.warning(f"  🛡️ Failsafe limit close order placed for position #{position.id}, waiting for fill")
                    return {
                        "action": "failsafe_limit_close_pending",
                        "reason": failsafe_reason,
                        "limit_order_placed": True,
                        "position_id": position.id,
                    }

                # Record signal for market sell
                signal = Signal(
                    position_id=position.id,
                    timestamp=datetime.utcnow(),
                    signal_type="sell",
                    macd_value=0,
                    macd_signal=0,
                    macd_histogram=0,
                    price=current_price,
                    action_taken="sell",
                    reason=failsafe_reason,
                )
                db.add(signal)
                await db.commit()

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
            else:
                logger.info(f"  Failsafe checked but not triggered: {failsafe_reason}")

        return {"action": "none", "reason": "No signal detected", "signal": None}

    # Get bot's available balance (budget-based or total portfolio)
    # Calculate aggregate portfolio value for bot budgeting
    print(f"🔍 Bot budget_percentage: {bot.budget_percentage}%, quote_currency: {quote_currency}")
    aggregate_value = None
    if bot.budget_percentage > 0:
        # Bot uses percentage-based budgeting - calculate aggregate value
        if quote_currency == "USD":
            aggregate_value = await exchange.calculate_aggregate_usd_value()
            print(f"🔍 Aggregate USD value: ${aggregate_value:.2f}")
            logger.info(f"  💰 Aggregate USD value: ${aggregate_value:.2f}")
        else:
            aggregate_value = await exchange.calculate_aggregate_btc_value()
            print(f"🔍 Aggregate BTC value: {aggregate_value:.8f} BTC")
            logger.info(f"  💰 Aggregate BTC value: {aggregate_value:.8f} BTC")

    reserved_balance = bot.get_reserved_balance(aggregate_value)
    print(f"🔍 Reserved balance (total bot budget): {reserved_balance:.8f}")
    if reserved_balance > 0:
        # Bot has reserved balance - divide by max_concurrent_deals to get per-position budget
        # This ensures each position gets its fair share (e.g., 33% ÷ 6 deals = 5.5% per deal)
        max_concurrent_deals = max(bot.strategy_config.get("max_concurrent_deals", 1), 1)
        per_position_budget = reserved_balance / max_concurrent_deals

        # Calculate how much is available for THIS position (per-position budget - already spent in this position)
        query = select(Position).where(
            Position.bot_id == bot.id, Position.status == "open", Position.product_id == product_id
        )
        result = await db.execute(query)
        open_positions = result.scalars().all()

        total_in_positions = sum(p.total_quote_spent for p in open_positions)
        quote_balance = per_position_budget - total_in_positions

        if bot.budget_percentage > 0:
            logger.info(
                f"  💰 Bot budget: {bot.budget_percentage}% of aggregate ({reserved_balance:.8f}), Max deals: {max_concurrent_deals}, Per-position: {per_position_budget:.8f}, In positions: {total_in_positions:.8f}, Available: {quote_balance:.8f}"
            )
        else:
            logger.info(
                f"  💰 Bot reserved balance: {reserved_balance}, Max deals: {max_concurrent_deals}, Per-position: {per_position_budget:.8f}, In positions: {total_in_positions}, Available: {quote_balance}"
            )
    else:
        # No reserved balance - use total portfolio balance (backward compatibility)
        quote_balance = await trading_client.get_quote_balance(product_id)
        logger.info(f"  💰 Using total portfolio balance: {quote_balance}")

    # Log AI thinking immediately after analysis (if AI bot and not already logged in batch mode)
    if bot.strategy_type == "ai_autonomous" and not signal_data.get("_already_logged", False):
        # DEBUG: This should NOT be called in batch mode!
        import traceback

        stack = "".join(traceback.format_stack()[-5:-1])
        logger.warning(f"  ⚠️ save_ai_log called despite _already_logged check! Bot #{bot.id} {product_id}")
        logger.warning(f"  _already_logged={signal_data.get('_already_logged')}")
        logger.warning(f"  Call stack:\n{stack}")

        # Log what the AI thinks, not what the bot will do
        ai_signal = signal_data.get("signal_type", "none")
        if ai_signal == "buy":
            decision = "buy"
        elif ai_signal == "sell":
            decision = "sell"
        else:
            decision = "hold"
        await save_ai_log(db, bot, product_id, signal_data, decision, current_price, position)

    # Check if we should buy (only if bot is active)
    should_buy = False
    quote_amount = 0
    buy_reason = ""

    print(f"🔍 Bot active: {bot.is_active}, Position exists: {position is not None}")
    logger.info(f"  🤖 Bot active: {bot.is_active}, Position exists: {position is not None}")

    if bot.is_active:
        # Check max concurrent deals limit (3Commas style)
        if position is None:  # Only check when considering opening a NEW position
            open_positions_count = await get_open_positions_count(db, bot)
            max_deals = strategy.config.get("max_concurrent_deals", 1)
            print(f"🔍 Open positions: {open_positions_count}/{max_deals}")

            if open_positions_count >= max_deals:
                should_buy = False
                buy_reason = f"Max concurrent deals limit reached ({open_positions_count}/{max_deals})"
                print(f"🔍 Should buy: FALSE - {buy_reason}")
            else:
                # Check if coin is blacklisted before considering a buy
                base_symbol = product_id.split("-")[0]  # "ETH-BTC" -> "ETH"
                blacklist_query = select(BlacklistedCoin).where(BlacklistedCoin.symbol == base_symbol)
                blacklist_result = await db.execute(blacklist_query)
                blacklisted_entry = blacklist_result.scalars().first()

                if blacklisted_entry:
                    # Check if it's an APPROVED coin (not actually blocked)
                    reason = blacklisted_entry.reason or ''
                    if reason.startswith('[APPROVED]'):
                        # Approved coins are allowed to trade
                        print(f"🔍 {base_symbol} is APPROVED: {reason}")
                        logger.info(f"  ✅ APPROVED: {base_symbol}")
                        print(f"🔍 Calling strategy.should_buy() with quote_balance={quote_balance:.8f}")
                        should_buy, quote_amount, buy_reason = await strategy.should_buy(signal_data, position, quote_balance)
                        print(f"🔍 Should buy result: {should_buy}, amount: {quote_amount:.8f}, reason: {buy_reason}")
                    else:
                        should_buy = False
                        buy_reason = f"{base_symbol} is blacklisted: {reason or 'No reason provided'}"
                        print(f"🔍 Should buy: FALSE - {buy_reason}")
                        logger.info(f"  🚫 BLACKLISTED: {buy_reason}")
                else:
                    print(f"🔍 Calling strategy.should_buy() with quote_balance={quote_balance:.8f}")
                    should_buy, quote_amount, buy_reason = await strategy.should_buy(signal_data, position, quote_balance)
                    print(f"🔍 Should buy result: {should_buy}, amount: {quote_amount:.8f}, reason: {buy_reason}")
        else:
            # Position already exists for this pair - check for DCA
            should_buy, quote_amount, buy_reason = await strategy.should_buy(signal_data, position, quote_balance)
    else:
        # Bot is stopped - don't open new positions
        if position is None:
            buy_reason = "Bot is stopped - not opening new positions"
        else:
            buy_reason = "Bot is stopped - managing existing position only"

    if should_buy:
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

        if is_new_position:
            logger.info(f"  🔨 Executing {trade_type} buy order FIRST (position will be created after success)...")
        else:
            logger.info(f"  🔨 Executing {trade_type} buy order for existing position...")

        # Execute buy FIRST - don't create position until we know trade succeeds
        try:
            # For new positions, we need to create position for the trade to reference
            # BUT we do it in a transaction that will rollback if trade fails
            if is_new_position:
                logger.info("  📝 Creating position (will commit only if trade succeeds)...")
                position = await create_position(db, exchange, bot, product_id, quote_balance, quote_amount)
                logger.info(f"  ✅ Position created: ID={position.id} (pending trade execution)")

            # Execute the actual trade
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
            logger.warning(f"  ⚠️ Continuing bot cycle to check for sells on other positions")

            # The error is already recorded on the position by execute_buy() if commit_on_error=True
            # Just return and let the bot continue to check for sells
            return {"action": "none", "reason": f"DCA buy failed: {str(e)}", "signal": signal_data}

        # Record signal
        signal = Signal(
            position_id=position.id,
            timestamp=datetime.utcnow(),
            signal_type=signal_data.get("signal_type", "buy"),
            macd_value=signal_data.get("macd_value", 0),
            macd_signal=signal_data.get("macd_signal", 0),
            macd_histogram=signal_data.get("macd_histogram", 0),
            price=current_price,
            action_taken="buy",
            reason=buy_reason,
        )
        db.add(signal)
        await db.commit()

        return {"action": "buy", "reason": buy_reason, "signal": signal_data, "trade": trade, "position": position}

    # Check if we should sell
    if position is not None:
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
            # Execute sell (market or limit based on config)
            trade, profit_quote, profit_pct = await execute_sell(
                db=db,
                exchange=exchange,
                trading_client=trading_client,
                bot=bot,
                product_id=product_id,
                position=position,
                current_price=current_price,
                signal_data=signal_data,
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
            signal = Signal(
                position_id=position.id,
                timestamp=datetime.utcnow(),
                signal_type=signal_data.get("signal_type", "sell"),
                macd_value=signal_data.get("macd_value", 0),
                macd_signal=signal_data.get("macd_signal", 0),
                macd_histogram=signal_data.get("macd_histogram", 0),
                price=current_price,
                action_taken="sell",
                reason=sell_reason,
            )
            db.add(signal)
            await db.commit()

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
            signal = Signal(
                position_id=position.id,
                timestamp=datetime.utcnow(),
                signal_type=signal_data.get("signal_type", "hold"),
                macd_value=signal_data.get("macd_value", 0),
                macd_signal=signal_data.get("macd_signal", 0),
                macd_histogram=signal_data.get("macd_histogram", 0),
                price=current_price,
                action_taken="hold",
                reason=sell_reason,
            )
            db.add(signal)
            await db.commit()

            return {"action": "hold", "reason": sell_reason, "signal": signal_data, "position": position}

    # Commit any pending changes (like AI logs)
    await db.commit()

    return {"action": "none", "reason": "Signal detected but no action criteria met", "signal": signal_data}
