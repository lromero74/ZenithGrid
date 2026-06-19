"""
Automation Engine

Evaluates trigger conditions and executes actions for user-configured
automation rules. Rules are account-scoped (HARD RULE from AGENTS.md).

Trigger types:
- price_threshold: fires when a symbol's price crosses a target
- profitability_threshold: fires when account P&L changes by X% over a time window
- volatility_threshold: fires when ATR-based volatility exceeds a threshold
- holding_threshold: fires when a position has been held longer than N hours
- period_check: fires every N minutes (scheduled)

Action types:
- cancel_open_orders: cancel all pending orders for a bot or account
- sell_all_positions: market-sell all open positions for a bot or account
- stop_trading: stop all bots on the account
- stop_strategies: stop specific bot(s)
- send_notification: send a Telegram notification
- start_bot: start a specific bot
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AutomationRule, Bot, Position
from app.utils.timeutil import utcnow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trigger evaluators
# ---------------------------------------------------------------------------


async def evaluate_price_threshold(
    rule: AutomationRule,
    db: AsyncSession,
    exchange: Any,
) -> bool:
    """Check if a price threshold has been crossed.

    trigger_config: {"symbol": "BTC-USD", "target_price": 100000, "direction": "above"|"below"}
    """
    config = rule.trigger_config or {}
    symbol = config.get("symbol")
    target_price = float(config.get("target_price", 0))
    direction = config.get("direction", "above")

    if not symbol or target_price <= 0:
        return False

    try:
        current_price = await exchange.get_current_price(symbol)
    except Exception as e:
        logger.warning(f"Automation rule '{rule.name}': failed to get price for {symbol}: {e}")
        return False

    if direction == "above":
        return current_price >= target_price
    else:
        return current_price <= target_price


async def evaluate_holding_threshold(
    rule: AutomationRule,
    db: AsyncSession,
) -> bool:
    """Check if any open position has been held longer than the threshold.

    trigger_config: {"hours": 24, "product_id": "BTC-USD" (optional)}
    """
    from datetime import timedelta

    config = rule.trigger_config or {}
    hours = float(config.get("hours", 0))
    product_id = config.get("product_id")

    if hours <= 0:
        return False

    cutoff = utcnow() - timedelta(hours=hours)
    query = select(Position).where(
        Position.account_id == rule.account_id,
        Position.status == "open",
        Position.opened_at <= cutoff,
    )
    if product_id:
        query = query.where(Position.product_id == product_id)

    result = await db.execute(query)
    positions = result.scalars().all()
    return len(positions) > 0


async def evaluate_period_check(
    rule: AutomationRule,
    db: AsyncSession,
) -> bool:
    """Check if it's time for a periodic trigger.

    trigger_config: {"interval_minutes": 60}
    """
    from datetime import timedelta

    config = rule.trigger_config or {}
    interval = float(config.get("interval_minutes", 0))

    if interval <= 0:
        return False

    if rule.last_fired_at is None:
        return True  # Never fired — fire immediately

    next_fire = rule.last_fired_at + timedelta(minutes=interval)
    return utcnow() >= next_fire


async def evaluate_profitability_threshold(
    rule: AutomationRule,
    db: AsyncSession,
) -> bool:
    """Check if account P&L has changed by more than the threshold.

    Simplified: compares current open P&L percentage against the threshold.
    trigger_config: {"percent_change": -5.0}
    """
    config = rule.trigger_config or {}
    percent_change = float(config.get("percent_change", 0))

    if percent_change == 0:
        return False

    # Sum open positions' profit percentage for this account
    result = await db.execute(
        select(Position).where(
            Position.account_id == rule.account_id,
            Position.status == "open",
        )
    )
    positions = result.scalars().all()

    if not positions:
        return False

    avg_pnl_pct = 0.0
    count = 0
    for pos in positions:
        if pos.profit_percentage is not None:
            avg_pnl_pct += pos.profit_percentage
            count += 1

    if count == 0:
        return False

    avg_pnl_pct /= count

    if percent_change < 0:
        # Looking for a drop
        return avg_pnl_pct <= percent_change
    else:
        # Looking for a gain
        return avg_pnl_pct >= percent_change


# ---------------------------------------------------------------------------
# Action executors
# ---------------------------------------------------------------------------


async def execute_cancel_open_orders(
    rule: AutomationRule,
    db: AsyncSession,
    exchange: Any,
) -> str:
    """Cancel all pending orders for a bot or all bots on the account."""
    from app.models import PendingOrder

    config = rule.action_config or {}
    bot_id = config.get("bot_id")

    query = select(PendingOrder).where(PendingOrder.account_id == rule.account_id)
    if bot_id:
        query = query.where(PendingOrder.bot_id == bot_id)

    result = await db.execute(query)
    orders = result.scalars().all()

    cancelled = 0
    for order in orders:
        try:
            if hasattr(exchange, "cancel_order"):
                await exchange.cancel_order(order.exchange_order_id)
            await db.delete(order)
            cancelled += 1
        except Exception as e:
            logger.warning(f"Failed to cancel order {order.id}: {e}")

    await db.commit()
    return f"Cancelled {cancelled} open orders"


async def execute_sell_all_positions(
    rule: AutomationRule,
    db: AsyncSession,
    exchange: Any,
) -> str:
    """Market-sell all open positions for a bot or all bots on the account."""
    config = rule.action_config or {}
    bot_id = config.get("bot_id")

    query = select(Position).where(
        Position.account_id == rule.account_id,
        Position.status == "open",
    )
    if bot_id:
        query = query.where(Position.bot_id == bot_id)

    result = await db.execute(query)
    positions = result.scalars().all()

    sold = 0
    for pos in positions:
        try:
            price = await exchange.get_current_price(pos.product_id)
            # Use the existing sell executor for proper trade recording
            from app.trading_engine_v2 import StrategyTradingEngine
            from app.strategies import StrategyRegistry

            bot_result = await db.execute(select(Bot).where(Bot.id == pos.bot_id))
            bot = bot_result.scalars().first()
            if not bot:
                continue

            strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)
            engine = StrategyTradingEngine(
                db=db, exchange=exchange, bot=bot, strategy=strategy,
                product_id=pos.product_id,
            )
            await engine.execute_sell(pos, price, force_market=True)
            sold += 1
        except Exception as e:
            logger.warning(f"Failed to sell position {pos.id}: {e}")

    return f"Sold {sold} positions"


async def execute_stop_trading(
    rule: AutomationRule,
    db: AsyncSession,
) -> str:
    """Stop all active bots on the account."""
    result = await db.execute(
        select(Bot).where(
            Bot.account_id == rule.account_id,
            Bot.is_active.is_(True),
        )
    )
    bots = result.scalars().all()

    stopped = 0
    for bot in bots:
        bot.is_active = False
        stopped += 1

    await db.commit()
    return f"Stopped {stopped} bots"


async def execute_stop_strategies(
    rule: AutomationRule,
    db: AsyncSession,
) -> str:
    """Stop specific bot(s) by ID."""
    config = rule.action_config or {}
    bot_ids = config.get("bot_ids", [])

    if not bot_ids:
        return "No bots specified"

    stopped = 0
    for bid in bot_ids:
        result = await db.execute(select(Bot).where(Bot.id == bid))
        bot = result.scalars().first()
        if bot and bot.is_active:
            bot.is_active = False
            stopped += 1

    await db.commit()
    return f"Stopped {stopped} bots"


async def execute_start_bot(
    rule: AutomationRule,
    db: AsyncSession,
) -> str:
    """Start a specific bot by ID."""
    config = rule.action_config or {}
    bot_id = config.get("bot_id")

    if not bot_id:
        return "No bot specified"

    result = await db.execute(select(Bot).where(Bot.id == bot_id))
    bot = result.scalars().first()

    if not bot:
        return f"Bot {bot_id} not found"

    if bot.is_active:
        return f"Bot '{bot.name}' already active"

    bot.is_active = True
    bot.last_started_at = utcnow()
    await db.commit()
    return f"Started bot '{bot.name}'"


async def execute_send_notification(
    rule: AutomationRule,
    db: AsyncSession,
) -> str:
    """Send a Telegram notification."""
    from app.services.telegram_service import get_telegram_settings, send_telegram_message

    config = rule.action_config or {}
    message = config.get("message", f"Automation rule '{rule.name}' triggered")

    settings = await get_telegram_settings(db, rule.user_id)
    if not settings:
        return "No Telegram settings configured"

    await send_telegram_message(settings.bot_token, settings.chat_id, message)
    return "Notification sent"


# ---------------------------------------------------------------------------
# Engine: evaluate a single rule
# ---------------------------------------------------------------------------


async def evaluate_rule(
    rule: AutomationRule,
    db: AsyncSession,
    exchange: Optional[Any] = None,
) -> Optional[str]:
    """Evaluate a single automation rule. If the trigger fires, execute the action.

    Returns the action result string if the rule fired, None otherwise.
    """
    if not rule.enabled:
        return None

    # Evaluate trigger
    triggered = False

    if rule.trigger_type == "price_threshold":
        if exchange is None:
            return None
        triggered = await evaluate_price_threshold(rule, db, exchange)

    elif rule.trigger_type == "holding_threshold":
        triggered = await evaluate_holding_threshold(rule, db)

    elif rule.trigger_type == "period_check":
        triggered = await evaluate_period_check(rule, db)

    elif rule.trigger_type == "profitability_threshold":
        triggered = await evaluate_profitability_threshold(rule, db)

    else:
        logger.warning(f"Automation rule '{rule.name}': unknown trigger type '{rule.trigger_type}'")
        return None

    if not triggered:
        return None

    logger.info(f"Automation rule '{rule.name}' triggered — executing action '{rule.action_type}'")

    # Execute action
    action_result = "Unknown action"

    try:
        if rule.action_type == "cancel_open_orders":
            if exchange is None:
                return "Exchange unavailable"
            action_result = await execute_cancel_open_orders(rule, db, exchange)

        elif rule.action_type == "sell_all_positions":
            if exchange is None:
                return "Exchange unavailable"
            action_result = await execute_sell_all_positions(rule, db, exchange)

        elif rule.action_type == "stop_trading":
            action_result = await execute_stop_trading(rule, db)

        elif rule.action_type == "stop_strategies":
            action_result = await execute_stop_strategies(rule, db)

        elif rule.action_type == "start_bot":
            action_result = await execute_start_bot(rule, db)

        elif rule.action_type == "send_notification":
            action_result = await execute_send_notification(rule, db)

        else:
            logger.warning(f"Automation rule '{rule.name}': unknown action type '{rule.action_type}'")
            return f"Unknown action type: {rule.action_type}"

    except Exception as e:
        logger.error(f"Automation rule '{rule.name}' action failed: {e}", exc_info=True)
        action_result = f"Action failed: {e}"

    # Update rule state
    rule.last_fired_at = utcnow()
    rule.fire_count = (rule.fire_count or 0) + 1
    await db.commit()

    logger.info(f"Automation rule '{rule.name}' result: {action_result}")
    return action_result


async def evaluate_all_rules(
    db: AsyncSession,
    exchange: Optional[Any] = None,
    account_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Evaluate all enabled automation rules (optionally filtered by account).

    Returns a list of {rule_id, rule_name, result} dicts for rules that fired.
    """
    query = select(AutomationRule).where(AutomationRule.enabled.is_(True))
    if account_id is not None:
        query = query.where(AutomationRule.account_id == account_id)

    result = await db.execute(query)
    rules = result.scalars().all()

    fired = []
    for rule in rules:
        action_result = await evaluate_rule(rule, db, exchange)
        if action_result is not None:
            fired.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "result": action_result,
            })

    return fired
