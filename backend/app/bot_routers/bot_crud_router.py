"""
Bot CRUD Router

Handles bot creation, reading, updating, deletion, and strategy listing.
Also includes bot stats and clone operations.
"""

import logging
from app.utils.timeutil import utcnow
from app.bot_routers._shared import bot_write_filter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot_routers.schemas import BotCreate, BotResponse, BotStats, BotUpdate
from app.database import get_db
from app.exceptions import ExchangeUnavailableError
from app.models import Account, Bot, BotProduct, Position, User
from app.auth.dependencies import get_current_user, require_permission, Perm
from app.services.rebalancer_gates import is_rebalancer_gated, is_rebalancer_bot_overweight
from app.services.account_access import accessible_account_ids, manager_accounts_filter
from app.services.exchange_service import get_exchange_client_for_account
from app.services.bot_stats_service import fetch_aggregate_values
from app.services.portfolio_service import get_coinbase_from_db
from app.strategies import StrategyRegistry

logger = logging.getLogger(__name__)
router = APIRouter()


async def _accessible_bot_filter(db: AsyncSession, current_user_id: int):
    """Filter for bots the user can read (owner, observer, or manager)."""
    from sqlalchemy import or_
    acc_ids = await accessible_account_ids(db, current_user_id)
    return or_(Bot.user_id == current_user_id, Bot.account_id.in_(acc_ids))


async def _get_paper_account(db: AsyncSession, user_id: int):
    """Get the user's first active paper trading account, if any."""
    query = select(Account).where(
        Account.user_id == user_id,
        Account.is_active.is_(True),
        Account.is_paper_trading.is_(True),
    ).limit(1)
    result = await db.execute(query)
    return result.scalar_one_or_none()


def _apply_risk_preset_defaults(strategy_config: Optional[dict]) -> dict:
    """Merge risk-preset defaults into strategy_config if ai_risk_preset is set.

    User-supplied values win over preset defaults — we only FILL IN missing
    keys. This keeps the preset a convenience (one-click sensible defaults)
    without silently overwriting the user's explicit customizations.

    Returns a fresh dict suitable for assignment. Idempotent: re-applying
    the same preset to an already-merged config is a no-op.

    See PRPs/high-risk-doubling-preset.md §Task C2.
    """
    if not isinstance(strategy_config, dict):
        return strategy_config or {}

    preset_name = strategy_config.get("ai_risk_preset")
    if not preset_name:
        return dict(strategy_config)

    from app.indicators.risk_presets import RISK_PRESETS, get_risk_preset_defaults
    if preset_name not in RISK_PRESETS:
        return dict(strategy_config)

    defaults = get_risk_preset_defaults(preset_name)
    merged = dict(defaults)
    # User values win
    merged.update(strategy_config)
    return merged


# Strategy listing lives in strategies_router (GET /api/strategies). The
# duplicate /api/bots/strategies endpoints were removed in the v3.14.13 sweep.


# Bot CRUD Endpoints
@router.post("/", response_model=BotResponse, status_code=201)
async def create_bot(
    bot_data: BotCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.BOTS_WRITE))
):
    """Create a new trading bot"""
    # Validate strategy exists
    try:
        StrategyRegistry.get_definition(bot_data.strategy_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {bot_data.strategy_type}")

    # Merge risk-preset defaults into strategy_config when ai_risk_preset is
    # set (e.g., "speculative"). User-supplied values win — the preset only
    # fills missing keys. See PRPs/high-risk-doubling-preset.md §Task C2.
    bot_data.strategy_config = _apply_risk_preset_defaults(bot_data.strategy_config)

    # Validate strategy config (create temporary instance to validate)
    try:
        StrategyRegistry.get_strategy(bot_data.strategy_type, bot_data.strategy_config)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid strategy configuration")

    # If creating a bot on a shared account, verify the user has manager access to it
    if bot_data.account_id is not None:
        acct_check = await db.execute(
            select(Account).where(
                Account.id == bot_data.account_id,
                manager_accounts_filter(current_user.id),
            )
        )
        if not acct_check.scalars().first():
            raise HTTPException(status_code=403, detail="Manager access required to create bots on this account")

    # Check if name is unique for this user (and managers of the same account)
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
        user_id=current_user.id,
    )

    # Generate webhook token if webhook integration is requested
    if getattr(bot_data, 'webhook_enabled', False):
        import secrets as _secrets
        bot.webhook_token = _secrets.token_urlsafe(32)

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


