"""
Bot Management Router

Handles CRUD operations for trading bots and strategy listing.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AIBotLog, Bot, Position
from app.strategies import StrategyDefinition, StrategyRegistry
from app.coinbase_unified_client import CoinbaseClient
from app.order_validation import calculate_minimum_budget_percentage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bots", tags=["bots"])


# Pydantic Schemas
class BotCreate(BaseModel):
    name: str
    description: Optional[str] = None
    strategy_type: str
    strategy_config: dict
    product_id: str = "ETH-BTC"  # Legacy - kept for backward compatibility
    product_ids: Optional[List[str]] = None  # Multi-pair support
    split_budget_across_pairs: bool = False  # Budget splitting toggle
    reserved_btc_balance: float = 0.0  # BTC allocated to this bot (legacy)
    reserved_usd_balance: float = 0.0  # USD allocated to this bot (legacy)
    budget_percentage: float = 0.0  # % of aggregate portfolio value (preferred)


class BotUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    strategy_config: Optional[dict] = None
    product_id: Optional[str] = None
    product_ids: Optional[List[str]] = None
    split_budget_across_pairs: Optional[bool] = None
    reserved_btc_balance: Optional[float] = None
    reserved_usd_balance: Optional[float] = None
    budget_percentage: Optional[float] = None


class BotResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    strategy_type: str
    strategy_config: dict
    product_id: str
    product_ids: Optional[List[str]] = None
    split_budget_across_pairs: bool = False
    reserved_btc_balance: float = 0.0
    reserved_usd_balance: float = 0.0
    budget_percentage: float = 0.0
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_signal_check: Optional[datetime]
    open_positions_count: int = 0
    total_positions_count: int = 0
    total_pnl_usd: float = 0.0
    avg_daily_pnl_usd: float = 0.0

    class Config:
        from_attributes = True


class BotStats(BaseModel):
    total_positions: int
    open_positions: int
    closed_positions: int
    total_profit_btc: float
    win_rate: float


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
@router.post("", response_model=BotResponse, status_code=201)
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
            if '-' in pair:
                quote = pair.split('-')[1]
                quote_currencies.add(quote)

        if len(quote_currencies) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"All trading pairs must use the same quote currency. Found: {', '.join(sorted(quote_currencies))}. "
                       f"Please use only BTC-based pairs OR only USD-based pairs, not a mix."
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
        is_active=False
    )

    db.add(bot)
    await db.commit()
    await db.refresh(bot)

    # Add counts
    response = BotResponse.model_validate(bot)
    response.open_positions_count = 0
    response.total_positions_count = 0

    return response


@router.get("", response_model=List[BotResponse])
async def list_bots(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """Get list of all bots"""
    query = select(Bot).order_by(desc(Bot.created_at))

    if active_only:
        query = query.where(Bot.is_active)

    result = await db.execute(query)
    bots = result.scalars().all()

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

        bot_response = BotResponse.model_validate(bot)
        bot_response.open_positions_count = len(open_positions)
        bot_response.total_positions_count = len(all_positions)
        bot_response.total_pnl_usd = total_pnl_usd
        bot_response.avg_daily_pnl_usd = avg_daily_pnl_usd
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
    open_pos_query = select(Position).where(
        Position.bot_id == bot.id,
        Position.status == "open"
    )
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
    db: AsyncSession = Depends(get_db)
):
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
            if '-' in pair:
                quote = pair.split('-')[1]
                quote_currencies.add(quote)

        if len(quote_currencies) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"All trading pairs must use the same quote currency. Found: {', '.join(sorted(quote_currencies))}. "
                       f"Please use only BTC-based pairs OR only USD-based pairs, not a mix."
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
    open_pos_query = select(Position).where(
        Position.bot_id == bot.id,
        Position.status == "open"
    )
    open_result = await db.execute(open_pos_query)
    if open_result.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="Cannot delete bot with open positions. Close positions first."
        )

    await db.delete(bot)
    await db.commit()

    return {"message": f"Bot '{bot.name}' deleted successfully"}


@router.post("/{bot_id}/start")
async def start_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    """Activate a bot to start trading"""
    query = select(Bot).where(Bot.id == bot_id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    if bot.is_active:
        return {"message": f"Bot '{bot.name}' is already active"}

    bot.is_active = True
    bot.updated_at = datetime.utcnow()

    await db.commit()

    return {"message": f"Bot '{bot.name}' started successfully"}


@router.post("/{bot_id}/stop")
async def stop_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    """Deactivate a bot to stop trading"""
    query = select(Bot).where(Bot.id == bot_id)
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    if not bot.is_active:
        return {"message": f"Bot '{bot.name}' is already inactive"}

    bot.is_active = False
    bot.updated_at = datetime.utcnow()

    await db.commit()

    return {"message": f"Bot '{bot.name}' stopped successfully"}


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
    copy_match = re.search(r'\(Copy(?: (\d+))?\)$', new_name)

    if copy_match:
        # Name already has (Copy) or (Copy N), increment
        copy_num = copy_match.group(1)
        if copy_num:
            # (Copy N) → (Copy N+1)
            next_num = int(copy_num) + 1
            new_name = re.sub(r'\(Copy \d+\)$', f'(Copy {next_num})', new_name)
        else:
            # (Copy) → (Copy 2)
            new_name = re.sub(r'\(Copy\)$', '(Copy 2)', new_name)
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
        updated_at=datetime.utcnow()
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

    return BotStats(
        total_positions=len(all_positions),
        open_positions=len(open_positions),
        closed_positions=len(closed_positions),
        total_profit_btc=total_profit,
        win_rate=win_rate
    )


# AI Bot Reasoning Log Endpoints

class AIBotLogCreate(BaseModel):
    thinking: str
    decision: str
    confidence: Optional[float] = None
    current_price: Optional[float] = None
    position_status: Optional[str] = None
    context: Optional[dict] = None


class AIBotLogResponse(BaseModel):
    id: int
    bot_id: int
    timestamp: datetime
    thinking: str
    decision: str
    confidence: Optional[float]
    current_price: Optional[float]
    position_status: Optional[str]
    product_id: Optional[str]
    context: Optional[dict]

    class Config:
        from_attributes = True


@router.post("/{bot_id}/logs", response_model=AIBotLogResponse, status_code=201)
async def create_ai_bot_log(
    bot_id: int,
    log_data: AIBotLogCreate,
    db: AsyncSession = Depends(get_db)
):
    """Save AI bot reasoning/thinking log"""
    # Verify bot exists
    bot_query = select(Bot).where(Bot.id == bot_id)
    bot_result = await db.execute(bot_query)
    bot = bot_result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Create log entry
    log_entry = AIBotLog(
        bot_id=bot_id,
        thinking=log_data.thinking,
        decision=log_data.decision,
        confidence=log_data.confidence,
        current_price=log_data.current_price,
        position_status=log_data.position_status,
        context=log_data.context,
        timestamp=datetime.utcnow()
    )

    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)

    return AIBotLogResponse.model_validate(log_entry)


@router.get("/{bot_id}/logs", response_model=List[AIBotLogResponse])
async def get_ai_bot_logs(
    bot_id: int,
    limit: int = 50,
    offset: int = 0,
    product_id: Optional[str] = None,
    since: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get AI bot reasoning logs (most recent first)

    Args:
        bot_id: Bot ID to get logs for
        limit: Maximum number of logs to return
        offset: Pagination offset
        product_id: Optional filter by trading pair (e.g., "ETH-BTC")
        since: Optional filter for logs since this timestamp
    """
    # Verify bot exists
    bot_query = select(Bot).where(Bot.id == bot_id)
    bot_result = await db.execute(bot_query)
    bot = bot_result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Build query with optional filters
    logs_query = select(AIBotLog).where(AIBotLog.bot_id == bot_id)

    if product_id:
        logs_query = logs_query.where(AIBotLog.product_id == product_id)

    if since:
        logs_query = logs_query.where(AIBotLog.timestamp >= since)

    logs_query = (
        logs_query
        .order_by(desc(AIBotLog.timestamp))
        .limit(limit)
        .offset(offset)
    )

    logs_result = await db.execute(logs_query)
    logs = logs_result.scalars().all()

    return [AIBotLogResponse.model_validate(log) for log in logs]


