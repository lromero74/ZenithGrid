"""
Bot CRUD Router

Handles bot creation, reading, updating, deletion, and strategy listing.
Also includes bot stats and clone operations.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot_routers.schemas import BotCreate, BotResponse, BotStats, BotUpdate
from app.coinbase_unified_client import CoinbaseClient
from app.database import get_db
from app.encryption import decrypt_value, is_encrypted
from app.exchange_clients.factory import create_exchange_client
from app.models import Account, Bot, BotProduct, Position, User
from app.auth.dependencies import get_current_user
from app.strategies import StrategyDefinition, StrategyRegistry

logger = logging.getLogger(__name__)


async def get_coinbase_from_db(db: AsyncSession, user_id: int = None) -> CoinbaseClient:
    """Get Coinbase client from the first active CEX account for a user."""
    from sqlalchemy import select

    query = select(Account).where(
        Account.type == "cex",
        Account.is_active.is_(True),
        Account.is_paper_trading.is_not(True),
    )
    if user_id:
        query = query.where(Account.user_id == user_id)
    query = query.order_by(Account.is_default.desc(), Account.created_at).limit(1)

    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account or not account.api_key_name or not account.api_private_key:
        return None

    private_key = account.api_private_key
    if private_key and is_encrypted(private_key):
        private_key = decrypt_value(private_key)

    return create_exchange_client(
        exchange_type="cex",
        coinbase_key_name=account.api_key_name,
        coinbase_private_key=private_key,
    )
router = APIRouter()


# Strategy Endpoints
@router.get("/strategies", response_model=List[StrategyDefinition])
async def list_strategies(current_user: User = Depends(get_current_user)):
    """Get list of all available trading strategies"""
    return StrategyRegistry.list_strategies()


@router.get("/strategies/{strategy_id}", response_model=StrategyDefinition)
async def get_strategy_definition(strategy_id: str, current_user: User = Depends(get_current_user)):
    """Get detailed definition for a specific strategy"""
    try:
        return StrategyRegistry.get_definition(strategy_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")


# Bot CRUD Endpoints
@router.post("/", response_model=BotResponse, status_code=201)
async def create_bot(
    bot_data: BotCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid strategy configuration")

    # Check if name is unique for this user
    query = select(Bot).where(Bot.name == bot_data.name, Bot.user_id == current_user.id)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(status_code=400, detail=f"Bot with name '{bot_data.name}' already exists")

    # Validate all pairs use the same quote currency (BTC or USD, not mixed)
    from app.services.bot_validation_service import (
        auto_correct_market_focus,
        validate_bidirectional_budget_config,
        validate_quote_currency,
    )

    all_pairs = bot_data.product_ids if bot_data.product_ids else ([bot_data.product_id] if bot_data.product_id else [])
    quote_currency = validate_quote_currency(all_pairs)

    # Auto-correct market_focus for AI autonomous bots based on quote currency
    auto_correct_market_focus(
        bot_data.strategy_type, bot_data.strategy_config, quote_currency,
    )

    # Create bot instance (but don't commit yet - need to validate bidirectional budget first)
    bot = Bot(
        name=bot_data.name,
        description=bot_data.description,
        account_id=bot_data.account_id,
        market_type=getattr(bot_data, 'market_type', 'spot') or 'spot',
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
        required_usd, required_btc = await validate_bidirectional_budget_config(
            db, bot, quote_currency, is_update=False,
        )
        bot.reserved_usd_for_longs = required_usd
        bot.reserved_btc_for_shorts = required_btc
        logger.info(
            f"Bidirectional bot validated: ${required_usd:.2f} USD reserved for longs, "
            f"{required_btc:.8f} BTC reserved for shorts"
        )
    else:
        bot.reserved_usd_for_longs = 0.0
        bot.reserved_btc_for_shorts = 0.0

    db.add(bot)
    await db.commit()
    await db.refresh(bot)

    # Sync bot_products junction table
    pair_list = bot_data.product_ids or ([bot_data.product_id] if bot_data.product_id else [])
    for pid in pair_list:
        if pid:
            db.add(BotProduct(bot_id=bot.id, product_id=pid))
    if pair_list:
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
    current_user: User = Depends(get_current_user)
):
    """Get list of all bots with projection stats based on selected timeframe"""
    from app.services.bot_stats_service import (
        calculate_bot_pnl,
        calculate_budget_utilization,
        fetch_aggregate_values,
        fetch_position_prices,
        get_open_position_products,
    )

    query = select(Bot).order_by(desc(Bot.created_at))
    query = query.where(Bot.user_id == current_user.id)

    if active_only:
        query = query.where(Bot.is_active)

    result = await db.execute(query)
    bots = result.scalars().all()

    # Initialize coinbase client for budget calculations (from database)
    coinbase = await get_coinbase_from_db(db, user_id=current_user.id)
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

    # Pre-fetch aggregate values and position prices ONCE
    aggregate_btc_value, aggregate_usd_value = await fetch_aggregate_values(coinbase)
    _, unique_products = await get_open_position_products(db, current_user.id)
    position_prices = await fetch_position_prices(coinbase, unique_products)

    # Build responses for each bot
    bot_responses = []
    for bot in bots:
        all_pos_query = select(Position).where(Position.bot_id == bot.id)
        all_pos_result = await db.execute(all_pos_query)
        all_positions = all_pos_result.scalars().all()

        open_positions = [p for p in all_positions if p.status == "open"]
        closed_positions = [p for p in all_positions if p.status == "closed"]

        pnl = calculate_bot_pnl(bot, closed_positions, open_positions, projection_timeframe)
        budget = calculate_budget_utilization(
            bot, open_positions, position_prices, aggregate_btc_value, aggregate_usd_value,
        )

        bot_response = BotResponse.model_validate(bot)
        bot_response.open_positions_count = len(open_positions)
        bot_response.total_positions_count = len(all_positions)
        bot_response.closed_positions_count = len(closed_positions)
        bot_response.trades_per_day = pnl["trades_per_day"]
        bot_response.total_pnl_usd = pnl["total_pnl_usd"]
        bot_response.total_pnl_btc = pnl["total_pnl_btc"]
        bot_response.total_pnl_percentage = pnl["total_pnl_percentage"]
        bot_response.avg_daily_pnl_usd = pnl["avg_daily_pnl_usd"]
        bot_response.avg_daily_pnl_btc = pnl["avg_daily_pnl_btc"]
        bot_response.insufficient_funds = budget["insufficient_funds"]
        bot_response.budget_utilization_percentage = budget["budget_utilization_percentage"]
        bot_response.win_rate = pnl["win_rate"]
        bot_responses.append(bot_response)

    return bot_responses


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get details for a specific bot"""
    query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
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
    current_user: User = Depends(get_current_user)
):
    """Update bot configuration"""
    query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
    query = query.where(Bot.user_id == current_user.id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Allow updates while bot is active
    # Changes will apply to new signals/positions, not existing open positions

    # Update fields
    if bot_update.name is not None:
        # Check name uniqueness
        name_query = select(Bot).where(Bot.name == bot_update.name, Bot.id != bot_id, Bot.user_id == current_user.id)
        name_result = await db.execute(name_query)
        if name_result.scalars().first():
            raise HTTPException(status_code=400, detail=f"Bot with name '{bot_update.name}' already exists")
        bot.name = bot_update.name

    if bot_update.description is not None:
        bot.description = bot_update.description

    if bot_update.market_type is not None:
        bot.market_type = bot_update.market_type

    if bot_update.strategy_config is not None:
        # Validate new config
        try:
            StrategyRegistry.get_strategy(bot.strategy_type, bot_update.strategy_config)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid strategy configuration")
        bot.strategy_config = bot_update.strategy_config

    if bot_update.product_id is not None:
        bot.product_id = bot_update.product_id

    if bot_update.product_ids is not None:
        bot.product_ids = bot_update.product_ids
        # Sync bot_products junction table: delete old, insert new
        from sqlalchemy import delete
        await db.execute(delete(BotProduct).where(BotProduct.bot_id == bot.id))
        for pid in bot_update.product_ids:
            if pid:
                db.add(BotProduct(bot_id=bot.id, product_id=pid))

    if bot_update.split_budget_across_pairs is not None:
        bot.split_budget_across_pairs = bot_update.split_budget_across_pairs

    if bot_update.reserved_btc_balance is not None:
        bot.reserved_btc_balance = bot_update.reserved_btc_balance

    if bot_update.reserved_usd_balance is not None:
        bot.reserved_usd_balance = bot_update.reserved_usd_balance

    if bot_update.budget_percentage is not None:
        bot.budget_percentage = bot_update.budget_percentage

    # Validate all pairs use the same quote currency after update
    from app.services.bot_validation_service import (
        auto_correct_market_focus,
        validate_bidirectional_budget_config,
        validate_quote_currency,
    )

    final_pairs = bot.product_ids if bot.product_ids else ([bot.product_id] if bot.product_id else [])
    quote_currency = validate_quote_currency(final_pairs)

    auto_correct_market_focus(
        bot.strategy_type, bot.strategy_config, quote_currency, entity_name=bot.name,
    )

    bot.updated_at = datetime.utcnow()

    # Recalculate bidirectional reservations if config or budget changed
    config_changed = bot_update.strategy_config is not None
    budget_changed = bot_update.budget_percentage is not None

    if (config_changed or budget_changed) and bot.strategy_config.get("enable_bidirectional", False):
        logger.info(f"Recalculating bidirectional reservations for updated bot '{bot.name}'")
        required_usd, required_btc = await validate_bidirectional_budget_config(
            db, bot, quote_currency, is_update=True,
        )
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
    current_user: User = Depends(get_current_user)
):
    """Delete a bot (only if it has no open positions)"""
    query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
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
        logger.info(
            f"Releasing bidirectional reservations for bot "
            f"'{bot.name}' (${bot.reserved_usd_for_longs:.2f} USD, "
            f"{bot.reserved_btc_for_shorts:.8f} BTC)"
        )
        bot.reserved_usd_for_longs = 0.0
        bot.reserved_btc_for_shorts = 0.0

    await db.delete(bot)
    await db.commit()

    return {"message": f"Bot '{bot.name}' deleted successfully"}


