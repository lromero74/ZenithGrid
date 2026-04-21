"""
Tests for reports_router — expense item create/update endpoints, bulk delete,
and account-scoped filtering for goals, schedules, and reports.
"""

import math
import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from app.models import (
    Account, AccountValueSnapshot, ExpenseItem, Position,
    Report, ReportGoal, ReportSchedule, User,
)


@pytest.fixture
async def expense_goal(db_session):
    """Create a user and an expenses-type goal for testing."""
    user = User(
        email="expense_router_test@example.com",
        hashed_password="hashed",
        display_name="Test",
    )
    db_session.add(user)
    await db_session.flush()

    goal = ReportGoal(
        user_id=user.id,
        name="Test Bills",
        target_type="expenses",
        target_currency="USD",
        target_value=5000.0,
        expense_period="monthly",
        time_horizon_months=12,
        start_date=datetime.utcnow(),
        target_date=datetime.utcnow() + timedelta(days=365),
    )
    db_session.add(goal)
    await db_session.flush()
    return user, goal


class TestCreateExpenseItemFields:
    """Verify all fields are saved when creating expense items."""

    @pytest.mark.asyncio
    async def test_create_expense_item_saves_due_day(self, db_session, expense_goal):
        """due_day should be persisted on create (was missing before fix)."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Housing",
            name="Rent",
            amount=1500.0,
            frequency="monthly",
            due_day=15,
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.due_day == 15

    @pytest.mark.asyncio
    async def test_create_expense_item_saves_due_day_last(self, db_session, expense_goal):
        """due_day=-1 (last day of month) should be persisted."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Housing",
            name="Rent Test",
            amount=1000.0,
            frequency="monthly",
            due_day=-1,
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.due_day == -1

    @pytest.mark.asyncio
    async def test_create_expense_item_saves_due_month(self, db_session, expense_goal):
        """due_month should be persisted on create (was missing before fix)."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Insurance",
            name="Car Insurance",
            amount=600.0,
            frequency="semi_annual",
            due_day=1,
            due_month=6,
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.due_month == 6
        assert item.due_day == 1

    @pytest.mark.asyncio
    async def test_create_expense_item_saves_login_url(self, db_session, expense_goal):
        """login_url should be persisted on create (was missing before fix)."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Streaming",
            name="Netflix",
            amount=15.99,
            frequency="monthly",
            login_url="https://netflix.com/login",
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.login_url == "https://netflix.com/login"

    @pytest.mark.asyncio
    async def test_create_expense_item_all_optional_fields(self, db_session, expense_goal):
        """All optional fields (due_day, due_month, login_url) saved together."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Utilities",
            name="Electric",
            amount=200.0,
            frequency="monthly",
            due_day=20,
            due_month=3,
            login_url="https://electric.com/pay",
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.due_day == 20
        assert item.due_month == 3
        assert item.login_url == "https://electric.com/pay"

    @pytest.mark.asyncio
    async def test_create_expense_item_null_optional_fields(self, db_session, expense_goal):
        """Optional fields default to None when not provided."""
        user, goal = expense_goal
        item = ExpenseItem(
            goal_id=goal.id,
            user_id=user.id,
            category="Food",
            name="Groceries",
            amount=400.0,
            frequency="monthly",
        )
        db_session.add(item)
        await db_session.flush()
        await db_session.refresh(item)

        assert item.due_day is None
        assert item.due_month is None
        assert item.login_url is None


# ---------------------------------------------------------------------------
# Bulk Delete Reports
# ---------------------------------------------------------------------------


@pytest.fixture
async def bulk_delete_setup(db_session):
    """Create two users, a schedule, and several reports for bulk delete testing."""
    user1 = User(
        email="bulk_del_user1@example.com",
        hashed_password="hashed",
        display_name="User1",
    )
    user2 = User(
        email="bulk_del_user2@example.com",
        hashed_password="hashed",
        display_name="User2",
    )
    db_session.add_all([user1, user2])
    await db_session.flush()

    schedule = ReportSchedule(
        user_id=user1.id,
        name="Weekly",
        periodicity="weekly",
        recipients=[],
    )
    db_session.add(schedule)
    await db_session.flush()

    reports = []
    for i in range(5):
        r = Report(
            user_id=user1.id,
            schedule_id=schedule.id,
            periodicity="weekly",
            period_start=datetime(2026, 1, 1 + i),
            period_end=datetime(2026, 1, 7 + i),
            html_content=f"<p>Report {i}</p>",
            delivery_status="sent",
        )
        reports.append(r)
    # One report owned by user2
    other_report = Report(
        user_id=user2.id,
        schedule_id=schedule.id,
        periodicity="weekly",
        period_start=datetime(2026, 2, 1),
        period_end=datetime(2026, 2, 7),
        html_content="<p>Other user report</p>",
        delivery_status="sent",
    )
    db_session.add_all(reports + [other_report])
    await db_session.flush()
    return user1, user2, reports, other_report


class TestBulkDeleteReports:
    """Tests for POST /reports/bulk-delete endpoint logic."""

    @pytest.mark.asyncio
    async def test_bulk_delete_happy_path(self, db_session, bulk_delete_setup):
        """Delete 3 reports owned by the user — should succeed and return count."""
        user1, _, reports, _ = bulk_delete_setup
        ids_to_delete = [reports[0].id, reports[1].id, reports[2].id]

        # Simulate the endpoint logic directly on the DB
        result = await db_session.execute(
            select(Report).where(
                Report.id.in_(ids_to_delete),
                Report.user_id == user1.id,
            )
        )
        found = list(result.scalars().all())
        assert len(found) == 3
        for r in found:
            await db_session.delete(r)
        await db_session.flush()

        # Verify they're gone
        remaining = await db_session.execute(
            select(Report).where(
                Report.user_id == user1.id,
            )
        )
        assert len(list(remaining.scalars().all())) == 2

    @pytest.mark.asyncio
    async def test_bulk_delete_partial_ids(self, db_session, bulk_delete_setup):
        """Some IDs exist, some don't — deletes what it can."""
        user1, _, reports, _ = bulk_delete_setup
        ids_to_delete = [reports[0].id, 99999]

        result = await db_session.execute(
            select(Report).where(
                Report.id.in_(ids_to_delete),
                Report.user_id == user1.id,
            )
        )
        found = list(result.scalars().all())
        assert len(found) == 1
        for r in found:
            await db_session.delete(r)
        await db_session.flush()

    @pytest.mark.asyncio
    async def test_bulk_delete_wrong_user_gets_nothing(self, db_session, bulk_delete_setup):
        """User2 cannot delete user1's reports — query returns empty list."""
        _, user2, reports, _ = bulk_delete_setup
        ids_to_delete = [reports[0].id, reports[1].id]

        result = await db_session.execute(
            select(Report).where(
                Report.id.in_(ids_to_delete),
                Report.user_id == user2.id,
            )
        )
        found = list(result.scalars().all())
        assert len(found) == 0

    @pytest.mark.asyncio
    async def test_bulk_delete_nonexistent_ids_empty(self, db_session, bulk_delete_setup):
        """All IDs invalid — returns empty list (endpoint would 404)."""
        user1, _, _, _ = bulk_delete_setup

        result = await db_session.execute(
            select(Report).where(
                Report.id.in_([88888, 99999]),
                Report.user_id == user1.id,
            )
        )
        found = list(result.scalars().all())
        assert len(found) == 0

    @pytest.mark.asyncio
    async def test_bulk_delete_request_validation_empty_list(self):
        """Empty list should fail Pydantic validation."""
        from app.routers.reports_crud_router import BulkDeleteRequest
        with pytest.raises(Exception):
            BulkDeleteRequest(report_ids=[])

    @pytest.mark.asyncio
    async def test_bulk_delete_request_validation_exceeds_max(self):
        """>100 IDs should fail Pydantic validation."""
        from app.routers.reports_crud_router import BulkDeleteRequest
        with pytest.raises(Exception):
            BulkDeleteRequest(report_ids=list(range(101)))


