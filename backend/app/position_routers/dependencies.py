"""
Position Router Dependencies

Shared dependency functions for all position router modules.
"""

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.database import get_db
from app.models import Account, User
from app.encryption import decrypt_value, is_encrypted
from app.exchange_clients.factory import create_exchange_client
from app.auth.dependencies import get_current_user


async def get_coinbase(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CoinbaseClient:
    """
    Get Coinbase client for the authenticated user's active CEX account.
    """
    # Get user's active CEX account (excluding paper trading)
    result = await db.execute(
        select(Account).where(
            Account.user_id == current_user.id,
            Account.type == "cex",
            Account.is_active.is_(True),
            Account.is_paper_trading.is_not(True),
        ).order_by(Account.is_default.desc(), Account.created_at).limit(1)
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

    # Decrypt private key if encrypted
    private_key = account.api_private_key
    if private_key and is_encrypted(private_key):
        private_key = decrypt_value(private_key)

    # Create and return the client
    client = create_exchange_client(
        exchange_type="cex",
        coinbase_key_name=account.api_key_name,
        coinbase_private_key=private_key,
    )

    if not client:
        raise HTTPException(
            status_code=503,
            detail="Failed to create Coinbase client. Please check your API credentials."
        )

    return client
