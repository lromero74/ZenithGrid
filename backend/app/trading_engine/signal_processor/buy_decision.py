"""Buy-side decision + execution for the signal processor.

Internal module — consumers should import through app.trading_engine.signal_processor.
Split out of the original monolithic signal_processor.py as part of
code-quality Phase 5.1.
"""

import asyncio
import logging
from app.utils.timeutil import utcnow
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select

from app.currency_utils import format_with_usd, get_quote_currency
from app.models import BlacklistedCoin, Position
from app.services.indicator_log_service import log_indicator_evaluation
from app.trading_engine.book_depth_guard import check_buy_slippage
from app.trading_engine.buy_executor import execute_buy
from app.trading_engine.order_logger import OrderLogEntry, log_order_to_history
from app.trading_engine.perps_executor import execute_perps_open
from app.trading_engine.position_manager import create_position, get_open_positions_count
from app.trading_engine.sell_executor import execute_sell_short
from app.order_validation import validate_order_size
from app.trading_engine.signal_processor._shared import (
    _is_duplicate_failed_order,
    _record_signal,
    calculate_soft_ceiling,
)
from app.trading_engine.soft_ceiling_config import is_soft_ceiling_enabled
from app.trading_engine.trade_context import TradeContext

logger = logging.getLogger(__name__)

# Per-bot locks to prevent concurrent pair tasks from exceeding
# max_concurrent_deals. When multiple pair tasks for the same bot run
# concurrently, they share a stale open_positions_count snapshot.
# This lock serializes the position-count check so each task sees
# the updated count from the previous task's position creation.
_bot_position_locks: Dict[int, asyncio.Lock] = {}


async def _log_budget_blocker_if_applicable(
    ctx: TradeContext, signal_data: Dict[str, Any],
    position: Optional[Position], quote_amount: Optional[float],
    quote_balance: float, buy_reason: str,
    phase: str, trade_type: str,
) -> None:
    """Record a budget-blocker to indicator_logs + order_history (deduplicated).

    No-op if buy_reason isn't a budget/insufficient message.
    """
    reason_lower = (buy_reason or "").lower()
    if "insufficient" not in reason_lower and "budget" not in reason_lower:
        return

    db, bot = ctx.db, ctx.bot
    product_id, current_price = ctx.product_id, ctx.current_price

    await log_indicator_evaluation(
        db=db,
        bot_id=bot.id,
        product_id=product_id,
        phase=phase,
        conditions_met=False,
        conditions_detail=[{
            "type": "budget",
            "indicator": "Available Balance",
            "operator": "sufficient_for",
            "threshold": quote_amount if quote_amount else 0,
            "actual_value": quote_balance,
            "result": False,
            "reason": buy_reason,
        }],
        indicators_snapshot=signal_data.get("indicators", {}),
        current_price=current_price,
    )

    is_dup = await _is_duplicate_failed_order(
        db, bot.id, product_id, trade_type, buy_reason, position,
    )
    if not is_dup:
        await log_order_to_history(
            db=db, bot=bot, position=position,
            entry=OrderLogEntry(
                product_id=product_id, side="BUY", order_type="MARKET",
                trade_type=trade_type, quote_amount=0.0,
                price=current_price, status="failed",
                error_message=buy_reason,
            ),
        )
        await db.commit()


