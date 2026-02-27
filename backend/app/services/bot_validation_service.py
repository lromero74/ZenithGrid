"""
Bot Validation Service

Validates quote currency consistency, auto-corrects AI bot market focus,
and validates bidirectional budget configuration. Extracted from
bot_crud_router create_bot() and update_bot() to deduplicate logic.
"""

import logging
from typing import List, Optional, Tuple

from app.exceptions import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def validate_quote_currency(pairs: List[str]) -> Optional[str]:
    """
    Validate all trading pairs use the same quote currency.

    Returns the quote currency string, or None if no pairs.
    Raises ValidationError if mixed quote currencies found.
    """
    if not pairs:
        return None

    quote_currencies = set()
    for pair in pairs:
        if "-" in pair:
            quote = pair.split("-")[1]
            quote_currencies.add(quote)

    if len(quote_currencies) > 1:
        raise ValidationError(
            f"All trading pairs must use the same quote currency."
            f" Found: {', '.join(sorted(quote_currencies))}."
            f" Please use only BTC-based pairs OR only"
            f" USD-based pairs, not a mix."
        )

    return quote_currencies.pop() if quote_currencies else None


def auto_correct_market_focus(
    strategy_type: str,
    strategy_config: dict,
    quote_currency: Optional[str],
    entity_name: str = "",
) -> None:
    """
    Auto-correct market_focus for AI autonomous bots to match quote currency.

    Modifies strategy_config in-place if correction is needed.
    """
    if strategy_type != "ai_autonomous" or not quote_currency:
        return

    if "market_focus" not in strategy_config:
        return

    if strategy_config["market_focus"] != quote_currency:
        logger.warning(
            f"Auto-correcting market_focus from "
            f"'{strategy_config['market_focus']}'"
            f" to '{quote_currency}' to match "
            f"{quote_currency}-based trading pairs"
            f"{f' for bot {entity_name!r}' if entity_name else ''}"
        )
        strategy_config["market_focus"] = quote_currency


async def validate_bidirectional_budget_config(
    db: AsyncSession,
    bot,
    quote_currency: Optional[str],
    is_update: bool = False,
) -> Tuple[float, float]:
    """
    Validate bidirectional budget config and calculate required reservations.

    Returns (required_usd, required_btc) for reservation.
    Raises ValidationError on validation failure.
    """
    long_pct = bot.strategy_config.get("long_budget_percentage", 50.0)
    short_pct = bot.strategy_config.get("short_budget_percentage", 50.0)

    if abs((long_pct + short_pct) - 100.0) > 0.01:
        raise ValidationError(
            f"Long and short budget percentages must sum"
            f" to 100% (got {long_pct}% + {short_pct}%"
            f" = {long_pct + short_pct}%)"
        )

    # Get exchange client
    try:
        from app.services.exchange_service import get_exchange_client_for_account
        exchange = await get_exchange_client_for_account(db, bot.account_id)
        if not exchange:
            raise ValidationError("No exchange client for account")
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("Failed to connect to exchange")

    # Get balances and aggregate values per quote currency
    try:
        # Use per-market aggregate for budget (not total portfolio)
        aggregate_usd_value = await exchange.calculate_aggregate_quote_value(
            "USD", bypass_cache=True
        )
        aggregate_btc_value = await exchange.calculate_aggregate_quote_value(
            "BTC", bypass_cache=True
        )
        current_btc_price = await exchange.get_btc_usd_price()
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("Failed to calculate aggregate values")

    # Calculate required reservations
    budget_pct = bot.budget_percentage or 0.0
    if budget_pct <= 0:
        raise ValidationError("Budget percentage must be > 0 for bidirectional bots")

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
        raise ValidationError(error_msg)

    return required_usd, required_btc