# ---------------------------------------------------------------------------
# Account-Scoped Reports
# ---------------------------------------------------------------------------


@pytest.fixture
async def account_scope_setup(db_session):
    """Create a user with two accounts and goals/schedules/reports on each."""
    user = User(
        email="acct_scope_test@example.com",
        hashed_password="hashed",
        display_name="Test",
    )
    db_session.add(user)
    await db_session.flush()

    acct_live = Account(
        user_id=user.id,
        name="Live",
        type="cex",
        is_default=True,
    )
    acct_paper = Account(
        user_id=user.id,
        name="Paper",
        type="cex",
        is_default=False,
    )
    db_session.add_all([acct_live, acct_paper])
    await db_session.flush()

    # Goals — one per account
    goal_live = ReportGoal(
        user_id=user.id,
        account_id=acct_live.id,
        name="Live Goal",
        target_type="balance",
        target_currency="USD",
        target_value=10000.0,
        time_horizon_months=12,
        start_date=datetime.utcnow(),
        target_date=datetime.utcnow() + timedelta(days=365),
    )
    goal_paper = ReportGoal(
        user_id=user.id,
        account_id=acct_paper.id,
        name="Paper Goal",
        target_type="balance",
        target_currency="USD",
        target_value=5000.0,
        time_horizon_months=6,
        start_date=datetime.utcnow(),
        target_date=datetime.utcnow() + timedelta(days=180),
    )
    db_session.add_all([goal_live, goal_paper])
    await db_session.flush()

    # Schedules — one per account
    sched_live = ReportSchedule(
        user_id=user.id,
        account_id=acct_live.id,
        name="Live Weekly",
        periodicity="weekly",
        recipients=[],
    )
    sched_paper = ReportSchedule(
        user_id=user.id,
        account_id=acct_paper.id,
        name="Paper Weekly",
        periodicity="weekly",
        recipients=[],
    )
    db_session.add_all([sched_live, sched_paper])
    await db_session.flush()

    # Reports — two per account
    reports_live = []
    for i in range(2):
        r = Report(
            user_id=user.id,
            account_id=acct_live.id,
            schedule_id=sched_live.id,
            periodicity="weekly",
            period_start=datetime(2026, 1, 1 + i),
            period_end=datetime(2026, 1, 7 + i),
            html_content=f"<p>Live Report {i}</p>",
            delivery_status="sent",
        )
        reports_live.append(r)

    reports_paper = []
    for i in range(2):
        r = Report(
            user_id=user.id,
            account_id=acct_paper.id,
            schedule_id=sched_paper.id,
            periodicity="weekly",
            period_start=datetime(2026, 2, 1 + i),
            period_end=datetime(2026, 2, 7 + i),
            html_content=f"<p>Paper Report {i}</p>",
            delivery_status="sent",
        )
        reports_paper.append(r)

    db_session.add_all(reports_live + reports_paper)
    await db_session.flush()

    return {
        "user": user,
        "acct_live": acct_live,
        "acct_paper": acct_paper,
        "goal_live": goal_live,
        "goal_paper": goal_paper,
        "sched_live": sched_live,
        "sched_paper": sched_paper,
        "reports_live": reports_live,
        "reports_paper": reports_paper,
    }