@router.post("/{bot_id}/clone", response_model=BotResponse, status_code=201)
async def clone_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
        name_check_query = select(Bot).where(Bot.name == new_name, Bot.user_id == current_user.id)
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

    # Copy bot_products from original bot
    pair_list = original_bot.product_ids.copy() if original_bot.product_ids else []
    if not pair_list and original_bot.product_id:
        pair_list = [original_bot.product_id]
    for pid in pair_list:
        if pid:
            db.add(BotProduct(bot_id=cloned_bot.id, product_id=pid))
    if pair_list:
        await db.commit()
        await db.refresh(cloned_bot)

    bot_response = BotResponse.model_validate(cloned_bot)
    return bot_response


@router.post("/{bot_id}/copy-to-account", response_model=BotResponse, status_code=201)
async def copy_bot_to_account(
    bot_id: int,
    target_account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    query = query.where(Bot.user_id == current_user.id)
    result = await db.execute(query)
    original_bot = result.scalars().first()

    if not original_bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Get target account and verify ownership
    account_query = select(Account).where(Account.id == target_account_id, Account.user_id == current_user.id)
    account_result = await db.execute(account_query)
    target_account = account_result.scalars().first()

    if not target_account:
        raise HTTPException(status_code=404, detail="Target account not found or not accessible")

    # Get source account to determine type
    _source_account = None  # noqa: F841
    if original_bot.account_id:
        source_account_query = select(Account).where(Account.id == original_bot.account_id)
        source_account_result = await db.execute(source_account_query)
        _source_account = source_account_result.scalars().first()  # noqa: F841

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
        name_check_query = select(Bot).where(Bot.name == new_name, Bot.user_id == current_user.id)
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

    # Copy bot_products from original bot
    pair_list = original_bot.product_ids.copy() if original_bot.product_ids else []
    if not pair_list and original_bot.product_id:
        pair_list = [original_bot.product_id]
    for pid in pair_list:
        if pid:
            db.add(BotProduct(bot_id=copied_bot.id, product_id=pid))
    if pair_list:
        await db.commit()
        await db.refresh(copied_bot)

    logger.info(f"Copied bot {bot_id} to account {target_account_id} as bot {copied_bot.id}")

    bot_response = BotResponse.model_validate(copied_bot)
    return bot_response


@router.get("/{bot_id}/stats", response_model=BotStats)
async def get_bot_stats(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get statistics for a specific bot"""
    query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
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
        coinbase = await get_coinbase_from_db(db, user_id=current_user.id)
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
            except Exception as _:  # noqa: F841
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