async def build_account_budget_aggregates(
    db,
    bots,
    default_aggregates: Tuple[Optional[float], Optional[float]],
) -> Dict[int, Tuple[Optional[float], Optional[float]]]:
    """Map each bot's ``account_id`` to that account's own (BTC, USD) budget
    aggregates.

    Budget utilization must reflect each bot's OWN account balance, never the
    default account's — a user owns multiple accounts (CLAUDE.md rule 12). One
    exchange client is built per distinct account. When an account's client
    can't be built (no creds / unavailable), that account falls back to
    ``default_aggregates`` so the row still renders rather than erroring.
    """
    aggregates: Dict[int, Tuple[Optional[float], Optional[float]]] = {}
    for account_id in {b.account_id for b in bots if b.account_id is not None}:
        try:
            client = await get_exchange_client_for_account(db, account_id)
        except ExchangeUnavailableError:
            client = None
        aggregates[account_id] = (
            await fetch_aggregate_values(client) if client else default_aggregates
        )
    return aggregates


@router.get("/", response_model=List[BotResponse])
async def list_bots(
    active_only: bool = False,
    projection_timeframe: Optional[str] = "all",
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of all bots with projection stats based on selected timeframe"""
    from app.services.bot_stats_service import (
        calculate_bot_pnl,
        calculate_budget_utilization,
        fetch_position_prices,
        get_open_position_products,
    )

    # Include bots owned by the user AND bots on accounts they have shared access to
    acc_ids = await accessible_account_ids(db, current_user.id)
    from sqlalchemy import or_

    if account_id is not None:
        account_result = await db.execute(
            select(Account.id).where(
                Account.id == account_id,
                or_(Account.user_id == current_user.id, Account.id.in_(acc_ids)),
            )
        )
        if account_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Not found")

    query = select(Bot).order_by(desc(Bot.created_at))
    query = query.where(
        or_(Bot.user_id == current_user.id, Bot.account_id.in_(acc_ids))
    )

    if account_id is not None:
        query = query.where(Bot.account_id == account_id)

    if active_only:
        query = query.where(Bot.is_active)

    result = await db.execute(query)
    bots = result.scalars().all()

    # Initialize exchange client for budget calculations (from database)
    try:
        coinbase = await get_coinbase_from_db(db, user_id=current_user.id)
    except ExchangeUnavailableError:
        coinbase = None

    if not coinbase:
        # Fall back to paper trading account for price data + stats
        paper_account = await _get_paper_account(db, current_user.id)
        if paper_account:
            coinbase = await get_exchange_client_for_account(db, paper_account.id)

    if not coinbase:
        # No accounts at all — return bots with position counts only (single aggregate query)
        bot_ids = [b.id for b in bots]
        counts_q = select(
            Position.bot_id,
            func.count(Position.id).label("total"),
            func.count(case((Position.status == "open", Position.id))).label("open_count"),
        ).where(Position.bot_id.in_(bot_ids)).group_by(Position.bot_id)
        counts_result = await db.execute(counts_q)
        counts_map = {row.bot_id: (row.open_count, row.total) for row in counts_result}

        bot_responses = []
        for bot in bots:
            open_count, total_count = counts_map.get(bot.id, (0, 0))
            response = BotResponse.model_validate(bot)
            response.open_positions_count = open_count
            response.total_positions_count = total_count
            response.quote_currency = bot.get_quote_currency()
            bot_responses.append(response)
        return bot_responses

    # Position prices are market-wide (account-agnostic) so one client is fine.
    # Budget aggregates, however, are per-account balances — build a map so each
    # bot's budget uses ITS OWN account, not the default account (rule 12).
    default_aggregates = await fetch_aggregate_values(coinbase)
    aggregates_by_account = await build_account_budget_aggregates(db, bots, default_aggregates)
    _, unique_products = await get_open_position_products(db, current_user.id)
    position_prices = await fetch_position_prices(coinbase, unique_products)

    # Batch-load all positions for user's bots in a single query
    from collections import defaultdict
    bot_ids = [b.id for b in bots]
    all_pos_query = select(Position).where(Position.bot_id.in_(bot_ids))
    all_pos_result = await db.execute(all_pos_query)
    positions_by_bot = defaultdict(list)
    for p in all_pos_result.scalars().all():
        positions_by_bot[p.bot_id].append(p)

    # Build responses for each bot
    bot_responses = []
    for bot in bots:
        all_positions = positions_by_bot[bot.id]

        open_positions = [p for p in all_positions if p.status == "open"]
        closed_positions = [p for p in all_positions if p.status == "closed"]

        today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        closed_today = [
            p for p in closed_positions
            if p.closed_at and p.closed_at.replace(tzinfo=timezone.utc) >= today_utc
        ]

        pnl = calculate_bot_pnl(bot, closed_positions, open_positions, projection_timeframe)
        bot_btc_value, bot_usd_value = aggregates_by_account.get(bot.account_id, default_aggregates)
        budget = calculate_budget_utilization(
            bot, open_positions, position_prices, bot_btc_value, bot_usd_value,
        )

        bot_response = BotResponse.model_validate(bot)
        bot_response.open_positions_count = len(open_positions)
        bot_response.total_positions_count = len(all_positions)
        bot_response.closed_positions_count = len(closed_positions)
        bot_response.closed_today_count = len(closed_today)
        bot_response.trades_per_day = pnl["trades_per_day"]
        bot_response.total_pnl_usd = pnl["total_pnl_usd"]
        bot_response.total_pnl_btc = pnl["total_pnl_btc"]
        bot_response.total_pnl_percentage = pnl["total_pnl_percentage"]
        bot_response.avg_daily_pnl_usd = pnl["avg_daily_pnl_usd"]
        bot_response.avg_daily_pnl_btc = pnl["avg_daily_pnl_btc"]
        bot_response.avg_daily_pnl_usd_active = pnl["avg_daily_pnl_usd_active"]
        bot_response.avg_daily_pnl_btc_active = pnl["avg_daily_pnl_btc_active"]
        bot_response.aggregate_running_days = pnl["aggregate_running_days"]
        bot_response.calendar_days = pnl["calendar_days"]
        bot_response.insufficient_funds = budget["insufficient_funds"]
        bot_response.budget_utilization_percentage = budget["budget_utilization_percentage"]
        bot_response.win_rate = pnl["win_rate"]
        bot_response.quote_currency = bot.get_quote_currency()
        bot_response.rebalancer_gated = is_rebalancer_gated(bot.id)
        bot_response.rebalancer_bot_overweight = is_rebalancer_bot_overweight(bot.id)
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
    query = query.where(await _accessible_bot_filter(db, current_user.id))
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Count positions via SQL COUNT instead of materializing all rows
    count_query = select(
        func.count(Position.id),
        func.count(case((Position.status == "open", 1))),
    ).where(Position.bot_id == bot.id)
    count_result = await db.execute(count_query)
    total_count, open_count = count_result.one()

    bot_response = BotResponse.model_validate(bot)
    bot_response.open_positions_count = open_count
    bot_response.total_positions_count = total_count
    bot_response.quote_currency = bot.get_quote_currency()

    return bot_response


@router.put("/{bot_id}", response_model=BotResponse)
async def update_bot(
    bot_id: int,
    bot_update: BotUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.BOTS_WRITE))
):
    """Update bot configuration"""
    query = select(Bot).where(Bot.id == bot_id, await bot_write_filter(db, current_user.id))
    result = await db.execute(query)
    bot = result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Allow updates while bot is active
    # Changes will apply to new signals/positions, not existing open positions

    # Update fields
    if bot_update.name is not None:
        # Check name uniqueness
        name_query = select(Bot).where(Bot.name == bot_update.name, Bot.id != bot_id, Bot.user_id == bot.user_id)
        name_result = await db.execute(name_query)
        if name_result.scalars().first():
            raise HTTPException(status_code=400, detail=f"Bot with name '{bot_update.name}' already exists")
        bot.name = bot_update.name

    if bot_update.description is not None:
        bot.description = bot_update.description

    if bot_update.market_type is not None:
        bot.market_type = bot_update.market_type

    if bot_update.strategy_config is not None:
        # Apply risk-preset defaults first (user values win). See Task C2.
        merged_config = _apply_risk_preset_defaults(bot_update.strategy_config)
        # Validate new config
        try:
            StrategyRegistry.get_strategy(bot.strategy_type, merged_config)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid strategy configuration")
        bot.strategy_config = merged_config

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

    bot.updated_at = utcnow()

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


@router.post("/{bot_id}/webhook-token", response_model=BotResponse)
async def regenerate_webhook_token(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.BOTS_WRITE))
):
    """Generate or regenerate the TradingView webhook token for a bot."""
    import secrets as _secrets
    query = select(Bot).where(Bot.id == bot_id, await bot_write_filter(db, current_user.id))
    result = await db.execute(query)
    bot = result.scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    bot.webhook_token = _secrets.token_urlsafe(32)
    bot.updated_at = utcnow()
    await db.commit()
    await db.refresh(bot)

    return BotResponse.model_validate(bot)


@router.delete("/{bot_id}/webhook-token", response_model=BotResponse)
async def revoke_webhook_token(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.BOTS_WRITE))
):
    """Revoke the TradingView webhook token for a bot."""
    query = select(Bot).where(Bot.id == bot_id, await bot_write_filter(db, current_user.id))
    result = await db.execute(query)
    bot = result.scalars().first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    bot.webhook_token = None
    bot.updated_at = utcnow()
    await db.commit()
    await db.refresh(bot)

    return BotResponse.model_validate(bot)


@router.delete("/{bot_id}")
async def delete_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.BOTS_DELETE))
):
    """Delete a bot (only if it has no open positions)"""
    query = select(Bot).where(Bot.id == bot_id, await bot_write_filter(db, current_user.id))
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
    current_user: User = Depends(require_permission(Perm.BOTS_WRITE))
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
    # Get original bot — accessible to owner and managers
    query = select(Bot).where(Bot.id == bot_id, await bot_write_filter(db, current_user.id))
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

    # Ensure name is unique with a single query instead of a per-conflict loop
    base_new_name = new_name
    existing_names_result = await db.execute(
        select(Bot.name).where(
            Bot.user_id == current_user.id,
            Bot.name.like(f"{base_new_name}%"),
        )
    )
    existing_names = {row[0] for row in existing_names_result.all()}
    if new_name in existing_names:
        counter = 2
        while f"{base_new_name} {counter}" in existing_names:
            counter += 1
        new_name = f"{base_new_name} {counter}"

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
        created_at=utcnow(),
        updated_at=utcnow(),
        user_id=current_user.id,
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
    current_user: User = Depends(require_permission(Perm.BOTS_WRITE))
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
    # Get original bot — accessible to owner and managers
    query = select(Bot).where(Bot.id == bot_id, await bot_write_filter(db, current_user.id))
    result = await db.execute(query)
    original_bot = result.scalars().first()

    if not original_bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Get target account — must be owned or managed by caller
    account_query = select(Account).where(
        Account.id == target_account_id,
        manager_accounts_filter(current_user.id),
    )
    account_result = await db.execute(account_query)
    target_account = account_result.scalars().first()

    if not target_account:
        raise HTTPException(status_code=404, detail="Target account not found or not accessible")

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
        created_at=utcnow(),
        updated_at=utcnow(),
        user_id=current_user.id,
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
    query = query.where(await _accessible_bot_filter(db, current_user.id))
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

    # Win rate: exclude manual closes (user intervention) from both numerator and denominator
    bot_driven_positions = [p for p in closed_positions if p.exit_reason != "manual"]
    winning_positions = [p for p in bot_driven_positions if p.profit_quote and p.profit_quote > 0]
    win_rate = (len(winning_positions) / len(bot_driven_positions) * 100) if bot_driven_positions else 0.0

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
        # Use the BOT'S account credentials, not the requester's. A shared-account
        # manager viewing another owner's bot would otherwise compute budget/balances
        # with their own exchange keys (wrong account / cross-account creds).
        from app.services.exchange_service import get_exchange_client_for_account
        coinbase = await get_exchange_client_for_account(db, bot.account_id)
        if coinbase is None:
            raise RuntimeError(f"No exchange client for account {bot.account_id}")
        quote_currency = bot.get_quote_currency()

        aggregate_value = await coinbase.calculate_market_budget(
            quote_currency
        )

        reserved_balance = bot.get_reserved_balance(aggregate_value)

        # Calculate current value of open positions (not just spent)
        total_in_positions_value = 0.0
        for position in open_positions:
            try:
                current_price = await coinbase.get_current_price(position.product_id)
                position_value = position.total_base_acquired * current_price
                total_in_positions_value += position_value
            except Exception:
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
        quote_currency=bot.get_quote_currency(),
        win_rate=win_rate,
        insufficient_funds=insufficient_funds,
        budget_utilization_percentage=budget_utilization_percentage,
    )
