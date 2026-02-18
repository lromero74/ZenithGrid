"""
Trading Router - Manual trading operations

Handles user-initiated buy/sell orders for portfolio management.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account, User
from app.auth.dependencies import get_current_user
from app.services.exchange_service import get_exchange_client_for_account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trading", tags=["trading"])


class MarketSellRequest(BaseModel):
    product_id: str  # e.g., "UNI-USD", "ETH-BTC"
    size: float  # Amount of base asset to sell
    account_id: int | None = None  # Optional: specify which account to use


@router.post("/market-sell")
async def market_sell(
    request: MarketSellRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Execute a market sell order.

    Sells the specified amount of base asset at current market price.
    Guaranteed to fill (market order).
    """
    try:
        # Get user's active trading account
        query = select(Account).where(
            Account.user_id == current_user.id,
            Account.is_active.is_(True),
            Account.type == 'cex'
        )

        if request.account_id:
            query = query.where(Account.id == request.account_id)
        else:
            query = query.where(Account.is_default.is_(True))

        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(
                status_code=404,
                detail="No active trading account found. Please configure your exchange account in Settings."
            )

        # Get exchange client
        exchange = await get_exchange_client_for_account(db, account.id)
        if not exchange:
            raise HTTPException(
                status_code=500,
                detail="Failed to connect to exchange"
            )

        # Validate product ID format
        if '-' not in request.product_id:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid product_id format: {request.product_id}. Expected format: BASE-QUOTE (e.g., UNI-USD)"
            )

        base_asset = request.product_id.split('-')[0]

        # Validate size
        if request.size <= 0:
            raise HTTPException(
                status_code=400,
                detail="Size must be greater than 0"
            )

        logger.info(
            f"User {current_user.email} executing market sell: "
            f"{request.size} {base_asset} on {request.product_id}"
        )

        # Execute market sell order
        order = await exchange.create_market_order(
            product_id=request.product_id,
            side='sell',
            size=request.size
        )

        logger.info(f"Market sell executed successfully: {order.get('order_id', 'N/A')}")

        # Return order details
        return {
            "success": True,
            "order_id": order.get('order_id'),
            "product_id": request.product_id,
            "side": "sell",
            "size": request.size,
            "filled_size": order.get('filled_size', 0),
            "filled_value": order.get('filled_value', 0),
            "average_filled_price": order.get('average_filled_price', 0),
            "status": order.get('status', 'unknown')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Market sell failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to execute market sell"
        )
