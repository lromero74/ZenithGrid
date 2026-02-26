"""
Account Service

Business logic for account management:
- Prop firm config validation
- Exchange account creation with credential encryption and connectivity testing
- Per-account portfolio retrieval (paper trading, CEX, DEX)
"""

import json
import logging
import re
from urllib.parse import urlparse

from app.exceptions import ExchangeUnavailableError, NotFoundError, ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption import encrypt_value
from app.models import Account, User
from app.services.exchange_service import get_coinbase_for_account, get_exchange_client_for_account
from app.services.portfolio_service import get_cex_portfolio, get_dex_portfolio, get_generic_cex_portfolio

logger = logging.getLogger(__name__)

VALID_EXCHANGES = {"coinbase", "bybit", "mt5_bridge"}
VALID_PROP_FIRMS = {"hyrotrader", "ftmo"}


def validate_prop_firm_config(config: dict, exchange: str) -> None:
    """Validate prop_firm_config schema and prevent SSRF via bridge_url."""
    if not isinstance(config, dict):
        raise ValidationError("prop_firm_config must be a JSON object")

    # MT5 bridge requires a bridge_url
    if exchange == "mt5_bridge":
        bridge_url = config.get("bridge_url", "")
        if bridge_url:
            parsed = urlparse(bridge_url)
            # Only allow http/https schemes
            if parsed.scheme not in ("http", "https"):
                raise ValidationError("bridge_url must use http:// or https:// scheme")
            # Block obvious internal/private IPs
            host = parsed.hostname or ""
            if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or \
               host.startswith("10.") or host.startswith("192.168.") or \
               re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host):
                raise ValidationError("bridge_url must not point to a private/internal address")

    # Validate testnet flag if present
    if "testnet" in config and not isinstance(config["testnet"], bool):
        raise ValidationError("prop_firm_config.testnet must be a boolean")

    # Only allow known keys to prevent arbitrary data injection
    allowed_keys = {"bridge_url", "testnet", "api_key", "api_secret", "broker", "server"}
    unknown = set(config.keys()) - allowed_keys
    if unknown:
        raise ValidationError(f"Unknown keys in prop_firm_config: {', '.join(sorted(unknown))}")


async def create_exchange_account(
    db: AsyncSession,
    current_user: User,
    account_data,
) -> Account:
    """
    Create a new exchange account with validation, encryption, and connectivity testing.

    Validates fields, encrypts credentials, persists the account, and tests the connection.
    On connection failure, the account is deleted and a ValidationError is raised.

    Returns the created Account ORM object.
    """
    # Validate account type
    if account_data.type not in ["cex", "dex"]:
        raise ValidationError("Account type must be 'cex' or 'dex'")

    # Validate required fields based on type
    if account_data.type == "cex":
        if not account_data.exchange:
            raise ValidationError("CEX accounts require 'exchange' field")
        if account_data.exchange not in VALID_EXCHANGES:
            raise ValidationError(
                f"Unsupported exchange '{account_data.exchange}'. "
                f"Valid: {', '.join(sorted(VALID_EXCHANGES))}",
            )
    else:  # dex
        if not account_data.chain_id:
            raise ValidationError("DEX accounts require 'chain_id' field")
        if not account_data.wallet_address:
            raise ValidationError("DEX accounts require 'wallet_address' field")

    # Validate prop firm fields
    if account_data.prop_firm:
        if account_data.prop_firm not in VALID_PROP_FIRMS:
            raise ValidationError(
                f"Unsupported prop firm '{account_data.prop_firm}'. "
                f"Valid: {', '.join(sorted(VALID_PROP_FIRMS))}",
            )
    if account_data.prop_firm_config:
        validate_prop_firm_config(
            account_data.prop_firm_config,
            account_data.exchange or "",
        )

    # If this is set as default, unset other defaults for this user
    if account_data.is_default:
        default_filter = Account.is_default & (Account.user_id == current_user.id)
        await db.execute(
            update(Account).where(default_filter).values(is_default=False)
        )

    # Create the account
    account = Account(
        name=account_data.name,
        type=account_data.type,
        is_default=account_data.is_default,
        user_id=current_user.id,
        is_active=True,
        exchange=account_data.exchange,
        api_key_name=(
            encrypt_value(account_data.api_key_name)
            if account_data.api_key_name
            else None
        ),
        api_private_key=encrypt_value(account_data.api_private_key) if account_data.api_private_key else None,
        chain_id=account_data.chain_id,
        wallet_address=account_data.wallet_address,
        wallet_private_key=(
            encrypt_value(account_data.wallet_private_key)
            if account_data.wallet_private_key else None
        ),
        rpc_url=account_data.rpc_url,
        wallet_type=account_data.wallet_type,
        # Prop firm fields
        prop_firm=account_data.prop_firm,
        prop_firm_config=account_data.prop_firm_config,
        prop_daily_drawdown_pct=account_data.prop_daily_drawdown_pct,
        prop_total_drawdown_pct=account_data.prop_total_drawdown_pct,
        prop_initial_deposit=account_data.prop_initial_deposit,
    )

    db.add(account)
    await db.commit()
    await db.refresh(account)

    # Verify credentials by testing connection
    if account.api_key_name or account.wallet_private_key or account.prop_firm_config:
        try:
            client = await get_exchange_client_for_account(db, account.id, use_cache=False)
            if client:
                connected = await client.test_connection()
                if not connected:
                    # Credentials don't work — delete the account
                    await db.delete(account)
                    await db.commit()
                    raise ValidationError(
                        "Connection test failed. Please verify your API credentials."
                    )
        except (ValidationError, ExchangeUnavailableError):
            raise
        except Exception as e:
            logger.warning(f"Connection test error for account {account.id}: {e}")
            await db.delete(account)
            await db.commit()
            raise ValidationError(f"Connection test failed: {str(e)}")

    logger.info(f"Created account: {account.name} (type={account.type}, id={account.id})")
    return account


