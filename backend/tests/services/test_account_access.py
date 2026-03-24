"""
Tests for backend/app/services/account_access.py

Covers:
- accessible_account_ids: owned accounts + member accounts (any role)
- accessible_account_ids: excludes expired memberships
- manager_account_ids: owned accounts + manager-role accounts only
- manager_account_ids: excludes observer-role memberships
- manager_account_ids: excludes expired manager memberships
"""

import pytest
from datetime import datetime, timedelta

from app.models import Account, User
from app.models.sharing import AccountMembership


# =============================================================================
# Helpers
# =============================================================================


async def _make_user(db, email: str) -> User:
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_account(db, owner: User, name: str = "TestAccount") -> Account:
    account = Account(
        user_id=owner.id,
        name=name,
        type="cex",
        exchange="coinbase",
        is_active=True,
    )
    db.add(account)
    await db.flush()
    return account


async def _make_membership(
    db,
    account: Account,
    user: User,
    role: str = "observer",
    expires_at=None,
) -> AccountMembership:
    m = AccountMembership(
        account_id=account.id,
        user_id=user.id,
        role=role,
        invited_by_user_id=account.user_id,
        expires_at=expires_at,
    )
    db.add(m)
    await db.flush()
    return m


# =============================================================================
# accessible_account_ids
# =============================================================================


class TestAccessibleAccountIds:
    """Tests for accessible_account_ids()"""

    @pytest.mark.asyncio
    async def test_returns_owned_accounts(self, db_session):
        """Happy path: own accounts are always included."""
        from app.services.account_access import accessible_account_ids

        owner = await _make_user(db_session, "owner@example.com")
        account = await _make_account(db_session, owner)

        ids = await accessible_account_ids(db_session, owner.id)

        assert account.id in ids

    @pytest.mark.asyncio
    async def test_returns_observer_membership_accounts(self, db_session):
        """Happy path: accounts where user has observer membership are included."""
        from app.services.account_access import accessible_account_ids

        owner = await _make_user(db_session, "owner2@example.com")
        observer = await _make_user(db_session, "observer2@example.com")
        account = await _make_account(db_session, owner)
        await _make_membership(db_session, account, observer, role="observer")

        ids = await accessible_account_ids(db_session, observer.id)

        assert account.id in ids

    @pytest.mark.asyncio
    async def test_returns_manager_membership_accounts(self, db_session):
        """Happy path: accounts where user has manager membership are included."""
        from app.services.account_access import accessible_account_ids

        owner = await _make_user(db_session, "owner3@example.com")
        manager = await _make_user(db_session, "manager3@example.com")
        account = await _make_account(db_session, owner)
        await _make_membership(db_session, account, manager, role="manager")

        ids = await accessible_account_ids(db_session, manager.id)

        assert account.id in ids

    @pytest.mark.asyncio
    async def test_excludes_accounts_with_no_relationship(self, db_session):
        """Edge case: accounts with no ownership or membership are excluded."""
        from app.services.account_access import accessible_account_ids

        owner = await _make_user(db_session, "owner4@example.com")
        outsider = await _make_user(db_session, "outsider4@example.com")
        account = await _make_account(db_session, owner)

        ids = await accessible_account_ids(db_session, outsider.id)

        assert account.id not in ids

    @pytest.mark.asyncio
    async def test_excludes_expired_memberships(self, db_session):
        """Edge case: expired memberships do not grant access."""
        from app.services.account_access import accessible_account_ids

        owner = await _make_user(db_session, "owner5@example.com")
        member = await _make_user(db_session, "member5@example.com")
        account = await _make_account(db_session, owner)
        expired_at = datetime.utcnow() - timedelta(hours=1)
        await _make_membership(db_session, account, member, role="observer", expires_at=expired_at)

        ids = await accessible_account_ids(db_session, member.id)

        assert account.id not in ids

    @pytest.mark.asyncio
    async def test_includes_non_expired_memberships(self, db_session):
        """Happy path: memberships that haven't expired yet are included."""
        from app.services.account_access import accessible_account_ids

        owner = await _make_user(db_session, "owner6@example.com")
        member = await _make_user(db_session, "member6@example.com")
        account = await _make_account(db_session, owner)
        future_expiry = datetime.utcnow() + timedelta(days=30)
        await _make_membership(db_session, account, member, role="observer", expires_at=future_expiry)

        ids = await accessible_account_ids(db_session, member.id)

        assert account.id in ids

    @pytest.mark.asyncio
    async def test_includes_memberships_with_no_expiry(self, db_session):
        """Happy path: memberships with no expiry date are permanently active."""
        from app.services.account_access import accessible_account_ids

        owner = await _make_user(db_session, "owner7@example.com")
        member = await _make_user(db_session, "member7@example.com")
        account = await _make_account(db_session, owner)
        await _make_membership(db_session, account, member, role="manager", expires_at=None)

        ids = await accessible_account_ids(db_session, member.id)

        assert account.id in ids

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_user_with_no_accounts(self, db_session):
        """Edge case: user with no owned or shared accounts gets empty list."""
        from app.services.account_access import accessible_account_ids

        lonely = await _make_user(db_session, "lonely@example.com")

        ids = await accessible_account_ids(db_session, lonely.id)

        assert ids == []

    @pytest.mark.asyncio
    async def test_returns_multiple_accounts(self, db_session):
        """Happy path: user can access multiple accounts (owned + shared)."""
        from app.services.account_access import accessible_account_ids

        owner_a = await _make_user(db_session, "owner_a@example.com")
        owner_b = await _make_user(db_session, "owner_b@example.com")
        member = await _make_user(db_session, "multi_member@example.com")
        own_account = await _make_account(db_session, member, name="OwnAccount")
        shared_account = await _make_account(db_session, owner_a, name="SharedAccount")
        other_account = await _make_account(db_session, owner_b, name="OtherAccount")

        await _make_membership(db_session, shared_account, member, role="observer")
        # other_account has no membership for member

        ids = await accessible_account_ids(db_session, member.id)

        assert own_account.id in ids
        assert shared_account.id in ids
        assert other_account.id not in ids


