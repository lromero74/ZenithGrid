"""
Settings and configuration API routes

Handles settings-related endpoints:
- Get current settings
- Update settings
- Test API connection
"""

import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.config import settings
from app.database import get_db
from app.models import Account, Settings, User
from app.encryption import decrypt_value, is_encrypted
from app.exchange_clients.factory import create_exchange_client
from app.routers.auth_dependencies import get_current_user
from app.schemas import SettingsUpdate, TestConnectionRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["settings"])


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


def update_env_file(key: str, value: str):
    """Update a value in the .env file"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

    # Read existing .env file
    lines = []
    key_found = False
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()

    # Update or add the key
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            key_found = True
            break

    if not key_found:
        lines.append(f"{key}={value}\n")

    # Write back to .env file
    with open(env_path, "w") as f:
        f.writelines(lines)


@router.get("/settings")
async def get_settings(current_user: User = Depends(get_current_user)):
    """Get current settings"""
    # Mask API credentials for security
    masked_key = ""
    masked_secret = ""
    if settings.coinbase_api_key:
        masked_key = settings.coinbase_api_key[:8] + "..." if len(settings.coinbase_api_key) > 8 else "***"
    if settings.coinbase_api_secret:
        masked_secret = "***************"

    return {
        "coinbase_api_key": masked_key,
        "coinbase_api_secret": masked_secret,
        "initial_btc_percentage": settings.initial_btc_percentage,
        "dca_percentage": settings.dca_percentage,
        "max_btc_usage_percentage": settings.max_btc_usage_percentage,
        "min_profit_percentage": settings.min_profit_percentage,
        "macd_fast_period": settings.macd_fast_period,
        "macd_slow_period": settings.macd_slow_period,
        "macd_signal_period": settings.macd_signal_period,
        "candle_interval": settings.candle_interval,
    }


@router.post("/settings")
async def update_settings(settings_update: SettingsUpdate, coinbase: CoinbaseClient = Depends(get_coinbase), current_user: User = Depends(get_current_user)):
    """Update trading settings"""
    # Update API credentials in .env file if provided
    if settings_update.coinbase_api_key is not None:
        update_env_file("COINBASE_API_KEY", settings_update.coinbase_api_key)
        settings.coinbase_api_key = settings_update.coinbase_api_key
        # Reinitialize coinbase client with new credentials
        coinbase.api_key = settings_update.coinbase_api_key
        if settings_update.coinbase_api_secret is not None:
            coinbase.api_secret = settings_update.coinbase_api_secret

    if settings_update.coinbase_api_secret is not None:
        update_env_file("COINBASE_API_SECRET", settings_update.coinbase_api_secret)
        settings.coinbase_api_secret = settings_update.coinbase_api_secret
        coinbase.api_secret = settings_update.coinbase_api_secret

    # Update settings object
    if settings_update.initial_btc_percentage is not None:
        settings.initial_btc_percentage = settings_update.initial_btc_percentage
    if settings_update.dca_percentage is not None:
        settings.dca_percentage = settings_update.dca_percentage
    if settings_update.max_btc_usage_percentage is not None:
        settings.max_btc_usage_percentage = settings_update.max_btc_usage_percentage
    if settings_update.min_profit_percentage is not None:
        settings.min_profit_percentage = settings_update.min_profit_percentage
    if settings_update.macd_fast_period is not None:
        settings.macd_fast_period = settings_update.macd_fast_period
    if settings_update.macd_slow_period is not None:
        settings.macd_slow_period = settings_update.macd_slow_period
    if settings_update.macd_signal_period is not None:
        settings.macd_signal_period = settings_update.macd_signal_period
    if settings_update.candle_interval is not None:
        settings.candle_interval = settings_update.candle_interval

    return {"message": "Settings updated successfully"}


@router.post("/test-connection")
async def test_connection(request: TestConnectionRequest, current_user: User = Depends(get_current_user)):
    """Test Coinbase API connection with provided credentials"""
    try:
        # Create a temporary client with the provided credentials
        test_client = CoinbaseClient()
        test_client.api_key = request.coinbase_api_key
        test_client.api_secret = request.coinbase_api_secret

        # Try to get account balances to test the connection
        try:
            btc_balance = await test_client.get_btc_balance()
            eth_balance = await test_client.get_eth_balance()

            return {
                "success": True,
                "message": f"Connection successful! BTC Balance: {btc_balance:.8f}, ETH Balance: {eth_balance:.8f}",
                "btc_balance": btc_balance,
                "eth_balance": eth_balance,
            }
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "403" in error_msg or "unauthorized" in error_msg.lower():
                raise HTTPException(
                    status_code=401, detail="Invalid API credentials. Please check your API key and secret."
                )
            elif "permission" in error_msg.lower():
                raise HTTPException(
                    status_code=403,
                    detail="Insufficient permissions. Make sure your API key has 'View' and 'Trade' permissions.",
                )
            else:
                raise HTTPException(status_code=400, detail=f"Connection failed: {error_msg}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/settings/{key}")
async def get_setting_by_key(key: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get a single database setting by key"""
    query = select(Settings).where(Settings.key == key)
    result = await db.execute(query)
    setting = result.scalars().first()

    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")

    return {
        "key": setting.key,
        "value": setting.value,
        "value_type": setting.value_type,
        "description": setting.description,
        "updated_at": setting.updated_at.isoformat() if setting.updated_at else None
    }


@router.put("/settings/{key}")
async def update_setting_by_key(key: str, value: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Update a single database setting by key"""
    query = select(Settings).where(Settings.key == key)
    result = await db.execute(query)
    setting = result.scalars().first()

    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")

    # Update the value
    setting.value = value
    setting.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(setting)

    return {
        "message": f"Setting '{key}' updated successfully",
        "key": setting.key,
        "value": setting.value,
        "updated_at": setting.updated_at.isoformat() if setting.updated_at else None
    }
