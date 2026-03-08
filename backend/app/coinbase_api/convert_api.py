"""
Convert operations for Coinbase API
Handles USD↔USDC 1:1 conversions via the convert endpoint.
"""

import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


async def create_convert_quote(
    request_func: Callable,
    from_account: str,
    to_account: str,
    amount: str,
) -> Dict[str, Any]:
    """
    Create a conversion quote (step 1 of 2).

    Args:
        request_func: Authenticated request function
        from_account: Coinbase account UUID for source currency
        to_account: Coinbase account UUID for target currency
        amount: Amount to convert (as string)

    Returns:
        Response containing trade details including trade_id
    """
    data = {
        "from_account": from_account,
        "to_account": to_account,
        "amount": amount,
    }
    return await request_func("POST", "/api/v3/brokerage/convert/quote", data=data)


async def commit_convert_trade(
    request_func: Callable,
    trade_id: str,
    from_account: str,
    to_account: str,
) -> Dict[str, Any]:
    """
    Commit a conversion trade (step 2 of 2).

    Args:
        request_func: Authenticated request function
        trade_id: Trade ID from create_convert_quote response
        from_account: Coinbase account UUID for source currency
        to_account: Coinbase account UUID for target currency

    Returns:
        Response confirming the committed conversion
    """
    data = {
        "from_account": from_account,
        "to_account": to_account,
    }
    return await request_func(
        "POST", f"/api/v3/brokerage/convert/trade/{trade_id}", data=data
    )