class TestAccountScopedGoals:
    """Goals should be filterable by account_id."""

    @pytest.mark.asyncio
    async def test_list_goals_filters_by_account_id(
        self, db_session, account_scope_setup
    ):
        """Filtering by account_id returns only that account's goals."""
        s = account_scope_setup
        result = await db_session.execute(
            select(ReportGoal).where(
                ReportGoal.user_id == s["user"].id,
                ReportGoal.account_id == s["acct_live"].id,
            )
        )
        goals = list(result.scalars().all())
        assert len(goals) == 1
        assert goals[0].name == "Live Goal"

    @pytest.mark.asyncio
    async def test_list_goals_no_filter_returns_all(
        self, db_session, account_scope_setup
    ):
        """Without account_id filter, all user goals are returned."""
        s = account_scope_setup
        result = await db_session.execute(
            select(ReportGoal).where(
                ReportGoal.user_id == s["user"].id,
            )
        )
        goals = list(result.scalars().all())
        assert len(goals) == 2

    @pytest.mark.asyncio
    async def test_create_goal_stores_account_id(
        self, db_session, account_scope_setup
    ):
        """account_id is persisted when creating a goal."""
        s = account_scope_setup
        goal = ReportGoal(
            user_id=s["user"].id,
            account_id=s["acct_paper"].id,
            name="New Paper Goal",
            target_type="profit",
            target_currency="USD",
            target_value=1000.0,
            time_horizon_months=3,
            start_date=datetime.utcnow(),
            target_date=datetime.utcnow() + timedelta(days=90),
        )
        db_session.add(goal)
        await db_session.flush()
        await db_session.refresh(goal)
        assert goal.account_id == s["acct_paper"].id


