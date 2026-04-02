"""
TDD tests for account-member read access.

Verifies that account members (observers / managers) can access the same
read-only data endpoints as the account owner.  Written BEFORE the fix so
they drive the implementation.

Coverage:
  - _accessible_accounts_filter includes owner + member accounts
  - _accessible_accounts_filter excludes unrelated accounts
  - get_portfolio_for_account: member (paper account) returns portfolio
  - get_portfolio_for_account: non-member raises 404 / NotFoundError
  - get_account_balances: member (paper account) returns balances
  - get_account_balances: non-member raises 404 / NotFoundError
  - list_bots: member sees bots linked to the shared account
  - list_bots: non-member sees zero bots
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.exceptions import NotFoundError
from app.models import Account, Bot, User
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


async def _make_paper_account(db, user: User, name: str = "Paper") -> Account:
    """Create a minimal paper trading account (avoids real exchange calls)."""
    acct = Account(
        user_id=user.id,
        name=name,
        type="cex",
        is_active=True,
        is_paper_trading=True,
        paper_balances=json.dumps({"BTC": 0.1, "USD": 1000.0, "USDC": 0.0, "USDT": 0.0, "ETH": 0.5}),
    )
    db.add(acct)
    await db.flush()
    return acct


async def _make_membership(db, account: Account, user: User, role: str = "observer") -> AccountMembership:
    m = AccountMembership(
        account_id=account.id,
        user_id=user.id,
        role=role,
        expires_at=None,
    )
    db.add(m)
    await db.flush()
    return m


async def _make_bot(db, user: User, account: Account, name: str = "TestBot") -> Bot:
    bot = Bot(
        user_id=user.id,
        account_id=account.id,
        name=name,
        product_id="BTC-USD",
        budget_percentage=10.0,
        is_active=False,
        strategy_config={},
    )
    db.add(bot)
    await db.flush()
    return bot


# =============================================================================
# Tests: _accessible_accounts_filter
# =============================================================================


class TestAccessibleAccountsFilter:
    """Unit-test the filter clause against a real (SQLite) DB."""

    @pytest.mark.asyncio
    async def test_owned_account_is_accessible(self, db_session):
        """Owner can always access their own account."""
        from app.routers.accounts_query_router import _accessible_accounts_filter

        owner = await _make_user(db_session, "owner_filt@example.com")
        acct = await _make_paper_account(db_session, owner, "Owner's Account")
        await db_session.commit()

        result = await db_session.execute(
            select(Account).where(_accessible_accounts_filter(owner.id))
        )
        account_ids = [a.id for a in result.scalars().all()]
        assert acct.id in account_ids

    @pytest.mark.asyncio
    async def test_member_account_is_accessible(self, db_session):
        """A member can access accounts they have membership on."""
        from app.routers.accounts_query_router import _accessible_accounts_filter

        owner = await _make_user(db_session, "owner_m@example.com")
        member = await _make_user(db_session, "member_m@example.com")
        acct = await _make_paper_account(db_session, owner, "Shared Account")
        await _make_membership(db_session, acct, member, "observer")
        await db_session.commit()

        result = await db_session.execute(
            select(Account).where(_accessible_accounts_filter(member.id))
        )
        account_ids = [a.id for a in result.scalars().all()]
        assert acct.id in account_ids

    @pytest.mark.asyncio
    async def test_unrelated_account_is_not_accessible(self, db_session):
        """A user with no ownership or membership cannot access the account."""
        from app.routers.accounts_query_router import _accessible_accounts_filter

        owner = await _make_user(db_session, "owner_unrel@example.com")
        stranger = await _make_user(db_session, "stranger@example.com")
        acct = await _make_paper_account(db_session, owner, "Private Account")
        await db_session.commit()

        result = await db_session.execute(
            select(Account).where(_accessible_accounts_filter(stranger.id))
        )
        account_ids = [a.id for a in result.scalars().all()]
        assert acct.id not in account_ids

    @pytest.mark.asyncio
    async def test_expired_membership_is_not_accessible(self, db_session):
        """Expired membership does not grant access."""
        from app.routers.accounts_query_router import _accessible_accounts_filter

        owner = await _make_user(db_session, "owner_exp@example.com")
        member = await _make_user(db_session, "member_exp@example.com")
        acct = await _make_paper_account(db_session, owner, "Expired Share")

        # Expired membership
        m = AccountMembership(
            account_id=acct.id,
            user_id=member.id,
            role="observer",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        db_session.add(m)
        await db_session.commit()

        result = await db_session.execute(
            select(Account).where(_accessible_accounts_filter(member.id))
        )
        account_ids = [a.id for a in result.scalars().all()]
        assert acct.id not in account_ids


# =============================================================================
# Tests: get_portfolio_for_account
# =============================================================================


class TestGetPortfolioForAccountAccess:
    """Member can read portfolio; non-member gets NotFoundError."""

    @pytest.mark.asyncio
    async def test_owner_can_get_portfolio(self, db_session):
        """Account owner always has portfolio access (paper account)."""
        from app.services.account_service import get_portfolio_for_account

        owner = await _make_user(db_session, "owner_port@example.com")
        acct = await _make_paper_account(db_session, owner)
        await db_session.commit()

        _price_module = "app.coinbase_api.public_market_data"
        with patch(f"{_price_module}.get_btc_usd_price", new=AsyncMock(return_value=50000.0)), \
             patch(f"{_price_module}.get_current_price", new=AsyncMock(return_value=0.05)):
            result = await get_portfolio_for_account(db_session, owner, acct.id)

        assert result is not None
        assert "holdings" in result

    @pytest.mark.asyncio
    async def test_member_can_get_portfolio(self, db_session):
        """Observer member can read the account portfolio."""
        from app.services.account_service import get_portfolio_for_account

        owner = await _make_user(db_session, "owner_pmem@example.com")
        member = await _make_user(db_session, "member_pmem@example.com")
        acct = await _make_paper_account(db_session, owner)
        await _make_membership(db_session, acct, member, "observer")
        await db_session.commit()

        _price_module = "app.coinbase_api.public_market_data"
        with patch(f"{_price_module}.get_btc_usd_price", new=AsyncMock(return_value=50000.0)), \
             patch(f"{_price_module}.get_current_price", new=AsyncMock(return_value=0.05)):
            result = await get_portfolio_for_account(db_session, member, acct.id)

        assert result is not None
        assert "holdings" in result

    @pytest.mark.asyncio
    async def test_non_member_cannot_get_portfolio(self, db_session):
        """A user with no access gets NotFoundError."""
        from app.services.account_service import get_portfolio_for_account

        owner = await _make_user(db_session, "owner_pnm@example.com")
        stranger = await _make_user(db_session, "stranger_pnm@example.com")
        acct = await _make_paper_account(db_session, owner)
        await db_session.commit()

        with pytest.raises(NotFoundError):
            await get_portfolio_for_account(db_session, stranger, acct.id)


# =============================================================================
# Tests: get_account_balances
# =============================================================================


class TestGetAccountBalancesAccess:
    """Member can read balances; non-member gets NotFoundError."""

    @pytest.mark.asyncio
    async def test_owner_can_get_balances(self, db_session):
        """Account owner can always read balances (paper account)."""
        from app.services.portfolio_service import get_account_balances

        owner = await _make_user(db_session, "owner_bal@example.com")
        acct = await _make_paper_account(db_session, owner)
        await db_session.commit()

        _price_module = "app.coinbase_api.public_market_data"
        with patch(f"{_price_module}.get_btc_usd_price", new=AsyncMock(return_value=50000.0)), \
             patch(f"{_price_module}.get_current_price", new=AsyncMock(return_value=0.05)):
            result = await get_account_balances(db_session, owner, acct.id)

        assert result is not None
        assert "btc_balance" in result or "BTC" in str(result)

    @pytest.mark.asyncio
    async def test_member_can_get_balances(self, db_session):
        """Observer member can read account balances (paper account)."""
        from app.services.portfolio_service import get_account_balances

        owner = await _make_user(db_session, "owner_bmem@example.com")
        member = await _make_user(db_session, "member_bmem@example.com")
        acct = await _make_paper_account(db_session, owner)
        await _make_membership(db_session, acct, member, "observer")
        await db_session.commit()

        _price_module = "app.coinbase_api.public_market_data"
        with patch(f"{_price_module}.get_btc_usd_price", new=AsyncMock(return_value=50000.0)), \
             patch(f"{_price_module}.get_current_price", new=AsyncMock(return_value=0.05)):
            result = await get_account_balances(db_session, member, acct.id)

        assert result is not None

    @pytest.mark.asyncio
    async def test_non_member_cannot_get_balances(self, db_session):
        """Stranger cannot read another user's account balances."""
        from app.services.portfolio_service import get_account_balances

        owner = await _make_user(db_session, "owner_bnm@example.com")
        stranger = await _make_user(db_session, "stranger_bnm@example.com")
        acct = await _make_paper_account(db_session, owner)
        await db_session.commit()

        with pytest.raises(NotFoundError):
            await get_account_balances(db_session, stranger, acct.id)


