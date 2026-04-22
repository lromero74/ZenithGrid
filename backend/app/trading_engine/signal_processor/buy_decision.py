"""Buy-side decision + execution for the signal processor.

Internal module — consumers should import through app.trading_engine.signal_processor.
Split out of the original monolithic signal_processor.py as part of
code-quality Phase 5.1.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import select

from app.currency_utils import format_with_usd
from app.models import BlacklistedCoin, Position
from app.services.indicator_log_service import log_indicator_evaluation
from app.trading_engine.book_depth_guard import check_buy_slippage
from app.trading_engine.buy_executor import execute_buy
from app.trading_engine.order_logger import OrderLogEntry, log_order_to_history
from app.trading_engine.perps_executor import execute_perps_open
from app.trading_engine.position_manager import create_position, get_open_positions_count
from app.trading_engine.sell_executor import execute_sell_short
from app.trading_engine.signal_processor._shared import (
    _is_duplicate_failed_order,
    _record_signal,
    calculate_soft_ceiling,
)
from app.trading_engine.trade_context import TradeContext

logger = logging.getLogger(__name__)


async def _decide_buy(
    ctx: TradeContext, signal_data: Dict[str, Any],
    position: Optional[Position], quote_balance: float,
    aggregate_value: Optional[float],
    open_positions_count: Optional[int] = None,
) -> tuple:
    """Decide whether to buy, including all checks (max deals, cooldown, blacklist).

    Returns (should_buy, quote_amount, buy_reason) tuple.
    """
    db, bot, strategy = ctx.db, ctx.bot, ctx.strategy
    product_id, current_price = ctx.product_id, ctx.current_price
    should_buy = False
    quote_amount = 0
    buy_reason = ""

    logger.debug(f"Bot active: {bot.is_active}, Position exists: {position is not None}")
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
            if open_positions_count is None:
                open_positions_count = await get_open_positions_count(db, bot)

            # Use soft ceiling if enabled, otherwise use fixed max_concurrent_deals
            max_deals = await calculate_soft_ceiling(ctx, aggregate_value or 0.0)

            # Persist the computed value so the bot list can display it
            if bot.strategy_config.get("enable_soft_ceiling", False):
                bot.soft_ceiling_effective_max = max_deals
                await db.commit()

            logger.debug(f"Open positions: {open_positions_count}/{max_deals}")

            if open_positions_count >= max_deals:
                should_buy = False
                ceiling_type = (
                    "Soft ceiling" if bot.strategy_config.get("enable_soft_ceiling")
                    else "Max concurrent deals"
                )
                buy_reason = f"{ceiling_type} reached ({open_positions_count}/{max_deals})"
                logger.debug(f"Should buy: FALSE - {buy_reason}")
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
                        logger.debug(f"Should buy: FALSE - {buy_reason}")
                        logger.info(f"  ⏳ {buy_reason}")

                # Check if coin is blacklisted before considering a buy (skip if cooldown blocked)
                if not buy_reason:
                    from sqlalchemy import or_
                    base_symbol = product_id.split("-")[0]  # "ETH-BTC" -> "ETH"

                    # Single query for both user-specific and global blacklist entries
                    blacklist_query = select(BlacklistedCoin).where(
                        BlacklistedCoin.symbol == base_symbol,
                        or_(
                            BlacklistedCoin.user_id == bot.user_id,
                            BlacklistedCoin.user_id.is_(None),
                        ),
                    )
                    blacklist_result = await db.execute(blacklist_query)
                    blacklist_entries = blacklist_result.scalars().all()

                    # Prefer user-specific entry over global
                    blacklisted_entry = None
                    for entry in blacklist_entries:
                        if entry.user_id is not None:
                            blacklisted_entry = entry
                            break
                    if blacklisted_entry is None and blacklist_entries:
                        blacklisted_entry = blacklist_entries[0]

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
                            logger.debug(f"{base_symbol} is {coin_category} (allowed): {reason}")
                            logger.info(f"  ✅ {coin_category}: {base_symbol} - allowed to trade")
                            should_buy, quote_amount, buy_reason = await strategy.should_buy(
                                signal_data, position, quote_balance,
                                aggregate_value=aggregate_value
                            )
                            logger.debug(
                                f"Should buy result: {should_buy},"
                                f" amount: {quote_amount or 0:.8f}, reason: {buy_reason}"
                            )
                        else:
                            should_buy = False
                            category_tag = f'[{coin_category}] '
                            buy_reason = (
                                f"{base_symbol} is {coin_category}:"
                                f" {reason.replace(category_tag, '')}"
                            )
                            logger.debug(f"Should buy: FALSE - {buy_reason}")
                            logger.info(f"  🚫 {coin_category} (blocked): {buy_reason}")
                    else:
                        should_buy, quote_amount, buy_reason = await strategy.should_buy(
                            signal_data, position, quote_balance,
                            aggregate_value=aggregate_value
                        )
                        logger.debug(
                            f"Should buy result: {should_buy},"
                            f" amount: {quote_amount or 0:.8f}, reason: {buy_reason}"
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
