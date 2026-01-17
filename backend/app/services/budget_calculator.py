"""
Budget Calculator for Bidirectional Bots

Calculates available capital considering bidirectional bot reservations.
Ensures that BTC acquired from longs and USD from shorts remain reserved.
"""

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.models import Bot

logger = logging.getLogger(__name__)


async def calculate_available_usd(
    db: AsyncSession,
    raw_usd_balance: float,
    current_btc_price: float,
    exclude_bot_id: int = None
) -> float:
    """
    Calculate available USD after accounting for bidirectional bot reservations.

    This ensures other bots can't use:
    - USD initially reserved for longs
    - BTC acquired from long positions (valued in USD - needs to be sold later)
    - USD received from short positions (needs to buy back BTC)

    Args:
        db: Database session
        raw_usd_balance: Raw USD balance from exchange
        current_btc_price: Current BTC/USD price
        exclude_bot_id: Optional bot ID to exclude (when creating/updating a bot)

    Returns:
        Available USD for other bots
    """
    # Get all active bidirectional bots
    query = select(Bot).where(
        Bot.is_active == True,
        Bot.strategy_config.op('->>')('enable_bidirectional') == 'true'
    )
    if exclude_bot_id:
        query = query.where(Bot.id != exclude_bot_id)

    result = await db.execute(query)
    bidirectional_bots = result.scalars().all()

    # Calculate total reserved USD
    total_reserved = 0.0
    for bot in bidirectional_bots:
        bot_reserved = bot.get_total_reserved_usd(current_btc_price)
        total_reserved += bot_reserved
        logger.debug(
            f"Bot {bot.id} ({bot.name}) reserves ${bot_reserved:.2f} USD "
            f"(initial: ${bot.reserved_usd_for_longs:.2f})"
        )

    available = raw_usd_balance - total_reserved

    logger.info(
        f"USD availability: ${raw_usd_balance:.2f} raw - ${total_reserved:.2f} reserved "
        f"= ${available:.2f} available"
    )

    return max(0.0, available)


async def calculate_available_btc(
    db: AsyncSession,
    raw_btc_balance: float,
    current_btc_price: float,
    exclude_bot_id: int = None
) -> float:
    """
    Calculate available BTC after accounting for bidirectional bot reservations.

    This ensures other bots can't use:
    - BTC initially reserved for shorts
    - BTC acquired from long positions (bought BTC, needs to be sold)
    - BTC equivalent of USD from shorts (got USD, needs to buy back BTC)

    Args:
        db: Database session
        raw_btc_balance: Raw BTC balance from exchange
        current_btc_price: Current BTC/USD price
        exclude_bot_id: Optional bot ID to exclude (when creating/updating a bot)

    Returns:
        Available BTC for other bots
    """
    # Get all active bidirectional bots
    query = select(Bot).where(
        Bot.is_active == True,
        Bot.strategy_config.op('->>')('enable_bidirectional') == 'true'
    )
    if exclude_bot_id:
        query = query.where(Bot.id != exclude_bot_id)

    result = await db.execute(query)
    bidirectional_bots = result.scalars().all()

    # Calculate total reserved BTC
    total_reserved = 0.0
    for bot in bidirectional_bots:
        bot_reserved = bot.get_total_reserved_btc(current_btc_price)
        total_reserved += bot_reserved
        logger.debug(
            f"Bot {bot.id} ({bot.name}) reserves {bot_reserved:.8f} BTC "
            f"(initial: {bot.reserved_btc_for_shorts:.8f})"
        )

    available = raw_btc_balance - total_reserved

    logger.info(
        f"BTC availability: {raw_btc_balance:.8f} raw - {total_reserved:.8f} reserved "
        f"= {available:.8f} available"
    )

    return max(0.0, available)


async def validate_bidirectional_budget(
    db: AsyncSession,
    bot: Bot,
    required_usd: float,
    required_btc: float,
    current_btc_price: float
) -> tuple[bool, str]:
    """
    Validate that sufficient USD and BTC are available for a bidirectional bot.

    Args:
        db: Database session
        bot: Bot instance being created/updated
        required_usd: USD needed for long side
        required_btc: BTC needed for short side
        current_btc_price: Current BTC/USD price

    Returns:
        (is_valid, error_message)
    """
    from app.exchange_clients.factory import create_exchange_client

    # Get exchange client for this bot's account
    try:
        exchange = await create_exchange_client(db, bot.account_id)
    except Exception as e:
        return False, f"Failed to connect to exchange: {e}"

    # Get raw balances
    try:
        balances = await exchange.get_account()
        raw_usd = balances.get("USD", 0.0) + balances.get("USDC", 0.0) + balances.get("USDT", 0.0)
        raw_btc = balances.get("BTC", 0.0)
    except Exception as e:
        return False, f"Failed to fetch account balances: {e}"

    # Calculate available (excluding other bidirectional bots)
    available_usd = await calculate_available_usd(db, raw_usd, current_btc_price, exclude_bot_id=bot.id)
    available_btc = await calculate_available_btc(db, raw_btc, current_btc_price, exclude_bot_id=bot.id)

    # Validate sufficiency
    if required_usd > available_usd:
        return False, (
            f"Insufficient USD for long side. "
            f"Need ${required_usd:.2f}, but only ${available_usd:.2f} available "
            f"(${raw_usd - available_usd:.2f} reserved by other bidirectional bots)"
        )

    if required_btc > available_btc:
        return False, (
            f"Insufficient BTC for short side. "
            f"Need {required_btc:.8f} BTC, but only {available_btc:.8f} BTC available "
            f"({raw_btc - available_btc:.8f} BTC reserved by other bidirectional bots)"
        )

    return True, ""
