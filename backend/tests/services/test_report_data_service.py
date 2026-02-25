"""
Tests for backend/app/services/report_data_service.py

Covers:
- gather_report_data: main aggregation (positions, transfers, goals)
- get_prior_period_data: fetching prior report data
- compute_goal_progress: balance/profit/income goal progress
- _get_account_value_at: snapshot lookup (single + all accounts)
"""

import pytest
from datetime import datetime
from unittest.mock import patch

from app.models import (
    Account, AccountTransfer, AccountValueSnapshot, Bot, Position,
    Report, ReportGoal, User,
)
from app.services.report_data_service import (
    gather_report_data,
    get_prior_period_data,
    compute_goal_progress,
    _get_account_value_at,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(db_session, user_id=1):
    user = User(id=user_id, email="test@example.com", hashed_password="x")
    db_session.add(user)
    return user


def _make_account(db_session, user_id=1, account_id=1, is_active=True,
                  is_paper=False):
    acct = Account(
        id=account_id, user_id=user_id, name="Test Account", type="cex",
        is_active=is_active, is_paper_trading=is_paper,
    )
    db_session.add(acct)
    return acct


def _make_snapshot(db_session, user_id=1, account_id=1,
                   date=None, usd=1000.0, btc=0.02,
                   usd_portion=None, btc_portion=None,
                   unrealized_pnl_usd=None, unrealized_pnl_btc=None,
                   btc_usd_price=None):
    snap = AccountValueSnapshot(
        user_id=user_id, account_id=account_id,
        snapshot_date=date or datetime(2025, 1, 15),
        total_value_usd=usd, total_value_btc=btc,
        usd_portion_usd=usd_portion, btc_portion_btc=btc_portion,
        unrealized_pnl_usd=unrealized_pnl_usd,
        unrealized_pnl_btc=unrealized_pnl_btc,
        btc_usd_price=btc_usd_price,
    )
    db_session.add(snap)
    return snap


def _make_position(db_session, user_id=1, account_id=1, bot_id=None,
                   product_id="ETH-USD", profit_usd=10.0, profit_quote=0.0,
                   status="closed", closed_at=None):
    pos = Position(
        user_id=user_id, account_id=account_id, bot_id=bot_id,
        product_id=product_id, status=status,
        profit_usd=profit_usd, profit_quote=profit_quote,
        closed_at=closed_at or datetime(2025, 1, 10),
        opened_at=datetime(2025, 1, 5),
    )
    db_session.add(pos)
    return pos


def _make_bot(db_session, bot_id=1, user_id=1, name="TestBot",
              strategy_type="grid", product_id="ETH-USD"):
    bot = Bot(
        id=bot_id, user_id=user_id, name=name,
        strategy_type=strategy_type, product_id=product_id,
        strategy_config={"upper": 100, "lower": 50},
    )
    db_session.add(bot)
    return bot


def _make_transfer(db_session, user_id=1, account_id=1,
                   transfer_type="deposit", amount_usd=100.0,
                   occurred_at=None, currency="USD", source="coinbase_api",
                   original_type=None):
    t = AccountTransfer(
        user_id=user_id, account_id=account_id,
        transfer_type=transfer_type, amount=amount_usd,
        amount_usd=amount_usd, currency=currency,
        occurred_at=occurred_at or datetime(2025, 1, 10),
        source=source, original_type=original_type,
    )
    db_session.add(t)
    return t


def _make_goal(user_id=1, target_type="balance", target_currency="USD",
               target_value=10000.0, income_period=None,
               expense_period=None, tax_pct=0):
    goal = ReportGoal(
        id=1, user_id=user_id, name="Test Goal",
        target_type=target_type, target_currency=target_currency,
        target_value=target_value,
        income_period=income_period,
        expense_period=expense_period,
        tax_withholding_pct=tax_pct,
        time_horizon_months=12,
        start_date=datetime(2024, 1, 1),
        target_date=datetime(2026, 1, 1),
    )
    return goal


# ===========================================================================
# Tests for _get_account_value_at
# ===========================================================================


class TestGetAccountValueAt:
    """Tests for _get_account_value_at() snapshot lookup."""

    @pytest.mark.asyncio
    async def test_single_account_returns_closest_snapshot(self, db_session):
        """Happy path: returns latest snapshot on or before at_date."""
        _make_user(db_session)
        _make_account(db_session)
        _make_snapshot(db_session, date=datetime(2025, 1, 10), usd=900, btc=0.01)
        _make_snapshot(db_session, date=datetime(2025, 1, 15), usd=1000, btc=0.02)
        _make_snapshot(db_session, date=datetime(2025, 1, 20), usd=1100, btc=0.03)
        await db_session.flush()

        result = await _get_account_value_at(
            db_session, user_id=1, account_id=1,
            at_date=datetime(2025, 1, 16),
        )
        assert result["usd"] == 1000.0
        assert result["btc"] == 0.02

    @pytest.mark.asyncio
    async def test_no_snapshot_returns_zeros(self, db_session):
        """Edge case: no snapshots exist, returns zeros."""
        _make_user(db_session)
        _make_account(db_session)
        await db_session.flush()

        result = await _get_account_value_at(
            db_session, user_id=1, account_id=1,
            at_date=datetime(2025, 1, 1),
        )
        assert result["usd"] == 0.0
        assert result["btc"] == 0.0

    @pytest.mark.asyncio
    async def test_all_accounts_sums_latest_per_account(self, db_session):
        """Happy path: account_id=None sums latest snapshot per active account."""
        _make_user(db_session)
        _make_account(db_session, account_id=1, is_active=True)
        _make_account(db_session, account_id=2, is_active=True)
        _make_snapshot(db_session, account_id=1, date=datetime(2025, 1, 15),
                       usd=1000, btc=0.02)
        _make_snapshot(db_session, account_id=2, date=datetime(2025, 1, 15),
                       usd=500, btc=0.01)
        await db_session.flush()

        result = await _get_account_value_at(
            db_session, user_id=1, account_id=None,
            at_date=datetime(2025, 1, 16),
        )
        assert result["usd"] == pytest.approx(1500.0)
        assert result["btc"] == pytest.approx(0.03)

    @pytest.mark.asyncio
    async def test_excludes_paper_and_inactive_accounts(self, db_session):
        """Edge case: paper trading and inactive accounts are excluded from sum."""
        _make_user(db_session)
        _make_account(db_session, account_id=1, is_active=True, is_paper=False)
        _make_account(db_session, account_id=2, is_active=False, is_paper=False)
        _make_account(db_session, account_id=3, is_active=True, is_paper=True)
        _make_snapshot(db_session, account_id=1, date=datetime(2025, 1, 15),
                       usd=1000, btc=0.02)
        _make_snapshot(db_session, account_id=2, date=datetime(2025, 1, 15),
                       usd=500, btc=0.01)
        _make_snapshot(db_session, account_id=3, date=datetime(2025, 1, 15),
                       usd=300, btc=0.005)
        await db_session.flush()

        result = await _get_account_value_at(
            db_session, user_id=1, account_id=None,
            at_date=datetime(2025, 1, 16),
        )
        # Only account_id=1 should be included
        assert result["usd"] == pytest.approx(1000.0)
        assert result["btc"] == pytest.approx(0.02)


# ===========================================================================
# Tests for gather_report_data
# ===========================================================================


class TestGatherReportData:
    """Tests for gather_report_data() main aggregation."""

    @pytest.mark.asyncio
    async def test_basic_report_data_with_trades(self, db_session):
        """Happy path: gathers trade stats, account values, and transfers."""
        _make_user(db_session)
        _make_account(db_session)
        # Snapshots for start and end
        _make_snapshot(db_session, date=datetime(2025, 1, 1), usd=5000, btc=0.1)
        _make_snapshot(db_session, date=datetime(2025, 1, 31), usd=5500, btc=0.11)
        # Closed positions
        _make_position(db_session, profit_usd=50.0,
                       closed_at=datetime(2025, 1, 10))
        _make_position(db_session, profit_usd=-20.0,
                       closed_at=datetime(2025, 1, 15))
        _make_position(db_session, profit_usd=30.0,
                       closed_at=datetime(2025, 1, 20))
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        assert data["total_trades"] == 3
        assert data["winning_trades"] == 2
        assert data["losing_trades"] == 1
        assert data["win_rate"] == pytest.approx(66.7, abs=0.1)
        assert data["period_profit_usd"] == pytest.approx(60.0)
        assert data["account_value_usd"] == pytest.approx(5500.0)
        assert data["period_start_value_usd"] == pytest.approx(5000.0)

    @pytest.mark.asyncio
    async def test_no_trades_returns_zero_stats(self, db_session):
        """Edge case: no closed positions in period."""
        _make_user(db_session)
        _make_account(db_session)
        _make_snapshot(db_session, date=datetime(2025, 1, 1), usd=5000, btc=0.1)
        _make_snapshot(db_session, date=datetime(2025, 1, 31), usd=5000, btc=0.1)
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        assert data["total_trades"] == 0
        assert data["winning_trades"] == 0
        assert data["losing_trades"] == 0
        assert data["win_rate"] == 0.0
        assert data["period_profit_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_transfers_included_in_data(self, db_session):
        """Happy path: deposits and withdrawals are aggregated."""
        _make_user(db_session)
        _make_account(db_session)
        _make_snapshot(db_session, date=datetime(2025, 1, 1), usd=5000, btc=0.1)
        _make_snapshot(db_session, date=datetime(2025, 1, 31), usd=5200, btc=0.1)
        _make_transfer(db_session, transfer_type="deposit", amount_usd=300.0,
                       occurred_at=datetime(2025, 1, 5))
        _make_transfer(db_session, transfer_type="withdrawal", amount_usd=100.0,
                       occurred_at=datetime(2025, 1, 20))
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        assert data["total_deposits_usd"] == pytest.approx(300.0)
        assert data["total_withdrawals_usd"] == pytest.approx(100.0)
        assert data["net_deposits_usd"] == pytest.approx(200.0)
        assert data["transfer_count"] == 2
        assert data["deposits_source"] == "transfers"

    @pytest.mark.asyncio
    async def test_implied_deposits_when_no_transfers(self, db_session):
        """Edge case: no transfer records uses implied net deposits."""
        _make_user(db_session)
        _make_account(db_session)
        # Account went from 5000 to 5500 with no trades = $500 implied deposit
        _make_snapshot(db_session, date=datetime(2025, 1, 1), usd=5000, btc=0.1)
        _make_snapshot(db_session, date=datetime(2025, 1, 31), usd=5500, btc=0.1)
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        assert data["net_deposits_usd"] == pytest.approx(500.0)
        assert data["deposits_source"] == "implied"

    @pytest.mark.asyncio
    async def test_bot_strategies_collected(self, db_session):
        """Happy path: bot strategy info collected for closed positions."""
        _make_user(db_session)
        _make_account(db_session)
        _make_snapshot(db_session, date=datetime(2025, 1, 1), usd=5000, btc=0.1)
        _make_snapshot(db_session, date=datetime(2025, 1, 31), usd=5100, btc=0.1)
        _make_bot(db_session, bot_id=1)
        _make_position(db_session, bot_id=1, profit_usd=50.0,
                       closed_at=datetime(2025, 1, 10))
        _make_position(db_session, bot_id=1, profit_usd=-10.0,
                       closed_at=datetime(2025, 1, 15))
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        assert len(data["bot_strategies"]) == 1
        strat = data["bot_strategies"][0]
        assert strat["name"] == "TestBot"
        assert strat["strategy_type"] == "grid"
        assert strat["trades_in_period"] == 2
        assert strat["wins_in_period"] == 1

    @pytest.mark.asyncio
    async def test_account_id_filter(self, db_session):
        """Edge case: positions outside target account are excluded."""
        _make_user(db_session)
        _make_account(db_session, account_id=1)
        _make_account(db_session, account_id=2)
        _make_snapshot(db_session, account_id=1, date=datetime(2025, 1, 1),
                       usd=5000, btc=0.1)
        _make_snapshot(db_session, account_id=1, date=datetime(2025, 1, 31),
                       usd=5100, btc=0.1)
        # Position on account 1
        _make_position(db_session, account_id=1, profit_usd=50.0,
                       closed_at=datetime(2025, 1, 10))
        # Position on account 2 (should be excluded)
        _make_position(db_session, account_id=2, profit_usd=999.0,
                       closed_at=datetime(2025, 1, 10))
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        assert data["total_trades"] == 1
        assert data["period_profit_usd"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_transfer_records_sorted_newest_first(self, db_session):
        """Verify transfer_records are sorted by date descending."""
        _make_user(db_session)
        _make_account(db_session)
        _make_snapshot(db_session, date=datetime(2025, 1, 1), usd=5000, btc=0.1)
        _make_snapshot(db_session, date=datetime(2025, 1, 31), usd=5000, btc=0.1)
        _make_transfer(db_session, transfer_type="deposit", amount_usd=100.0,
                       occurred_at=datetime(2025, 1, 5))
        _make_transfer(db_session, transfer_type="deposit", amount_usd=200.0,
                       occurred_at=datetime(2025, 1, 20))
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        records = data["transfer_records"]
        assert len(records) == 2
        assert records[0]["date"] == "2025-01-20"
        assert records[1]["date"] == "2025-01-05"


# ===========================================================================
# Tests for get_prior_period_data
# ===========================================================================


class TestGetPriorPeriodData:
    """Tests for get_prior_period_data()."""

    @pytest.mark.asyncio
    async def test_returns_prior_report_data(self, db_session):
        """Happy path: returns report_data from most recent prior report."""
        _make_user(db_session)
        prior_data = {"period_profit_usd": 100.0, "total_trades": 5}
        report = Report(
            user_id=1, schedule_id=1,
            period_start=datetime(2024, 12, 1),
            period_end=datetime(2024, 12, 31),
            periodicity="monthly",
            report_data=prior_data,
        )
        db_session.add(report)
        await db_session.flush()

        result = await get_prior_period_data(
            db_session, schedule_id=1,
            current_period_start=datetime(2025, 1, 1),
        )

        assert result is not None
        assert result["period_profit_usd"] == 100.0
        assert result["total_trades"] == 5

    @pytest.mark.asyncio
    async def test_returns_none_when_no_prior_report(self, db_session):
        """Edge case: no prior report exists."""
        _make_user(db_session)
        await db_session.flush()

        result = await get_prior_period_data(
            db_session, schedule_id=1,
            current_period_start=datetime(2025, 1, 1),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_prior_report_has_no_data(self, db_session):
        """Edge case: prior report exists but report_data is None."""
        _make_user(db_session)
        report = Report(
            user_id=1, schedule_id=1,
            period_start=datetime(2024, 12, 1),
            period_end=datetime(2024, 12, 31),
            periodicity="monthly",
            report_data=None,
        )
        db_session.add(report)
        await db_session.flush()

        result = await get_prior_period_data(
            db_session, schedule_id=1,
            current_period_start=datetime(2025, 1, 1),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_most_recent_prior_report(self, db_session):
        """Returns the most recent report, not an older one."""
        _make_user(db_session)
        old = Report(
            user_id=1, schedule_id=1,
            period_start=datetime(2024, 11, 1),
            period_end=datetime(2024, 11, 30),
            periodicity="monthly",
            report_data={"profit": 50},
        )
        recent = Report(
            user_id=1, schedule_id=1,
            period_start=datetime(2024, 12, 1),
            period_end=datetime(2024, 12, 31),
            periodicity="monthly",
            report_data={"profit": 100},
        )
        db_session.add_all([old, recent])
        await db_session.flush()

        result = await get_prior_period_data(
            db_session, schedule_id=1,
            current_period_start=datetime(2025, 1, 1),
        )
        assert result["profit"] == 100


# ===========================================================================
# Tests for compute_goal_progress
# ===========================================================================


class TestComputeGoalProgress:
    """Tests for compute_goal_progress() with balance/profit goal types."""

    @pytest.mark.asyncio
    async def test_balance_goal_usd_progress(self, db_session):
        """Happy path: USD balance goal shows correct progress %."""
        goal = _make_goal(target_type="balance", target_currency="USD",
                          target_value=10000.0)
        result = await compute_goal_progress(
            db_session, goal,
            current_usd=5000.0, current_btc=0.1,
            period_profit_usd=100.0, period_profit_btc=0.002,
        )

        assert result["goal_id"] == 1
        assert result["target_type"] == "balance"
        assert result["progress_pct"] == pytest.approx(50.0)
        assert result["current_value"] == pytest.approx(5000.0)

    @pytest.mark.asyncio
    async def test_balance_goal_btc_progress(self, db_session):
        """Happy path: BTC balance goal uses btc value."""
        goal = _make_goal(target_type="balance", target_currency="BTC",
                          target_value=1.0)
        result = await compute_goal_progress(
            db_session, goal,
            current_usd=50000.0, current_btc=0.5,
            period_profit_usd=100.0, period_profit_btc=0.001,
        )

        assert result["progress_pct"] == pytest.approx(50.0)
        assert result["current_value"] == pytest.approx(0.5)
        assert result["target_currency"] == "BTC"

    @pytest.mark.asyncio
    async def test_profit_goal_progress(self, db_session):
        """Happy path: profit goal uses period profit for progress."""
        goal = _make_goal(target_type="profit", target_currency="USD",
                          target_value=200.0)
        result = await compute_goal_progress(
            db_session, goal,
            current_usd=5000.0, current_btc=0.1,
            period_profit_usd=150.0, period_profit_btc=0.003,
        )

        assert result["progress_pct"] == pytest.approx(75.0)
        assert result["current_value"] == pytest.approx(150.0)

    @pytest.mark.asyncio
    async def test_zero_target_returns_zero_progress(self, db_session):
        """Edge case: target_value of 0 avoids division by zero."""
        goal = _make_goal(target_type="balance", target_value=0.0)
        result = await compute_goal_progress(
            db_session, goal,
            current_usd=5000.0, current_btc=0.1,
            period_profit_usd=0.0, period_profit_btc=0.0,
        )

        assert result["progress_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_progress_capped_at_100(self, db_session):
        """Edge case: progress is capped at 100%."""
        goal = _make_goal(target_type="balance", target_value=1000.0)
        result = await compute_goal_progress(
            db_session, goal,
            current_usd=2000.0, current_btc=0.1,
            period_profit_usd=0.0, period_profit_btc=0.0,
        )

        assert result["progress_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_on_track_when_progress_exceeds_time(self, db_session):
        """on_track is True when progress% >= time elapsed%."""
        goal = _make_goal(target_type="balance", target_value=10000.0)
        # Goal: start_date=2024-01-01, target_date=2026-01-01 (2 years)
        # Mock utcnow to mid-point (50% time elapsed)
        with patch("app.services.report_data_service.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2025, 1, 1)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await compute_goal_progress(
                db_session, goal,
                current_usd=6000.0, current_btc=0.1,
                period_profit_usd=0.0, period_profit_btc=0.0,
            )

        # 60% progress vs ~50% time elapsed => on track
        assert result["on_track"] is True

    @pytest.mark.asyncio
    async def test_income_goal_delegates(self, db_session):
        """Income goal type calls _compute_income_goal_progress."""
        _make_user(db_session)
        goal = _make_goal(target_type="income", target_currency="USD",
                          target_value=500.0, income_period="monthly")
        # Create a closed position for income calculation
        _make_position(db_session, profit_usd=100.0,
                       closed_at=datetime(2025, 1, 10))
        await db_session.flush()

        result = await compute_goal_progress(
            db_session, goal,
            current_usd=5000.0, current_btc=0.1,
            period_profit_usd=100.0, period_profit_btc=0.001,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
        )

        assert result["target_type"] == "income"
        assert "income_period" in result
        assert "current_daily_income" in result
        assert "projected_income_linear" in result

    @pytest.mark.asyncio
    async def test_income_goal_no_trades_zero_projection(self, db_session):
        """Income goal with no trades projects zero income."""
        _make_user(db_session)
        goal = _make_goal(target_type="income", target_currency="USD",
                          target_value=500.0, income_period="monthly")
        await db_session.flush()

        result = await compute_goal_progress(
            db_session, goal,
            current_usd=5000.0, current_btc=0.1,
            period_profit_usd=0.0, period_profit_btc=0.0,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
        )

        assert result["current_daily_income"] == 0.0
        assert result["projected_income_linear"] == 0.0
        assert result["on_track"] is False

    @pytest.mark.asyncio
    async def test_income_goal_filters_by_account_id(self, db_session):
        """Income goal only counts positions from the specified account."""
        _make_user(db_session)
        # Account 1 (live): $100 profit
        _make_position(db_session, account_id=1, profit_usd=100.0,
                       closed_at=datetime(2025, 1, 10))
        # Account 2 (paper): $50 profit — should be excluded
        _make_position(db_session, account_id=2, profit_usd=50.0,
                       closed_at=datetime(2025, 1, 15))
        await db_session.flush()

        goal = _make_goal(target_type="income", target_currency="USD",
                          target_value=500.0, income_period="monthly")

        # With account_id=1: only $100 profit
        result = await compute_goal_progress(
            db_session, goal,
            current_usd=5000.0, current_btc=0.1,
            period_profit_usd=100.0, period_profit_btc=0.0,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            account_id=1,
        )
        assert result["sample_trades"] == 1
        # daily = 100/30, projected = (100/30)*30 = 100
        assert abs(result["projected_income_linear"] - 100.0) < 0.01

        # Without account_id: both accounts ($150 total)
        result_all = await compute_goal_progress(
            db_session, goal,
            current_usd=5000.0, current_btc=0.1,
            period_profit_usd=150.0, period_profit_btc=0.0,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
        )
        assert result_all["sample_trades"] == 2
        assert abs(result_all["projected_income_linear"] - 150.0) < 0.01

    @pytest.mark.asyncio
    async def test_expenses_goal_filters_by_account_id(self, db_session):
        """Expenses goal only counts positions from the specified account."""
        _make_user(db_session)
        # Account 1 (live): $200 profit
        _make_position(db_session, account_id=1, profit_usd=200.0,
                       closed_at=datetime(2025, 1, 10))
        # Account 2 (paper): $300 profit — should be excluded
        _make_position(db_session, account_id=2, profit_usd=300.0,
                       closed_at=datetime(2025, 1, 15))
        await db_session.flush()

        goal = _make_goal(target_type="expenses", target_currency="USD",
                          target_value=1000.0, expense_period="monthly",
                          tax_pct=0)

        with patch(
            "app.services.expense_service.compute_expense_coverage"
        ) as mock_cov:
            mock_cov.return_value = {
                "coverage_pct": 50.0,
                "income_after_tax": 200.0,
                "shortfall": 200.0,
                "total_expenses": 400.0,
            }
            result = await compute_goal_progress(
                db_session, goal,
                current_usd=5000.0, current_btc=0.1,
                period_profit_usd=200.0, period_profit_btc=0.0,
                period_start=datetime(2025, 1, 1),
                period_end=datetime(2025, 1, 31),
                account_id=1,
            )

        assert result["sample_trades"] == 1
        # daily = 200/30, projected = (200/30)*30 = 200
        assert abs(result["projected_income"] - 200.0) < 0.01

    @pytest.mark.asyncio
    async def test_expenses_goal_delegates(self, db_session):
        """Expenses goal type calls _compute_expenses_goal_progress."""
        _make_user(db_session)
        goal = _make_goal(target_type="expenses", target_currency="USD",
                          target_value=1000.0, expense_period="monthly",
                          tax_pct=25)
        await db_session.flush()

        with patch(
            "app.services.expense_service.compute_expense_coverage"
        ) as mock_cov:
            mock_cov.return_value = {
                "coverage_pct": 80.0,
                "income_after_tax": 400.0,
                "shortfall": 100.0,
                "total_expenses": 500.0,
            }
            result = await compute_goal_progress(
                db_session, goal,
                current_usd=5000.0, current_btc=0.1,
                period_profit_usd=0.0, period_profit_btc=0.0,
                period_start=datetime(2025, 1, 1),
                period_end=datetime(2025, 1, 31),
            )

        assert result["target_type"] == "expenses"
        assert result["expense_period"] == "monthly"
        assert result["tax_withholding_pct"] == 25


# ===========================================================================
# Tests for native-currency accounting
# ===========================================================================


class TestNativeCurrencyAccounting:
    """Tests for native-currency deposit/withdrawal accounting."""

    @pytest.mark.asyncio
    async def test_btc_price_drop_no_phantom_withdrawal(self, db_session):
        """BTC price drops $33k with no trades or transfers — no phantom
        withdrawal, market_value_effect explains the USD change."""
        _make_user(db_session)
        _make_account(db_session, is_paper=True)
        # Start: 2 BTC at $100k = $200k total, $0 USD portion
        _make_snapshot(
            db_session, date=datetime(2025, 1, 1),
            usd=200000, btc=2.0,
            usd_portion=0.0, btc_portion=2.0,
            unrealized_pnl_usd=0.0, unrealized_pnl_btc=0.0,
            btc_usd_price=100000.0,
        )
        # End: 2 BTC at $67k = $134k total, $0 USD portion
        _make_snapshot(
            db_session, date=datetime(2025, 1, 31),
            usd=134000, btc=2.0,
            usd_portion=0.0, btc_portion=2.0,
            unrealized_pnl_usd=0.0, unrealized_pnl_btc=0.0,
            btc_usd_price=67000.0,
        )
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        # No trades, no transfers, BTC unchanged — implied deposits = $0
        assert data["net_deposits_usd"] == pytest.approx(0.0)
        assert data["deposits_source"] == "transfers"
        # Market value effect = 2 BTC * (67000 - 100000) = -$66,000
        assert data["market_value_effect_usd"] == pytest.approx(-66000.0)

    @pytest.mark.asyncio
    async def test_native_currency_mixed_account_with_trades(self, db_session):
        """USD+BTC account with trades in both currencies — correct split."""
        _make_user(db_session)
        _make_account(db_session)
        # Start: $5000 USD, 0.5 BTC at $80k
        _make_snapshot(
            db_session, date=datetime(2025, 1, 1),
            usd=45000, btc=0.5625,
            usd_portion=5000.0, btc_portion=0.5,
            unrealized_pnl_usd=0.0, unrealized_pnl_btc=0.0,
            btc_usd_price=80000.0,
        )
        # End: $5100 USD, 0.51 BTC at $82k — $100 USD profit, 0.01 BTC profit
        _make_snapshot(
            db_session, date=datetime(2025, 1, 31),
            usd=46920, btc=0.5722,
            usd_portion=5100.0, btc_portion=0.51,
            unrealized_pnl_usd=0.0, unrealized_pnl_btc=0.0,
            btc_usd_price=82000.0,
        )
        # USD-pair trade: $100 profit
        _make_position(
            db_session, product_id="ETH-USD", profit_usd=100.0,
            profit_quote=100.0, closed_at=datetime(2025, 1, 15),
        )
        # BTC-pair trade: 0.01 BTC profit ($820 at end price)
        _make_position(
            db_session, product_id="ETH-BTC", profit_usd=820.0,
            profit_quote=0.01, closed_at=datetime(2025, 1, 20),
        )
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        # USD portion: end(5100) - start(5000) - usd_profit(100) = 0
        # BTC portion: end(0.51) - start(0.5) - btc_profit(0.01) = 0
        # Combined implied = 0 * 82000 + 0 = $0
        assert data["net_deposits_usd"] == pytest.approx(0.0)
        assert data["deposits_source"] == "transfers"
        # Market value effect = 0.5 * (82000 - 80000) = $1000
        assert data["market_value_effect_usd"] == pytest.approx(1000.0)

    @pytest.mark.asyncio
    async def test_unrealized_pnl_subtracted_from_remainder(self, db_session):
        """Unrealized PnL change is subtracted to isolate actual deposits."""
        _make_user(db_session)
        _make_account(db_session)
        # Start: $10000 USD, 0 BTC, $0 unrealized
        _make_snapshot(
            db_session, date=datetime(2025, 1, 1),
            usd=10000, btc=0.0,
            usd_portion=10000.0, btc_portion=0.0,
            unrealized_pnl_usd=0.0, unrealized_pnl_btc=0.0,
            btc_usd_price=80000.0,
        )
        # End: $10500 USD, 0 BTC, $300 unrealized (from open positions)
        _make_snapshot(
            db_session, date=datetime(2025, 1, 31),
            usd=10500, btc=0.0,
            usd_portion=10500.0, btc_portion=0.0,
            unrealized_pnl_usd=300.0, unrealized_pnl_btc=0.0,
            btc_usd_price=80000.0,
        )
        # One closed trade with $100 realized profit
        _make_position(
            db_session, product_id="ETH-USD", profit_usd=100.0,
            profit_quote=100.0, closed_at=datetime(2025, 1, 15),
        )
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        # USD portion change: 10500 - 10000 = 500
        # Minus realized: 500 - 100 = 400
        # Minus unrealized change: 400 - (300 - 0) = 100
        # So implied deposit = $100
        assert data["net_deposits_usd"] == pytest.approx(100.0)
        assert data["deposits_source"] == "implied"
        # Unrealized PnL change = $300 (from 0 to 300)
        assert data["unrealized_pnl_change_usd"] == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_fallback_when_portions_null(self, db_session):
        """Old snapshots without portion data fall back to legacy formula."""
        _make_user(db_session)
        _make_account(db_session)
        # Old-style snapshots: no portions, no btc_usd_price
        _make_snapshot(
            db_session, date=datetime(2025, 1, 1),
            usd=5000, btc=0.1,
        )
        _make_snapshot(
            db_session, date=datetime(2025, 1, 31),
            usd=5500, btc=0.1,
        )
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        # Legacy: implied = account_growth - profit = 500 - 0 = 500
        assert data["net_deposits_usd"] == pytest.approx(500.0)
        assert data["deposits_source"] == "implied"
        # No market value effect when portions are NULL
        assert data["market_value_effect_usd"] is None

    @pytest.mark.asyncio
    async def test_btc_price_derived_from_old_snapshots(self, db_session):
        """Pre-v2.55 snapshots (no btc_usd_price) derive BTC price from
        total_value_usd - usd_portion / btc_portion, enabling native-currency
        accounting on historical data."""
        _make_user(db_session)
        _make_account(db_session, is_paper=True)
        # Old snapshot: has portions but no btc_usd_price
        # total_usd=200000, usd_portion=500, btc_portion=2.3
        # → derived btc_price = (200000 - 500) / 2.3 ≈ 86739.13
        _make_snapshot(
            db_session, date=datetime(2025, 1, 1),
            usd=200000, btc=2.3,
            usd_portion=500.0, btc_portion=2.3,
        )
        # End: btc_price = (167500 - 500) / 2.5 = 66800
        _make_snapshot(
            db_session, date=datetime(2025, 1, 31),
            usd=167500, btc=2.5,
            usd_portion=500.0, btc_portion=2.5,
        )
        _make_position(
            db_session, product_id="ETH-BTC", profit_usd=13360.0,
            profit_quote=0.2, closed_at=datetime(2025, 1, 20),
        )
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        # Native-currency accounting should work via derived prices
        assert data["net_deposits_usd"] == pytest.approx(0.0)
        assert data["deposits_source"] == "transfers"
        # Market value effect should be computed (not None)
        assert data["market_value_effect_usd"] is not None
        # 2.3 * (66800 - 86739.13) ≈ -45,860
        assert data["market_value_effect_usd"] == pytest.approx(-45860.0, abs=2.0)

    @pytest.mark.asyncio
    async def test_paper_account_btc_drop_native_currency(self, db_session):
        """Paper trading account: BTC price drop correctly handled by
        native-currency accounting (replaces old is_paper workaround)."""
        _make_user(db_session)
        _make_account(db_session, is_paper=True)
        # Paper account: 2.3 BTC at $86956/BTC, some USD
        _make_snapshot(
            db_session, date=datetime(2025, 1, 1),
            usd=200000, btc=2.3,
            usd_portion=500.0, btc_portion=2.3,
            unrealized_pnl_usd=0.0, unrealized_pnl_btc=0.0,
            btc_usd_price=86739.13,
        )
        # BTC dropped to $72565/BTC, gained 0.2 BTC from trading
        _make_snapshot(
            db_session, date=datetime(2025, 1, 31),
            usd=167500, btc=2.5,
            usd_portion=500.0, btc_portion=2.5,
            unrealized_pnl_usd=0.0, unrealized_pnl_btc=0.0,
            btc_usd_price=66800.0,
        )
        # BTC-pair trade: +0.2 BTC profit
        _make_position(
            db_session, product_id="ETH-BTC", profit_usd=13360.0,
            profit_quote=0.2, closed_at=datetime(2025, 1, 20),
        )
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        # BTC: end(2.5) - start(2.3) - btc_profit(0.2) = 0
        # USD: end(500) - start(500) - usd_profit(0) = 0
        # Combined = 0
        assert data["net_deposits_usd"] == pytest.approx(0.0)
        assert data["deposits_source"] == "transfers"
        # Market value effect = 2.3 * (66800 - 86739.13) = -$45,860
        assert data["market_value_effect_usd"] == pytest.approx(-45860.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_get_account_value_at_returns_expanded_fields(self, db_session):
        """_get_account_value_at returns all new snapshot fields."""
        _make_user(db_session)
        _make_account(db_session)
        _make_snapshot(
            db_session, date=datetime(2025, 1, 15),
            usd=10000, btc=0.1,
            usd_portion=8000.0, btc_portion=0.1,
            unrealized_pnl_usd=50.0, unrealized_pnl_btc=0.001,
            btc_usd_price=90000.0,
        )
        await db_session.flush()

        result = await _get_account_value_at(
            db_session, user_id=1, account_id=1,
            at_date=datetime(2025, 1, 16),
        )

        assert result["usd"] == 10000.0
        assert result["btc"] == 0.1
        assert result["usd_portion_usd"] == 8000.0
        assert result["btc_portion_btc"] == 0.1
        assert result["unrealized_pnl_usd"] == 50.0
        assert result["unrealized_pnl_btc"] == 0.001
        assert result["btc_usd_price"] == 90000.0

    @pytest.mark.asyncio
    async def test_btc_pair_profit_native_currency(self, db_session):
        """BTC-pair trades don't leak into USD deposits calculation."""
        _make_user(db_session)
        _make_account(db_session)
        # Start: $1000 USD, 1.0 BTC at $80k
        _make_snapshot(
            db_session, date=datetime(2025, 1, 1),
            usd=81000, btc=1.0125,
            usd_portion=1000.0, btc_portion=1.0,
            unrealized_pnl_usd=0.0, unrealized_pnl_btc=0.0,
            btc_usd_price=80000.0,
        )
        # End: $1000 USD, 1.05 BTC (gained 0.05 from trade) at $80k
        _make_snapshot(
            db_session, date=datetime(2025, 1, 31),
            usd=85000, btc=1.0625,
            usd_portion=1000.0, btc_portion=1.05,
            unrealized_pnl_usd=0.0, unrealized_pnl_btc=0.0,
            btc_usd_price=80000.0,
        )
        # BTC-pair trade: 0.05 BTC profit
        _make_position(
            db_session, product_id="ETH-BTC", profit_usd=4000.0,
            profit_quote=0.05, closed_at=datetime(2025, 1, 20),
        )
        await db_session.flush()

        data = await gather_report_data(
            db_session, user_id=1, account_id=1,
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 1, 31),
            goals=[],
        )

        # BTC: end(1.05) - start(1.0) - btc_profit(0.05) = 0
        # USD: end(1000) - start(1000) - usd_profit(0) = 0
        # Combined = 0
        assert data["net_deposits_usd"] == pytest.approx(0.0)
        assert data["deposits_source"] == "transfers"
        # No BTC price change → market value effect = 0
        assert data["market_value_effect_usd"] == pytest.approx(0.0)
