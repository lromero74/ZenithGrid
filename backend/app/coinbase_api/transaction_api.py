"""
Coinbase v2 transaction fetching for deposits and withdrawals.

Uses the Coinbase v2 account transactions endpoint to retrieve
deposit/withdrawal history for accurate P&L calculation.

Our HMAC auth headers (CB-ACCESS-KEY/SIGN/TIMESTAMP) are compatible
with both v3 (Advanced Trade) and v2 (App API) endpoints.
CDP/JWT auth may not work with v2 — handled gracefully.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Transaction types we care about for deposit/withdrawal tracking
DEPOSIT_TYPES = {"fiat_deposit", "exchange_deposit", "send"}
WITHDRAWAL_TYPES = {"fiat_withdrawal", "exchange_withdrawal", "cardspend"}
ALL_TRANSFER_TYPES = DEPOSIT_TYPES | WITHDRAWAL_TYPES


async def get_transactions(
    request_func: Callable,
    account_uuid: str,
    starting_after: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Fetch transactions for a Coinbase account (v2 API).

    Args:
        request_func: Authenticated request callable
        account_uuid: Coinbase account UUID
        starting_after: Pagination cursor (transaction ID)
        limit: Max results per page (max 100)

    Returns:
        Raw API response dict with 'data' and 'pagination' keys
    """
    url = f"/v2/accounts/{account_uuid}/transactions?limit={limit}"
    if starting_after:
        url += f"&starting_after={starting_after}"

    return await request_func("GET", url)


async def get_all_transfers(
    request_func: Callable,
    account_uuid: str,
    since_iso: Optional[str] = None,
    max_pages: int = 10,
) -> List[Dict[str, Any]]:
    """
    Fetch all deposit/withdrawal transactions for an account, paginating
    until we reach `since_iso` date or run out of pages.

    Args:
        request_func: Authenticated request callable
        account_uuid: Coinbase account UUID
        since_iso: ISO datetime string — stop paginating once we pass this date
        max_pages: Safety limit on pagination

    Returns:
        List of normalized transfer dicts
    """
    transfers = []
    cursor = None
    page = 0

    while page < max_pages:
        try:
            result = await get_transactions(
                request_func, account_uuid,
                starting_after=cursor,
            )
        except Exception as e:
            logger.warning(
                f"Failed to fetch transactions for account {account_uuid}: {e}"
            )
            break

        data = result.get("data", [])
        if not data:
            break

        for txn in data:
            txn_type = txn.get("type", "")
            if txn_type not in ALL_TRANSFER_TYPES:
                continue

            # Check date cutoff
            created_at = txn.get("created_at", "")
            if since_iso and created_at < since_iso:
                # Past our cutoff — we can stop (transactions are newest-first)
                return transfers

            normalized = _normalize_transaction(txn)
            if normalized:
                transfers.append(normalized)

        # Pagination
        pagination = result.get("pagination", {})
        next_uri = pagination.get("next_uri")
        if not next_uri:
            break

        # Extract starting_after from next_uri query param
        cursor = pagination.get("next_starting_after")
        if not cursor:
            # Try to parse from next_uri
            if "starting_after=" in next_uri:
                cursor = next_uri.split("starting_after=")[1].split("&")[0]
            else:
                break

        page += 1

    return transfers


def _normalize_transaction(txn: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Normalize a Coinbase v2 transaction into our transfer format.

    For 'send' type: positive amount = incoming (deposit), negative = outgoing (withdrawal)
    """
    txn_type = txn.get("type", "")
    amount_data = txn.get("amount", {})
    native_amount_data = txn.get("native_amount", {})

    try:
        amount = float(amount_data.get("amount", 0))
        currency = amount_data.get("currency", "")
    except (ValueError, TypeError):
        return None

    # Determine USD equivalent
    amount_usd = None
    try:
        native_currency = native_amount_data.get("currency", "")
        native_amount = float(native_amount_data.get("amount", 0))
        if native_currency == "USD":
            amount_usd = abs(native_amount)
    except (ValueError, TypeError):
        pass

    # Classify as deposit or withdrawal
    if txn_type in DEPOSIT_TYPES:
        if txn_type == "send" and amount < 0:
            transfer_type = "withdrawal"
        else:
            transfer_type = "deposit"
    elif txn_type in WITHDRAWAL_TYPES:
        transfer_type = "withdrawal"
    else:
        return None

    return {
        "external_id": txn.get("id"),
        "transfer_type": transfer_type,
        "amount": abs(amount),
        "currency": currency,
        "amount_usd": amount_usd,
        "occurred_at": txn.get("created_at", ""),
        "coinbase_type": txn_type,
        "status": txn.get("status", ""),
    }
