"""
Bot Validation Router

Handles validation of bot configurations against Coinbase minimum order sizes.
Works for both live and paper trading accounts.
"""

import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account, User
from app.auth.dependencies import get_current_user
from app.encryption import decrypt_value, is_encrypted
from app.exchange_clients.factory import create_exchange_client, ExchangeClientConfig, CoinbaseCredentials
from app.exchange_clients.paper_trading_client import PaperTradingClient
from app.order_validation import calculate_minimum_budget_percentage
from app.bot_routers.schemas import (
    ValidateBotConfigRequest, ValidateBotConfigResponse, ValidationWarning,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_exchange_client(db: AsyncSession, user_id: int):
    """
    Get an exchange client for validation.

    Tries a real CEX account first. Falls back to a PaperTradingClient
    (which uses public market data) so paper-trading users still get
    proper exchange-minimum validation.

    Returns (client, account) tuple.
    """
    # Try real CEX account first
    query = select(Account).where(
        Account.type == "cex",
        Account.is_active.is_(True),
        Account.is_paper_trading.is_not(True),
    )
    query = query.where(Account.user_id == user_id)
    query = query.order_by(Account.is_default.desc(), Account.created_at).limit(1)

    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if account and account.api_key_name and account.api_private_key:
        private_key = account.api_private_key
        if private_key and is_encrypted(private_key):
            private_key = decrypt_value(private_key)
        client = create_exchange_client(ExchangeClientConfig(
            exchange_type="cex",
            coinbase=CoinbaseCredentials(
                key_name=account.api_key_name,
                private_key=private_key,
            ),
        ))
        return client, account

    # Fall back to paper trading account
    paper_query = select(Account).where(
        Account.user_id == user_id,
        Account.is_active.is_(True),
        Account.is_paper_trading.is_(True),
    )
    paper_query = paper_query.order_by(
        Account.is_default.desc(), Account.created_at
    ).limit(1)

    result = await db.execute(paper_query)
    paper_account = result.scalar_one_or_none()

    if paper_account:
        client = PaperTradingClient(
            account=paper_account, db=db
        )
        return client, paper_account

    return None, None


@router.post("/validate-config", response_model=ValidateBotConfigResponse)
async def validate_bot_config(
    request: ValidateBotConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Validate if bot configuration meets minimum order size requirements.

    Works for both live and paper trading accounts. Paper trading uses
    public market data to enforce the same exchange minimums as live.
    """
    client, account = await _get_exchange_client(db, current_user.id)
    if not client:
        raise HTTPException(
            status_code=400,
            detail="No active exchange or paper trading account found.",
        )

    is_paper = getattr(account, "is_paper_trading", False)

    # Get quote balance if not provided
    quote_balance = request.quote_balance
    if quote_balance is None:
        if not request.product_ids:
            raise HTTPException(
                status_code=400, detail="No product_ids provided"
            )

        first_product = request.product_ids[0]
        quote_currency = (
            first_product.split("-")[1] if "-" in first_product else "BTC"
        )

        if is_paper:
            # Read balance from paper_balances JSON
            balances = {}
            if account.paper_balances:
                balances = json.loads(account.paper_balances)
            quote_balance = balances.get(quote_currency, 0.0)
        else:
            if quote_currency == "BTC":
                quote_balance = await client.get_btc_balance()
            elif quote_currency == "USD":
                breakdown = await client.get_portfolio_breakdown()
                spot_positions = breakdown.get("spot_positions", [])
                for pos in spot_positions:
                    if pos.get("asset") == "USD":
                        quote_balance = float(
                            pos.get("available_to_trade_fiat", 0)
                        )
                        break
            else:
                quote_balance = 100.0  # Default fallback

    if not quote_balance or quote_balance <= 0:
        return ValidateBotConfigResponse(
            is_valid=False,
            warnings=[],
            message="No quote currency balance available. Cannot validate.",
        )

    # Extract relevant percentages from config
    base_order_pct = request.strategy_config.get("base_order_percentage", 0)
    safety_order_pct = request.strategy_config.get(
        "safety_order_percentage", 0
    )
    initial_budget_pct = request.strategy_config.get(
        "initial_budget_percentage", 0
    )

    # Use whichever is configured (different strategies use different names)
    order_pct = max(base_order_pct, safety_order_pct, initial_budget_pct)

    if order_pct <= 0:
        return ValidateBotConfigResponse(
            is_valid=False,
            warnings=[],
            message=(
                "No order percentage configured. Please set "
                "base_order_percentage, safety_order_percentage, "
                "or initial_budget_percentage."
            ),
        )

    # Check each product against exchange minimums
    warnings: List[ValidationWarning] = []
    for product_id in request.product_ids:
        try:
            min_pct = await calculate_minimum_budget_percentage(
                client, product_id, quote_balance
            )

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

    is_valid = len(warnings) == 0

    if is_valid:
        message = (
            "Bot configuration is valid. "
            "All orders meet minimum size requirements."
        )
    else:
        message = (
            f"Warning: {len(warnings)} product(s) may fail "
            f"due to minimum order size requirements."
        )

    return ValidateBotConfigResponse(
        is_valid=is_valid, warnings=warnings, message=message
    )