# Validation Schemas
class ValidateBotConfigRequest(BaseModel):
    product_ids: List[str]
    strategy_config: dict
    quote_balance: Optional[float] = None  # Will use actual balance if not provided


class ValidationWarning(BaseModel):
    product_id: str
    issue: str
    suggested_minimum_pct: float
    current_pct: float


class ValidateBotConfigResponse(BaseModel):
    is_valid: bool
    warnings: List[ValidationWarning]
    message: str


@router.post("/validate-config", response_model=ValidateBotConfigResponse)
async def validate_bot_config(
    request: ValidateBotConfigRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Validate if bot configuration meets minimum order size requirements

    Checks if the configured budget percentages will result in orders
    that meet Coinbase's minimum order sizes for each product.

    Returns warnings with suggested minimum percentages if validation fails.
    """
    coinbase = CoinbaseClient()

    # Get quote balance if not provided
    quote_balance = request.quote_balance
    if quote_balance is None:
        # Use first product to determine quote currency
        if not request.product_ids:
            raise HTTPException(status_code=400, detail="No product_ids provided")

        first_product = request.product_ids[0]
        quote_currency = first_product.split('-')[1] if '-' in first_product else "BTC"

        if quote_currency == "BTC":
            quote_balance = await coinbase.get_btc_balance()
        elif quote_currency == "USD":
            # Get USD balance from portfolio
            breakdown = await coinbase.get_portfolio_breakdown()
            spot_positions = breakdown.get("spot_positions", [])
            for pos in spot_positions:
                if pos.get("asset") == "USD":
                    quote_balance = float(pos.get("available_to_trade_fiat", 0))
                    break
        else:
            quote_balance = 100.0  # Default fallback

    if quote_balance <= 0:
        return ValidateBotConfigResponse(
            is_valid=False,
            warnings=[],
            message="No quote currency balance available. Cannot validate."
        )

    # Extract relevant percentages from config
    base_order_pct = request.strategy_config.get("base_order_percentage", 0)
    safety_order_pct = request.strategy_config.get("safety_order_percentage", 0)
    initial_budget_pct = request.strategy_config.get("initial_budget_percentage", 0)

    # Use whichever is configured (different strategies use different field names)
    order_pct = max(base_order_pct, safety_order_pct, initial_budget_pct)

    if order_pct <= 0:
        return ValidateBotConfigResponse(
            is_valid=False,
            warnings=[],
            message="No order percentage configured. Please set base_order_percentage, safety_order_percentage, or initial_budget_percentage."
        )

    # Check each product
    warnings = []
    for product_id in request.product_ids:
        # Calculate actual order amount
        order_amount = (order_pct / 100) * quote_balance

        # Get minimum required percentage for this product
        try:
            min_pct = await calculate_minimum_budget_percentage(
                coinbase,
                product_id,
                quote_balance
            )

            if order_pct < min_pct:
                warnings.append(ValidationWarning(
                    product_id=product_id,
                    issue=f"Order size will be below Coinbase minimum",
                    suggested_minimum_pct=min_pct,
                    current_pct=order_pct
                ))
        except Exception as e:
            logger.warning(f"Failed to validate {product_id}: {e}")
            # Continue checking other products

    is_valid = len(warnings) == 0

    if is_valid:
        message = "Bot configuration is valid. All orders meet minimum size requirements."
    else:
        message = f"Warning: {len(warnings)} product(s) may fail due to minimum order size requirements."

    return ValidateBotConfigResponse(
        is_valid=is_valid,
        warnings=warnings,
        message=message
    )