# =============================================================================
# manager_account_ids
# =============================================================================


class TestManagerAccountIds:
    """Tests for manager_account_ids()"""

    @pytest.mark.asyncio
    async def test_returns_owned_accounts(self, db_session):
        """Happy path: own accounts are always included for write access."""
        from app.services.account_access import manager_account_ids

        owner = await _make_user(db_session, "mgr_owner@example.com")
        account = await _make_account(db_session, owner)

        ids = await manager_account_ids(db_session, owner.id)

        assert account.id in ids

    @pytest.mark.asyncio
    async def test_returns_manager_membership_accounts(self, db_session):
        """Happy path: accounts with manager-role membership are included."""
        from app.services.account_access import manager_account_ids

        owner = await _make_user(db_session, "mgr_owner2@example.com")
        manager = await _make_user(db_session, "mgr_user2@example.com")
        account = await _make_account(db_session, owner)
        await _make_membership(db_session, account, manager, role="manager")

        ids = await manager_account_ids(db_session, manager.id)

        assert account.id in ids

    @pytest.mark.asyncio
    async def test_excludes_observer_role_memberships(self, db_session):
        """Critical: observer-role members cannot get write access."""
        from app.services.account_access import manager_account_ids

        owner = await _make_user(db_session, "mgr_owner3@example.com")
        observer = await _make_user(db_session, "mgr_observer3@example.com")
        account = await _make_account(db_session, owner)
        await _make_membership(db_session, account, observer, role="observer")

        ids = await manager_account_ids(db_session, observer.id)

        assert account.id not in ids

    @pytest.mark.asyncio
    async def test_excludes_expired_manager_memberships(self, db_session):
        """Edge case: expired manager memberships do not grant write access."""
        from app.services.account_access import manager_account_ids

        owner = await _make_user(db_session, "mgr_owner4@example.com")
        manager = await _make_user(db_session, "mgr_user4@example.com")
        account = await _make_account(db_session, owner)
        expired_at = datetime.utcnow() - timedelta(hours=2)
        await _make_membership(db_session, account, manager, role="manager", expires_at=expired_at)

        ids = await manager_account_ids(db_session, manager.id)

        assert account.id not in ids

    @pytest.mark.asyncio
    async def test_excludes_accounts_with_no_relationship(self, db_session):
        """Edge case: unrelated accounts are not included."""
        from app.services.account_access import manager_account_ids

        owner = await _make_user(db_session, "mgr_owner5@example.com")
        outsider = await _make_user(db_session, "mgr_outsider5@example.com")
        account = await _make_account(db_session, owner)

        ids = await manager_account_ids(db_session, outsider.id)

        assert account.id not in ids

    @pytest.mark.asyncio
    async def test_observer_cannot_gain_write_access_even_with_multiple_accounts(self, db_session):
        """Security: observer on one account doesn't get write access to it, only reads."""
        from app.services.account_access import accessible_account_ids, manager_account_ids

        owner = await _make_user(db_session, "mgr_owner6@example.com")
        observer = await _make_user(db_session, "mgr_observer6@example.com")
        account = await _make_account(db_session, owner)
        await _make_membership(db_session, account, observer, role="observer")

        readable_ids = await accessible_account_ids(db_session, observer.id)
        writable_ids = await manager_account_ids(db_session, observer.id)

        # Observer can read but not write
        assert account.id in readable_ids
        assert account.id not in writable_ids

    @pytest.mark.asyncio
    async def test_active_manager_membership_grants_write_access(self, db_session):
        """Happy path: non-expired manager membership is included."""
        from app.services.account_access import manager_account_ids

        owner = await _make_user(db_session, "mgr_owner7@example.com")
        manager = await _make_user(db_session, "mgr_user7@example.com")
        account = await _make_account(db_session, owner)
        future_expiry = datetime.utcnow() + timedelta(days=7)
        await _make_membership(db_session, account, manager, role="manager", expires_at=future_expiry)

        ids = await manager_account_ids(db_session, manager.id)

        assert account.id in ids

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_user_with_no_accounts(self, db_session):
        """Edge case: user with nothing owned or managed gets empty list."""
        from app.services.account_access import manager_account_ids

        nobody = await _make_user(db_session, "nobody@example.com")

        ids = await manager_account_ids(db_session, nobody.id)

        assert ids == []
