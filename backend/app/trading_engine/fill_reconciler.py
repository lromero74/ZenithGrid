"""
Shared fill reconciliation logic for buy and sell executors.

Provides retry-based order fill data retrieval with exponential backoff.
Both buy_executor and sell_executor use this to fetch actual fill amounts
from the exchange after placing orders.
"""

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Optional

from app.product_precision import get_base_precision

logger = logging.getLogger(__name__)


@dataclass
class FillData:
    """Result of order fill reconciliation."""
    filled_size: float  # Base currency amount filled (net of fees for buy)
    filled_value: float  # Quote currency amount
    average_price: float  # Average fill price
    total_fees: float  # Total fees charged


async def reconcile_order_fill(
    exchange,
    order_id: str,
    product_id: str,
    max_retries: int = 10,
    adjust_btc_fees: bool = False,
    round_base_to_precision: bool = False,
    fallback_base: Optional[float] = None,
    fallback_price: Optional[float] = None,
) -> FillData:
    """
    Retry-based order fill data retrieval with exponential backoff.

    Market orders can take time to fill on illiquid pairs - retries up to
    max_retries times over ~30s with exponential backoff (0.5s, 1s, 2s, 4s,
    then capped at 5s).

    Args:
        exchange: Exchange client instance with get_order() method
        order_id: The exchange order ID to check
        product_id: Trading pair (e.g., 'ETH-USD', 'ETH-BTC')
        max_retries: Maximum number of retry attempts (default 10)
        adjust_btc_fees: If True, deduct fees from base amount for BTC pairs.
            For BTC pair buy orders, fees are charged IN the base currency,
            so filled_size is GROSS and actual received = filled_size - fee_in_base.
        round_base_to_precision: If True, floor base amount to exchange's
            base_increment precision. This ensures we never record more than
            we can sell (avoids precision loss on sell).
        fallback_base: If provided, use this as base amount when fill data
            is unavailable after all retries (for sell orders that have an
            expected amount).
        fallback_price: If provided, use this as price when fill data is
            unavailable after all retries.

    Returns:
        FillData with filled amounts. If order never fills and no fallback
        is provided, returns zero amounts.
    """
    for attempt in range(max_retries):
        if attempt > 0:
            # Exponential backoff: 0.5s, 1s, 2s, 4s, then cap at 5s
            if attempt < 5:
                delay = 0.5 * (2 ** (attempt - 1))
            else:
                delay = 5.0
            logger.info(f"Waiting {delay}s before retry {attempt + 1}/{max_retries}...")
            await asyncio.sleep(delay)

        try:
            order_details = await exchange.get_order(order_id)
        except Exception as get_err:
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries}: "
                f"get_order({order_id}) failed: {get_err}"
            )
            if attempt == max_retries - 1:
                logger.error(
                    f"Order {order_id} placed but fill data "
                    f"unavailable after {max_retries} attempts."
                )
            continue

        # Parse fill data from order details
        raw_filled_size = float(order_details.get("filled_size", "0"))
        raw_filled_value = float(order_details.get("filled_value", "0"))
        raw_avg_price = float(order_details.get("average_filled_price", "0"))
        raw_total_fees = float(order_details.get("total_fees", "0"))

        # Apply BTC pair fee adjustment if requested
        actual_base = raw_filled_size
        if adjust_btc_fees:
            is_btc_pair = product_id.endswith("-BTC")
            if is_btc_pair and raw_avg_price > 0 and raw_total_fees > 0:
                if raw_filled_value > 0:
                    fee_rate = raw_total_fees / raw_filled_value
                    fee_in_base = raw_filled_size * fee_rate
                    actual_base = raw_filled_size - fee_in_base
                    logger.info(
                        f"BTC pair fee adjustment: gross={raw_filled_size:.8f}, "
                        f"fee_rate={fee_rate:.4%}, fee_in_base={fee_in_base:.8f}, "
                        f"net={actual_base:.8f}"
                    )

        # Round base amount to exchange precision if requested
        if round_base_to_precision and actual_base > 0:
            precision = get_base_precision(product_id)
            actual_base_raw = actual_base
            actual_base = math.floor(actual_base * (10 ** precision)) / (10 ** precision)
            if actual_base_raw != actual_base:
                logger.info(
                    f"Rounded base amount to increment: raw={actual_base_raw:.8f}, "
                    f"rounded={actual_base:.8f} (precision={precision} decimals)"
                )

        # Check if order has filled (non-zero amounts)
        if actual_base > 0 and raw_filled_value > 0:
            logger.info(
                f"Order filled - Base: {actual_base}, "
                f"Quote: {raw_filled_value}, Avg Price: {raw_avg_price}"
            )
            return FillData(
                filled_size=actual_base,
                filled_value=raw_filled_value,
                average_price=raw_avg_price,
                total_fees=raw_total_fees,
            )

        logger.warning(
            f"Attempt {attempt + 1}/{max_retries}: Order not yet filled (amounts still zero)"
        )
        if attempt == max_retries - 1:
            logger.error(
                f"Order {order_id} did not fill after {max_retries} "
                f"attempts (~30s)."
            )

    # All retries exhausted - use fallbacks if provided
    if fallback_base is not None and fallback_price is not None:
        logger.warning(
            f"Could not fetch fill data for {order_id} after "
            f"{max_retries} attempts. Using estimates: "
            f"{fallback_base} @ {fallback_price}"
        )
        return FillData(
            filled_size=fallback_base,
            filled_value=fallback_base * fallback_price,
            average_price=fallback_price,
            total_fees=0.0,
        )

    # No fallback - return zeros (caller must handle)
    logger.error(
        f"WARNING: Order {order_id} has zero fill amounts after all retries! "
        f"Manual fix required using scripts/fix_position.py"
    )
    return FillData(
        filled_size=0.0,
        filled_value=0.0,
        average_price=0.0,
        total_fees=0.0,
    )
