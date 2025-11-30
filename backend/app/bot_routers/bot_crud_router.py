"""
Bot CRUD Router

Handles bot creation, reading, updating, deletion, and strategy listing.
Also includes bot stats and clone operations.
"""

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bot, Position
from app.strategies import StrategyDefinition, StrategyRegistry
from app.coinbase_unified_client import CoinbaseClient
from app.bot_routers.schemas import BotCreate, BotUpdate, BotResponse, BotStats

logger = logging.getLogger(__name__)
router = APIRouter()


# Strategy Endpoints
@router.get("/strategies", response_model=List[StrategyDefinition])
async def list_strategies():
    """Get list of all available trading strategies"""
    return StrategyRegistry.list_strategies()


@router.get("/strategies/{strategy_id}", response_model=StrategyDefinition)
async def get_strategy_definition(strategy_id: str):
    """Get detailed definition for a specific strategy"""
    try:
        return StrategyRegistry.get_definition(strategy_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Bot CRUD Endpoints
@router.post("/", response_model=BotResponse, status_code=201)
async def create_bot(bot_data: BotCreate, db: AsyncSession = Depends(get_db)):
    """Create a new trading bot"""
    # Validate strategy exists
    try:
        _strategy_def = StrategyRegistry.get_definition(bot_data.strategy_type)  # noqa: F841
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {bot_data.strategy_type}")

    # Validate strategy config (create temporary instance to validate)
    try:
        StrategyRegistry.get_strategy(bot_data.strategy_type, bot_data.strategy_config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid strategy config: {str(e)}")

    # Check if name is unique
    query = select(Bot).where(Bot.name == bot_data.name)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(status_code=400, detail=f"Bot with name '{bot_data.name}' already exists")

    # Validate all pairs use the same quote currency (BTC or USD, not mixed)
    all_pairs = bot_data.product_ids if bot_data.product_ids else ([bot_data.product_id] if bot_data.product_id else [])
    quote_currency = None
    if all_pairs and len(all_pairs) > 0:
        quote_currencies = set()
        for pair in all_pairs:
            if "-" in pair:
                quote = pair.split("-")[1]
                quote_currencies.add(quote)

        if len(quote_currencies) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"All trading pairs must use the same quote currency. Found: {', '.join(sorted(quote_currencies))}. "
                f"Please use only BTC-based pairs OR only USD-based pairs, not a mix.",
            )

        # Set quote_currency for market_focus correction
        quote_currency = quote_currencies.pop() if quote_currencies else None

    # Auto-correct market_focus for AI autonomous bots based on quote currency
    if bot_data.strategy_type == "ai_autonomous" and quote_currency:
        if "market_focus" in bot_data.strategy_config:
            if bot_data.strategy_config["market_focus"] != quote_currency:
                logger.warning(
                    f"Auto-correcting market_focus from '{bot_data.strategy_config['market_focus']}' to '{quote_currency}' "
                    f"to match {quote_currency}-based trading pairs"
                )
                bot_data.strategy_config["market_focus"] = quote_currency

    # Create bot
    bot = Bot(
        name=bot_data.name,
        description=bot_data.description,
        strategy_type=bot_data.strategy_type,
        strategy_config=bot_data.strategy_config,
        product_id=bot_data.product_id,
        product_ids=bot_data.product_ids or [],
        split_budget_across_pairs=bot_data.split_budget_across_pairs,
        reserved_btc_balance=bot_data.reserved_btc_balance,
        reserved_usd_balance=bot_data.reserved_usd_balance,
        budget_percentage=bot_data.budget_percentage,
        is_active=False,
    )

    db.add(bot)
    await db.commit()
    await db.refresh(bot)

    # Add counts
    response = BotResponse.model_validate(bot)
    response.open_positions_count = 0
    response.total_positions_count = 0

    return response


@router.get("/", response_model=List[BotResponse])
async def list_bots(active_only: bool = False, db: AsyncSession = Depends(get_db)):
    """Get list of all bots"""
    import asyncio

    query = select(Bot).order_by(desc(Bot.created_at))

    if active_only:
        query = query.where(Bot.is_active)

    result = await db.execute(query)
    bots = result.scalars().all()

    # Initialize coinbase client for budget calculations
    coinbase = CoinbaseClient()

    # Pre-fetch aggregate values ONCE (not per-bot) to avoid repeated API calls
    aggregate_btc_value = None
    aggregate_usd_value = None

    try:
        aggregate_btc_value = await coinbase.calculate_aggregate_btc_value()
    except Exception as e:
        logger.warning(f"Could not calculate aggregate BTC value: {e}")

    try:
        aggregate_usd_value = await coinbase.calculate_aggregate_usd_value()
    except Exception as e:
        logger.warning(f"Could not calculate aggregate USD value: {e}")

    # Pre-fetch all open position prices in parallel
    all_open_positions_query = select(Position).where(Position.status == "open")
    all_open_result = await db.execute(all_open_positions_query)
    all_open_positions = all_open_result.scalars().all()

    # Get unique product IDs and fetch prices in parallel
    unique_products = list({p.product_id for p in all_open_positions})

    async def fetch_price(product_id: str):
        try:
            price = await coinbase.get_current_price(product_id)
            return (product_id, price)
        except Exception:
            return (product_id, None)

    # Batch fetch prices (15 at a time to avoid rate limits)
    position_prices = {}
    batch_size = 15
    for i in range(0, len(unique_products), batch_size):
        batch = unique_products[i:i + batch_size]
        batch_results = await asyncio.gather(*[fetch_price(pid) for pid in batch])
        for pid, price in batch_results:
            if price is not None:
                position_prices[pid] = price
        if i + batch_size < len(unique_products):
            await asyncio.sleep(0.2)

    # Add position counts and PnL for each bot
    bot_responses = []
    for bot in bots:
        # Get all positions for this bot
        all_pos_query = select(Position).where(Position.bot_id == bot.id)
        all_pos_result = await db.execute(all_pos_query)
        all_positions = all_pos_result.scalars().all()

        open_positions = [p for p in all_positions if p.status == "open"]
        closed_positions = [p for p in all_positions if p.status == "closed"]

        # Calculate total PnL (only from closed positions)
        # Note: Open positions don't have realized profit_usd yet
        total_pnl_usd = 0.0
        for pos in closed_positions:
            if pos.profit_usd:
                total_pnl_usd += pos.profit_usd

        # Calculate avg daily PnL (total PnL / days since bot created)
        days_active = (datetime.utcnow() - bot.created_at).total_seconds() / 86400
        avg_daily_pnl_usd = total_pnl_usd / days_active if days_active > 0 else 0.0

        # Calculate trades per day (closed positions / days active)
        trades_per_day = len(closed_positions) / days_active if days_active > 0 else 0.0

        # Calculate win rate (percentage of profitable closed positions)
        winning_positions = [p for p in closed_positions if p.profit_usd is not None and p.profit_usd > 0]
        win_rate = (len(winning_positions) / len(closed_positions) * 100) if closed_positions else 0.0

        # Calculate budget utilization percentage (for all bots with open positions)
        insufficient_funds = False
        budget_utilization_percentage = 0.0
        # Check for both "max_concurrent_deals" and "max_concurrent_positions" (used by bull_flag)
        max_concurrent_deals = (
            bot.strategy_config.get("max_concurrent_deals")
            or bot.strategy_config.get("max_concurrent_positions")
            or 1
        )

        try:
            quote_currency = bot.get_quote_currency()

            # Use pre-fetched aggregate values
            if quote_currency == "BTC":
                aggregate_value = aggregate_btc_value
            else:  # USD
                aggregate_value = aggregate_usd_value

            if aggregate_value is None:
                raise ValueError(f"No aggregate {quote_currency} value available")

            reserved_balance = bot.get_reserved_balance(aggregate_value)

            # Calculate budget utilization using pre-fetched prices
            total_in_positions_value = 0.0
            for position in open_positions:
                current_price = position_prices.get(position.product_id)
                if current_price is not None:
                    position_value = position.total_base_acquired * current_price
                    total_in_positions_value += position_value
                else:
                    # Fallback to quote spent if price unavailable
                    total_in_positions_value += position.total_quote_spent

            if reserved_balance > 0:
                budget_utilization_percentage = (total_in_positions_value / reserved_balance) * 100

            # Check if bot has insufficient funds for new positions
            if len(open_positions) < max_concurrent_deals:
                total_in_positions = sum(p.total_quote_spent for p in open_positions)
                available_budget = reserved_balance - total_in_positions
                min_per_position = reserved_balance / max(max_concurrent_deals, 1)
                insufficient_funds = available_budget < min_per_position

        except Exception as e:
            logger.error(f"Error calculating budget for bot {bot.id}: {e}")
            # Don't fail the whole request if budget calc fails
            insufficient_funds = False
            budget_utilization_percentage = 0.0

        bot_response = BotResponse.model_validate(bot)
        bot_response.open_positions_count = len(open_positions)
        bot_response.total_positions_count = len(all_positions)
        bot_response.closed_positions_count = len(closed_positions)
        bot_response.trades_per_day = trades_per_day
        bot_response.total_pnl_usd = total_pnl_usd
        bot_response.avg_daily_pnl_usd = avg_daily_pnl_usd
        bot_response.insufficient_funds = insufficient_funds
        bot_response.budget_utilization_percentage = budget_utilization_percentage
        bot_response.win_rate = win_rate
        bot_responses.append(bot_response)

    return bot_responses


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    """Get details for a specific bot"""
    query = select(Bot).where(Bot.id == bot_id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Count positions
    open_pos_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
    total_pos_query = select(Position).where(Position.bot_id == bot.id)

    open_result = await db.execute(open_pos_query)
    total_result = await db.execute(total_pos_query)

    bot_response = BotResponse.model_validate(bot)
    bot_response.open_positions_count = len(open_result.scalars().all())
    bot_response.total_positions_count = len(total_result.scalars().all())

    return bot_response


@router.put("/{bot_id}", response_model=BotResponse)
async def update_bot(bot_id: int, bot_update: BotUpdate, db: AsyncSession = Depends(get_db)):
    """Update bot configuration"""
    query = select(Bot).where(Bot.id == bot_id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Allow updates while bot is active (3Commas style)
    # Changes will apply to new signals/positions, not existing open positions

    # Update fields
    if bot_update.name is not None:
        # Check name uniqueness
        name_query = select(Bot).where(Bot.name == bot_update.name, Bot.id != bot_id)
        name_result = await db.execute(name_query)
        if name_result.scalars().first():
            raise HTTPException(status_code=400, detail=f"Bot with name '{bot_update.name}' already exists")
        bot.name = bot_update.name

    if bot_update.description is not None:
        bot.description = bot_update.description

    if bot_update.strategy_config is not None:
        # Validate new config
        try:
            StrategyRegistry.get_strategy(bot.strategy_type, bot_update.strategy_config)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid strategy config: {str(e)}")
        bot.strategy_config = bot_update.strategy_config

    if bot_update.product_id is not None:
        bot.product_id = bot_update.product_id

    if bot_update.product_ids is not None:
        bot.product_ids = bot_update.product_ids

    if bot_update.split_budget_across_pairs is not None:
        bot.split_budget_across_pairs = bot_update.split_budget_across_pairs

    if bot_update.reserved_btc_balance is not None:
        bot.reserved_btc_balance = bot_update.reserved_btc_balance

    if bot_update.reserved_usd_balance is not None:
        bot.reserved_usd_balance = bot_update.reserved_usd_balance

    if bot_update.budget_percentage is not None:
        bot.budget_percentage = bot_update.budget_percentage

    # Validate all pairs use the same quote currency after update
    final_pairs = bot.product_ids if bot.product_ids else ([bot.product_id] if bot.product_id else [])
    quote_currency = None
    if final_pairs and len(final_pairs) > 0:
        quote_currencies = set()
        for pair in final_pairs:
            if "-" in pair:
                quote = pair.split("-")[1]
                quote_currencies.add(quote)

        if len(quote_currencies) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"All trading pairs must use the same quote currency. Found: {', '.join(sorted(quote_currencies))}. "
                f"Please use only BTC-based pairs OR only USD-based pairs, not a mix.",
            )

        # Set quote_currency for market_focus correction
        quote_currency = quote_currencies.pop() if quote_currencies else None

    # Auto-correct market_focus for AI autonomous bots based on quote currency
    if bot.strategy_type == "ai_autonomous" and quote_currency:
        if "market_focus" in bot.strategy_config:
            if bot.strategy_config["market_focus"] != quote_currency:
                logger.warning(
                    f"Auto-correcting market_focus from '{bot.strategy_config['market_focus']}' to '{quote_currency}' "
                    f"to match {quote_currency}-based trading pairs for bot '{bot.name}'"
                )
                bot.strategy_config["market_focus"] = quote_currency

    bot.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(bot)

    bot_response = BotResponse.model_validate(bot)
    return bot_response


@router.delete("/{bot_id}")
async def delete_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a bot (only if it has no open positions)"""
    query = select(Bot).where(Bot.id == bot_id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Check for open positions
    open_pos_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
    open_result = await db.execute(open_pos_query)
    if open_result.scalars().first():
        raise HTTPException(status_code=400, detail="Cannot delete bot with open positions. Close positions first.")

    await db.delete(bot)
    await db.commit()

    return {"message": f"Bot '{bot.name}' deleted successfully"}


@router.post("/{bot_id}/clone", response_model=BotResponse, status_code=201)
async def clone_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    """
    Clone/duplicate a bot configuration

    Creates a copy of the bot with:
    - Same strategy and configuration
    - Same trading pairs
    - Incremented name (e.g., "My Bot" → "My Bot (Copy)")
    - Starts in stopped state (is_active = False)
    - No positions copied (fresh start)
    """
    # Get original bot
    query = select(Bot).where(Bot.id == bot_id)
    result = await db.execute(query)
    original_bot = result.scalars().first()

    if not original_bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Generate new name with (Copy) suffix
    new_name = original_bot.name

    # Check if name already has (Copy X) pattern
    import re

    copy_match = re.search(r"\(Copy(?: (\d+))?\)$", new_name)

    if copy_match:
        # Name already has (Copy) or (Copy N), increment
        copy_num = copy_match.group(1)
        if copy_num:
            # (Copy N) → (Copy N+1)
            next_num = int(copy_num) + 1
            new_name = re.sub(r"\(Copy \d+\)$", f"(Copy {next_num})", new_name)
        else:
            # (Copy) → (Copy 2)
            new_name = re.sub(r"\(Copy\)$", "(Copy 2)", new_name)
    else:
        # No (Copy) yet → add (Copy)
        new_name = f"{new_name} (Copy)"

    # Ensure name is unique (in case of conflicts)
    counter = 2
    base_new_name = new_name
    while True:
        name_check_query = select(Bot).where(Bot.name == new_name)
        name_check_result = await db.execute(name_check_query)
        if not name_check_result.scalars().first():
            break
        new_name = f"{base_new_name} {counter}"
        counter += 1

    # Create cloned bot
    cloned_bot = Bot(
        name=new_name,
        description=original_bot.description,
        strategy_type=original_bot.strategy_type,
        strategy_config=original_bot.strategy_config.copy() if original_bot.strategy_config else {},
        product_id=original_bot.product_id,
        product_ids=original_bot.product_ids.copy() if original_bot.product_ids else [],
        split_budget_across_pairs=original_bot.split_budget_across_pairs,
        reserved_btc_balance=0.0,  # Don't copy reserved balances - user must allocate fresh
        reserved_usd_balance=0.0,
        is_active=False,  # Start stopped
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(cloned_bot)
    await db.commit()
    await db.refresh(cloned_bot)

    bot_response = BotResponse.model_validate(cloned_bot)
    return bot_response


@router.get("/{bot_id}/stats", response_model=BotStats)
async def get_bot_stats(bot_id: int, db: AsyncSession = Depends(get_db)):
    """Get statistics for a specific bot"""
    query = select(Bot).where(Bot.id == bot_id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Get all positions for this bot
    all_pos_query = select(Position).where(Position.bot_id == bot.id)
    all_result = await db.execute(all_pos_query)
    all_positions = all_result.scalars().all()

    open_positions = [p for p in all_positions if p.status == "open"]
    closed_positions = [p for p in all_positions if p.status == "closed"]

    # Calculate total profit
    total_profit = sum(p.profit_quote for p in closed_positions if p.profit_quote)

    # Calculate win rate
    winning_positions = [p for p in closed_positions if p.profit_quote and p.profit_quote > 0]
    win_rate = (len(winning_positions) / len(closed_positions) * 100) if closed_positions else 0.0

    # Check if bot has insufficient funds for new positions and calculate budget utilization
    insufficient_funds = False
    budget_utilization_percentage = 0.0
    # Check for both "max_concurrent_deals" and "max_concurrent_positions" (used by bull_flag)
    max_concurrent_deals = (
        bot.strategy_config.get("max_concurrent_deals")
        or bot.strategy_config.get("max_concurrent_positions")
        or 1
    )

    try:
        coinbase = CoinbaseClient()
        quote_currency = bot.get_quote_currency()

        if quote_currency == "BTC":
            aggregate_value = await coinbase.calculate_aggregate_btc_value()
        else:  # USD
            aggregate_value = await coinbase.calculate_aggregate_usd_value()

        reserved_balance = bot.get_reserved_balance(aggregate_value)

        # Calculate current value of open positions (not just spent)
        total_in_positions_value = 0.0
        for position in open_positions:
            try:
                current_price = await coinbase.get_current_price(position.product_id)
                position_value = position.total_base_acquired * current_price
                total_in_positions_value += position_value
            except Exception as _:
                # Fallback to quote spent if can't get current price
                logger.warning(f"Could not get current price for position {position.id}, using quote spent")
                total_in_positions_value += position.total_quote_spent

        # Calculate budget utilization percentage
        if reserved_balance > 0:
            budget_utilization_percentage = (total_in_positions_value / reserved_balance) * 100

        # Check insufficient funds if bot has room for more positions
        if len(open_positions) < max_concurrent_deals:
            available_budget = reserved_balance - total_in_positions_value
            min_per_position = reserved_balance / max(max_concurrent_deals, 1)
            insufficient_funds = available_budget < min_per_position
    except Exception as e:
        logger.error(f"Error calculating budget for bot {bot_id}: {e}")
        # Don't fail the whole request if budget calc fails
        insufficient_funds = False
        budget_utilization_percentage = 0.0

    return BotStats(
        total_positions=len(all_positions),
        open_positions=len(open_positions),
        closed_positions=len(closed_positions),
        max_concurrent_deals=max_concurrent_deals,
        total_profit_btc=total_profit,
        total_profit_quote=total_profit,  # Same value, field name frontend expects
        win_rate=win_rate,
        insufficient_funds=insufficient_funds,
        budget_utilization_percentage=budget_utilization_percentage,
    )
