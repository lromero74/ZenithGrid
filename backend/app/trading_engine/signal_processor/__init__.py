"""Signal processing and trading decision orchestration.

Coordinates buy/sell decisions based on strategy analysis. The public
entrypoint is `process_signal()`. The decision + execution logic is split
across `_shared`, `buy_decision`, and `sell_decision` submodules (Phase 5.1).
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.currency_utils import get_quote_currency
from app.exchange_clients.base import ExchangeClient
from app.models import Bot
from app.strategies import TradingStrategy
from app.trading_client import TradingClient
from app.trading_engine.order_logger import save_ai_log
from app.trading_engine.position_manager import get_active_position
from app.trading_engine.signal_processor._shared import (
    _POSITION_NOT_SET,
    _calculate_budget,
    _calculate_market_context_with_indicators,
    _handle_ai_failsafe,
    _is_duplicate_failed_order,
    _record_signal,
    calculate_soft_ceiling,
)
from app.trading_engine.signal_processor.buy_decision import (
    _decide_buy,
    _execute_buy_trade,
)
from app.trading_engine.signal_processor.sell_decision import (
    _decide_and_execute_sell,
)
from app.trading_engine.trade_context import TradeContext
from app.trading_engine.soft_ceiling_config import is_soft_ceiling_enabled

logger = logging.getLogger(__name__)

__all__ = [
    "_POSITION_NOT_SET",
    "_calculate_budget",
    "_calculate_market_context_with_indicators",
    "_decide_and_execute_sell",
    "_decide_buy",
    "_execute_buy_trade",
    "_handle_ai_failsafe",
    "_is_duplicate_failed_order",
    "_record_signal",
    "calculate_soft_ceiling",
    "process_signal",
]


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
    open_positions_count: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Process market data with bot's strategy — orchestrator function.

    Delegates to private helper functions for each phase:
    1. Get position + analyze signal
    2. AI failsafe (if no signal)
    3. Calculate soft ceiling
    4. Calculate budget
    5. Log AI thinking
    6. Decide buy
    7. Execute buy
    8. Sell decision + execution

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
    _position_is_override = False
    if position_override is not _POSITION_NOT_SET:
        position = position_override
        _position_is_override = True
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
            db=db, user_id=bot.user_id,
            bot=bot, account_id=bot.account_id,
        )

    # 2. AI failsafe — handle case where signal analysis returned None
    if not signal_data:
        failsafe_result = await _handle_ai_failsafe(ctx, position)
        if failsafe_result:
            return failsafe_result
        return {"action": "none", "reason": "No signal detected", "signal": None}

    # 3. Calculate soft ceiling BEFORE budget so split_budget_across_pairs
    #    divides by the clamped effective max, not the raw config value.
    #    Percentage-budget bots need a real aggregate value here; passing 0
    #    incorrectly clamps the soft ceiling to 1 while the UI can show 2+.
    aggregate_value_for_ceiling = None
    if bot.budget_percentage > 0 and is_soft_ceiling_enabled(bot):
        aggregate_value_for_ceiling = await exchange.calculate_market_budget(
            quote_currency, bypass_cache=True
        )
    max_deals = await calculate_soft_ceiling(ctx, aggregate_value_for_ceiling or 0.0)
    logger.info(f"  📊 Soft ceiling: max_deals={max_deals} (raw={bot.strategy_config.get('max_concurrent_deals', 1)})")

    # Persist the computed value so the bot list can display it
    if is_soft_ceiling_enabled(bot):
        bot.soft_ceiling_effective_max = max_deals
        await db.commit()

    # 4. Calculate budget (uses max_deals for split division)
    aggregate_value = aggregate_value_for_ceiling
    quote_balance, aggregate_value = await _calculate_budget(
        ctx, position, quote_currency, aggregate_value,
        effective_max_deals=max_deals,
    )

    # 5. Log AI thinking immediately after analysis (if AI bot and not already logged in batch mode)
    if bot.strategy_type == "ai_autonomous" and not signal_data.get("_already_logged", False):
        logger.warning(f"  ⚠️ save_ai_log called despite _already_logged check! Bot #{bot.id} {product_id}")
        logger.warning(f"  _already_logged={signal_data.get('_already_logged')}")
        if logger.isEnabledFor(logging.DEBUG):
            import traceback
            stack = "".join(traceback.format_stack()[-5:-1])
            logger.debug(f"  Call stack:\n{stack}")

        ai_signal = signal_data.get("signal_type", "none")
        if ai_signal == "buy":
            decision = "buy"
        elif ai_signal == "sell":
            decision = "sell"
        else:
            decision = "hold"
        await save_ai_log(db, bot, product_id, signal_data, decision, current_price, position)

    # 6. Decide buy
    should_buy, quote_amount, buy_reason = await _decide_buy(
        ctx, signal_data, position, quote_balance, aggregate_value,
        open_positions_count=open_positions_count,
        max_deals=max_deals,
    )

    # 7. Execute buy
    if should_buy:
        buy_result = await _execute_buy_trade(
            ctx, position, quote_amount, quote_balance,
            signal_data, aggregate_value, buy_reason,
        )
        if buy_result:
            return buy_result

    # 8. Sell decision + execution
    if position is not None:
        # Re-fetch position to guard against TOCTOU: a concurrent pair task
        # or the limit order monitor could have closed the position between
        # the initial fetch (line 111) and this sell decision.
        # Skip re-fetch for position_override — the caller owns that object.
        if not _position_is_override:
            fresh_position = await get_active_position(db, bot, product_id)
            if fresh_position is None or fresh_position.status != "open":
                logger.info(
                    f"  ⚠️ Position #{position.id} was closed by another process "
                    f"before sell decision — skipping"
                )
                position = None
            else:
                position = fresh_position
        if position is not None:
            sell_result = await _decide_and_execute_sell(
                ctx, position, signal_data, candles, candles_by_timeframe,
            )
            if sell_result:
                return sell_result

    # Commit any pending changes (like AI logs)
    await db.commit()

    return {"action": "none", "reason": "Signal detected but no action criteria met", "signal": signal_data}
