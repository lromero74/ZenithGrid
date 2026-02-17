"""
Bot Validation Router

Handles validation of bot configurations against Coinbase minimum order sizes.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account, User
from app.coinbase_unified_client import CoinbaseClient
from app.routers.auth_dependencies import get_current_user
from app.encryption import decrypt_value, is_encrypted
from app.exchange_clients.factory import create_exchange_client
from app.order_validation import calculate_minimum_budget_percentage
from app.bot_routers.schemas import ValidateBotConfigRequest, ValidateBotConfigResponse, ValidationWarning

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_coinbase_from_db(db: AsyncSession, user_id: int = None) -> CoinbaseClient:
    """Get Coinbase client from the first active CEX account for a user."""
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


@router.post("/validate-config", response_model=ValidateBotConfigResponse)
async def validate_bot_config(request: ValidateBotConfigRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Validate if bot configuration meets minimum order size requirements

    Checks if the configured budget percentages will result in orders
    that meet Coinbase's minimum order sizes for each product.

    Returns warnings with suggested minimum percentages if validation fails.
    """
    coinbase = await get_coinbase_from_db(db, user_id=current_user.id)
    if not coinbase:
        raise HTTPException(
            status_code=503,
            detail="No Coinbase account configured. Please add your API credentials in Settings."
        )

    # Get quote balance if not provided
    quote_balance = request.quote_balance
    if quote_balance is None:
        # Use first product to determine quote currency
        if not request.product_ids:
            raise HTTPException(status_code=400, detail="No product_ids provided")

        first_product = request.product_ids[0]
        quote_currency = first_product.split("-")[1] if "-" in first_product else "BTC"

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
            is_valid=False, warnings=[], message="No quote currency balance available. Cannot validate."
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
            message="No order percentage configured. Please set base_order_percentage, safety_order_percentage, or initial_budget_percentage.",
        )

    # Check each product
    warnings: List[ValidationWarning] = []
    for product_id in request.product_ids:
        # Get minimum required percentage for this product
        try:
            min_pct = await calculate_minimum_budget_percentage(coinbase, product_id, quote_balance)

            if order_pct < min_pct:
                warnings.append(
                    ValidationWarning(
                        product_id=product_id,
                        issue="Order size will be below Coinbase minimum",
                        suggested_minimum_pct=min_pct,
                        current_pct=order_pct,
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to validate {product_id}: {e}")
            # Continue checking other products

    is_valid = len(warnings) == 0

    if is_valid:
        message = "Bot configuration is valid. All orders meet minimum size requirements."
    else:
        message = f"Warning: {len(warnings)} product(s) may fail due to minimum order size requirements."

    return ValidateBotConfigResponse(is_valid=is_valid, warnings=warnings, message=message)