# =============================================================================
# Tests: list_bots (bot_crud_router)
# =============================================================================


class TestListBotsAccess:
    """
    Member sees bots linked to their shared account.
    Non-member sees only their own bots (zero if they have none).
    """

    @pytest.mark.asyncio
    async def test_member_sees_shared_account_bots(self, db_session):
        """Observer with membership can see bots on the shared account."""
        from app.services.account_access import accessible_account_ids

        owner = await _make_user(db_session, "owner_bot@example.com")
        member = await _make_user(db_session, "member_bot@example.com")
        acct = await _make_paper_account(db_session, owner, "BotAccount")
        await _make_membership(db_session, acct, member, "observer")
        bot = await _make_bot(db_session, owner, acct)
        await db_session.commit()

        ids = await accessible_account_ids(db_session, member.id)
        assert acct.id in ids

        # The bot belongs to an account the member can access
        bots_result = await db_session.execute(
            select(Bot).where(Bot.account_id.in_(ids))
        )
        bots = bots_result.scalars().all()
        assert any(b.id == bot.id for b in bots)

    @pytest.mark.asyncio
    async def test_non_member_does_not_see_others_bots(self, db_session):
        """User with no membership cannot see another user's bots via accessible_account_ids."""
        from app.services.account_access import accessible_account_ids

        owner = await _make_user(db_session, "owner_nb@example.com")
        stranger = await _make_user(db_session, "stranger_nb@example.com")
        acct = await _make_paper_account(db_session, owner, "PrivateBotAccount")
        await _make_bot(db_session, owner, acct)
        await db_session.commit()

        ids = await accessible_account_ids(db_session, stranger.id)
        assert acct.id not in ids