class TestAccountScopedSchedules:
    """Schedules should be filterable by account_id."""

    @pytest.mark.asyncio
    async def test_list_schedules_filters_by_account_id(
        self, db_session, account_scope_setup
    ):
        """Filtering by account_id returns only that account's schedules."""
        s = account_scope_setup
        result = await db_session.execute(
            select(ReportSchedule).where(
                ReportSchedule.user_id == s["user"].id,
                ReportSchedule.account_id == s["acct_paper"].id,
            )
        )
        schedules = list(result.scalars().all())
        assert len(schedules) == 1
        assert schedules[0].name == "Paper Weekly"

    @pytest.mark.asyncio
    async def test_list_schedules_no_filter_returns_all(
        self, db_session, account_scope_setup
    ):
        """Without account_id filter, all user schedules are returned."""
        s = account_scope_setup
        result = await db_session.execute(
            select(ReportSchedule).where(
                ReportSchedule.user_id == s["user"].id,
            )
        )
        schedules = list(result.scalars().all())
        assert len(schedules) == 2


class TestAccountScopedReports:
    """Reports should be filterable by account_id."""

    @pytest.mark.asyncio
    async def test_list_reports_filters_by_account_id(
        self, db_session, account_scope_setup
    ):
        """Filtering by account_id returns only that account's reports."""
        s = account_scope_setup
        result = await db_session.execute(
            select(Report).where(
                Report.user_id == s["user"].id,
                Report.account_id == s["acct_live"].id,
            )
        )
        reports = list(result.scalars().all())
        assert len(reports) == 2
        for r in reports:
            assert "Live" in r.html_content

    @pytest.mark.asyncio
    async def test_list_reports_no_filter_returns_all(
        self, db_session, account_scope_setup
    ):
        """Without account_id filter, all user reports are returned."""
        s = account_scope_setup
        result = await db_session.execute(
            select(Report).where(
                Report.user_id == s["user"].id,
            )
        )
        reports = list(result.scalars().all())
        assert len(reports) == 4

    @pytest.mark.asyncio
    async def test_report_inherits_account_from_schedule(
        self, db_session, account_scope_setup
    ):
        """A report created for a schedule inherits its account_id."""
        s = account_scope_setup
        report = Report(
            user_id=s["user"].id,
            account_id=s["sched_live"].account_id,
            schedule_id=s["sched_live"].id,
            periodicity="weekly",
            period_start=datetime(2026, 3, 1),
            period_end=datetime(2026, 3, 7),
            html_content="<p>Test</p>",
            delivery_status="manual",
        )
        db_session.add(report)
        await db_session.flush()
        await db_session.refresh(report)
        assert report.account_id == s["acct_live"].id


