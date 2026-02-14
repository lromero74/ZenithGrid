"""
Bot CRUD Router

Handles bot creation, reading, updating, deletion, and strategy listing.
Also includes bot stats and clone operations.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account, Bot, Position, User
from app.strategies import StrategyDefinition, StrategyRegistry
from app.coinbase_unified_client import CoinbaseClient
from app.exchange_clients.factory import create_exchange_client
from app.bot_routers.schemas import BotCreate, BotUpdate, BotResponse, BotStats
from app.routers.auth_dependencies import get_current_user_optional

logger = logging.getLogger(__name__)


async def get_coinbase_from_db(db: AsyncSession) -> CoinbaseClient:
    """Get Coinbase client from the first active CEX account in the database."""
    from sqlalchemy import select

    result = await db.execute(
        select(Account).where(
            Account.type == "cex",
            Account.is_active.is_(True),
            Account.is_paper_trading.is_not(True)  # Exclude paper trading accounts
        ).order_by(Account.is_default.desc(), Account.created_at).limit(1)
    )
    account = result.scalar_one_or_none()

    if not account or not account.api_key_name or not account.api_private_key:
        return None

    return create_exchange_client(
        exchange_type="cex",
        coinbase_key_name=account.api_key_name,
        coinbase_private_key=account.api_private_key,
    )
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
async def create_bot(
    bot_data: BotCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
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

    # Create bot instance (but don't commit yet - need to validate bidirectional budget first)
    bot = Bot(
        name=bot_data.name,
        description=bot_data.description,
        account_id=bot_data.account_id,
        strategy_type=bot_data.strategy_type,
        strategy_config=bot_data.strategy_config,
        product_id=bot_data.product_id,
        product_ids=bot_data.product_ids or [],
        split_budget_across_pairs=bot_data.split_budget_across_pairs,
        reserved_btc_balance=bot_data.reserved_btc_balance,
        reserved_usd_balance=bot_data.reserved_usd_balance,
        budget_percentage=bot_data.budget_percentage,
        is_active=False,
        user_id=current_user.id if current_user else None,
    )

    # Validate bidirectional budget if enabled
    if bot.strategy_config.get("enable_bidirectional", False):
        logger.info(f"Validating bidirectional budget for new bot '{bot.name}'")

        # Validate percentages sum to 100%
        long_pct = bot.strategy_config.get("long_budget_percentage", 50.0)
        short_pct = bot.strategy_config.get("short_budget_percentage", 50.0)

        if abs((long_pct + short_pct) - 100.0) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=f"Long and short budget percentages must sum to 100% (got {long_pct}% + {short_pct}% = {long_pct + short_pct}%)"
            )

        # Get exchange client for this bot's account
        try:
            exchange = await create_exchange_client(db, bot.account_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to connect to exchange: {e}")

        # Get raw balances
        try:
            balances = await exchange.get_account()
            raw_usd = balances.get("USD", 0.0) + balances.get("USDC", 0.0) + balances.get("USDT", 0.0)
            raw_btc = balances.get("BTC", 0.0)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch account balances: {e}")

        # Calculate aggregate values
        try:
            if quote_currency == "USD":
                aggregate_usd_value = await exchange.calculate_aggregate_usd_value()
                aggregate_btc_value = raw_btc  # For USD bots, BTC aggregate is just raw BTC
            else:
                # Bypass cache for bot creation to ensure accurate budget validation
                aggregate_btc_value = await exchange.calculate_aggregate_btc_value(bypass_cache=True)
                aggregate_usd_value = raw_usd  # For BTC bots, USD aggregate is just raw USD

            # Get current BTC price for validation
            current_btc_price = await exchange.get_btc_usd_price()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to calculate aggregate values: {e}")

        # Calculate bot's total budget
        budget_pct = bot.budget_percentage or 0.0
        if budget_pct <= 0:
            raise HTTPException(status_code=400, detail="Budget percentage must be > 0 for bidirectional bots")

        bot_budget_usd = aggregate_usd_value * (budget_pct / 100.0)
        bot_budget_btc = aggregate_btc_value * (budget_pct / 100.0)

        # Calculate required reservations
        required_usd = bot_budget_usd * (long_pct / 100.0)
        required_btc = bot_budget_btc * (short_pct / 100.0)

        # Validate availability using budget calculator
        from app.services.budget_calculator import validate_bidirectional_budget

        is_valid, error_msg = await validate_bidirectional_budget(
            db, bot, required_usd, required_btc, current_btc_price
        )

        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        # Set reservations on bot
        bot.reserved_usd_for_longs = required_usd
        bot.reserved_btc_for_shorts = required_btc

        logger.info(
            f"Bidirectional bot validated: ${required_usd:.2f} USD reserved for longs, "
            f"{required_btc:.8f} BTC reserved for shorts"
        )
    else:
        # Non-bidirectional bot - clear any reservations
        bot.reserved_usd_for_longs = 0.0
        bot.reserved_btc_for_shorts = 0.0

    db.add(bot)
    await db.commit()
    await db.refresh(bot)

    # Add counts
    response = BotResponse.model_validate(bot)
    response.open_positions_count = 0
    response.total_positions_count = 0

    return response


@router.get("/", response_model=List[BotResponse])
async def list_bots(
    active_only: bool = False,
    projection_timeframe: Optional[str] = "all",
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get list of all bots with projection stats based on selected timeframe"""
    import asyncio

    query = select(Bot).order_by(desc(Bot.created_at))

    # Filter by user if authenticated
    if current_user:
        query = query.where(Bot.user_id == current_user.id)

    if active_only:
        query = query.where(Bot.is_active)

    result = await db.execute(query)
    bots = result.scalars().all()

    # Initialize coinbase client for budget calculations (from database)
    coinbase = await get_coinbase_from_db(db)
    if not coinbase:
        # Return bots without budget calculations if no CEX account configured
        bot_responses = []
        for bot in bots:
            open_count_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
            open_result = await db.execute(open_count_query)
            open_count = len(open_result.scalars().all())

            total_count_query = select(Position).where(Position.bot_id == bot.id)
            total_result = await db.execute(total_count_query)
            total_count = len(total_result.scalars().all())

            response = BotResponse.model_validate(bot)
            response.open_positions_count = open_count
            response.total_positions_count = total_count
            bot_responses.append(response)
        return bot_responses

    # Pre-fetch aggregate values ONCE (not per-bot) to avoid repeated API calls
    # Fetch BOTH in parallel for better performance
    async def fetch_btc_aggregate():
        try:
            return await coinbase.calculate_aggregate_btc_value()
        except Exception as e:
            logger.warning(f"Could not calculate aggregate BTC value: {e}")
            return None

    async def fetch_usd_aggregate():
        try:
            return await coinbase.calculate_aggregate_usd_value()
        except Exception as e:
            logger.warning(f"Could not calculate aggregate USD value: {e}")
            return None

    aggregate_btc_value, aggregate_usd_value = await asyncio.gather(
        fetch_btc_aggregate(), fetch_usd_aggregate()
    )

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
        total_pnl_btc = 0.0
        for pos in closed_positions:
            profit_usd = pos.profit_usd or 0.0
            total_pnl_usd += profit_usd

            # Calculate profit_btc based on pair type
            if pos.product_id and "-BTC" in pos.product_id:
                # BTC pair: profit_quote IS the BTC profit
                profit_btc = pos.profit_quote or 0.0
            else:
                # USD/USDC/USDT pair: convert USD profit to BTC
                btc_price = pos.btc_usd_price_at_close or pos.btc_usd_price_at_open or 100000.0
                if btc_price > 0:
                    profit_btc = profit_usd / btc_price
                else:
                    profit_btc = 0.0
            total_pnl_btc += profit_btc

        # Calculate avg daily PnL based on selected projection timeframe
        # This prevents wild projections when portfolio value changes due to withdrawals
        # Timeframe mapping: '7d' -> 7 days, '14d' -> 14, '30d' -> 30, '3m' -> 90, '6m' -> 180, '1y' -> 365, 'all' -> all-time
        timeframe_days_map = {
            '7d': 7,
            '14d': 14,
            '30d': 30,
            '3m': 90,
            '6m': 180,
            '1y': 365,
            'all': None  # Use all closed positions
        }

        timeframe_days = timeframe_days_map.get(projection_timeframe, None)  # Default to 'all' if unknown

        if timeframe_days is None:
            # Use all-time for 'all' or unknown timeframes
            recent_closed_positions = closed_positions
        else:
            # Filter to positions closed within the timeframe
            cutoff_date = datetime.utcnow() - timedelta(days=timeframe_days)
            recent_closed_positions = [
                p for p in closed_positions
                if p.closed_at and p.closed_at >= cutoff_date
            ]

        recent_pnl_usd = sum(p.profit_usd for p in recent_closed_positions if p.profit_usd)

        # Calculate recent BTC PnL
        recent_pnl_btc = 0.0
        for pos in recent_closed_positions:
            profit_usd = pos.profit_usd or 0.0

            # Calculate profit_btc based on pair type
            if pos.product_id and "-BTC" in pos.product_id:
                # BTC pair: profit_quote IS the BTC profit
                profit_btc = pos.profit_quote or 0.0
            else:
                # USD/USDC/USDT pair: convert USD profit to BTC
                btc_price = pos.btc_usd_price_at_close or pos.btc_usd_price_at_open or 100000.0
                if btc_price > 0:
                    profit_btc = profit_usd / btc_price
                else:
                    profit_btc = 0.0
            recent_pnl_btc += profit_btc

        # Calculate days in period using the full timeframe window (not time since first trade)
        # This prevents inflated PnL/day when few trades happened recently
        if timeframe_days is None:
            # All-time: use bot age as denominator
            days_in_recent_period = max(1, (datetime.utcnow() - bot.created_at).total_seconds() / 86400)
        else:
            # Specific timeframe: always use the full timeframe window
            days_in_recent_period = timeframe_days

        avg_daily_pnl_usd = recent_pnl_usd / days_in_recent_period
        avg_daily_pnl_btc = recent_pnl_btc / days_in_recent_period

        # Calculate trades per day (use all-time for this metric)
        days_active = (datetime.utcnow() - bot.created_at).total_seconds() / 86400
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
            # Use current position values (already calculated above) for consistency with budget utilization
            if len(open_positions) < max_concurrent_deals:
                available_budget = reserved_balance - total_in_positions_value
                min_per_position = reserved_balance / max(max_concurrent_deals, 1)
                insufficient_funds = available_budget < min_per_position

        except Exception as e:
            logger.error(f"Error calculating budget for bot {bot.id}: {e}")
            # Don't fail the whole request if budget calc fails
            insufficient_funds = False
            budget_utilization_percentage = 0.0

        # Calculate PnL percentage (total_pnl_usd / total capital deployed)
        total_capital_deployed_usd = 0.0
        for pos in closed_positions:
            quote_spent = pos.total_quote_spent or 0.0
            if pos.product_id and "-BTC" in pos.product_id:
                # BTC pair: convert BTC spent to USD
                btc_price = pos.btc_usd_price_at_close or pos.btc_usd_price_at_open or 100000.0
                total_capital_deployed_usd += quote_spent * btc_price
            else:
                total_capital_deployed_usd += quote_spent
        total_pnl_percentage = (total_pnl_usd / total_capital_deployed_usd * 100) if total_capital_deployed_usd > 0 else 0.0

        bot_response = BotResponse.model_validate(bot)
        bot_response.open_positions_count = len(open_positions)
        bot_response.total_positions_count = len(all_positions)
        bot_response.closed_positions_count = len(closed_positions)
        bot_response.trades_per_day = trades_per_day
        bot_response.total_pnl_usd = total_pnl_usd
        bot_response.total_pnl_btc = total_pnl_btc
        bot_response.total_pnl_percentage = total_pnl_percentage
        bot_response.avg_daily_pnl_usd = avg_daily_pnl_usd
        bot_response.avg_daily_pnl_btc = avg_daily_pnl_btc
        bot_response.insufficient_funds = insufficient_funds
        bot_response.budget_utilization_percentage = budget_utilization_percentage
        bot_response.win_rate = win_rate
        bot_responses.append(bot_response)

    return bot_responses


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get details for a specific bot"""
    query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
    if current_user:
        query = query.where(Bot.user_id == current_user.id)
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
async def update_bot(
    bot_id: int,
    bot_update: BotUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Update bot configuration"""
    query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
    if current_user:
        query = query.where(Bot.user_id == current_user.id)
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

    # Recalculate bidirectional reservations if config or budget changed
    config_changed = bot_update.strategy_config is not None
    budget_changed = bot_update.budget_percentage is not None

    if (config_changed or budget_changed) and bot.strategy_config.get("enable_bidirectional", False):
        logger.info(f"Recalculating bidirectional reservations for updated bot '{bot.name}'")

        # Validate percentages sum to 100%
        long_pct = bot.strategy_config.get("long_budget_percentage", 50.0)
        short_pct = bot.strategy_config.get("short_budget_percentage", 50.0)

        if abs((long_pct + short_pct) - 100.0) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=f"Long and short budget percentages must sum to 100% (got {long_pct}% + {short_pct}% = {long_pct + short_pct}%)"
            )

        # Get exchange client
        try:
            exchange = await create_exchange_client(db, bot.account_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to connect to exchange: {e}")

        # Get raw balances and aggregate values
        try:
            balances = await exchange.get_account()
            if quote_currency == "USD":
                aggregate_usd_value = await exchange.calculate_aggregate_usd_value()
                aggregate_btc_value = balances.get("BTC", 0.0)
            else:
                # Bypass cache for bot update to ensure accurate budget validation
                aggregate_btc_value = await exchange.calculate_aggregate_btc_value(bypass_cache=True)
                aggregate_usd_value = balances.get("USD", 0.0) + balances.get("USDC", 0.0) + balances.get("USDT", 0.0)

            current_btc_price = await exchange.get_btc_usd_price()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to calculate aggregate values: {e}")

        # Calculate new reservations
        budget_pct = bot.budget_percentage or 0.0
        if budget_pct <= 0:
            raise HTTPException(status_code=400, detail="Budget percentage must be > 0 for bidirectional bots")

        bot_budget_usd = aggregate_usd_value * (budget_pct / 100.0)
        bot_budget_btc = aggregate_btc_value * (budget_pct / 100.0)

        required_usd = bot_budget_usd * (long_pct / 100.0)
        required_btc = bot_budget_btc * (short_pct / 100.0)

        # Validate availability
        from app.services.budget_calculator import validate_bidirectional_budget

        is_valid, error_msg = await validate_bidirectional_budget(
            db, bot, required_usd, required_btc, current_btc_price
        )

        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        # Update reservations
        bot.reserved_usd_for_longs = required_usd
        bot.reserved_btc_for_shorts = required_btc

        logger.info(
            f"Bidirectional reservations updated: ${required_usd:.2f} USD for longs, "
            f"{required_btc:.8f} BTC for shorts"
        )
    elif config_changed and not bot.strategy_config.get("enable_bidirectional", False):
        # Bidirectional was disabled - release reservations
        bot.reserved_usd_for_longs = 0.0
        bot.reserved_btc_for_shorts = 0.0
        logger.info(f"Bidirectional disabled for bot '{bot.name}' - reservations released")

    await db.commit()
    await db.refresh(bot)

    bot_response = BotResponse.model_validate(bot)
    return bot_response


@router.delete("/{bot_id}")
async def delete_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Delete a bot (only if it has no open positions)"""
    query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
    if current_user:
        query = query.where(Bot.user_id == current_user.id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Check for open positions
    open_pos_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
    open_result = await db.execute(open_pos_query)
    if open_result.scalars().first():
        raise HTTPException(status_code=400, detail="Cannot delete bot with open positions. Close positions first.")

    # Release bidirectional reservations before deletion
    if bot.strategy_config.get("enable_bidirectional", False):
        logger.info(f"Releasing bidirectional reservations for bot '{bot.name}' (${bot.reserved_usd_for_longs:.2f} USD, {bot.reserved_btc_for_shorts:.8f} BTC)")
        bot.reserved_usd_for_longs = 0.0
        bot.reserved_btc_for_shorts = 0.0

    await db.delete(bot)
    await db.commit()

    return {"message": f"Bot '{bot.name}' deleted successfully"}


@router.post("/{bot_id}/clone", response_model=BotResponse, status_code=201)
async def clone_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
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
    # Filter by user if authenticated
    if current_user:
        query = query.where(Bot.user_id == current_user.id)
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
        account_id=original_bot.account_id,  # Clone to same account
        strategy_type=original_bot.strategy_type,
        strategy_config=original_bot.strategy_config.copy() if original_bot.strategy_config else {},
        product_id=original_bot.product_id,
        product_ids=original_bot.product_ids.copy() if original_bot.product_ids else [],
        split_budget_across_pairs=original_bot.split_budget_across_pairs,
        budget_percentage=original_bot.budget_percentage,
        exchange_type=original_bot.exchange_type,
        check_interval_seconds=original_bot.check_interval_seconds,
        reserved_btc_balance=0.0,  # Don't copy reserved balances - user must allocate fresh
        reserved_usd_balance=0.0,
        reserved_usd_for_longs=0.0,
        reserved_btc_for_shorts=0.0,
        is_active=False,  # Start stopped
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        user_id=current_user.id if current_user else None,
    )

    db.add(cloned_bot)
    await db.commit()
    await db.refresh(cloned_bot)

    bot_response = BotResponse.model_validate(cloned_bot)
    return bot_response


@router.post("/{bot_id}/copy-to-account", response_model=BotResponse, status_code=201)
async def copy_bot_to_account(
    bot_id: int,
    target_account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Copy bot configuration to a different account (e.g., live to paper trading or vice versa)

    Creates a copy of the bot with:
    - Same strategy and configuration
    - Same trading pairs
    - Assigned to target account
    - Name suffix indicating source account type
    - Starts in stopped state (is_active = False)
    - No positions copied (fresh start)
    - Reserved balances reset to 0
    """
    # Get original bot
    query = select(Bot).where(Bot.id == bot_id)
    if current_user:
        query = query.where(Bot.user_id == current_user.id)
    result = await db.execute(query)
    original_bot = result.scalars().first()

    if not original_bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Get target account and verify ownership
    account_query = select(Account).where(Account.id == target_account_id)
    if current_user:
        account_query = account_query.where(Account.user_id == current_user.id)
    account_result = await db.execute(account_query)
    target_account = account_result.scalars().first()

    if not target_account:
        raise HTTPException(status_code=404, detail="Target account not found or not accessible")

    # Get source account to determine type
    source_account = None
    if original_bot.account_id:
        source_account_query = select(Account).where(Account.id == original_bot.account_id)
        source_account_result = await db.execute(source_account_query)
        source_account = source_account_result.scalars().first()

    # Generate new name with account type suffix
    new_name = original_bot.name

    # Determine suffix based on target account type
    if target_account.is_paper_trading:
        suffix = " (Paper)"
    else:
        suffix = f" ({target_account.name})"

    # Remove existing suffixes first
    import re
    new_name = re.sub(r" \((Paper|Copy.*?)\)$", "", new_name)
    new_name = f"{new_name}{suffix}"

    # Ensure name is unique
    counter = 2
    base_new_name = new_name
    while True:
        name_check_query = select(Bot).where(Bot.name == new_name)
        if current_user:
            name_check_query = name_check_query.where(Bot.user_id == current_user.id)
        name_check_result = await db.execute(name_check_query)
        if not name_check_result.scalars().first():
            break
        new_name = f"{base_new_name} {counter}"
        counter += 1

    # Create copied bot
    copied_bot = Bot(
        name=new_name,
        description=original_bot.description,
        account_id=target_account_id,
        strategy_type=original_bot.strategy_type,
        strategy_config=original_bot.strategy_config.copy() if original_bot.strategy_config else {},
        product_id=original_bot.product_id,
        product_ids=original_bot.product_ids.copy() if original_bot.product_ids else [],
        split_budget_across_pairs=original_bot.split_budget_across_pairs,
        budget_percentage=original_bot.budget_percentage,
        reserved_btc_balance=0.0,  # Reset reserved balances
        reserved_usd_balance=0.0,
        reserved_usd_for_longs=0.0,
        reserved_btc_for_shorts=0.0,
        is_active=False,  # Start stopped
        check_interval_seconds=original_bot.check_interval_seconds,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        user_id=current_user.id if current_user else None,
    )

    db.add(copied_bot)
    await db.commit()
    await db.refresh(copied_bot)

    logger.info(f"Copied bot {bot_id} to account {target_account_id} as bot {copied_bot.id}")

    bot_response = BotResponse.model_validate(copied_bot)
    return bot_response


@router.get("/{bot_id}/stats", response_model=BotStats)
async def get_bot_stats(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get statistics for a specific bot"""
    query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
    if current_user:
        query = query.where(Bot.user_id == current_user.id)
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
        coinbase = await get_coinbase_from_db(db)
        if not coinbase:
            raise ValueError("No CEX account configured")

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
