"""
Backtesting Router

Endpoints for running backtests and retrieving results.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtesting", tags=["backtesting"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    """Request to run a backtest."""
    strategy_type: str
    strategy_config: Dict[str, Any]
    product_id: str
    start_ts: int  # Unix timestamp (seconds)
    end_ts: int  # Unix timestamp (seconds)
    granularity: str = "FIVE_MINUTE"  # Candle interval
    initial_capital: float = 1000.0
    fee_pct: float = 0.0
    account_id: Optional[int] = None  # For account-scoped data fetching


class BacktestResponse(BaseModel):
    """Backtest result response."""
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run", response_model=BacktestResponse)
async def run_backtest(
    request: BacktestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BacktestResponse:
    """Run a backtest synchronously.

    Fetches historical candles from the exchange, replays them through
    the specified strategy, and returns the performance report.
    """
    from app.backtesting import run_backtest as _run_backtest
    from app.services.exchange_service import get_exchange_client_for_account

    # Validate strategy exists
    from app.strategies import StrategyRegistry
    try:
        StrategyRegistry.get_definition(request.strategy_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {request.strategy_type}")

    # Determine which account to use for fetching candles
    account_id = request.account_id
    if account_id is None:
        # Fall back to user's first active CEX account
        from app.models import Account
        result = await db.execute(
            select(Account).where(
                Account.user_id == current_user.id,
                Account.is_active.is_(True),
                Account.type == "cex",
            ).order_by(Account.is_default.desc(), Account.created_at).limit(1)
        )
        account = result.scalars().first()
        if not account:
            raise HTTPException(status_code=400, detail="No active CEX account to fetch historical data")
        account_id = account.id

    # Get exchange client
    exchange = await get_exchange_client_for_account(db, account_id)
    if not exchange:
        raise HTTPException(status_code=400, detail="Could not create exchange client for account")

    # Fetch historical candles
    try:
        candles = await exchange.get_candles(
            request.product_id,
            request.start_ts,
            request.end_ts,
            request.granularity,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch candles: {e}")

    if not candles or len(candles) < 20:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient candle data: got {len(candles) if candles else 0} candles (minimum 20 required)",
        )

    # Sort candles oldest-first (exchanges often return newest-first)
    candles.sort(key=lambda c: int(float(c.get("start", c.get("time", 0)))))

    # Run the backtest
    try:
        result = await _run_backtest(
            strategy_type=request.strategy_type,
            strategy_config=request.strategy_config,
            candles=candles,
            product_id=request.product_id,
            initial_capital=request.initial_capital,
            fee_pct=request.fee_pct,
            user_id=current_user.id,
            account_id=account_id,
        )
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        return BacktestResponse(status="error", error=str(e))

    return BacktestResponse(status="ok", result=result.to_dict())