class TestGetUserTradingMetricsAccountScoping:
    """_get_user_trading_metrics must scope to a single account when account_id is given.

    This prevents paper-trading accounts (or other accounts) from inflating the
    account balance and diluting the growth-rate calculation used for expense planning.
    """

    @pytest.mark.asyncio
    async def test_metrics_scoped_to_specific_account(self, db_session):
        """When account_id is provided, only that account's snapshot is used.

        A second account (paper trading) with a much larger balance must NOT
        influence the result.
        """
        from datetime import datetime as dt
        from unittest.mock import MagicMock
        from app.routers.reports_generation_router import _get_user_trading_metrics

        # We test by mocking db.execute and verifying account_id appears in the
        # WHERE clauses. Use the real function signature to check parameter flow.
        calls = []

        class FakeScalar:
            def __init__(self, val):
                self._val = val

            def scalar(self):
                return self._val

        async def fake_execute(stmt):
            # Capture the compiled SQL text to verify account_id filtering
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            calls.append(compiled)
            # First call = profit SUM → return 100.0
            # Second call = max(snapshot_date) → return a date
            # Third call = sum(value) → return 1000.0
            if "profit_usd" in compiled or "profit_quote" in compiled:
                return FakeScalar(100.0)
            elif "MAX" in compiled.upper():
                return FakeScalar(dt(2026, 3, 25, 0, 0, 0))
            else:
                return FakeScalar(1000.0)

        mock_db = MagicMock()
        mock_db.execute = fake_execute

        annual_pct, balance = await _get_user_trading_metrics(
            mock_db, user_id=1, is_btc=False, account_id=42
        )

        # Verify account_id=42 appears in at least the balance queries
        balance_calls = [c for c in calls if "42" in c]
        assert len(balance_calls) >= 2, (
            "account_id must appear in snapshot queries. calls: " + str(calls)
        )
        assert balance == pytest.approx(1000.0)
        assert annual_pct > 0

    @pytest.mark.asyncio
    async def test_metrics_without_account_id_uses_all_accounts(self, db_session):
        """When account_id is None, all accounts for the user are included."""
        from datetime import datetime as dt
        from unittest.mock import MagicMock
        from app.routers.reports_generation_router import _get_user_trading_metrics

        calls = []

        class FakeScalar:
            def __init__(self, val):
                self._val = val

            def scalar(self):
                return self._val

        async def fake_execute(stmt):
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            calls.append(compiled)
            if "profit_usd" in compiled or "profit_quote" in compiled:
                return FakeScalar(50.0)
            elif "MAX" in compiled.upper():
                return FakeScalar(dt(2026, 3, 25, 0, 0, 0))
            else:
                return FakeScalar(5000.0)

        mock_db = MagicMock()
        mock_db.execute = fake_execute

        annual_pct, balance = await _get_user_trading_metrics(
            mock_db, user_id=1, is_btc=False, account_id=None
        )

        # No account_id filter → no specific account id in WHERE clauses
        # (user_id=1 will appear, but a specific account id like "42" won't)
        assert balance == pytest.approx(5000.0)
        assert annual_pct > 0


