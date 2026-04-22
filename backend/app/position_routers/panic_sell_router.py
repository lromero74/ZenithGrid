"""
Panic Sell Router — Account-wide emergency liquidation.

POST /panic-sell
    Initiate panic sell (returns task_id immediately).
GET  /panic-sell-status/{task_id}
    Poll progress.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import Perm, get_current_user, require_permission
from app.auth.mfa_verification import verify_mfa
from app.database import get_db
from app.models.auth import User
from app.models.trading import Account, Bot, BotRebalancerGroup, Position
from app.services.account_access import manager_account_ids
from app.services.exchange_service import get_exchange_client_for_account
from app.services.portfolio_conversion_service import (
    SUPPORTED_TARGET_CURRENCIES,
    run_portfolio_conversion,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── In-memory progress tracking (mirrors portfolio_conversion_service pattern) ─
_panic_tasks: Dict[str, Dict] = {}


class PanicSellRequest(BaseModel):
    account_id: int
    action: Literal["cancel", "sell"]
    target_currency: Optional[Literal["USD", "USDC", "USDT", "BTC", "ETH"]] = None
    stop_bots: bool = True
    stop_portfolio_rebalancer: bool = True
    stop_bot_rebalancer: bool = True
    stop_auto_buy: bool = True
    zero_min_balances: bool = True
    mfa_code: Optional[str] = None
    confirm: bool = False


def _init_task(task_id: str, user_id: int = None) -> None:
    _panic_tasks[task_id] = {
        "task_id": task_id,
        "user_id": user_id,
        "status": "running",
        "phase": "starting",
        "message": "Initializing...",
        "bots_stopped": 0,
        "positions_total": 0,
        "positions_current": 0,
        "positions_acted": 0,
        "positions_failed": 0,
        "portfolio_rebalancer_stopped": False,
        "bot_rebalancer_groups_stopped": 0,
        "auto_buy_stopped": False,
        "min_balances_zeroed": False,
        "conversion_task_id": None,
        "conversion_status_url": None,
        "errors": [],
        "progress_pct": 0,
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": None,
    }


def _update_task(task_id: str, **kwargs) -> None:
    if task_id not in _panic_tasks:
        return
    task = _panic_tasks[task_id]
    task.update(kwargs)
    total = task.get("positions_total", 0)
    current = task.get("positions_current", 0)
    if total > 0:
        task["progress_pct"] = int((current / total) * 100)
    if kwargs.get("status") in ("completed", "failed"):
        task["completed_at"] = datetime.utcnow().isoformat()


@router.post("/panic-sell-send-mfa")
async def panic_sell_send_mfa(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a one-time MFA email code for panic sell confirmation.

    Returns the user's MFA method so the frontend can display the right prompt.
    If the user has TOTP, no email is sent — they use their authenticator app.
    """
    if current_user.mfa_enabled and current_user.totp_secret:
        return {"method": "totp"}

    if current_user.mfa_email_enabled:
        import random
        from app.models.auth import EmailVerificationToken
        # Invalidate old unused action_mfa tokens for this user
        old_result = await db.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.user_id == current_user.id,
                EmailVerificationToken.token_type == "action_mfa",
                EmailVerificationToken.used_at.is_(None),
            )
        )
        for old_token in old_result.scalars().all():
            old_token.used_at = datetime.utcnow()

        verify_code = f"{random.randint(0, 999999):06d}"
        from datetime import timedelta
        mfa_email_token = EmailVerificationToken(
            user_id=current_user.id,
            token=str(uuid.uuid4()).replace("-", ""),
            verification_code=verify_code,
            token_type="action_mfa",
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )
        db.add(mfa_email_token)
        await db.commit()

        try:
            from app.services.email_service import send_mfa_verification_email
            send_mfa_verification_email(
                to=current_user.email,
                code=verify_code,
                link_url="",
                display_name=current_user.display_name or "",
            )
        except Exception as e:
            logger.error(f"Failed to send panic sell MFA email: {e}")

        email = current_user.email or ""
        at_idx = email.find("@")
        masked = email[:2] + "***" + email[at_idx:] if at_idx > 2 else email
        return {"method": "email", "masked_email": masked}

    # No MFA configured
    return {"method": "none"}


@router.post("/panic-sell")
async def panic_sell(
    request: PanicSellRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.POSITIONS_WRITE, Perm.BOTS_WRITE)),
):
    """Initiate account-wide panic sell. Returns task_id immediately."""
    if not request.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true")

    if request.target_currency and request.target_currency not in SUPPORTED_TARGET_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"target_currency must be one of: {', '.join(sorted(SUPPORTED_TARGET_CURRENCIES))}",
        )

    # Verify MFA before taking any action
    await verify_mfa(db, current_user, request.mfa_code)

    account_ids = await manager_account_ids(db, current_user.id)
    if request.account_id not in account_ids:
        raise HTTPException(status_code=403, detail="Not authorized for this account")

    task_id = str(uuid.uuid4())
    _init_task(task_id, user_id=current_user.id)

    background_tasks.add_task(
        _run_panic_sell,
        task_id=task_id,
        account_id=request.account_id,
        action=request.action,
        target_currency=request.target_currency,
        stop_bots=request.stop_bots,
        stop_portfolio_rebalancer=request.stop_portfolio_rebalancer,
        stop_bot_rebalancer=request.stop_bot_rebalancer,
        stop_auto_buy=request.stop_auto_buy,
        zero_min_balances=request.zero_min_balances,
        user_id=current_user.id,
    )

    return {
        "task_id": task_id,
        "message": "Panic sell initiated",
        "status_url": f"/api/positions/panic-sell-status/{task_id}",
    }


