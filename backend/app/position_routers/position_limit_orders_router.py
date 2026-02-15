"""
Position Limit Orders Router

Handles all limit order operations for positions:
- Create limit close order
- Get ticker (bid/ask/mark)
- Check slippage
- Cancel limit close
- Update limit close price
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import PendingOrder, Position
from app.coinbase_unified_client import CoinbaseClient
from app.position_routers.dependencies import get_coinbase
from app.position_routers.schemas import LimitCloseRequest, UpdateLimitCloseRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{position_id}/limit-close")
async def limit_close_position(
    position_id: int,
    request: LimitCloseRequest,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase),
):
    """Close a position via limit order"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        if position.closing_via_limit:
            raise HTTPException(status_code=400, detail="Position already has a pending limit close order")

        # Round size to proper precision using product precision data
        from app.order_validation import get_product_minimums
        from decimal import Decimal

        minimums = await get_product_minimums(coinbase, position.product_id)
        base_increment = Decimal(minimums.get('base_increment', '0.00000001'))
        total_base = Decimal(str(position.total_base_acquired))

        # Floor division to round down to nearest increment (avoid INSUFFICIENT_FUND)
        rounded_size = (total_base // base_increment) * base_increment
        size_to_sell = str(float(rounded_size))

        logger.info(
            f"Position {position_id} limit close: "
            f"raw size={position.total_base_acquired}, "
            f"base_increment={base_increment}, "
            f"rounded size={size_to_sell}"
        )

        # Validate GTD orders have end_time
        if request.time_in_force == "gtd" and not request.end_time:
            raise HTTPException(status_code=400, detail="end_time is required for GTD orders")

        # Create limit sell order via Coinbase
        order_result = await coinbase.create_limit_order(
            product_id=position.product_id,
            side="SELL",
            limit_price=request.limit_price,
            size=size_to_sell,  # Sell entire position (rounded to valid precision)
            time_in_force=request.time_in_force,
            end_time=request.end_time,
        )

        # Log the full response for debugging
        logger.info(f"Coinbase create_limit_order response: {order_result}")

        # Extract order ID from response
        order_id = order_result.get("order_id") or order_result.get("success_response", {}).get("order_id")

        if not order_id:
            # Log the full error for debugging
            error_response = order_result.get("error_response", {})
            error_msg = error_response.get("message", "Unknown error")
            error_details = error_response.get("error_details", "")
            logger.error(
                f"Failed to create limit order for position {position_id}: "
                f"error={error_response.get('error')}, message={error_msg}, details={error_details}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create limit order: {error_msg}"
            )

        # Create PendingOrder record to track this limit sell
        # Manual limit close orders should not be auto-adjusted by the system
        pending_order = PendingOrder(
            position_id=position.id,
            bot_id=position.bot_id,
            order_id=order_id,
            product_id=position.product_id,
            side="SELL",
            order_type="LIMIT",
            limit_price=request.limit_price,
            quote_amount=0.0,  # Will be filled when order completes
            base_amount=position.total_base_acquired,
            trade_type="limit_close",
            status="pending",
            remaining_base_amount=position.total_base_acquired,
            fills=[],
            time_in_force=request.time_in_force,
            end_time=request.end_time,
            is_manual=True,  # Manual orders are NOT auto-adjusted to bid
        )
        db.add(pending_order)

        # Update position to indicate it's closing via limit
        position.closing_via_limit = True
        position.limit_close_order_id = order_id

        await db.commit()

        return {
            "message": "Limit close order placed successfully",
            "order_id": order_id,
            "limit_price": request.limit_price,
            "base_amount": position.total_base_acquired,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating limit close order for position {position_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/{position_id}/ticker")
async def get_position_ticker(
    position_id: int, db: AsyncSession = Depends(get_db), coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Get current bid/ask/mark prices for a position"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        # Get ticker data including bid/ask
        ticker = await coinbase.get_ticker(position.product_id)

        best_bid = float(ticker.get("best_bid", 0))
        best_ask = float(ticker.get("best_ask", 0))
        mark_price = (best_bid + best_ask) / 2 if best_bid and best_ask else float(ticker.get("price", 0))

        return {
            "product_id": position.product_id,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mark_price": mark_price,
            "last_price": float(ticker.get("price", 0)),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/{position_id}/slippage-check")
async def check_market_close_slippage(
    position_id: int, db: AsyncSession = Depends(get_db), coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Check if closing at market would result in significant slippage"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        # Get ticker data including bid/ask
        ticker = await coinbase.get_ticker(position.product_id)
        best_bid = float(ticker.get("best_bid", 0))
        best_ask = float(ticker.get("best_ask", 0))
        mark_price = (best_bid + best_ask) / 2 if best_bid and best_ask else float(ticker.get("price", 0))

        # Calculate expected profit at mark price
        current_value_at_mark = position.total_base_acquired * mark_price
        expected_profit_at_mark = current_value_at_mark - position.total_quote_spent

        # Calculate actual profit when selling at best bid (market sell)
        actual_value_at_bid = position.total_base_acquired * best_bid
        actual_profit_at_bid = actual_value_at_bid - position.total_quote_spent

        # Calculate slippage
        slippage_amount = expected_profit_at_mark - actual_profit_at_bid
        slippage_percentage = 0.0

        # Calculate slippage as % of expected profit (if profitable)
        if expected_profit_at_mark > 0:
            slippage_percentage = (slippage_amount / expected_profit_at_mark) * 100

        # Determine if warning should be shown (>25% slippage)
        show_warning = slippage_percentage > 25.0

        return {
            "product_id": position.product_id,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mark_price": mark_price,
            "expected_profit_at_mark": expected_profit_at_mark,
            "actual_profit_at_bid": actual_profit_at_bid,
            "slippage_amount": slippage_amount,
            "slippage_percentage": slippage_percentage,
            "show_warning": show_warning,
            "position_value_at_bid": actual_value_at_bid,
            "position_value_at_mark": current_value_at_mark,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/{position_id}/cancel-limit-close")
async def cancel_limit_close(
    position_id: int, db: AsyncSession = Depends(get_db), coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Cancel a pending limit close order"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if not position.closing_via_limit:
            raise HTTPException(status_code=400, detail="Position does not have a pending limit close order")

        # Cancel the order on Coinbase
        await coinbase.cancel_order(position.limit_close_order_id)

        # Update pending order status
        pending_order_query = select(PendingOrder).where(PendingOrder.order_id == position.limit_close_order_id)
        pending_order_result = await db.execute(pending_order_query)
        pending_order = pending_order_result.scalars().first()

        if pending_order:
            pending_order.status = "canceled"
            pending_order.canceled_at = datetime.utcnow()

        # Reset position limit close flags
        position.closing_via_limit = False
        position.limit_close_order_id = None

        await db.commit()

        return {"message": "Limit close order canceled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/{position_id}/update-limit-close")
async def update_limit_close(
    position_id: int,
    request: UpdateLimitCloseRequest,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase),
):
    """Update the limit price for a pending limit close order using Coinbase's native Edit Order API"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if not position.closing_via_limit:
            raise HTTPException(status_code=400, detail="Position does not have a pending limit close order")

        # Get the pending order
        pending_order_query = select(PendingOrder).where(PendingOrder.order_id == position.limit_close_order_id)
        pending_order_result = await db.execute(pending_order_query)
        pending_order = pending_order_result.scalars().first()

        if not pending_order:
            raise HTTPException(status_code=404, detail="Pending order not found")

        # Format the new limit price with product-specific precision
        from app.product_precision import format_quote_amount_for_product
        formatted_price = format_quote_amount_for_product(request.new_limit_price, position.product_id)

        logger.info(
            f"Position {position_id} editing limit order: "
            f"order_id={position.limit_close_order_id}, "
            f"new_price={formatted_price}"
        )

        # Use Coinbase's native Edit Order API (atomic operation, preserves order in some cases)
        edit_result = await coinbase.edit_order(
            order_id=position.limit_close_order_id,
            price=formatted_price
        )

        # Log the full response for debugging
        logger.info(f"Coinbase edit_order response: {edit_result}")

        # Check if edit was successful
        success_response = edit_result.get("success_response") or edit_result
        if not success_response or edit_result.get("error_response"):
            error_response = edit_result.get("error_response", {})
            error_msg = error_response.get("message", "Unknown error")
            logger.error(
                f"Failed to edit limit order for position {position_id}: "
                f"error={error_response.get('error')}, message={error_msg}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to edit limit order: {error_msg}"
            )

        # Update pending order with new price (order ID stays the same)
        pending_order.limit_price = request.new_limit_price

        await db.commit()

        return {
            "message": "Limit close order updated successfully",
            "order_id": position.limit_close_order_id,  # Same order ID
            "new_limit_price": request.new_limit_price,
            "remaining_amount": pending_order.remaining_base_amount or position.total_base_acquired,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating limit close order for position {position_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")