class TestListExpenseItemsResponseShape:
    """Guard against regression where list_expense_items returned a bare list
    instead of {items, coverage_summary} envelope, causing FastAPI to reject the
    response with a validation error (list_type, 'Input should be a valid list')."""

    @pytest.mark.asyncio
    async def test_response_is_dict_not_list(self, db_session, expense_goal):
        """Happy path: endpoint must return a dict with 'items' and 'coverage_summary'."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.routers.reports_generation_router import list_expense_items

        user, goal = expense_goal

        mock_current_user = MagicMock()
        mock_current_user.id = user.id

        # Stub the waterfall and metric helpers to keep the test lightweight
        with (
            patch(
                "app.routers.reports_generation_router._get_user_trading_metrics",
                new=AsyncMock(return_value=(0.0, 0.0)),
            ),
            patch(
                "app.services.expense_service.compute_expense_coverage",
                return_value={
                    "items": [],
                    "savings_targets": [],
                    "shortfall": 0.0,
                    "coverage_pct": 100.0,
                    "income_after_tax": 0.0,
                    "total_expenses": 0.0,
                    "total_claims": 0.0,
                    "covered_count": 0,
                    "total_count": 0,
                    "first_gap_savings_name": None,
                    "first_gap_savings_cap_gap": None,
                    "first_gap_savings_capital_required": None,
                    "first_blocked_after_savings_name": None,
                    "first_blocked_after_savings_amount": None,
                    "partial_item_name": None,
                    "partial_item_shortfall": None,
                    "next_uncovered_name": None,
                    "next_uncovered_amount": None,
                },
            ),
        ):
            result = await list_expense_items(
                goal_id=goal.id,
                db=db_session,
                current_user=mock_current_user,
            )

        # Must be a dict, not a list
        assert isinstance(result, dict), (
            f"list_expense_items must return a dict (envelope), got {type(result)}"
        )
        assert "items" in result, "Response dict must contain 'items' key"
        assert "coverage_summary" in result, "Response dict must contain 'coverage_summary' key"
        assert isinstance(result["items"], list), "'items' must be a list"
        assert isinstance(result["coverage_summary"], dict), "'coverage_summary' must be a dict"

    @pytest.mark.asyncio
    async def test_items_key_contains_expense_items(self, db_session, expense_goal):
        """Edge case: when goal has expense items, they appear under 'items' key."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.models import ExpenseItem as ExpenseItemModel
        from app.routers.reports_generation_router import list_expense_items

        user, goal = expense_goal

        # Add a real expense item
        item = ExpenseItemModel(
            goal_id=goal.id,
            user_id=user.id,
            category="Housing",
            name="Rent",
            amount=1200.0,
            frequency="monthly",
        )
        db_session.add(item)
        await db_session.flush()

        mock_current_user = MagicMock()
        mock_current_user.id = user.id

        with (
            patch(
                "app.routers.reports_generation_router._get_user_trading_metrics",
                new=AsyncMock(return_value=(0.0, 0.0)),
            ),
            patch("app.services.expense_service.compute_expense_coverage") as mock_cov,
        ):
            mock_cov.return_value = {
                "items": [{"id": item.id, "name": "Rent", "status": "uncovered"}],
                "savings_targets": [],
                "shortfall": 1200.0,
                "coverage_pct": 0.0,
                "income_after_tax": 0.0,
                "total_expenses": 1200.0,
                "total_claims": 1200.0,
                "covered_count": 0,
                "total_count": 1,
                "first_gap_savings_name": None,
                "first_gap_savings_cap_gap": None,
                "first_gap_savings_capital_required": None,
                "first_blocked_after_savings_name": None,
                "first_blocked_after_savings_amount": None,
                "partial_item_name": "Rent",
                "partial_item_shortfall": 1200.0,
                "next_uncovered_name": None,
                "next_uncovered_amount": None,
            }
            result = await list_expense_items(
                goal_id=goal.id,
                db=db_session,
                current_user=mock_current_user,
            )

        assert isinstance(result, dict)
        assert len(result["items"]) >= 1


# ---------------------------------------------------------------------------
# Fixtures for financial helper tests
# ---------------------------------------------------------------------------