async def get_portfolio_for_account(
    db: AsyncSession,
    current_user: User,
    account_id: int,
    force_fresh: bool = False,
) -> dict:
    """
    Get portfolio for a specific account.

    For CEX accounts: Fetches from exchange API
    For DEX accounts: Fetches from blockchain via RPC
    For Paper Trading accounts: Returns virtual balances with real-time pricing
    """
    # Get the account (filtered by user)
    query = select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise NotFoundError("Not found")

    # Handle paper trading accounts
    if account.is_paper_trading:
        return await _build_paper_portfolio(account)

    if account.type == "cex":
        exchange_name = account.exchange or "coinbase"
        if exchange_name in ("bybit", "mt5_bridge"):
            return await get_generic_cex_portfolio(account, db)
        else:
            return await get_cex_portfolio(account, db, get_coinbase_for_account, force_fresh=force_fresh)
    else:
        return await get_dex_portfolio(account, db, get_coinbase_for_account)


async def _build_paper_portfolio(account: Account) -> dict:
    """Build portfolio response for a paper trading account with real-time pricing."""
    if account.paper_balances:
        balances = json.loads(account.paper_balances)
    else:
        balances = {"BTC": 0.0, "ETH": 0.0, "USD": 0.0, "USDC": 0.0, "USDT": 0.0}

    from app.coinbase_api.public_market_data import (
        get_btc_usd_price as get_public_btc_price,
        get_current_price as get_public_price,
    )

    btc_usd_price = await get_public_btc_price()

    # Fetch BTC prices for all non-stablecoin currencies
    altcoin_btc_prices = {}
    for currency in balances:
        if currency in ("BTC", "USD", "USDC", "USDT"):
            continue
        try:
            altcoin_btc_prices[currency] = await get_public_price(f"{currency}-BTC")
        except Exception:
            altcoin_btc_prices[currency] = 0.0

    # Build holdings array (compatible with frontend Portfolio page)
    holdings = []
    total_btc = 0.0
    total_usd = 0.0
    for currency, amount in balances.items():
        if amount > 0:
            if currency == "BTC":
                btc_value = amount
                usd_value = amount * btc_usd_price
                current_price_usd = btc_usd_price
            elif currency in ("USD", "USDC", "USDT"):
                usd_value = amount
                btc_value = amount / btc_usd_price if btc_usd_price > 0 else 0
                current_price_usd = 1.0
            else:
                btc_price = altcoin_btc_prices.get(currency, 0.0)
                btc_value = amount * btc_price
                usd_value = btc_value * btc_usd_price
                current_price_usd = btc_price * btc_usd_price

            total_btc += btc_value
            total_usd += usd_value

            holdings.append({
                "asset": currency,
                "total_balance": amount,
                "available": amount,
                "hold": 0.0,
                "current_price_usd": current_price_usd,
                "usd_value": usd_value,
                "btc_value": btc_value,
                "percentage": 0.0,
            })

    # Calculate allocation percentages now that we have totals
    for holding in holdings:
        if total_usd > 0:
            holding["percentage"] = (holding["usd_value"] / total_usd) * 100

    return {
        "holdings": holdings,
        "holdings_count": len(holdings),
        "total_btc_value": total_btc,
        "total_usd_value": total_usd,
        "btc_usd_price": btc_usd_price,
        "is_paper_trading": True,
    }