@router.get("/panic-sell-status/{task_id}")
async def get_panic_sell_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """Poll panic sell progress."""
    progress = _panic_tasks.get(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Task not found")
    if progress.get("user_id") and progress["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this task")
    return progress


async def _run_panic_sell(
    task_id: str,
    account_id: int,
    action: str,
    target_currency: Optional[str],
    stop_bots: bool,
    stop_portfolio_rebalancer: bool,
    stop_bot_rebalancer: bool,
    stop_auto_buy: bool,
    zero_min_balances: bool,
    user_id: int,
) -> None:
    """Background worker: opens a fresh DB session and runs all phases."""
    try:
        async for db in get_db():
            await _execute_panic_sell(
                db, task_id, account_id, action, target_currency,
                stop_bots, stop_portfolio_rebalancer, stop_bot_rebalancer,
                stop_auto_buy, zero_min_balances, user_id,
            )
            break
    except Exception as e:
        logger.error(f"Panic sell task {task_id} failed: {e}")
        _update_task(task_id, status="failed", message=f"Panic sell failed: {str(e)}")


async def _execute_panic_sell(
    db,
    task_id: str,
    account_id: int,
    action: str,
    target_currency: Optional[str],
    stop_bots: bool,
    stop_portfolio_rebalancer: bool,
    stop_bot_rebalancer: bool,
    stop_auto_buy: bool,
    zero_min_balances: bool,
    user_id: int,
) -> None:
    """Execute all phases of the panic sell on the provided DB session."""
    errors: List[str] = []

    # ── Phase 1: Stop all active bots ──────────────────────────────────────
    bots_stopped = 0
    if stop_bots:
        _update_task(task_id, phase="stopping_bots", message="Stopping all active bots...")
        bots_result = await db.execute(
            select(Bot).where(Bot.account_id == account_id, Bot.is_active.is_(True))
        )
        active_bots = bots_result.scalars().all()
        now = datetime.utcnow()
        for bot in active_bots:
            try:
                if bot.last_started_at:
                    elapsed = (now - bot.last_started_at).total_seconds()
                    bot.total_running_seconds = (bot.total_running_seconds or 0.0) + elapsed
                bot.is_active = False
                bot.last_started_at = None
                bot.updated_at = now
                bots_stopped += 1
            except Exception as e:
                errors.append(f"Failed to stop bot {bot.id}: {str(e)}")
        await db.commit()
        _update_task(task_id, bots_stopped=bots_stopped)

    # ── Phase 2: Disable rebalancers, auto-buy, zero reserves ─────────────
    # Must happen BEFORE position closing so rebalancers can't buy into other
    # bases while sells are executing.
    portfolio_rebalancer_stopped = False
    bot_rebalancer_groups_stopped = 0
    auto_buy_stopped = False
    min_balances_zeroed = False

    _update_task(task_id, phase="stopping_rebalancers", message="Disabling rebalancers and auto-buy...")

    account_needs_update = stop_portfolio_rebalancer or stop_auto_buy or zero_min_balances
    if account_needs_update:
        account_result = await db.execute(select(Account).where(Account.id == account_id))
        account = account_result.scalars().first()
        if account:
            if stop_portfolio_rebalancer and account.rebalance_enabled:
                account.rebalance_enabled = False
                portfolio_rebalancer_stopped = True

            if stop_auto_buy:
                account.auto_buy_enabled = False
                account.auto_buy_usd_enabled = False
                account.auto_buy_usdc_enabled = False
                account.auto_buy_usdt_enabled = False
                auto_buy_stopped = True

            if zero_min_balances:
                account.min_balance_usd = 0.0
                account.min_balance_btc = 0.0
                account.min_balance_eth = 0.0
                account.min_balance_usdc = 0.0
                account.min_balance_usdt = 0.0
                min_balances_zeroed = True

        try:
            await db.commit()
        except Exception as e:
            errors.append(f"Failed to update account settings: {str(e)}")

    if stop_bot_rebalancer:
        try:
            groups_result = await db.execute(
                select(BotRebalancerGroup).where(
                    BotRebalancerGroup.account_id == account_id,
                    BotRebalancerGroup.enabled.is_(True),
                )
            )
            groups = groups_result.scalars().all()
            for group in groups:
                group.enabled = False
                bot_rebalancer_groups_stopped += 1
            await db.commit()
        except Exception as e:
            errors.append(f"Failed to stop bot rebalancer groups: {str(e)}")

    _update_task(
        task_id,
        portfolio_rebalancer_stopped=portfolio_rebalancer_stopped,
        bot_rebalancer_groups_stopped=bot_rebalancer_groups_stopped,
        auto_buy_stopped=auto_buy_stopped,
        min_balances_zeroed=min_balances_zeroed,
    )

    # ── Phase 3: Cancel or sell all open positions ──────────────────────────
    _update_task(task_id, phase="closing_positions", message="Loading open positions...")
    positions_result = await db.execute(
        select(Position).where(
            Position.account_id == account_id,
            Position.status == "open",
        )
    )
    positions = positions_result.scalars().all()
    total = len(positions)
    _update_task(task_id, positions_total=total, message=f"Closing {total} positions...")

    positions_acted = 0
    positions_failed = 0

    if action == "cancel":
        now = datetime.utcnow()
        for idx, position in enumerate(positions, 1):
            try:
                position.status = "cancelled"
                position.closed_at = now
                positions_acted += 1
            except Exception as e:
                positions_failed += 1
                errors.append(f"Cancel #{position.id}: {str(e)}")
            _update_task(
                task_id,
                positions_current=idx,
                positions_acted=positions_acted,
                positions_failed=positions_failed,
                message=f"Cancelling {idx}/{total}...",
            )
        await db.commit()

    elif action == "sell":
        from app.strategies import StrategyRegistry
        from app.trading_engine_v2 import StrategyTradingEngine

        exchange = await get_exchange_client_for_account(db, account_id)
        if not exchange:
            _update_task(task_id, status="failed", message="No exchange client for account")
            return

        bots_result = await db.execute(select(Bot).where(Bot.account_id == account_id))
        bots_map = {b.id: b for b in bots_result.scalars().all()}

        unique_products = list({p.product_id for p in positions if p.product_id})

        async def _get_price(product_id):
            try:
                return (product_id, await exchange.get_current_price(product_id))
            except Exception:
                return (product_id, None)

        price_results = await asyncio.gather(*[_get_price(pid) for pid in unique_products])
        price_map = {pid: price for pid, price in price_results if price is not None}

        for idx, position in enumerate(positions, 1):
            try:
                bot = bots_map.get(position.bot_id)
                if not bot:
                    raise ValueError(f"Bot {position.bot_id} not found")
                current_price = price_map.get(position.product_id)
                if current_price is None:
                    raise ValueError(f"No price for {position.product_id}")

                strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)
                # Reset any pending limit close — panic sell always uses market orders
                # so we don't want the sell_executor's early-return guard to block it.
                if position.closing_via_limit:
                    position.closing_via_limit = False
                    position.limit_close_order_id = None
                # Set exit_reason BEFORE execute_sell so panic-sold positions are
                # excluded from win rate denominator (bot_stats_service.py line 147)
                position.exit_reason = "manual"
                engine = StrategyTradingEngine(
                    db=db, exchange=exchange, bot=bot,
                    strategy=strategy, product_id=position.product_id,
                )
                await engine.execute_sell(
                    position=position, current_price=current_price, signal_data=None,
                    force_market=True,  # bypass _validate_market_fallback profit check
                )
                positions_acted += 1
            except Exception as e:
                positions_failed += 1
                errors.append(f"Sell #{position.id} ({position.product_id}): {str(e)}")

            _update_task(
                task_id,
                positions_current=idx,
                positions_acted=positions_acted,
                positions_failed=positions_failed,
                message=f"Selling {idx}/{total}...",
            )

    # ── Phase 4: Trigger portfolio conversion (optional, sell only) ─────────
    conversion_task_id = None
    if action == "sell" and target_currency:
        _update_task(
            task_id, phase="converting",
            message=f"Starting portfolio conversion to {target_currency}..."
        )
        conversion_task_id = str(uuid.uuid4())
        asyncio.ensure_future(
            run_portfolio_conversion(
                task_id=conversion_task_id,
                account_id=account_id,
                target_currency=target_currency,
                user_id=user_id,
            )
        )
        _update_task(
            task_id,
            conversion_task_id=conversion_task_id,
            conversion_status_url=f"/api/account/conversion-status/{conversion_task_id}",
        )

    # ── Complete ────────────────────────────────────────────────────────────
    verb = "cancelled" if action == "cancel" else "sold"
    logger.warning(
        f"🚨 PANIC SELL task {task_id}: action={action}, "
        f"bots_stopped={bots_stopped}, positions={positions_acted}/{total}, "
        f"rebalancer={'stopped' if portfolio_rebalancer_stopped else 'kept'}, "
        f"auto_buy={'stopped' if auto_buy_stopped else 'kept'}, "
        f"min_balances={'zeroed' if min_balances_zeroed else 'kept'}"
    )

    _update_task(
        task_id,
        status="completed",
        phase="completed",
        message=(
            f"Complete: {bots_stopped} bots stopped, "
            f"{positions_acted} positions {verb}"
            + (f", converting to {target_currency}" if conversion_task_id else "")
        ),
        errors=errors,
        positions_current=total,
    )