@pytest.fixture
async def metrics_user_with_data(db_session):
    """User with account, closed positions, and account value snapshots."""
    user = User(
        email="metrics_test@example.com",
        hashed_password="hashed",
        display_name="Metrics Tester",
    )
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id,
        name="Test Account",
        type="cex",
        is_default=True,
    )
    db_session.add(account)
    await db_session.flush()

    now = datetime.utcnow()

    # Create closed positions with known profit in last 30 days
    for i in range(3):
        pos = Position(
            user_id=user.id,
            account_id=account.id,
            product_id=f"ETH-USD-{i}",
            status="closed",
            closed_at=now - timedelta(days=i + 1),
            profit_usd=100.0,  # 3 positions × $100 = $300 total
            profit_quote=0.0,
        )
        db_session.add(pos)

    # Account value snapshot (recent)
    snap = AccountValueSnapshot(
        account_id=account.id,
        user_id=user.id,
        snapshot_date=now - timedelta(hours=6),
        total_value_usd=10000.0,
        total_value_btc=0.15,
    )
    db_session.add(snap)
    await db_session.flush()

    return user, account


class TestGetUserAnnualReturnPct:
    """Tests for _get_user_annual_return_pct helper."""

    @pytest.mark.asyncio
    async def test_annual_return_with_profit_data(self, db_session, metrics_user_with_data):
        """With 30-day profit and account value, returns compound-annualized %."""
        from app.routers.reports_generation_router import _get_user_annual_return_pct

        user, account = metrics_user_with_data
        result = await _get_user_annual_return_pct(db_session, user.id)

        # $300 profit over 30 days, $10000 account value
        # daily_rate = (300/30) / 10000 = 0.001
        # annual = ((1 + 0.001)^365 - 1) * 100 ≈ 44.025%
        expected = round((math.pow(1 + 0.001, 365) - 1) * 100, 4)
        assert result == expected

    @pytest.mark.asyncio
    async def test_annual_return_no_snapshots(self, db_session):
        """With no data at all, returns 0.0."""
        from app.routers.reports_generation_router import _get_user_annual_return_pct

        # Non-existent user ID
        result = await _get_user_annual_return_pct(db_session, 99999)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_annual_return_no_profit(self, db_session, metrics_user_with_data):
        """With zero profit, returns 0.0."""
        from app.routers.reports_generation_router import _get_user_annual_return_pct

        user, account = metrics_user_with_data
        # Request BTC mode — positions only have profit_usd, so profit_quote is 0
        result = await _get_user_annual_return_pct(db_session, user.id, is_btc=True)
        assert result == 0.0


class TestGetUserTradingMetrics:
    """Tests for _get_user_trading_metrics helper."""

    @pytest.mark.asyncio
    async def test_trading_metrics_returns_tuple(self, db_session, metrics_user_with_data):
        """Returns (annual_return_pct, account_balance) tuple."""
        from app.routers.reports_generation_router import _get_user_trading_metrics

        user, account = metrics_user_with_data
        annual_pct, balance = await _get_user_trading_metrics(db_session, user.id)

        assert isinstance(annual_pct, float)
        assert isinstance(balance, float)
        assert annual_pct > 0
        assert balance == pytest.approx(10000.0)

    @pytest.mark.asyncio
    async def test_trading_metrics_account_scoped(self, db_session, metrics_user_with_data):
        """When account_id provided, scopes to that account."""
        from app.routers.reports_generation_router import _get_user_trading_metrics

        user, account = metrics_user_with_data
        annual_pct, balance = await _get_user_trading_metrics(
            db_session, user.id, account_id=account.id
        )
        assert annual_pct > 0
        assert balance == pytest.approx(10000.0)

    @pytest.mark.asyncio
    async def test_trading_metrics_no_data(self, db_session):
        """With no data, returns (0.0, 0.0)."""
        from app.routers.reports_generation_router import _get_user_trading_metrics

        annual_pct, balance = await _get_user_trading_metrics(db_session, 99999)
        assert annual_pct == 0.0
        assert balance == 0.0

    @pytest.mark.asyncio
    async def test_trading_metrics_negative_profit_returns_zero_pct(self, db_session):
        """When profit is negative, annual_return_pct is 0 but balance is returned."""
        from app.routers.reports_generation_router import _get_user_trading_metrics

        user = User(
            email="neg_profit@example.com",
            hashed_password="hashed",
            display_name="Neg",
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Neg Account",
            type="cex",
            is_default=False,
        )
        db_session.add(account)
        await db_session.flush()

        now = datetime.utcnow()
        # Negative profit position
        pos = Position(
            user_id=user.id,
            account_id=account.id,
            product_id="ETH-USD-neg",
            status="closed",
            closed_at=now - timedelta(days=1),
            profit_usd=-50.0,
            profit_quote=0.0,
        )
        db_session.add(pos)

        snap = AccountValueSnapshot(
            account_id=account.id,
            user_id=user.id,
            snapshot_date=now - timedelta(hours=1),
            total_value_usd=5000.0,
            total_value_btc=0.1,
        )
        db_session.add(snap)
        await db_session.flush()

        annual_pct, balance = await _get_user_trading_metrics(db_session, user.id)
        assert annual_pct == 0.0
        assert balance == pytest.approx(5000.0)