# =============================================================================
# Tests: list_expense_items (GET /reports/goals/{goal_id}/expenses)
# =============================================================================


async def _make_goal(db, user: User, name: str = "Test Goal") -> "ReportGoal":
    from app.models import ReportGoal
    from datetime import datetime, timedelta
    goal = ReportGoal(
        user_id=user.id,
        name=name,
        target_type="balance",
        target_currency="USD",
        target_value=1000.0,
        time_horizon_months=12,
        start_date=datetime.utcnow(),
        target_date=datetime.utcnow() + timedelta(days=365),
    )
    db.add(goal)
    await db.flush()
    return goal


class TestListExpenseItemsAccess:
    """Observer can list expense items for goals on a shared account."""

    @pytest.mark.asyncio
    async def test_owner_can_list_expenses(self, db_session):
        """Goal owner can list expense items."""
        from app.routers.reports_crud_router import _get_accessible_goal

        owner = await _make_user(db_session, "owner_exp_lst@example.com")
        goal = await _make_goal(db_session, owner)
        await db_session.commit()

        result = await _get_accessible_goal(db_session, goal.id, owner.id)
        assert result.id == goal.id

    @pytest.mark.asyncio
    async def test_observer_can_list_expenses_on_shared_account(self, db_session):
        """Observer can fetch expense goal when they have membership on owner's account."""
        from app.routers.reports_crud_router import _get_accessible_goal

        owner = await _make_user(db_session, "owner_exp_obs@example.com")
        observer = await _make_user(db_session, "observer_exp_obs@example.com")
        acct = await _make_paper_account(db_session, owner)
        await _make_membership(db_session, acct, observer, "observer")
        goal = await _make_goal(db_session, owner)
        await db_session.commit()

        result = await _get_accessible_goal(db_session, goal.id, observer.id)
        assert result.id == goal.id

    @pytest.mark.asyncio
    async def test_stranger_cannot_access_goal(self, db_session):
        """User with no membership gets 404 on another user's goal."""
        from fastapi import HTTPException
        from app.routers.reports_crud_router import _get_accessible_goal

        owner = await _make_user(db_session, "owner_exp_str@example.com")
        stranger = await _make_user(db_session, "stranger_exp_str@example.com")
        goal = await _make_goal(db_session, owner)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await _get_accessible_goal(db_session, goal.id, stranger.id)
        assert exc_info.value.status_code == 404


# =============================================================================
# Tests: get_report (GET /reports/{report_id})
# =============================================================================


async def _make_report(db, user: User) -> "Report":
    from app.models import Report
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    report = Report(
        user_id=user.id,
        period_start=now - timedelta(days=30),
        period_end=now,
        periodicity="monthly",
        delivery_status="manual",
    )
    db.add(report)
    await db.flush()
    return report


class TestGetReportAccess:
    """Observer can view individual report entries from a shared account."""

    @pytest.mark.asyncio
    async def test_owner_can_get_report(self, db_session):
        """Report owner can fetch their own report."""
        from app.routers.reports_crud_router import _get_accessible_report

        owner = await _make_user(db_session, "owner_rep@example.com")
        report = await _make_report(db_session, owner)
        await db_session.commit()

        result = await _get_accessible_report(db_session, report.id, owner.id)
        assert result.id == report.id

    @pytest.mark.asyncio
    async def test_observer_can_get_report_on_shared_account(self, db_session):
        """Observer can fetch a report owned by the account they observe."""
        from app.routers.reports_crud_router import _get_accessible_report

        owner = await _make_user(db_session, "owner_rep_obs@example.com")
        observer = await _make_user(db_session, "observer_rep_obs@example.com")
        acct = await _make_paper_account(db_session, owner)
        await _make_membership(db_session, acct, observer, "observer")
        report = await _make_report(db_session, owner)
        await db_session.commit()

        result = await _get_accessible_report(db_session, report.id, observer.id)
        assert result.id == report.id

    @pytest.mark.asyncio
    async def test_stranger_cannot_get_report(self, db_session):
        """Stranger gets 404 on another user's report."""
        from fastapi import HTTPException
        from app.routers.reports_crud_router import _get_accessible_report

        owner = await _make_user(db_session, "owner_rep_str@example.com")
        stranger = await _make_user(db_session, "stranger_rep_str@example.com")
        report = await _make_report(db_session, owner)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await _get_accessible_report(db_session, report.id, stranger.id)
        assert exc_info.value.status_code == 404
