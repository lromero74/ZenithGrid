"""
Accounts mutation API routes (POST/PUT/DELETE endpoints)

Write operations for trading accounts:
- Account creation, update, deletion
- Default account selection
- Settings updates (auto-buy, rebalance, dust sweep)
- Perps portfolio linking, dust sweep execution
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.database import get_db
from app.encryption import encrypt_value, mask_api_key
from app.models import Account, Bot, User
from app.auth.dependencies import require_permission, Perm
from app.services.account_service import (
    VALID_PROP_FIRMS,
    create_exchange_account,
    validate_prop_firm_config,
)
from app.services.exchange_service import (
    clear_exchange_client_cache,
    get_coinbase_for_account,
)
from app.position_routers.panic_sell_router import _verify_mfa
from sqlalchemy import func

from app.routers.accounts_query_router import (
    AccountCreate,
    AccountResponse,
    AccountUpdate,
    AutoBuySettings,
    AutoBuySettingsUpdate,
    DustSweepSettingsUpdate,
    RebalanceSettingsResponse,
    RebalanceSettingsUpdate,
    _build_rebalance_response,
    _TTL_REBALANCE_STATUS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# =============================================================================
# POST/PUT/DELETE Endpoints
# =============================================================================


@router.post("", response_model=AccountResponse)
async def create_account(
    account_data: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE))
):
    """
    Create a new account for the current user.

    For CEX accounts, provide exchange, api_key_name, and api_private_key.
    For DEX accounts, provide chain_id, wallet_address, and optionally rpc_url and wallet_private_key.
    """
    # Block non-privileged users from adding live exchange accounts
    if not current_user.is_superuser:
        user_groups = {g.name for g in (current_user.groups or [])}
        privileged = {"System Owners", "Administrators", "Traders"}
        if not user_groups & privileged:
            raise HTTPException(
                status_code=403,
                detail="live_accounts_restricted",
            )

    try:
        account = await create_exchange_account(db, current_user, account_data)

        return AccountResponse(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            is_paper_trading=account.is_paper_trading or False,
            exchange=account.exchange,
            api_key_name=mask_api_key(account.api_key_name),
            chain_id=account.chain_id,
            wallet_address=account.wallet_address,
            rpc_url=account.rpc_url,
            wallet_type=account.wallet_type,
            perps_portfolio_uuid=account.perps_portfolio_uuid,
            default_leverage=account.default_leverage or 1,
            margin_type=account.margin_type or "CROSS",
            prop_firm=account.prop_firm,
            prop_daily_drawdown_pct=account.prop_daily_drawdown_pct,
            prop_total_drawdown_pct=account.prop_total_drawdown_pct,
            prop_initial_deposit=account.prop_initial_deposit,
            created_at=account.created_at,
            updated_at=account.updated_at,
            last_used_at=account.last_used_at,
            display_name=account.get_display_name(),
            short_address=account.get_short_address() if account.type == "dex" else None,
            bot_count=0
        )

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error creating account: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    account_data: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE))
):
    """Update an existing account."""
    try:
        # Get the account
        query = select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Update fields that are provided
        update_data = account_data.model_dump(exclude_unset=True)

        # Validate prop firm fields if being updated
        if 'prop_firm' in update_data and update_data['prop_firm']:
            if update_data['prop_firm'] not in VALID_PROP_FIRMS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported prop firm '{update_data['prop_firm']}'. "
                           f"Valid: {', '.join(sorted(VALID_PROP_FIRMS))}",
                )
        if 'prop_firm_config' in update_data and update_data['prop_firm_config']:
            validate_prop_firm_config(
                update_data['prop_firm_config'],
                update_data.get('exchange') or account.exchange or "",
            )

        # Encrypt sensitive fields before storing
        sensitive_fields = {'api_private_key', 'wallet_private_key'}
        # Fields that affect exchange client construction — invalidate cache on change
        exchange_config_fields = {
            'api_key_name', 'exchange',
            'prop_firm', 'prop_firm_config',
            'prop_daily_drawdown_pct', 'prop_total_drawdown_pct', 'prop_initial_deposit',
        }
        credentials_changed = False
        for field, value in update_data.items():
            if value is not None:
                if field in sensitive_fields:
                    credentials_changed = True
                    value = encrypt_value(value)
                if field == 'api_key_name':
                    credentials_changed = True
                    value = encrypt_value(value)
                if field in exchange_config_fields:
                    credentials_changed = True
                setattr(account, field, value)

        # Clear cached exchange client if credentials changed
        if credentials_changed:
            clear_exchange_client_cache(account_id)

        account.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(account)

        # Get bot count with aggregate query
        bot_count_result = await db.execute(
            select(func.count(Bot.id)).where(Bot.account_id == account.id)
        )
        bot_count = bot_count_result.scalar() or 0

        logger.info(f"Updated account: {account.name} (id={account.id})")

        return AccountResponse(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            is_paper_trading=account.is_paper_trading or False,
            exchange=account.exchange,
            api_key_name=mask_api_key(account.api_key_name),
            chain_id=account.chain_id,
            wallet_address=account.wallet_address,
            rpc_url=account.rpc_url,
            wallet_type=account.wallet_type,
            perps_portfolio_uuid=account.perps_portfolio_uuid,
            default_leverage=account.default_leverage or 1,
            margin_type=account.margin_type or "CROSS",
            prop_firm=account.prop_firm,
            prop_daily_drawdown_pct=account.prop_daily_drawdown_pct,
            prop_total_drawdown_pct=account.prop_total_drawdown_pct,
            prop_initial_deposit=account.prop_initial_deposit,
            created_at=account.created_at,
            updated_at=account.updated_at,
            last_used_at=account.last_used_at,
            display_name=account.get_display_name(),
            short_address=account.get_short_address() if account.type == "dex" else None,
            bot_count=bot_count
        )

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error updating account {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    confirm: bool = Query(False, description="Must be true to execute"),
    mfa_code: Optional[str] = Query(None, description="MFA code (TOTP or email) for verification"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE))
):
    """
    Delete an account. Requires confirm=true and MFA verification.

    This will fail if there are bots linked to this account.
    Unlink or delete bots first.
    """
    try:
        if not confirm:
            raise HTTPException(status_code=400, detail="Must confirm with confirm=true")

        # Verify MFA before irreversible deletion
        await _verify_mfa(db, current_user, mfa_code)

        # Get the account (filtered by user)
        query = select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail="Not found")

        # Check if any bots are linked
        bot_query = select(Bot).where(Bot.account_id == account_id)
        bot_result = await db.execute(bot_query)
        linked_bots = bot_result.scalars().all()

        if linked_bots:
            bot_names = ", ".join([b.name for b in linked_bots])
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete account with linked bots. Unlink these bots first: {bot_names}"
            )

        # Clear cached exchange client before deleting account
        clear_exchange_client_cache(account_id)

        # Delete the account
        await db.delete(account)
        await db.commit()

        logger.info(f"Deleted account: {account.name} (id={account_id})")

        return {"message": f"Account '{account.name}' deleted successfully"}

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error deleting account {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/{account_id}/set-default")
async def set_default_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE))
):
    """Set an account as the default."""
    try:
        # Get the account (filtered by user)
        query = select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail="Not found")

        # Unset all other defaults for this user
        await db.execute(
            update(Account).where(Account.is_default, Account.user_id == current_user.id).values(is_default=False)
        )

        # Set this one as default
        account.is_default = True
        account.updated_at = datetime.utcnow()

        await db.commit()

        logger.info(f"Set default account: {account.name} (id={account_id})")

        return {"message": f"Account '{account.name}' is now the default"}

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error setting default account {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


# =============================================================================
# Auto-Buy BTC Settings (PUT)
# =============================================================================


@router.put("/{account_id}/auto-buy-settings", response_model=AutoBuySettings)
async def update_auto_buy_settings(
    account_id: int,
    settings: AutoBuySettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE))
):
    """Update auto-buy BTC settings for an account"""
    query = select(Account).where(Account.id == account_id)

    query = query.where(Account.user_id == current_user.id)

    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    # Mutual exclusivity: enabling auto-buy disables portfolio rebalancing
    if settings.enabled and account.rebalance_enabled:
        account.rebalance_enabled = False

    # Update fields if provided
    if settings.enabled is not None:
        account.auto_buy_enabled = settings.enabled
    if settings.check_interval_minutes is not None:
        account.auto_buy_check_interval_minutes = settings.check_interval_minutes
    if settings.order_type is not None:
        account.auto_buy_order_type = settings.order_type

    # Update per-stablecoin settings
    if settings.usd_enabled is not None:
        account.auto_buy_usd_enabled = settings.usd_enabled
    if settings.usd_min is not None:
        account.auto_buy_usd_min = settings.usd_min

    if settings.usdc_enabled is not None:
        account.auto_buy_usdc_enabled = settings.usdc_enabled
    if settings.usdc_min is not None:
        account.auto_buy_usdc_min = settings.usdc_min

    if settings.usdt_enabled is not None:
        account.auto_buy_usdt_enabled = settings.usdt_enabled
    if settings.usdt_min is not None:
        account.auto_buy_usdt_min = settings.usdt_min

    await db.commit()
    await db.refresh(account)

    return AutoBuySettings(
        enabled=account.auto_buy_enabled or False,
        check_interval_minutes=account.auto_buy_check_interval_minutes or 5,
        order_type=account.auto_buy_order_type or "market",
        usd_enabled=account.auto_buy_usd_enabled or False,
        usd_min=account.auto_buy_usd_min or 10.0,
        usdc_enabled=account.auto_buy_usdc_enabled or False,
        usdc_min=account.auto_buy_usdc_min or 10.0,
        usdt_enabled=account.auto_buy_usdt_enabled or False,
        usdt_min=account.auto_buy_usdt_min or 10.0,
    )


# =============================================================================
# Perpetual Futures Portfolio (POST)
# =============================================================================


@router.post("/{account_id}/link-perps-portfolio")
async def link_perps_portfolio(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE)),
):
    """
    Discover and link the INTX perpetuals portfolio for a CEX account.

    Queries Coinbase for the user's perpetuals portfolio UUID and saves it
    to the account record.
    """
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if account.type != "cex":
        raise HTTPException(status_code=400, detail="Perps portfolio only available for CEX accounts")

    # Get exchange client
    coinbase_client = await get_coinbase_for_account(account)

    try:
        # Try to get portfolios and find the INTX perpetuals portfolio
        portfolios = await coinbase_client.get_portfolios()

        perps_uuid = None
        for portfolio in portfolios:
            ptype = portfolio.get("type", "")
            if ptype in ("PERPETUALS", "INTX", "DEFAULT"):
                # Try to query perps positions to confirm it's a perps portfolio
                uuid = portfolio.get("uuid", "")
                if uuid:
                    try:
                        await coinbase_client.get_perps_portfolio_summary(uuid)
                        perps_uuid = uuid
                        break
                    except Exception:
                        continue

        if not perps_uuid:
            raise HTTPException(
                status_code=404,
                detail="No INTX perpetuals portfolio found. Please enable perpetual futures on Coinbase first."
            )

        # Save to account
        account.perps_portfolio_uuid = perps_uuid
        await db.commit()

        return {
            "success": True,
            "portfolio_uuid": perps_uuid,
            "message": "Perpetuals portfolio linked successfully",
        }

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Failed to discover perps portfolio: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


# =============================================================================
# Portfolio Rebalancing (PUT)
# =============================================================================


@router.put("/{account_id}/rebalance-settings", response_model=RebalanceSettingsResponse)
async def update_rebalance_settings(
    account_id: int,
    settings: RebalanceSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE)),
):
    """Update portfolio rebalance settings for an account."""
    query = select(Account).where(
        Account.id == account_id, Account.user_id == current_user.id
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    # Only validate percentages if any are being changed or rebalancing is being enabled
    any_pct_changing = any(v is not None for v in [
        settings.target_usd_pct, settings.target_btc_pct, settings.target_eth_pct,
        settings.target_usdc_pct, settings.target_usdt_pct,
    ])
    if any_pct_changing or settings.enabled:
        usd = settings.target_usd_pct if settings.target_usd_pct is not None \
            else account.rebalance_target_usd_pct or 34.0
        btc = settings.target_btc_pct if settings.target_btc_pct is not None \
            else account.rebalance_target_btc_pct or 33.0
        eth = settings.target_eth_pct if settings.target_eth_pct is not None \
            else account.rebalance_target_eth_pct or 33.0
        usdc = (settings.target_usdc_pct if settings.target_usdc_pct is not None
                else account.rebalance_target_usdc_pct or 0.0)
        usdt = (settings.target_usdt_pct if settings.target_usdt_pct is not None
                else account.rebalance_target_usdt_pct or 0.0)

        pct_total = usd + btc + eth + usdc + usdt
        if abs(pct_total - 100.0) > 0.1:
            raise HTTPException(
                status_code=400,
                detail=f"Target percentages must sum to 100% (got {pct_total:.1f}%)"
            )

    # Mutual exclusivity: enabling rebalancing disables auto-buy
    if settings.enabled and account.auto_buy_enabled:
        account.auto_buy_enabled = False

    # Update fields
    if settings.enabled is not None:
        account.rebalance_enabled = settings.enabled
    if settings.target_usd_pct is not None:
        account.rebalance_target_usd_pct = settings.target_usd_pct
    if settings.target_btc_pct is not None:
        account.rebalance_target_btc_pct = settings.target_btc_pct
    if settings.target_eth_pct is not None:
        account.rebalance_target_eth_pct = settings.target_eth_pct
    if settings.target_usdc_pct is not None:
        account.rebalance_target_usdc_pct = settings.target_usdc_pct
    if settings.target_usdt_pct is not None:
        account.rebalance_target_usdt_pct = settings.target_usdt_pct
    if settings.drift_threshold_pct is not None:
        account.rebalance_drift_threshold_pct = settings.drift_threshold_pct
    if settings.check_interval_minutes is not None:
        account.rebalance_check_interval_minutes = settings.check_interval_minutes
    if settings.min_trade_pct is not None:
        account.rebalance_min_trade_pct = settings.min_trade_pct
    if settings.min_balance_usd is not None:
        account.min_balance_usd = settings.min_balance_usd
    if settings.min_balance_btc is not None:
        account.min_balance_btc = settings.min_balance_btc
    if settings.min_balance_eth is not None:
        account.min_balance_eth = settings.min_balance_eth
    if settings.min_balance_usdc is not None:
        account.min_balance_usdc = settings.min_balance_usdc
    if settings.min_balance_usdt is not None:
        account.min_balance_usdt = settings.min_balance_usdt

    await db.commit()
    await db.refresh(account)

    # Clear cached status so the next fetch reflects the new reserve settings
    _TTL_REBALANCE_STATUS.pop(account_id, None)

    return _build_rebalance_response(account)


# =============================================================================
# Dust Sweep (PUT/POST)
# =============================================================================


@router.put("/{account_id}/dust-sweep-settings")
async def update_dust_sweep_settings(
    account_id: int,
    settings: DustSweepSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE)),
):
    """Update dust sweep settings for an account."""
    query = select(Account).where(
        Account.id == account_id, Account.user_id == current_user.id
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    if settings.enabled is not None:
        account.dust_sweep_enabled = settings.enabled
    if settings.threshold_usd is not None:
        account.dust_sweep_threshold_usd = settings.threshold_usd

    await db.commit()
    await db.refresh(account)

    return {
        "enabled": account.dust_sweep_enabled or False,
        "threshold_usd": account.dust_sweep_threshold_usd or 5.0,
        "last_sweep_at": (
            account.dust_last_sweep_at.isoformat()
            if account.dust_last_sweep_at else None
        ),
    }


@router.post("/{account_id}/dust-sweep")
async def sweep_dust(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE)),
):
    """Execute an on-demand dust sweep for an account."""
    query = select(Account).where(
        Account.id == account_id, Account.user_id == current_user.id
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    if account.type != "cex":
        raise HTTPException(status_code=400, detail="Dust sweep only available for CEX accounts")

    try:
        if account.is_paper_trading:
            client = await get_coinbase_for_account(account)
        else:
            client = await get_coinbase_for_account(account)

        from app.services.rebalance_monitor import execute_dust_sweep
        results = await execute_dust_sweep(account, client, db)

        successes = [r for r in results if r.get("status") == "success"]
        failures = [r for r in results if r.get("status") == "failed"]

        return {
            "swept": len(successes),
            "failed": len(failures),
            "details": [
                {
                    "coin": r["coin"],
                    "amount": r["amount"],
                    "usd_value": r["usd_value"],
                    "target_currency": r["target_currency"],
                    "order_id": r.get("order_id", ""),
                }
                for r in successes
            ],
            "errors": [
                {
                    "coin": r["coin"],
                    "amount": r["amount"],
                    "usd_value": r["usd_value"],
                    "error": r.get("error", "Unknown error"),
                }
                for r in failures
            ],
        }

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error executing dust sweep for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")
