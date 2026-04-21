"""
Tests for backend/app/auth_routers/device_trust_router.py

Covers /mfa/devices (list / revoke single / revoke all):
- Happy paths: active devices listed, specific device revoked, all revoked
- Expired devices are excluded from the list
- Revoke non-existent device returns 404
- Cross-user isolation: user A cannot list, revoke, or revoke-all user B's devices
"""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import TrustedDevice, User


async def _mk_user(db_session, email: str) -> User:
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _mk_device(
    db_session,
    user_id: int,
    *,
    device_id: str,
    name: str = "Test Device",
    expires_in_days: float = 30,
) -> TrustedDevice:
    device = TrustedDevice(
        user_id=user_id,
        device_id=device_id,
        device_name=name,
        ip_address="127.0.0.1",
        location="Local",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
    )
    db_session.add(device)
    await db_session.flush()
    return device


# ---------------------------------------------------------------------------
# GET /mfa/devices
# ---------------------------------------------------------------------------


class TestListTrustedDevices:
    @pytest.mark.asyncio
    async def test_lists_active_devices(self, db_session):
        from app.auth_routers.device_trust_router import list_trusted_devices

        user = await _mk_user(db_session, "lister@example.com")
        await _mk_device(db_session, user.id, device_id="dev-1", name="Laptop")
        await _mk_device(db_session, user.id, device_id="dev-2", name="Phone")

        result = await list_trusted_devices(current_user=user, db=db_session)
        assert len(result) == 2
        names = {d.device_name for d in result}
        assert names == {"Laptop", "Phone"}

    @pytest.mark.asyncio
    async def test_expired_devices_excluded(self, db_session):
        from app.auth_routers.device_trust_router import list_trusted_devices

        user = await _mk_user(db_session, "expired-list@example.com")
        await _mk_device(db_session, user.id, device_id="active", name="Active")
        await _mk_device(
            db_session, user.id, device_id="old", name="Old", expires_in_days=-1
        )

        result = await list_trusted_devices(current_user=user, db=db_session)
        assert len(result) == 1
        assert result[0].device_name == "Active"

    @pytest.mark.asyncio
    async def test_only_sees_own_devices(self, db_session):
        """Cross-user isolation: user A's list never contains user B's devices."""
        from app.auth_routers.device_trust_router import list_trusted_devices

        user_a = await _mk_user(db_session, "a-dev@example.com")
        user_b = await _mk_user(db_session, "b-dev@example.com")
        await _mk_device(db_session, user_a.id, device_id="a-dev", name="A's Laptop")
        await _mk_device(db_session, user_b.id, device_id="b-dev", name="B's Laptop")

        result = await list_trusted_devices(current_user=user_a, db=db_session)
        assert len(result) == 1
        assert result[0].device_name == "A's Laptop"


# ---------------------------------------------------------------------------
# DELETE /mfa/devices/{device_id}
# ---------------------------------------------------------------------------


class TestRevokeTrustedDevice:
    @pytest.mark.asyncio
    async def test_revokes_own_device(self, db_session):
        from app.auth_routers.device_trust_router import revoke_trusted_device

        user = await _mk_user(db_session, "revoker@example.com")
        device = await _mk_device(db_session, user.id, device_id="rev-1")
        device_pk = device.id

        result = await revoke_trusted_device(
            device_id=device_pk, current_user=user, db=db_session
        )
        assert "revoked" in result["message"].lower()

        remaining = (await db_session.execute(
            select(TrustedDevice).where(TrustedDevice.id == device_pk)
        )).scalar_one_or_none()
        assert remaining is None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_returns_404(self, db_session):
        from app.auth_routers.device_trust_router import revoke_trusted_device

        user = await _mk_user(db_session, "ghost@example.com")
        with pytest.raises(HTTPException) as exc:
            await revoke_trusted_device(device_id=99999, current_user=user, db=db_session)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_user_b_cannot_revoke_user_a_device(self, db_session):
        """Cross-user isolation: user B gets 404, device survives."""
        from app.auth_routers.device_trust_router import revoke_trusted_device

        user_a = await _mk_user(db_session, "owner@example.com")
        user_b = await _mk_user(db_session, "attacker@example.com")
        device = await _mk_device(db_session, user_a.id, device_id="a-dev")
        device_pk = device.id

        with pytest.raises(HTTPException) as exc:
            await revoke_trusted_device(
                device_id=device_pk, current_user=user_b, db=db_session
            )
        assert exc.value.status_code == 404

        # Device must still exist.
        still_there = (await db_session.execute(
            select(TrustedDevice).where(TrustedDevice.id == device_pk)
        )).scalar_one_or_none()
        assert still_there is not None


# ---------------------------------------------------------------------------
# DELETE /mfa/devices (revoke all)
# ---------------------------------------------------------------------------


class TestRevokeAllTrustedDevices:
    @pytest.mark.asyncio
    async def test_revokes_all_own_devices(self, db_session):
        from app.auth_routers.device_trust_router import revoke_all_trusted_devices

        user = await _mk_user(db_session, "nuke@example.com")
        await _mk_device(db_session, user.id, device_id="d1")
        await _mk_device(db_session, user.id, device_id="d2")
        await _mk_device(db_session, user.id, device_id="d3")

        result = await revoke_all_trusted_devices(current_user=user, db=db_session)
        assert "3" in result["message"]

        remaining = (await db_session.execute(
            select(TrustedDevice).where(TrustedDevice.user_id == user.id)
        )).scalars().all()
        assert remaining == []

    @pytest.mark.asyncio
    async def test_revoke_all_with_zero_devices(self, db_session):
        """Edge case: revoke-all on a user with no devices succeeds with count 0."""
        from app.auth_routers.device_trust_router import revoke_all_trusted_devices

        user = await _mk_user(db_session, "empty@example.com")
        result = await revoke_all_trusted_devices(current_user=user, db=db_session)
        assert "0" in result["message"]

    @pytest.mark.asyncio
    async def test_revoke_all_does_not_touch_other_users(self, db_session):
        """Cross-user isolation: user A's revoke-all leaves user B's devices intact."""
        from app.auth_routers.device_trust_router import revoke_all_trusted_devices

        user_a = await _mk_user(db_session, "a-nuke@example.com")
        user_b = await _mk_user(db_session, "b-safe@example.com")
        await _mk_device(db_session, user_a.id, device_id="a1")
        await _mk_device(db_session, user_a.id, device_id="a2")
        await _mk_device(db_session, user_b.id, device_id="b1")
        await _mk_device(db_session, user_b.id, device_id="b2")

        await revoke_all_trusted_devices(current_user=user_a, db=db_session)

        a_left = (await db_session.execute(
            select(TrustedDevice).where(TrustedDevice.user_id == user_a.id)
        )).scalars().all()
        b_left = (await db_session.execute(
            select(TrustedDevice).where(TrustedDevice.user_id == user_b.id)
        )).scalars().all()
        assert a_left == []
        assert len(b_left) == 2
