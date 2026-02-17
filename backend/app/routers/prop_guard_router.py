"""
PropGuard API Router

Endpoints for monitoring and controlling PropGuard safety system:
- GET  /api/propguard/{account_id}/status  - Current PropGuard state
- POST /api/propguard/{account_id}/reset   - Reset kill switch
- POST /api/propguard/{account_id}/kill    - Manual emergency kill
- GET  /api/propguard/{account_id}/history - Equity snapshots
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Query
from app.database import get_db
from app.models import Account, PropFirmState, PropFirmEquitySnapshot
from app.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/propguard", tags=["propguard"])


async def _get_prop_account(
    db: AsyncSession, account_id: int, user
) -> Account:
    """Get and validate a prop firm account belongs to user."""
    result = await db.execute(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if not account.prop_firm:
        raise HTTPException(
            status_code=400,
            detail="Account is not a prop firm account",
        )
    return account


@router.get("/{account_id}/status")
async def get_propguard_status(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get current PropGuard status for an account."""
    account = await _get_prop_account(db, account_id, user)

    # Get PropFirmState
    result = await db.execute(
        select(PropFirmState).where(
            PropFirmState.account_id == account_id
        )
    )
    state = result.scalar_one_or_none()

    if not state:
        return {
            "account_id": account_id,
            "prop_firm": account.prop_firm,
            "status": "not_initialized",
            "message": "PropGuard state not yet created. "
                       "Will initialize on next monitor cycle.",
        }

    # Calculate drawdown percentages
    from app.exchange_clients.prop_guard_state import (
        calculate_daily_drawdown_pct,
        calculate_total_drawdown_pct,
    )

    daily_dd = 0.0
    total_dd = 0.0
    initial = state.initial_deposit or 0
    equity = state.current_equity or 0

    if state.daily_start_equity and state.daily_start_equity > 0 and equity > 0:
        daily_dd = calculate_daily_drawdown_pct(
            state.daily_start_equity, equity
        )
    if initial > 0 and equity > 0:
        total_dd = calculate_total_drawdown_pct(initial, equity)

    return {
        "account_id": account_id,
        "prop_firm": account.prop_firm,
        "initial_deposit": state.initial_deposit,
        "current_equity": state.current_equity,
        "current_equity_timestamp": (
            state.current_equity_timestamp.isoformat()
            if state.current_equity_timestamp else None
        ),
        "daily_start_equity": state.daily_start_equity,
        "daily_start_timestamp": (
            state.daily_start_timestamp.isoformat()
            if state.daily_start_timestamp else None
        ),
        "daily_drawdown_pct": round(daily_dd, 2),
        "daily_drawdown_limit": account.prop_daily_drawdown_pct or 4.5,
        "total_drawdown_pct": round(total_dd, 2),
        "total_drawdown_limit": account.prop_total_drawdown_pct or 9.0,
        "daily_pnl": state.daily_pnl,
        "total_pnl": state.total_pnl,
        "is_killed": state.is_killed,
        "kill_reason": state.kill_reason,
        "kill_timestamp": (
            state.kill_timestamp.isoformat()
            if state.kill_timestamp else None
        ),
    }


@router.post("/{account_id}/reset")
async def reset_kill_switch(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Reset kill switch (manual resume after review)."""
    await _get_prop_account(db, account_id, user)

    result = await db.execute(
        select(PropFirmState).where(
            PropFirmState.account_id == account_id
        )
    )
    state = result.scalar_one_or_none()

    if not state:
        raise HTTPException(
            status_code=404,
            detail="PropGuard state not found",
        )

    if not state.is_killed:
        return {
            "message": "Kill switch is not active",
            "account_id": account_id,
        }

    # Reset kill switch
    old_reason = state.kill_reason
    state.is_killed = False
    state.kill_reason = None
    state.kill_timestamp = None

    # Reset daily start to current equity
    if state.current_equity:
        state.daily_start_equity = state.current_equity
        state.daily_start_timestamp = datetime.utcnow()
        state.daily_pnl = 0.0

    await db.commit()

    # Clear exchange client cache to force re-wrap
    from app.services.exchange_service import clear_exchange_client_cache
    clear_exchange_client_cache(account_id)

    logger.info(
        f"PropGuard: Kill switch reset for account "
        f"{account_id} (was: {old_reason})"
    )

    return {
        "message": "Kill switch reset successfully",
        "account_id": account_id,
        "previous_reason": old_reason,
    }


@router.post("/{account_id}/kill")
async def manual_kill(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Manual emergency kill — close all positions."""
    account = await _get_prop_account(db, account_id, user)

    result = await db.execute(
        select(PropFirmState).where(
            PropFirmState.account_id == account_id
        )
    )
    state = result.scalar_one_or_none()

    now = datetime.utcnow()
    reason = "Manual kill switch activated by user"

    if state:
        state.is_killed = True
        state.kill_reason = reason
        state.kill_timestamp = now
    else:
        state = PropFirmState(
            account_id=account_id,
            initial_deposit=account.prop_initial_deposit or 100000.0,
            is_killed=True,
            kill_reason=reason,
            kill_timestamp=now,
        )
        db.add(state)

    await db.commit()

    # Attempt emergency liquidation
    liquidation_result = "not_attempted"
    try:
        from app.services.exchange_service import (
            get_exchange_client_for_account,
        )
        client = await get_exchange_client_for_account(
            db, account_id, use_cache=False
        )
        if client:
            inner = client
            if hasattr(client, '_inner'):
                inner = client._inner
            if hasattr(inner, 'close_all_positions'):
                await inner.close_all_positions()
                liquidation_result = "success"
            else:
                liquidation_result = "no_close_method"
    except Exception as e:
        liquidation_result = f"failed: {e}"
        logger.critical(
            f"PropGuard: Manual kill liquidation failed "
            f"for account {account_id}: {e}"
        )

    # Clear exchange client cache
    from app.services.exchange_service import clear_exchange_client_cache
    clear_exchange_client_cache(account_id)

    logger.critical(
        f"PropGuard: MANUAL KILL for account {account_id} "
        f"(liquidation={liquidation_result})"
    )

    return {
        "message": "Kill switch activated",
        "account_id": account_id,
        "liquidation_result": liquidation_result,
    }


@router.get("/{account_id}/history")
async def get_propguard_history(
    account_id: int,
    hours: int = Query(24, ge=1, le=168, description="Hours of history (max 7 days)"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get PropGuard equity time-series snapshots."""
    await _get_prop_account(db, account_id, user)

    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    result = await db.execute(
        select(PropFirmEquitySnapshot).where(
            PropFirmEquitySnapshot.account_id == account_id,
            PropFirmEquitySnapshot.timestamp >= cutoff,
        ).order_by(PropFirmEquitySnapshot.timestamp.asc())
    )
    snapshots = result.scalars().all()

    return {
        "account_id": account_id,
        "hours": hours,
        "count": len(snapshots),
        "snapshots": [{
            "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            "equity": s.equity,
            "daily_drawdown_pct": s.daily_drawdown_pct,
            "total_drawdown_pct": s.total_drawdown_pct,
            "daily_pnl": s.daily_pnl,
            "is_killed": s.is_killed,
        } for s in snapshots],
    }
