"""
Tests for backend/app/routers/prop_guard_router.py

Covers PropGuard endpoints: get_propguard_status, reset_kill_switch,
manual_kill, get_propguard_history, and _get_prop_account helper.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import Account, PropFirmEquitySnapshot, PropFirmState, User


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_user(db_session):
    user = User(
        id=1, email="test@test.com",
        hashed_password="hashed", is_active=True, is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def prop_account(db_session, test_user):
    account = Account(
        id=1, user_id=test_user.id, name="Prop Account",
        type="cex", exchange="coinbase", is_default=True, is_active=True,
        prop_firm="hyrotrader",
        prop_daily_drawdown_pct=4.5,
        prop_total_drawdown_pct=9.0,
        prop_initial_deposit=100000.0,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest.fixture
async def non_prop_account(db_session, test_user):
    account = Account(
        id=2, user_id=test_user.id, name="Regular Account",
        type="cex", exchange="coinbase", is_default=False, is_active=True,
        prop_firm=None,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest.fixture
async def prop_state(db_session, prop_account):
    state = PropFirmState(
        id=1, account_id=prop_account.id,
        initial_deposit=100000.0,
        daily_start_equity=99000.0,
        daily_start_timestamp=datetime.utcnow(),
        current_equity=98500.0,
        current_equity_timestamp=datetime.utcnow(),
        is_killed=False,
        daily_pnl=-500.0,
        total_pnl=-1500.0,
    )
    db_session.add(state)
    await db_session.flush()
    return state


@pytest.fixture
async def killed_prop_state(db_session, prop_account):
    state = PropFirmState(
        id=1, account_id=prop_account.id,
        initial_deposit=100000.0,
        daily_start_equity=99000.0,
        current_equity=95000.0,
        current_equity_timestamp=datetime.utcnow(),
        is_killed=True,
        kill_reason="Daily drawdown limit exceeded",
        kill_timestamp=datetime.utcnow(),
        daily_pnl=-4000.0,
        total_pnl=-5000.0,
    )
    db_session.add(state)
    await db_session.flush()
    return state


# =============================================================================
# _get_prop_account helper
# =============================================================================


class TestGetPropAccount:
    """Tests for _get_prop_account helper function."""

    @pytest.mark.asyncio
    async def test_get_prop_account_success(
        self, db_session, test_user, prop_account,
    ):
        """Happy path: returns prop firm account."""
        from app.routers.prop_guard_router import _get_prop_account
        result = await _get_prop_account(
            db=db_session, account_id=prop_account.id, user=test_user,
        )
        assert result.id == prop_account.id
        assert result.prop_firm == "hyrotrader"

    @pytest.mark.asyncio
    async def test_get_prop_account_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.prop_guard_router import _get_prop_account
        with pytest.raises(HTTPException) as exc_info:
            await _get_prop_account(
                db=db_session, account_id=999, user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_prop_account_not_prop_firm(
        self, db_session, test_user, non_prop_account,
    ):
        """Failure case: non-prop account raises 400."""
        from app.routers.prop_guard_router import _get_prop_account
        with pytest.raises(HTTPException) as exc_info:
            await _get_prop_account(
                db=db_session, account_id=non_prop_account.id, user=test_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_prop_account_wrong_user(
        self, db_session, prop_account,
    ):
        """Failure case: wrong user raises 404."""
        other_user = User(
            id=2, email="other@test.com",
            hashed_password="hashed", is_active=True,
        )
        from app.routers.prop_guard_router import _get_prop_account
        with pytest.raises(HTTPException) as exc_info:
            await _get_prop_account(
                db=db_session, account_id=prop_account.id, user=other_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# get_propguard_status
# =============================================================================


class TestGetPropguardStatus:
    """Tests for get_propguard_status endpoint."""

    @pytest.mark.asyncio
    @patch(
        "app.exchange_clients.prop_guard_state.calculate_daily_drawdown_pct",
        return_value=0.51,
    )
    @patch(
        "app.exchange_clients.prop_guard_state.calculate_total_drawdown_pct",
        return_value=1.5,
    )
    async def test_status_with_state(
        self, mock_total_dd, mock_daily_dd,
        db_session, test_user, prop_account, prop_state,
    ):
        """Happy path: returns full PropGuard status."""
        from app.routers.prop_guard_router import get_propguard_status
        result = await get_propguard_status(
            account_id=prop_account.id, db=db_session, user=test_user,
        )
        assert result["account_id"] == prop_account.id
        assert result["prop_firm"] == "hyrotrader"
        assert result["current_equity"] == 98500.0
        assert result["is_killed"] is False
        assert result["daily_drawdown_pct"] == 0.51
        assert result["total_drawdown_pct"] == 1.5

    @pytest.mark.asyncio
    async def test_status_not_initialized(
        self, db_session, test_user, prop_account,
    ):
        """Edge case: no state yet returns 'not_initialized'."""
        from app.routers.prop_guard_router import get_propguard_status
        result = await get_propguard_status(
            account_id=prop_account.id, db=db_session, user=test_user,
        )
        assert result["status"] == "not_initialized"

    @pytest.mark.asyncio
    async def test_status_non_prop_account_raises_400(
        self, db_session, test_user, non_prop_account,
    ):
        """Failure case: non-prop account raises 400."""
        from app.routers.prop_guard_router import get_propguard_status
        with pytest.raises(HTTPException) as exc_info:
            await get_propguard_status(
                account_id=non_prop_account.id, db=db_session, user=test_user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# reset_kill_switch
# =============================================================================


class TestResetKillSwitch:
    """Tests for reset_kill_switch endpoint."""

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.clear_exchange_client_cache")
    async def test_reset_success(
        self, mock_clear, db_session, test_user, prop_account, killed_prop_state,
    ):
        """Happy path: resets the kill switch."""
        from app.routers.prop_guard_router import reset_kill_switch
        result = await reset_kill_switch(
            account_id=prop_account.id, db=db_session, user=test_user,
        )
        assert "reset successfully" in result["message"]
        assert result["previous_reason"] == "Daily drawdown limit exceeded"
        mock_clear.assert_called_once_with(prop_account.id)

    @pytest.mark.asyncio
    async def test_reset_not_killed(
        self, db_session, test_user, prop_account, prop_state,
    ):
        """Edge case: reset when not killed returns info message."""
        from app.routers.prop_guard_router import reset_kill_switch
        result = await reset_kill_switch(
            account_id=prop_account.id, db=db_session, user=test_user,
        )
        assert "not active" in result["message"]

    @pytest.mark.asyncio
    async def test_reset_no_state_raises_404(
        self, db_session, test_user, prop_account,
    ):
        """Failure case: no state record raises 404."""
        from app.routers.prop_guard_router import reset_kill_switch
        with pytest.raises(HTTPException) as exc_info:
            await reset_kill_switch(
                account_id=prop_account.id, db=db_session, user=test_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# manual_kill
# =============================================================================


class TestManualKill:
    """Tests for manual_kill endpoint."""

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.clear_exchange_client_cache")
    @patch(
        "app.services.exchange_service.get_exchange_client_for_account",
        new_callable=AsyncMock,
    )
    async def test_manual_kill_with_existing_state(
        self, mock_client, mock_clear,
        db_session, test_user, prop_account, prop_state,
    ):
        """Happy path: activates kill switch on existing state."""
        mock_inner = AsyncMock()
        mock_inner.close_all_positions = AsyncMock()
        mock_client.return_value = mock_inner

        from app.routers.prop_guard_router import manual_kill
        result = await manual_kill(
            account_id=prop_account.id, db=db_session, user=test_user,
        )
        assert result["message"] == "Kill switch activated"
        assert result["account_id"] == prop_account.id

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.clear_exchange_client_cache")
    @patch(
        "app.services.exchange_service.get_exchange_client_for_account",
        new_callable=AsyncMock,
        return_value=None,
    )
    async def test_manual_kill_creates_state_if_none(
        self, mock_client, mock_clear,
        db_session, test_user, prop_account,
    ):
        """Edge case: creates PropFirmState if none exists."""
        from app.routers.prop_guard_router import manual_kill
        result = await manual_kill(
            account_id=prop_account.id, db=db_session, user=test_user,
        )
        assert result["message"] == "Kill switch activated"
        assert result["liquidation_result"] == "not_attempted"

    @pytest.mark.asyncio
    async def test_manual_kill_non_prop_raises_400(
        self, db_session, test_user, non_prop_account,
    ):
        """Failure case: non-prop account raises 400."""
        from app.routers.prop_guard_router import manual_kill
        with pytest.raises(HTTPException) as exc_info:
            await manual_kill(
                account_id=non_prop_account.id, db=db_session, user=test_user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# get_propguard_history
# =============================================================================


class TestGetPropguardHistory:
    """Tests for get_propguard_history endpoint."""

    @pytest.mark.asyncio
    async def test_history_returns_snapshots(
        self, db_session, test_user, prop_account,
    ):
        """Happy path: returns equity snapshots."""
        snapshot = PropFirmEquitySnapshot(
            account_id=prop_account.id,
            equity=99000.0,
            daily_drawdown_pct=1.0,
            total_drawdown_pct=1.0,
            daily_pnl=-1000.0,
            is_killed=False,
            timestamp=datetime.utcnow(),
        )
        db_session.add(snapshot)
        await db_session.flush()

        from app.routers.prop_guard_router import get_propguard_history
        result = await get_propguard_history(
            account_id=prop_account.id, hours=24,
            db=db_session, user=test_user,
        )
        assert result["count"] == 1
        assert result["snapshots"][0]["equity"] == 99000.0

    @pytest.mark.asyncio
    async def test_history_empty(self, db_session, test_user, prop_account):
        """Edge case: no snapshots returns empty list."""
        from app.routers.prop_guard_router import get_propguard_history
        result = await get_propguard_history(
            account_id=prop_account.id, hours=24,
            db=db_session, user=test_user,
        )
        assert result["count"] == 0
        assert result["snapshots"] == []

    @pytest.mark.asyncio
    async def test_history_filters_by_hours(
        self, db_session, test_user, prop_account,
    ):
        """Edge case: old snapshots are filtered out."""
        old_snapshot = PropFirmEquitySnapshot(
            account_id=prop_account.id,
            equity=98000.0,
            daily_drawdown_pct=2.0,
            total_drawdown_pct=2.0,
            daily_pnl=-2000.0,
            is_killed=False,
            timestamp=datetime.utcnow() - timedelta(hours=48),
        )
        db_session.add(old_snapshot)
        await db_session.flush()

        from app.routers.prop_guard_router import get_propguard_history
        result = await get_propguard_history(
            account_id=prop_account.id, hours=24,
            db=db_session, user=test_user,
        )
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_history_non_prop_raises_400(
        self, db_session, test_user, non_prop_account,
    ):
        """Failure case: non-prop account raises 400."""
        from app.routers.prop_guard_router import get_propguard_history
        with pytest.raises(HTTPException) as exc_info:
            await get_propguard_history(
                account_id=non_prop_account.id, hours=24,
                db=db_session, user=test_user,
            )
        assert exc_info.value.status_code == 400
