"""
Perpetual futures (INTX) API endpoints

Provides endpoints for:
- Listing available perpetual products
- Viewing perpetuals portfolio summary
- Listing/managing open perps positions
- Modifying TP/SL on existing positions
- Manually closing positions
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.coinbase_unified_client import CoinbaseClient
from app.database import get_db
from app.models import Account, Position, User
from app.position_routers.dependencies import get_coinbase
from app.routers.auth_dependencies import get_current_user_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/perps", tags=["perpetuals"])


# ===== Request/Response Schemas =====


class ModifyTpSlRequest(BaseModel):
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None


class ClosePositionRequest(BaseModel):
    reason: str = "manual"


class PerpsPortfolioResponse(BaseModel):
    portfolio_uuid: str
    summary: dict
    balances: dict


# ===== Helper: get CoinbaseClient from adapter =====


def _get_coinbase_client(exchange) -> CoinbaseClient:
    """Extract raw CoinbaseClient from ExchangeClient adapter"""
    client = getattr(exchange, '_client', None) or getattr(exchange, 'client', None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Cannot access Coinbase client for perpetuals"
        )
    return client


# ===== Endpoints =====


@router.get("/products")
async def list_perps_products(
    exchange=Depends(get_coinbase),
):
    """List available INTX perpetual futures products"""
    client = _get_coinbase_client(exchange)
    try:
        products = await client.list_perps_products()
        return {
            "products": [
                {
                    "product_id": p.get("product_id", ""),
                    "display_name": p.get("display_name", p.get("product_id", "")),
                    "base_currency": p.get("base_currency_id", ""),
                    "quote_currency": p.get("quote_currency_id", ""),
                    "status": p.get("status", ""),
                    "price": p.get("price", "0"),
                    "volume_24h": p.get("volume_24h", "0"),
                }
                for p in products
            ],
            "count": len(products),
        }
    except Exception as e:
        logger.error(f"Failed to list perps products: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio")
async def get_perps_portfolio(
    db: AsyncSession = Depends(get_db),
    exchange=Depends(get_coinbase),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get perpetuals portfolio summary (margin, balances, positions)"""
    client = _get_coinbase_client(exchange)

    # Get portfolio UUID from account
    portfolio_uuid = await _get_portfolio_uuid(db, current_user)

    try:
        summary = await client.get_perps_portfolio_summary(portfolio_uuid)
        balances = await client.get_perps_balances(portfolio_uuid)

        return {
            "portfolio_uuid": portfolio_uuid,
            "summary": summary,
            "balances": balances,
        }
    except Exception as e:
        logger.error(f"Failed to get perps portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def list_perps_positions(
    db: AsyncSession = Depends(get_db),
    exchange=Depends(get_coinbase),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """List open perps positions (DB records synced with exchange)"""
    # Get DB positions
    query = (
        select(Position)
        .where(Position.product_type == "future")
        .where(Position.status == "open")
        .options(selectinload(Position.trades))
    )
    if current_user:
        query = query.where(Position.user_id == current_user.id)

    result = await db.execute(query)
    positions = result.scalars().all()

    return {
        "positions": [
            {
                "id": p.id,
                "product_id": p.product_id,
                "direction": p.direction,
                "status": p.status,
                "leverage": p.leverage,
                "margin_type": p.perps_margin_type,
                "entry_price": p.entry_price or p.average_buy_price,
                "current_size": (
                    p.total_base_acquired if p.direction == "long"
                    else p.short_total_sold_base
                ),
                "notional_usdc": p.total_quote_spent or p.short_total_sold_quote,
                "unrealized_pnl": p.unrealized_pnl,
                "liquidation_price": p.liquidation_price,
                "tp_price": p.tp_price,
                "sl_price": p.sl_price,
                "funding_fees_total": p.funding_fees_total,
                "opened_at": p.opened_at.isoformat() if p.opened_at else None,
                "trade_count": len(p.trades) if p.trades else 0,
            }
            for p in positions
        ],
        "count": len(positions),
    }


@router.post("/positions/{position_id}/modify-tp-sl")
async def modify_tp_sl(
    position_id: int,
    request: ModifyTpSlRequest,
    db: AsyncSession = Depends(get_db),
    exchange=Depends(get_coinbase),
):
    """Update TP/SL prices on an existing perps position"""
    client = _get_coinbase_client(exchange)

    position = await db.get(Position, position_id)
    if not position or position.product_type != "future" or position.status != "open":
        raise HTTPException(status_code=404, detail="Open perps position not found")

    # Cancel existing TP/SL orders
    for order_id in [position.tp_order_id, position.sl_order_id]:
        if order_id:
            try:
                await client.cancel_order(order_id)
            except Exception as e:
                logger.warning(f"Failed to cancel bracket order {order_id}: {e}")

    # Determine new TP/SL
    new_tp = request.tp_price if request.tp_price is not None else position.tp_price
    new_sl = request.sl_price if request.sl_price is not None else position.sl_price

    # Place new bracket orders if prices are set
    base_size = (
        position.total_base_acquired if position.direction == "long"
        else position.short_total_sold_base
    ) or 0.0
    base_size_str = f"{base_size:.8f}"

    # For TP: place opposite side limit order
    # For SL: place opposite side stop order
    close_side = "SELL" if position.direction == "long" else "BUY"

    new_tp_order_id = None
    new_sl_order_id = None

    if new_tp:
        try:
            from app.coinbase_api.order_api import create_stop_limit_order
            result = await create_stop_limit_order(
                client._request,
                product_id=position.product_id,
                side=close_side,
                base_size=base_size_str,
                stop_price=f"{new_tp:.2f}",
                limit_price=f"{new_tp:.2f}",
            )
            resp = result.get("success_response", {})
            new_tp_order_id = resp.get("order_id")
        except Exception as e:
            logger.error(f"Failed to place new TP order: {e}")

    if new_sl:
        try:
            from app.coinbase_api.order_api import create_stop_limit_order
            result = await create_stop_limit_order(
                client._request,
                product_id=position.product_id,
                side=close_side,
                base_size=base_size_str,
                stop_price=f"{new_sl:.2f}",
                limit_price=f"{new_sl:.2f}",
            )
            resp = result.get("success_response", {})
            new_sl_order_id = resp.get("order_id")
        except Exception as e:
            logger.error(f"Failed to place new SL order: {e}")

    # Update position
    position.tp_price = new_tp
    position.sl_price = new_sl
    position.tp_order_id = new_tp_order_id
    position.sl_order_id = new_sl_order_id
    await db.commit()

    return {
        "success": True,
        "tp_price": new_tp,
        "sl_price": new_sl,
        "tp_order_id": new_tp_order_id,
        "sl_order_id": new_sl_order_id,
    }


@router.post("/positions/{position_id}/close")
async def close_perps_position(
    position_id: int,
    request: ClosePositionRequest,
    db: AsyncSession = Depends(get_db),
    exchange=Depends(get_coinbase),
):
    """Manually close a perps position"""
    client = _get_coinbase_client(exchange)

    position = await db.get(Position, position_id)
    if not position or position.product_type != "future" or position.status != "open":
        raise HTTPException(status_code=404, detail="Open perps position not found")

    # Get current price for PnL calculation
    try:
        current_price = await client.get_current_price(position.product_id)
    except Exception:
        current_price = position.entry_price or position.average_buy_price or 0

    from app.trading_engine.perps_executor import execute_perps_close

    success, profit_usdc, profit_pct = await execute_perps_close(
        db=db,
        client=client,
        position=position,
        current_price=current_price,
        reason=request.reason,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to close perps position")

    return {
        "success": True,
        "profit_usdc": profit_usdc,
        "profit_pct": profit_pct,
    }


# ===== Helpers =====


async def _get_portfolio_uuid(db: AsyncSession, user: Optional[User]) -> str:
    """Get the perps portfolio UUID from the user's account"""
    query = select(Account).where(
        Account.type == "cex",
        Account.is_active.is_(True),
        Account.perps_portfolio_uuid.isnot(None),
    )
    if user:
        query = query.where(Account.user_id == user.id)

    result = await db.execute(query.limit(1))
    account = result.scalar_one_or_none()

    if not account or not account.perps_portfolio_uuid:
        raise HTTPException(
            status_code=404,
            detail="No perpetuals portfolio configured. Link your INTX portfolio in Settings."
        )

    return account.perps_portfolio_uuid