class TestComputeMonthlyGrowthRate:
    """Tests for compute_monthly_growth_rate (extracted to report_data_service)."""

    def test_positive_annual_return(self):
        """Converts annual return % to monthly growth rate."""
        from app.services.report_data_service import compute_monthly_growth_rate

        annual_pct = 44.0
        expected = math.pow(1 + annual_pct / 100, 1 / 12) - 1
        result = compute_monthly_growth_rate(annual_pct)
        assert result == pytest.approx(expected)

    def test_zero_annual_return(self):
        """Zero annual return gives zero monthly rate."""
        from app.services.report_data_service import compute_monthly_growth_rate

        result = compute_monthly_growth_rate(0.0)
        assert result == 0.0

    def test_negative_annual_return(self):
        """Negative annual return gives zero monthly rate."""
        from app.services.report_data_service import compute_monthly_growth_rate

        result = compute_monthly_growth_rate(-10.0)
        assert result == 0.0


class TestReportsRouteOrdering:
    """Guard against regression where string routes are shadowed by a
    sibling router's ``/{report_id}`` catch-all.

    Background: ``reports_crud_router`` defines ``GET /{report_id}`` with an
    ``int`` path parameter. If another router registered under the same
    ``/reports`` prefix declares a string path like ``/expense-categories``
    after it, Starlette route-matching tries ``/{report_id}`` first, fails
    int validation, and returns 422 — the categories dropdown in the
    Expenses editor then breaks.
    """

    def test_expense_categories_resolves_before_report_id(self):
        """``GET /api/reports/expense-categories`` must resolve to the
        categories endpoint, not the ``/{report_id}`` catch-all."""
        from starlette.routing import Match
        from app.main import app
        from app.routers.reports_generation_router import get_expense_categories

        # Find the first route that matches GET /api/reports/expense-categories
        matched = None
        for route in app.routes:
            if not hasattr(route, "matches"):
                continue
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/api/reports/expense-categories",
            }
            match, _ = route.matches(scope)
            if match == Match.FULL:
                matched = route
                break

        assert matched is not None, (
            "No route matched GET /api/reports/expense-categories"
        )
        assert matched.endpoint is get_expense_categories, (
            f"Expected /expense-categories to resolve to "
            f"get_expense_categories; got {matched.endpoint!r}. "
            "This means a sibling router's /{report_id} catch-all is "
            "shadowing the string route."
        )

    def test_report_id_catchall_still_resolves_for_int_paths(self):
        """``GET /api/reports/123`` must still resolve to get_report
        after any route-order fix."""
        from starlette.routing import Match
        from app.main import app
        from app.routers.reports_crud_router import get_report

        matched = None
        for route in app.routes:
            if not hasattr(route, "matches"):
                continue
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/api/reports/123",
            }
            match, _ = route.matches(scope)
            if match == Match.FULL:
                matched = route
                break

        assert matched is not None, "No route matched GET /api/reports/123"
        assert matched.endpoint is get_report, (
            f"Expected /api/reports/123 to resolve to get_report; "
            f"got {matched.endpoint!r}."
        )
