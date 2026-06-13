"""
Account and portfolio API routes

Handles account-related endpoints:
- Account balances (BTC, ETH, totals)
- Aggregate portfolio value calculations
- Full portfolio breakdown
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.exceptions import AppError, NotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account, User
from app.auth.dependencies import get_current_user
from app.auth.mfa_verification import verify_mfa
from app.services import portfolio_conversion_service as pcs
from app.services.account_access import accessible_accounts_filter
from app.services.exchange_service import get_exchange_client_for_account
from app.services.portfolio_service import (
    get_account_balances,
    get_account_portfolio_data,
    get_coinbase_from_db,
    get_user_paper_account,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["account"])


@router.get("/balances")
async def get_balances(
    account_id: Optional[int] = Query(None, description="Account ID (defaults to first active CEX account)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current account balances with capital reservation tracking."""
    try:
        return await get_account_balances(db, current_user, account_id)
    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error getting balances: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


def _empty_aggregate_response() -> dict:
    """Zeroed aggregate-value payload (client unavailable)."""
    return {
        "aggregate_btc_value": 0.0,
        "aggregate_usd_value": 0.0,
        "aggregate_eth_value": 0.0,
        "market_values": {},
        "market_btc_value": 0.0,
        "market_usd_value": 0.0,
        "market_usdc_value": 0.0,
        "market_eth_value": 0.0,
        "btc_usd_price": 0.0,
        "eth_usd_price": 0.0,
    }


async def _build_aggregate_response(client) -> dict:
    """Compute aggregate portfolio values + per-quote market budgets for one
    already-resolved (account-scoped) exchange client."""
    async def _safe_call(coro, fallback=0.0):
        try:
            return await coro
        except Exception as e:
            logger.warning(f"Aggregate value sub-call failed: {e}")
            return fallback

    quotes = {"USD", "BTC", "ETH", "USDC", "USDT", "EUR"}
    try:
        products = await client.list_products()
        for product in products or []:
            product_id = product.get("product_id", "")
            quote = (
                product.get("quote_currency_id")
                or product.get("quote_currency")
                or (product_id.rsplit("-", 1)[1] if "-" in product_id else "")
            )
            if quote:
                quotes.add(str(quote).upper())
    except Exception as e:
        logger.warning(f"Could not discover quote buckets from products: {e}")

    market_values = {
        quote: await _safe_call(client.calculate_market_budget(quote))
        for quote in sorted(quotes)
    }

    aggregate_btc = await _safe_call(client.calculate_aggregate_btc_value())
    aggregate_usd = await _safe_call(client.calculate_aggregate_usd_value())
    btc_usd_price = await _safe_call(client.get_btc_usd_price())
    eth_usd_price = await _safe_call(client.get_eth_usd_price())

    return {
        "aggregate_btc_value": aggregate_btc,
        "aggregate_usd_value": aggregate_usd,
        "aggregate_eth_value": market_values.get("ETH", 0.0),
        "market_values": market_values,
        "market_btc_value": market_values.get("BTC", 0.0),
        "market_usd_value": market_values.get("USD", 0.0),
        "market_usdc_value": market_values.get("USDC", 0.0),
        "market_eth_value": market_values.get("ETH", 0.0),
        "btc_usd_price": btc_usd_price,
        "eth_usd_price": eth_usd_price,
    }


@router.get("/aggregate-value")
async def get_aggregate_value(
    account_id: Optional[int] = Query(
        None, description="Account to value (defaults to the user's paper or first CEX account)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get portfolio aggregate values and quote-market budget buckets.

    When ``account_id`` is supplied, values are scoped to THAT account (after
    verifying the caller owns it). This prevents a multi-account user — or a bot
    on a non-default/paper account — from seeing the wrong account's budget.
    Without it, the legacy default applies: paper-only users get their paper
    account, everyone else gets their first active CEX account.
    """
    try:
        # Explicit account: authorize ownership, then scope strictly to it.
        if account_id is not None:
            result = await db.execute(
                select(Account).where(
                    Account.id == account_id,
                    accessible_accounts_filter(current_user.id),
                )
            )
            if result.scalar_one_or_none() is None:
                raise NotFoundError("Account not found")
            client = await get_exchange_client_for_account(db, account_id)
            if not client:
                return _empty_aggregate_response()
            return await _build_aggregate_response(client)

        # Legacy default: paper-only user → paper account.
        paper_account = await get_user_paper_account(db, current_user.id)
        if paper_account:
            client = await get_exchange_client_for_account(db, paper_account.id)
            if not client:
                return _empty_aggregate_response()
            return await _build_aggregate_response(client)

        # Otherwise the user's first active CEX account.
        coinbase = await get_coinbase_from_db(db, current_user.id)
        return await _build_aggregate_response(coinbase)
    except (HTTPException, AppError):
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/portfolio")
async def get_portfolio(
    force_fresh: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full portfolio breakdown (all coins)."""
    try:
        return await get_account_portfolio_data(db, current_user, force_fresh)
    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.exception(f"Portfolio endpoint error: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/conversion-status/{task_id}")
async def get_conversion_status(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Get status of a portfolio conversion task (requires auth + ownership)
    """
    progress = pcs.get_task_progress(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Conversion task not found")
    if progress.get("user_id") and progress["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this task")
    return progress


@router.post("/sell-portfolio-to-base")
async def sell_portfolio_to_base_currency(
    background_tasks: BackgroundTasks,
    target_currency: str = Query("BTC", description="Target currency: BTC or USD"),
    confirm: bool = Query(False, description="Must be true to execute"),
    account_id: Optional[int] = Query(None, description="Account ID to convert (defaults to default account)"),
    mfa_code: Optional[str] = Query(None, description="MFA code (TOTP or email) for verification"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start portfolio conversion to BTC or USD (runs in background).

    Returns immediately with a task_id to check progress via /conversion-status/{task_id}
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="Must confirm with confirm=true")

    await verify_mfa(db, current_user, mfa_code)

    from app.services.portfolio_conversion_service import SUPPORTED_TARGET_CURRENCIES
    if target_currency not in SUPPORTED_TARGET_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"target_currency must be one of: {', '.join(sorted(SUPPORTED_TARGET_CURRENCIES))}",
        )

    # Get the specified account or user's default account
    if account_id:
        account_query = select(Account).where(
            Account.id == account_id,
            Account.user_id == current_user.id
        )
    else:
        account_query = select(Account).where(
            Account.user_id == current_user.id,
            Account.is_default.is_(True)
        )
    account_result = await db.execute(account_query)
    account = account_result.scalars().first()

    if not account:
        if account_id:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
        else:
            raise HTTPException(status_code=404, detail="No default account found")

    # Generate task ID and init with owner tracking
    task_id = str(uuid.uuid4())
    pcs.init_task(task_id, user_id=current_user.id)

    # Start the conversion in the background
    background_tasks.add_task(
        pcs.run_portfolio_conversion,
        task_id=task_id,
        account_id=account.id,
        target_currency=target_currency,
        user_id=current_user.id
    )

    return {
        "task_id": task_id,
        "message": f"Portfolio conversion to {target_currency} started",
        "status_url": f"/api/account/conversion-status/{task_id}"
    }
