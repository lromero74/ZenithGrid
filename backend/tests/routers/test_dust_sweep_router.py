"""
Tests for dust sweep endpoints in accounts_router.py.

Covers:
- GET /{account_id}/dust-sweep-settings — returns config + dust positions
- PUT /{account_id}/dust-sweep-settings — update enabled/threshold (RBAC)
- POST /{account_id}/dust-sweep — on-demand sweep execution (RBAC)
"""

import inspect
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.auth.dependencies import Perm


# ---------------------------------------------------------------------------
# RBAC annotation checks
# ---------------------------------------------------------------------------


class TestDustSweepRBAC:
    """Verify RBAC annotations on dust sweep endpoints."""

    def test_get_dust_settings_uses_get_current_user(self):
        """GET dust-sweep-settings should use get_current_user (read-only)."""
        from app.routers.accounts_router import get_dust_sweep_settings

        sig = inspect.signature(get_dust_sweep_settings)
        param = sig.parameters.get("current_user")
        assert param is not None
        dep = param.default
        inner = dep.dependency
        # Should NOT use require_permission
        assert "require_permission" not in inner.__qualname__

    def test_put_dust_settings_requires_write(self):
        """PUT dust-sweep-settings should require accounts:write."""
        from app.routers.accounts_router import update_dust_sweep_settings

        sig = inspect.signature(update_dust_sweep_settings)
        param = sig.parameters.get("current_user")
        assert param is not None
        dep = param.default
        inner = dep.dependency
        assert "require_permission" in inner.__qualname__

        closure_vars = inspect.getclosurevars(inner)
        perms = closure_vars.nonlocals.get("permissions")
        perm_names = [str(p) for p in perms]
        assert str(Perm.ACCOUNTS_WRITE) in perm_names

    def test_post_sweep_requires_write(self):
        """POST dust-sweep should require accounts:write."""
        from app.routers.accounts_router import sweep_dust

        sig = inspect.signature(sweep_dust)
        param = sig.parameters.get("current_user")
        assert param is not None
        dep = param.default
        inner = dep.dependency
        assert "require_permission" in inner.__qualname__

        closure_vars = inspect.getclosurevars(inner)
        perms = closure_vars.nonlocals.get("permissions")
        perm_names = [str(p) for p in perms]
        assert str(Perm.ACCOUNTS_WRITE) in perm_names


# ---------------------------------------------------------------------------
# GET dust-sweep-settings (paper account)
# ---------------------------------------------------------------------------


class TestGetDustSettings:
    """Tests for GET /{account_id}/dust-sweep-settings."""

    @pytest.mark.asyncio
    async def test_returns_dust_list_from_paper_balances(self, db_session):
        """Happy path: returns dust positions from paper_balances."""
        from app.models import Account, User
        from app.routers.accounts_router import get_dust_sweep_settings

        user = User(
            email="test@example.com", hashed_password="x",
            is_active=True, is_superuser=True,
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            name="Paper", type="cex", exchange="coinbase",
            user_id=user.id, is_paper_trading=True,
            paper_balances=json.dumps({
                "USD": 5000, "BTC": 0.05, "ETH": 2.0,
                "ADA": 73.5, "SOL": 0.06,
            }),
            dust_sweep_enabled=True,
            dust_sweep_threshold_usd=5.0,
            dust_last_sweep_at=None,
        )
        db_session.add(account)
        await db_session.flush()

        prices = {
            "BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0,
            "ADA-USD": 0.38, "SOL-USD": 163.0,
        }

        with patch(
            "app.routers.accounts_router.get_public_prices",
            return_value=prices,
        ):
            result = await get_dust_sweep_settings(
                account_id=account.id, db=db_session, current_user=user,
            )

        assert result["enabled"] is True
        assert result["threshold_usd"] == 5.0
        assert result["last_sweep_at"] is None

        dust = result["dust_positions"]
        dust_coins = {d["coin"] for d in dust}
        assert "ADA" in dust_coins
        assert "SOL" in dust_coins
        # Target currencies should NOT appear as dust
        assert "USD" not in dust_coins
        assert "BTC" not in dust_coins

    @pytest.mark.asyncio
    async def test_empty_paper_balances_returns_empty_list(self, db_session):
        """Edge case: no non-target currencies means empty dust list."""
        from app.models import Account, User
        from app.routers.accounts_router import get_dust_sweep_settings

        user = User(
            email="test2@example.com", hashed_password="x",
            is_active=True, is_superuser=True,
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            name="Clean", type="cex", exchange="coinbase",
            user_id=user.id, is_paper_trading=True,
            paper_balances=json.dumps({"USD": 5000, "BTC": 0.05}),
            dust_sweep_enabled=False,
            dust_sweep_threshold_usd=5.0,
        )
        db_session.add(account)
        await db_session.flush()

        with patch(
            "app.routers.accounts_router.get_public_prices",
            return_value={"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0},
        ):
            result = await get_dust_sweep_settings(
                account_id=account.id, db=db_session, current_user=user,
            )

        assert result["dust_positions"] == []


# ---------------------------------------------------------------------------
# PUT dust-sweep-settings
# ---------------------------------------------------------------------------


class TestUpdateDustSettings:
    """Tests for PUT /{account_id}/dust-sweep-settings."""

    @pytest.mark.asyncio
    async def test_crud_round_trip(self, db_session):
        """Happy path: update and read back dust sweep settings."""
        from app.models import Account, User
        from app.routers.accounts_router import (
            get_dust_sweep_settings, update_dust_sweep_settings,
        )
        from pydantic import BaseModel
        from typing import Optional

        user = User(
            email="crud@example.com", hashed_password="x",
            is_active=True, is_superuser=True,
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            name="CRUD Test", type="cex", exchange="coinbase",
            user_id=user.id, is_paper_trading=True,
            paper_balances=json.dumps({"USD": 1000}),
            dust_sweep_enabled=False,
            dust_sweep_threshold_usd=5.0,
        )
        db_session.add(account)
        await db_session.flush()

        # Import the update model
        from app.routers.accounts_router import DustSweepSettingsUpdate

        settings = DustSweepSettingsUpdate(enabled=True, threshold_usd=10.0)
        result = await update_dust_sweep_settings(
            account_id=account.id, settings=settings,
            db=db_session, current_user=user,
        )

        assert result["enabled"] is True
        assert result["threshold_usd"] == 10.0

        # Verify via GET
        with patch(
            "app.routers.accounts_router.get_public_prices",
            return_value={"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0},
        ):
            get_result = await get_dust_sweep_settings(
                account_id=account.id, db=db_session, current_user=user,
            )
        assert get_result["enabled"] is True
        assert get_result["threshold_usd"] == 10.0
