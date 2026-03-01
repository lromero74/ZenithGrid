"""
Position Manual Operations Router

Handles manual position operations: add funds and update notes.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.currency_utils import get_quote_currency
from app.database import get_db
from app.models import Account, Position, User
from app.position_routers.dependencies import get_coinbase
from app.position_routers.schemas import AddFundsRequest, UpdateNotesRequest
from app.auth.dependencies import require_permission, Perm
from app.trading_client import TradingClient
from app.trading_engine.buy_executor import execute_buy

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{position_id}/add-funds")
async def add_funds_to_position(
    position_id: int,
    request: AddFundsRequest,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase),
    current_user: User = Depends(require_permission(Perm.POSITIONS_WRITE)),
):
    """Manually add funds to a position (manual safety order)"""
    quote_amount = request.btc_amount  # Multi-currency: actually quote amount (BTC or USD)
    try:
        # Verify position belongs to current user
        accounts_q = select(Account.id).where(Account.user_id == current_user.id)
        accounts_r = await db.execute(accounts_q)
        user_account_ids = [row[0] for row in accounts_r.fetchall()]
        if not user_account_ids:
            raise HTTPException(status_code=404, detail="Position not found")

        query = select(Position).where(
            Position.id == position_id,
            Position.account_id.in_(user_account_ids),
        )
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        # Get quote currency for this position
        quote_currency = get_quote_currency(position.product_id)

        # Check if adding funds would exceed max allowed (multi-currency)
        if position.total_quote_spent + quote_amount > position.max_quote_allowed:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Adding {quote_amount:.8f} {quote_currency} would exceed max allowed "
                    f"({position.max_quote_allowed:.8f} {quote_currency})"
                ),
            )

        # Get current price for the position's product
        current_price = await coinbase.get_current_price(position.product_id)

        # Get bot for this position (required for execute_buy)
        if not position.bot:
            raise HTTPException(status_code=400, detail="Position has no associated bot")

        # Execute buy using modular function
        trading_client = TradingClient(coinbase)
        trade = await execute_buy(
            db=db,
            coinbase=coinbase,
            trading_client=trading_client,
            bot=position.bot,
            product_id=position.product_id,
            position=position,
            quote_amount=quote_amount,
            current_price=current_price,
            trade_type="manual_safety_order",
            signal_data=None,
            commit_on_error=True,
        )

        # Format response (multi-currency aware)
        base_currency = position.product_id.split("-")[0]
        return {
            "message": f"Added {quote_amount:.8f} {quote_currency} to position {position_id}",
            "trade_id": trade.id if trade else None,
            "price": current_price,
            "base_acquired": trade.base_amount if trade else 0.0,
            "base_currency": base_currency,
            "quote_currency": quote_currency,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.patch("/{position_id}/notes")
async def update_position_notes(
    position_id: int, request: UpdateNotesRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission(Perm.POSITIONS_WRITE))
):
    """Update notes for a position"""
    try:
        # Verify position belongs to current user
        accounts_q = select(Account.id).where(Account.user_id == current_user.id)
        accounts_r = await db.execute(accounts_q)
        user_account_ids = [row[0] for row in accounts_r.fetchall()]
        if not user_account_ids:
            raise HTTPException(status_code=404, detail="Position not found")

        query = select(Position).where(
            Position.id == position_id,
            Position.account_id.in_(user_account_ids),
        )
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        # Update notes
        position.notes = request.notes

        await db.commit()

        return {"message": f"Notes updated for position {position_id}", "notes": position.notes}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="An internal error occurred")