async def _run_new_position_preflight(
    ctx: TradeContext, aggregate_value: Optional[float],
    open_positions_count: Optional[int],
    max_deals: Optional[int] = None,
) -> Tuple[bool, str, Optional[int]]:
    """Preflight checks for opening a NEW position.

    Runs stable-pair guard, soft-ceiling / max-concurrent-deals, and
    per-pair deal-cooldown. Returns (blocked, reason, open_positions_count).
    When blocked=True, reason is populated and the caller should skip the buy.

    Args:
        max_deals: Pre-computed soft-ceiling-clamped max deals. If None,
            computes it via calculate_soft_ceiling (backward compat).
    """
    db, bot, strategy = ctx.db, ctx.bot, ctx.strategy
    product_id = ctx.product_id

    # Skip stable/pegged pairs (layer-2 safety check)
    skip_stable = bot.strategy_config.get("skip_stable_pairs", True) if bot.strategy_config else True
    if skip_stable:
        from app.services.delisted_pair_monitor import is_stable_pair
        if is_stable_pair(product_id):
            return True, f"{product_id} is a stable/pegged pair (skipped)", open_positions_count

    if open_positions_count is None:
        open_positions_count = await get_open_positions_count(db, bot)

    # Acquire per-bot lock to prevent concurrent pair tasks from exceeding
    # max_concurrent_deals. Without this, two concurrent tasks both see
    # open_positions_count=N and both open a position → N+2 > max_deals.
    lock = _bot_position_locks.setdefault(bot.id, asyncio.Lock())
    async with lock:
        # Re-fetch under lock — another task may have opened a position
        # since the initial fetch above.
        open_positions_count = await get_open_positions_count(db, bot)

        if max_deals is None:
            max_deals = await calculate_soft_ceiling(ctx, aggregate_value or 0.0)

        # Persist the computed value so the bot list can display it
        if is_soft_ceiling_enabled(bot):
            bot.soft_ceiling_effective_max = max_deals
            await db.commit()

        logger.debug(f"Open positions: {open_positions_count}/{max_deals}")

        if open_positions_count >= max_deals:
            ceiling_type = (
                "Soft ceiling" if is_soft_ceiling_enabled(bot)
                else "Max concurrent deals"
            )
            reason = f"{ceiling_type} reached ({open_positions_count}/{max_deals})"
            logger.debug(f"Should buy: FALSE - {reason}")
            logger.info(f"  🔒 {ctx.product_id} blocked: {reason}")
            return True, reason, open_positions_count

    deal_cooldown = strategy.config.get("deal_cooldown_seconds", 0) or 0
    if deal_cooldown > 0:
        cooldown_cutoff = utcnow() - timedelta(seconds=deal_cooldown)
        recent_close_query = select(Position).where(
            Position.bot_id == bot.id,
            Position.product_id == product_id,
            Position.status == "closed",
            Position.closed_at >= cooldown_cutoff,
        )
        recent_result = await db.execute(recent_close_query)
        recently_closed = recent_result.scalars().first()
        if recently_closed:
            elapsed = (utcnow() - recently_closed.closed_at).total_seconds()
            remaining = deal_cooldown - elapsed
            reason = f"Deal cooldown active for {product_id} ({int(remaining)}s remaining)"
            logger.debug(f"Should buy: FALSE - {reason}")
            logger.info(f"  ⏳ {reason}")
            return True, reason, open_positions_count

    # Speculative bucket hard cap (account-level).
    # Speculative-tagged bots (strategy_config["is_speculative"] == "true") opt
    # into a shared cost-basis envelope capped by Account.speculative_allocation_pct.
    # See PRPs/high-risk-doubling-preset.md §Recommended Design §6.
    if bot.strategy_config and str(bot.strategy_config.get("is_speculative", "")).lower() == "true":
        from app.services.speculative_bucket_service import validate_speculative_entry
        intended_cost_basis = float(strategy.config.get("base_order_size", 0.0) or 0.0)
        # Use USD aggregate when available; for BTC-quote bots the preflight
        # runs before the quote-conversion step so we pass 0 for btc_usd_price
        # and accept a small approximation — bucket semantics treat cost basis
        # in the bot's quote currency as USD for the cap, which is acceptable
        # since the speculative preset is USD-biased by design.
        allowed, spec_reason = await validate_speculative_entry(
            db, bot,
            intended_cost_basis_usd=intended_cost_basis,
            aggregate_usd_value=aggregate_value or 0.0,
        )
        if not allowed:
            logger.debug(f"Should buy: FALSE - {spec_reason}")
            logger.info(f"  🚫 {spec_reason}")
            return True, spec_reason, open_positions_count

    return False, "", open_positions_count


