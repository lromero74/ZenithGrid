"""
Position Router Dependencies

Shared dependency functions for all position router modules.
"""

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.database import get_db
from app.models import Account
from app.exchange_clients.factory import create_exchange_client


async def get_coinbase(db: AsyncSession = Depends(get_db)) -> CoinbaseClient:
    """
    Get Coinbase client from the first active CEX account in the database.

    TODO: Once authentication is wired up, this should get the exchange
    client for the currently logged-in user's account.
    """
    # Get first active CEX account
    result = await db.execute(
        select(Account).where(
            Account.type == "cex",
            Account.is_active.is_(True)
        ).order_by(Account.is_default.desc(), Account.created_at)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=503,
            detail="No Coinbase account configured. Please add your API credentials in Settings."
        )

    if not account.api_key_name or not account.api_private_key:
        raise HTTPException(
            status_code=503,
            detail="Coinbase account missing API credentials. Please update in Settings."
        )

    # Create and return the client
    client = create_exchange_client(
        exchange_type="cex",
        coinbase_key_name=account.api_key_name,
        coinbase_private_key=account.api_private_key,
    )

    if not client:
        raise HTTPException(
            status_code=503,
            detail="Failed to create Coinbase client. Please check your API credentials."
        )

    return client
