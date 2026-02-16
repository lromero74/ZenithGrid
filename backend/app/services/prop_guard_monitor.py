"""
PropGuard Background Monitor

Background async task that runs every 30 seconds to:
- Query accounts with prop_firm IS NOT NULL and is_active
- For ByBit accounts: start/manage WebSocket managers
- For MT5 accounts: poll bridge /status endpoint for equity
- Update PropFirmState in DB
- If drawdown breached: trigger kill switch + liquidate
- If daily reset time passed: snapshot new daily_start_equity
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Monitor state
_monitor_task: Optional[asyncio.Task] = None
_running = False


async def _monitor_loop():
    """Main monitor loop — runs every 30 seconds."""
    global _running
    _running = True

    # Wait 30 seconds after startup before first check
    await asyncio.sleep(30)

    while _running:
        try:
            await _check_all_prop_accounts()
        except Exception as e:
            logger.error(f"PropGuard monitor error: {e}")

        await asyncio.sleep(30)


async def _check_all_prop_accounts():
    """Check all active prop firm accounts."""
    from sqlalchemy import select

    from app.database import async_session_maker
    from app.models import Account

    async with async_session_maker() as db:
        # Get all active prop firm accounts
        result = await db.execute(
            select(Account).where(
                Account.prop_firm.isnot(None),
                Account.is_active.is_(True),
            )
        )
        accounts = result.scalars().all()

        if not accounts:
            return

        for account in accounts:
            try:
                await _check_account(db, account)
            except Exception as e:
                logger.error(
                    f"PropGuard: Error checking account "
                    f"{account.id}: {e}"
                )

        await db.commit()


async def _check_account(db, account):
    """Check a single prop firm account."""
    from sqlalchemy import select
    from app.models import PropFirmState, PropFirmEquitySnapshot
    from app.exchange_clients.prop_guard_state import (
        calculate_daily_drawdown_pct,
        calculate_total_drawdown_pct,
        should_reset_daily,
    )

    # Ensure WS manager is running for ByBit accounts
    if account.exchange == "bybit":
        await _ensure_ws_manager(account)

    # Get current equity
    equity = await _get_account_equity(account)
    if equity <= 0:
        return

    # Get or create PropFirmState
    result = await db.execute(
        select(PropFirmState).where(
            PropFirmState.account_id == account.id
        )
    )
    state = result.scalar_one_or_none()

    if not state:
        state = PropFirmState(
            account_id=account.id,
            initial_deposit=account.prop_initial_deposit or 100000.0,
            daily_start_equity=equity,
            daily_start_timestamp=datetime.utcnow(),
            current_equity=equity,
            current_equity_timestamp=datetime.utcnow(),
        )
        db.add(state)
        logger.info(
            f"PropGuard: Created state for account "
            f"{account.id} (equity={equity:.2f})"
        )
        return

    # Skip if already killed
    if state.is_killed:
        return

    # Update current equity
    state.current_equity = equity
    state.current_equity_timestamp = datetime.utcnow()

    # Check daily reset
    if should_reset_daily(state.daily_start_timestamp):
        state.daily_start_equity = equity
        state.daily_start_timestamp = datetime.utcnow()
        state.daily_pnl = 0.0
        logger.info(
            f"PropGuard: Daily reset for account "
            f"{account.id} (equity={equity:.2f})"
        )

    # Calculate drawdowns
    daily_dd = 0.0
    total_dd = 0.0
    initial_deposit = state.initial_deposit or 100000.0

    if state.daily_start_equity and state.daily_start_equity > 0:
        daily_dd = calculate_daily_drawdown_pct(
            state.daily_start_equity, equity
        )

    if initial_deposit > 0:
        total_dd = calculate_total_drawdown_pct(
            initial_deposit, equity
        )

    # Update P&L
    if state.daily_start_equity:
        state.daily_pnl = equity - state.daily_start_equity
    state.total_pnl = equity - initial_deposit

    # Record equity snapshot for time-series history
    db.add(PropFirmEquitySnapshot(
        account_id=account.id,
        equity=equity,
        daily_drawdown_pct=daily_dd,
        total_drawdown_pct=total_dd,
        daily_pnl=state.daily_pnl or 0.0,
        is_killed=False,
        timestamp=datetime.utcnow(),
    ))

    # Check daily drawdown limit
    daily_limit = account.prop_daily_drawdown_pct or 4.5
    if daily_dd >= daily_limit:
        reason = (
            f"Daily drawdown {daily_dd:.2f}% "
            f">= limit {daily_limit}%"
        )
        logger.critical(
            f"PropGuard MONITOR KILL: {reason} "
            f"(account {account.id})"
        )
        await _kill_account(db, state, account, reason)
        return

    # Check total drawdown limit
    total_limit = account.prop_total_drawdown_pct or 9.0
    if total_dd >= total_limit:
        reason = (
            f"Total drawdown {total_dd:.2f}% "
            f">= limit {total_limit}%"
        )
        logger.critical(
            f"PropGuard MONITOR KILL: {reason} "
            f"(account {account.id})"
        )
        await _kill_account(db, state, account, reason)
        return


async def _get_account_equity(account) -> float:
    """Get current equity for a prop firm account."""
    # Try WS state first (ByBit) with staleness check
    if account.exchange == "bybit":
        from app.exchange_clients.bybit_ws import get_ws_manager
        ws_mgr = get_ws_manager(account.id)
        if ws_mgr and ws_mgr.state.connected:
            eq = ws_mgr.state.equity
            eq_ts = ws_mgr.state.equity_timestamp
            if eq > 0 and eq_ts:
                age = (datetime.utcnow() - eq_ts).total_seconds()
                if age <= 60:
                    return eq
                logger.warning(
                    f"PropGuard monitor: WS equity stale "
                    f"({age:.0f}s) for account {account.id}"
                )

    # Fallback: get exchange client and query
    try:
        from app.services.exchange_service import (
            get_exchange_client_for_account,
        )
        from app.database import async_session_maker
        async with async_session_maker() as db:
            client = await get_exchange_client_for_account(
                db, account.id, use_cache=True
            )
            if client:
                # Unwrap PropGuard to get inner client
                inner = client
                if hasattr(client, '_inner'):
                    inner = client._inner

                if hasattr(inner, 'get_equity'):
                    return await inner.get_equity()
                return await inner.calculate_aggregate_usd_value()
    except Exception as e:
        logger.error(
            f"PropGuard: Failed to get equity for "
            f"account {account.id}: {e}"
        )

    return 0.0


async def _ensure_ws_manager(account):
    """Ensure WebSocket manager is running for a ByBit account."""
    from app.exchange_clients.bybit_ws import (
        get_ws_manager,
        register_ws_manager,
        ByBitWSManager,
    )
    from app.encryption import decrypt_value, is_encrypted

    ws_mgr = get_ws_manager(account.id)
    if ws_mgr and ws_mgr.state.connected:
        return  # Already running

    # Start new WS manager
    try:
        ak = account.api_key_name
        sk = account.api_private_key
        if is_encrypted(sk):
            sk = decrypt_value(sk)

        config = account.prop_firm_config or {}
        testnet = config.get("testnet", False)

        manager = ByBitWSManager(
            api_key=ak,
            api_secret=sk,
            testnet=testnet,
            symbols=["BTCUSDT"],
        )
        manager.start()
        register_ws_manager(account.id, manager)
        logger.info(
            f"PropGuard: Started WS manager for "
            f"account {account.id}"
        )
    except Exception as e:
        logger.error(
            f"PropGuard: Failed to start WS manager "
            f"for account {account.id}: {e}"
        )


async def _kill_account(db, state, account, reason: str):
    """Trigger kill switch for an account."""
    state.is_killed = True
    state.kill_reason = reason
    state.kill_timestamp = datetime.utcnow()

    # Emergency liquidation
    try:
        from app.services.exchange_service import (
            get_exchange_client_for_account,
        )
        from app.database import async_session_maker
        async with async_session_maker() as inner_db:
            client = await get_exchange_client_for_account(
                inner_db, account.id, use_cache=True
            )
            if client:
                inner = client
                if hasattr(client, '_inner'):
                    inner = client._inner
                if hasattr(inner, 'close_all_positions'):
                    await inner.close_all_positions()
                    logger.critical(
                        f"PropGuard: Liquidated all positions "
                        f"for account {account.id}"
                    )
    except Exception as e:
        logger.critical(
            f"PropGuard: LIQUIDATION FAILED for "
            f"account {account.id}: {e}"
        )


async def start_prop_guard_monitor():
    """Start the PropGuard background monitor."""
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        logger.warning("PropGuard monitor already running")
        return
    _monitor_task = asyncio.create_task(_monitor_loop())
    logger.info("PropGuard monitor started")


async def stop_prop_guard_monitor():
    """Stop the PropGuard background monitor."""
    global _running, _monitor_task
    _running = False

    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
        _monitor_task = None

    # Stop all WS managers
    from app.exchange_clients.bybit_ws import stop_all_ws_managers
    stop_all_ws_managers()

    logger.info("PropGuard monitor stopped")