async def _evaluate_blacklist_category(
    ctx: TradeContext,
) -> Tuple[bool, str, str]:
    """Look up the base symbol's blacklist entry and decide allow/deny.

    Returns (allowed, category, reason). If no entry exists, allowed=True
    with empty category/reason. If blocked, allowed=False and reason
    contains the user-facing explanation.
    """
    from sqlalchemy import or_

    db, bot = ctx.db, ctx.bot
    product_id = ctx.product_id
    base_symbol = product_id.split("-")[0]

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

    if blacklisted_entry is None:
        return True, "", ""

    reason = blacklisted_entry.reason or ""
    if reason.startswith("[APPROVED]"):
        coin_category = "APPROVED"
    elif reason.startswith("[BORDERLINE]"):
        coin_category = "BORDERLINE"
    elif reason.startswith("[QUESTIONABLE]"):
        coin_category = "QUESTIONABLE"
    elif reason.startswith("[MEME]"):
        coin_category = "MEME"
    else:
        coin_category = "BLACKLISTED"

    allowed_categories = ["APPROVED"]
    if bot.strategy_config and bot.strategy_config.get("allowed_categories"):
        allowed_categories = bot.strategy_config["allowed_categories"]

    if coin_category in allowed_categories:
        logger.debug(f"{base_symbol} is {coin_category} (allowed): {reason}")
        logger.info(f"  ✅ {coin_category}: {base_symbol} - allowed to trade")
        return True, coin_category, ""

    category_tag = f"[{coin_category}] "
    block_reason = (
        f"{base_symbol} is {coin_category}:"
        f" {reason.replace(category_tag, '')}"
    )
    logger.debug(f"Should buy: FALSE - {block_reason}")
    logger.info(f"  🚫 {coin_category} (blocked): {block_reason}")
    return False, coin_category, block_reason


async def _decide_buy(
    ctx: TradeContext, signal_data: Dict[str, Any],
    position: Optional[Position], quote_balance: float,
    aggregate_value: Optional[float],
    open_positions_count: Optional[int] = None,
    max_deals: Optional[int] = None,
) -> tuple:
    """Decide whether to buy, including all checks (max deals, cooldown, blacklist).

    Returns (should_buy, quote_amount, buy_reason) tuple.

    Args:
        max_deals: Pre-computed soft-ceiling-clamped max deals. If None,
            computed inside _run_new_position_preflight (backward compat).
    """
    bot, strategy = ctx.bot, ctx.strategy

    logger.debug(f"Bot active: {bot.is_active}, Position exists: {position is not None}")
    logger.info(f"  🤖 Bot active: {bot.is_active}, Position exists: {position is not None}")

    if not bot.is_active:
        return await _decide_buy_bot_stopped(
            ctx, signal_data, position, quote_balance, aggregate_value,
        )

    # Active bot, existing position → DCA path
    if position is not None:
        return await _decide_buy_dca(
            ctx, signal_data, position, quote_balance, aggregate_value,
        )

    # Active bot, no position → new-position path with preflight + blacklist gates
    blocked, reason, _ = await _run_new_position_preflight(
        ctx, aggregate_value, open_positions_count,
        max_deals=max_deals,
    )
    if blocked:
        return False, 0, reason

    allowed, _category, block_reason = await _evaluate_blacklist_category(ctx)
    if not allowed:
        return False, 0, block_reason

    # Pass the effective soft-ceiling deal count so bidirectional base-order
    # sizing splits the budget by the same number the preflight gated on (the
    # preflight persisted it to bot.soft_ceiling_effective_max just above).
    effective_max_deals = (
        bot.soft_ceiling_effective_max
        if bot.strategy_config.get("enable_soft_ceiling", False)
        else None
    )
    should_buy, quote_amount, buy_reason = await strategy.should_buy(
        signal_data, position, quote_balance,
        aggregate_value=aggregate_value,
        effective_max_deals=effective_max_deals,
    )
    logger.debug(
        f"Should buy result: {should_buy},"
        f" amount: {quote_amount or 0:.8f}, reason: {buy_reason}"
    )

    if not should_buy:
        await _log_budget_blocker_if_applicable(
            ctx, signal_data, None, quote_amount, quote_balance,
            buy_reason, phase="budget_check", trade_type="initial",
        )

    return should_buy, quote_amount, buy_reason


