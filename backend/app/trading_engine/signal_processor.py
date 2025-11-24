"""
Signal processing and trading decision orchestration
Coordinates buy/sell decisions based on strategy analysis
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.currency_utils import format_with_usd, get_quote_currency
from app.models import Bot, Position, Signal
from app.strategies import TradingStrategy
from app.trading_client import TradingClient
from app.trading_engine.position_manager import get_active_position, get_open_positions_count, create_position
from app.trading_engine.order_logger import save_ai_log
from app.trading_engine.buy_executor import execute_buy
from app.trading_engine.sell_executor import execute_sell

logger = logging.getLogger(__name__)


async def process_signal(
    db: AsyncSession,
    coinbase: CoinbaseClient,
    trading_client: TradingClient,
    bot: Bot,
    strategy: TradingStrategy,
    product_id: str,
    candles: List[Dict[str, Any]],
    current_price: float,
    pre_analyzed_signal: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process market data with bot's strategy

    Args:
        db: Database session
        coinbase: CoinbaseClient instance
        trading_client: TradingClient instance
        bot: Bot instance
        strategy: TradingStrategy instance
        product_id: Trading pair (e.g., 'ETH-BTC')
        candles: Recent candle data
        current_price: Current market price
        pre_analyzed_signal: Optional pre-analyzed signal from batch mode (prevents duplicate AI calls)

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
        return {"action": "none", "reason": "No signal detected", "signal": None}

    # Get bot's available balance (budget-based or total portfolio)
    # Calculate aggregate portfolio value for bot budgeting
    print(f"🔍 Bot budget_percentage: {bot.budget_percentage}%, quote_currency: {quote_currency}")
    aggregate_value = None
    if bot.budget_percentage > 0:
        # Bot uses percentage-based budgeting - calculate aggregate value
        if quote_currency == "USD":
            aggregate_value = await coinbase.calculate_aggregate_usd_value()
            print(f"🔍 Aggregate USD value: ${aggregate_value:.2f}")
            logger.info(f"  💰 Aggregate USD value: ${aggregate_value:.2f}")
        else:
            aggregate_value = await coinbase.calculate_aggregate_btc_value()
            print(f"🔍 Aggregate BTC value: {aggregate_value:.8f} BTC")
            logger.info(f"  💰 Aggregate BTC value: {aggregate_value:.8f} BTC")

    reserved_balance = bot.get_reserved_balance(aggregate_value)
    print(f"🔍 Reserved balance (per-position): {reserved_balance:.8f}")
    if reserved_balance > 0:
        # Bot has reserved balance - get_reserved_balance() already divides by max_concurrent_deals
        # so reserved_balance IS the per-position budget
        max_concurrent_deals = max(bot.strategy_config.get("max_concurrent_deals", 1), 1)
        per_position_budget = reserved_balance  # Already per-position, don't divide again!

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
            btc_usd_price = await coinbase.get_btc_usd_price()
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
                position = await create_position(db, coinbase, bot, product_id, quote_balance, quote_amount)
                logger.info(f"  ✅ Position created: ID={position.id} (pending trade execution)")

            # Execute the actual trade
            trade = await execute_buy(
                db=db,
                coinbase=coinbase,
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
                logger.info(f"  ✅ Limit order placed (pending fill)")
            else:
                # Market order executed immediately
                logger.info(f"  ✅ Trade executed: ID={trade.id}, Order={trade.order_id}")

        except Exception as e:
            logger.error(f"  ❌ Trade execution failed: {e}")
            # If this was a new position and trade failed, remove the position from session
            if is_new_position and position:
                logger.warning(f"  🗑️ Removing failed position {position.id} from session (trade failed)")
                # Expunge the position from session instead of rolling back
                # This prevents session corruption when processing multiple pairs in batch mode
                db.expunge(position)
                return {"action": "none", "reason": f"Buy failed: {str(e)}", "signal": signal_data}
            raise  # Re-raise for existing positions (DCA failures)

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
        should_sell, sell_reason = await strategy.should_sell(signal_data, position, current_price)

        if should_sell:
            # Execute sell (market or limit based on config)
            trade, profit_quote, profit_pct = await execute_sell(
                db=db,
                coinbase=coinbase,
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
