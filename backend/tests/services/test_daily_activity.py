"""
Tests for get_daily_activity — aggregates closed positions and transfers
into daily activity records for chart markers.

Tests cover:
- Happy path: positions + transfers produce correct aggregated records
- Same-day aggregation: multiple items on same day are grouped
- Line assignment: BTC-pair trades → btc line, USD-pair trades → usd line
- Transfer line assignment: BTC deposits → btc, USD deposits → usd
- Empty result when no data in range
- Paper trading exclusion by default
"""

from datetime import datetime, timedelta

import pytest

from app.models import Account, AccountTransfer, Position, User
from app.services.account_snapshot_service import get_daily_activity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user_and_account(db, paper_trading=False):
    """Create a user + account for testing."""
    user = User(
        email="test@example.com",
        hashed_password="fakehash",
    )
    db.add(user)
    await db.flush()

    account = Account(
        user_id=user.id,
        name="Test Account",
        type="cex",
        is_active=True,
        is_paper_trading=paper_trading,
    )
    db.add(account)
    await db.flush()
    return user, account


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetDailyActivity:
    """Tests for get_daily_activity service function."""

    @pytest.mark.asyncio
    async def test_happy_path_positions_and_transfers(self, db_session):
        """Positions and transfers produce correct aggregated records."""
        user, account = await _seed_user_and_account(db_session)
        now = datetime.utcnow()

        # Add a winning trade (USD pair)
        pos = Position(
            user_id=user.id,
            account_id=account.id,
            product_id="ETH-USD",
            status="closed",
            opened_at=now - timedelta(days=2),
            closed_at=now - timedelta(days=1),
            profit_usd=50.0,
            profit_quote=50.0,
        )
        db_session.add(pos)

        # Add a deposit
        transfer = AccountTransfer(
            user_id=user.id,
            account_id=account.id,
            transfer_type="deposit",
            amount=100.0,
            currency="USD",
            amount_usd=100.0,
            occurred_at=now - timedelta(days=1),
        )
        db_session.add(transfer)
        await db_session.flush()

        result = await get_daily_activity(db_session, user.id, days=30)

        assert len(result) == 2
        # One trade_win and one deposit
        categories = {r["category"] for r in result}
        assert "trade_win" in categories
        assert "deposit" in categories

        # Check the trade_win record
        win = next(r for r in result if r["category"] == "trade_win")
        assert win["line"] == "usd"
        assert win["amount"] == 50.0
        assert win["count"] == 1

        # Check the deposit record
        dep = next(r for r in result if r["category"] == "deposit")
        assert dep["line"] == "usd"
        assert dep["amount"] == 100.0
        assert dep["count"] == 1

    @pytest.mark.asyncio
    async def test_same_day_aggregation(self, db_session):
        """Two BTC wins on the same day → single record with count: 2."""
        user, account = await _seed_user_and_account(db_session)
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)

        for profit in [0.001, 0.002]:
            pos = Position(
                user_id=user.id,
                account_id=account.id,
                product_id="ETH-BTC",
                status="closed",
                opened_at=now - timedelta(days=3),
                closed_at=yesterday,
                profit_usd=50.0,
                profit_quote=profit,
            )
            db_session.add(pos)
        await db_session.flush()

        result = await get_daily_activity(db_session, user.id, days=30)

        assert len(result) == 1
        assert result[0]["line"] == "btc"
        assert result[0]["category"] == "trade_win"
        assert result[0]["count"] == 2
        assert result[0]["amount"] == pytest.approx(0.003)

    @pytest.mark.asyncio
    async def test_line_assignment_usd_pair(self, db_session):
        """ADA-USD trade → usd line."""
        user, account = await _seed_user_and_account(db_session)
        now = datetime.utcnow()

        pos = Position(
            user_id=user.id,
            account_id=account.id,
            product_id="ADA-USD",
            status="closed",
            opened_at=now - timedelta(days=3),
            closed_at=now - timedelta(days=1),
            profit_usd=-20.0,
            profit_quote=-20.0,
        )
        db_session.add(pos)
        await db_session.flush()

        result = await get_daily_activity(db_session, user.id, days=30)

        assert len(result) == 1
        assert result[0]["line"] == "usd"
        assert result[0]["category"] == "trade_loss"
        assert result[0]["amount"] == -20.0

    @pytest.mark.asyncio
    async def test_line_assignment_btc_pair(self, db_session):
        """ETH-BTC trade → btc line, uses profit_quote."""
        user, account = await _seed_user_and_account(db_session)
        now = datetime.utcnow()

        pos = Position(
            user_id=user.id,
            account_id=account.id,
            product_id="ETH-BTC",
            status="closed",
            opened_at=now - timedelta(days=3),
            closed_at=now - timedelta(days=1),
            profit_usd=100.0,
            profit_quote=0.005,
        )
        db_session.add(pos)
        await db_session.flush()

        result = await get_daily_activity(db_session, user.id, days=30)

        assert len(result) == 1
        assert result[0]["line"] == "btc"
        assert result[0]["category"] == "trade_win"
        assert result[0]["amount"] == pytest.approx(0.005)

    @pytest.mark.asyncio
    async def test_btc_deposit_on_btc_line(self, db_session):
        """BTC deposit → btc line, uses raw amount."""
        user, account = await _seed_user_and_account(db_session)
        now = datetime.utcnow()

        transfer = AccountTransfer(
            user_id=user.id,
            account_id=account.id,
            transfer_type="deposit",
            amount=0.5,
            currency="BTC",
            amount_usd=50000.0,
            occurred_at=now - timedelta(days=1),
        )
        db_session.add(transfer)
        await db_session.flush()

        result = await get_daily_activity(db_session, user.id, days=30)

        assert len(result) == 1
        assert result[0]["line"] == "btc"
        assert result[0]["category"] == "deposit"
        assert result[0]["amount"] == 0.5

    @pytest.mark.asyncio
    async def test_usd_withdrawal(self, db_session):
        """USD withdrawal → usd line, withdrawal category."""
        user, account = await _seed_user_and_account(db_session)
        now = datetime.utcnow()

        transfer = AccountTransfer(
            user_id=user.id,
            account_id=account.id,
            transfer_type="withdrawal",
            amount=500.0,
            currency="USD",
            amount_usd=500.0,
            occurred_at=now - timedelta(days=1),
        )
        db_session.add(transfer)
        await db_session.flush()

        result = await get_daily_activity(db_session, user.id, days=30)

        assert len(result) == 1
        assert result[0]["category"] == "withdrawal"
        assert result[0]["line"] == "usd"
        assert result[0]["amount"] == 500.0

    @pytest.mark.asyncio
    async def test_empty_result_no_data(self, db_session):
        """Empty list when no positions or transfers in range."""
        user, account = await _seed_user_and_account(db_session)

        result = await get_daily_activity(db_session, user.id, days=30)
        assert result == []

    @pytest.mark.asyncio
    async def test_paper_trading_excluded_by_default(self, db_session):
        """Paper trading positions excluded by default."""
        user, account = await _seed_user_and_account(db_session, paper_trading=True)
        now = datetime.utcnow()

        pos = Position(
            user_id=user.id,
            account_id=account.id,
            product_id="ETH-USD",
            status="closed",
            opened_at=now - timedelta(days=3),
            closed_at=now - timedelta(days=1),
            profit_usd=50.0,
            profit_quote=50.0,
        )
        db_session.add(pos)
        await db_session.flush()

        # Default: exclude paper trading
        result = await get_daily_activity(db_session, user.id, days=30)
        assert result == []

        # Explicitly include paper trading
        result = await get_daily_activity(
            db_session, user.id, days=30, include_paper_trading=True,
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_outside_range_excluded(self, db_session):
        """Positions/transfers outside the day range are excluded."""
        user, account = await _seed_user_and_account(db_session)
        now = datetime.utcnow()

        # Position closed 60 days ago — outside 30-day range
        pos = Position(
            user_id=user.id,
            account_id=account.id,
            product_id="ETH-USD",
            status="closed",
            opened_at=now - timedelta(days=90),
            closed_at=now - timedelta(days=60),
            profit_usd=50.0,
            profit_quote=50.0,
        )
        db_session.add(pos)
        await db_session.flush()

        result = await get_daily_activity(db_session, user.id, days=30)
        assert result == []

    @pytest.mark.asyncio
    async def test_zero_profit_excluded(self, db_session):
        """Positions with zero profit are excluded (break-even)."""
        user, account = await _seed_user_and_account(db_session)
        now = datetime.utcnow()

        pos = Position(
            user_id=user.id,
            account_id=account.id,
            product_id="ETH-USD",
            status="closed",
            opened_at=now - timedelta(days=3),
            closed_at=now - timedelta(days=1),
            profit_usd=0.0,
            profit_quote=0.0,
        )
        db_session.add(pos)
        await db_session.flush()

        result = await get_daily_activity(db_session, user.id, days=30)
        assert result == []

    @pytest.mark.asyncio
    async def test_account_id_filter(self, db_session):
        """When account_id is specified, only that account's data is returned."""
        user, account = await _seed_user_and_account(db_session)
        now = datetime.utcnow()

        # Create a second account
        account2 = Account(
            user_id=user.id,
            name="Other Account",
            type="cex",
            is_active=True,
            is_paper_trading=False,
        )
        db_session.add(account2)
        await db_session.flush()

        # Position on account 1
        pos1 = Position(
            user_id=user.id,
            account_id=account.id,
            product_id="ETH-USD",
            status="closed",
            opened_at=now - timedelta(days=3),
            closed_at=now - timedelta(days=1),
            profit_usd=50.0,
            profit_quote=50.0,
        )
        # Position on account 2
        pos2 = Position(
            user_id=user.id,
            account_id=account2.id,
            product_id="ETH-USD",
            status="closed",
            opened_at=now - timedelta(days=3),
            closed_at=now - timedelta(days=1),
            profit_usd=100.0,
            profit_quote=100.0,
        )
        db_session.add_all([pos1, pos2])
        await db_session.flush()

        # All accounts — same day/line/category so aggregated into 1 record
        result_all = await get_daily_activity(db_session, user.id, days=30)
        assert len(result_all) == 1
        assert result_all[0]["amount"] == 150.0
        assert result_all[0]["count"] == 2

        # Filter to account 1 only
        result_one = await get_daily_activity(
            db_session, user.id, days=30, account_id=account.id,
        )
        assert len(result_one) == 1
        assert result_one[0]["amount"] == 50.0
        assert result_one[0]["count"] == 1