async def _decide_buy_dca(
    ctx: TradeContext, signal_data: Dict[str, Any],
    position: Position, quote_balance: float,
    aggregate_value: Optional[float],
) -> tuple:
    """Active-bot path when a position already exists (DCA check)."""
    strategy = ctx.strategy
    should_buy, quote_amount, buy_reason = await strategy.should_buy(
        signal_data, position, quote_balance,
        aggregate_value=aggregate_value,
    )
    if not should_buy:
        await _log_budget_blocker_if_applicable(
            ctx, signal_data, position, quote_amount, quote_balance,
            buy_reason, phase="budget_check_dca", trade_type="safety_order",
        )
    return should_buy, quote_amount, buy_reason


async def _decide_buy_bot_stopped(
    ctx: TradeContext, signal_data: Dict[str, Any],
    position: Optional[Position], quote_balance: float,
    aggregate_value: Optional[float],
) -> tuple:
    """Stopped-bot path: don't open new positions; still evaluate DCA for existing."""
    strategy = ctx.strategy
    if position is None:
        return False, 0, "Bot is stopped - not opening new positions"

    should_buy, quote_amount, buy_reason = await strategy.should_buy(
        signal_data, position, quote_balance,
        aggregate_value=aggregate_value,
    )
    if not should_buy:
        buy_reason = f"Bot stopped, DCA check: {buy_reason}"
        await _log_budget_blocker_if_applicable(
            ctx, signal_data, position, quote_amount, quote_balance,
            buy_reason, phase="budget_check_dca", trade_type="safety_order",
        )
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

    # Pre-validate order size against exchange minimums BEFORE creating position.
    # This prevents a flood of failed positions when the budget is too thin
    # (e.g., 15% of $12 split by 20 deals = $0.09, below Coinbase's $1 minimum).
    is_valid, validation_error = await validate_order_size(
        exchange, product_id, quote_amount=quote_amount,
    )
    if not is_valid:
        logger.warning(f"  🚫 Order size pre-validation failed: {validation_error}")
        # Log to indicator_logs so the user can see why buys are being skipped
        await log_indicator_evaluation(
            db=db,
            bot_id=bot.id,
            product_id=product_id,
            phase="order_size_prevalidation",
            conditions_met=False,
            conditions_detail=[{
                "type": "order_minimum",
                "indicator": "quote_amount",
                "operator": ">=",
                "threshold": None,  # min is in validation_error string
                "actual_value": quote_amount,
                "result": False,
                "reason": validation_error,
            }],
            indicators_snapshot=signal_data.get("indicators", {}),
            current_price=current_price,
        )
        return {
            "action": "hold",
            "reason": f"Order size below exchange minimum: {validation_error}",
            "signal": signal_data,
        }

    # Re-validate available balance just before order execution to guard
    # against TOCTOU: a concurrent pair task for the same bot could have
    # consumed part of the budget between _calculate_budget() and here.
    quote_currency = get_quote_currency(product_id)
    try:
        balance_info = await exchange.get_balance(quote_currency)
        fresh_available = float(balance_info.get("available", 0))
        if fresh_available < quote_amount:
            logger.warning(
                f"  🚫 Budget TOCTOU guard: available {quote_currency} balance "
                f"({fresh_available:.8f}) < quote_amount ({quote_amount:.8f}) — "
                f"another pair task likely consumed the budget"
            )
            return {
                "action": "hold",
                "reason": f"Insufficient {quote_currency} balance at execution time "
                          f"({fresh_available:.8f} < {quote_amount:.8f})",
                "signal": signal_data,
            }
    except Exception as e:
        # Fail CLOSED: if we can't verify the balance, hold rather than risk
        # overdrawing the account.  Multiple concurrent pair tasks could all
        # proceed with stale balance assumptions, collectively over-spending.
        logger.warning(
            f"  🚫 Budget TOCTOU guard: could not verify {quote_currency} balance ({e}) — holding"
        )
        return {
            "action": "hold",
            "reason": f"Balance verification failed for {quote_currency}: {e}",
            "signal": signal_data,
        }

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
                        position.last_error_timestamp = utcnow()
                        position.closed_at = utcnow()
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
            position.last_error_timestamp = utcnow()
            position.closed_at = utcnow()
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
