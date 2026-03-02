"""Reporting models: snapshots, goals, expenses, schedules, reports, transfers."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class AccountValueSnapshot(Base):
    """
    Daily snapshot of account value for historical tracking.

    Stores total account value in both BTC and USD for charting over time.
    Captured once daily by scheduled task.
    """
    __tablename__ = "account_value_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date = Column(DateTime, nullable=False, index=True)
    total_value_btc = Column(Float, nullable=False, default=0.0)
    total_value_usd = Column(Float, nullable=False, default=0.0)
    usd_portion_usd = Column(Float, nullable=True)   # USD+USDC+USDT free + USD/USDC/USDT-pair position values
    btc_portion_btc = Column(Float, nullable=True)   # BTC free + BTC-pair position values (in BTC)
    unrealized_pnl_usd = Column(Float, nullable=True)   # From USD-pair open positions
    unrealized_pnl_btc = Column(Float, nullable=True)   # From BTC-pair open positions (in BTC)
    btc_usd_price = Column(Float, nullable=True)         # BTC/USD price at snapshot time
    created_at = Column(DateTime, default=datetime.utcnow)

    # Unique constraint: one snapshot per account per day
    __table_args__ = (UniqueConstraint("account_id", "snapshot_date", name="uq_account_snapshot_date"),)

    # Relationships
    account = relationship("Account")
    user = relationship("User")


class MetricSnapshot(Base):
    """
    Rolling history of market metric values for sparkline charts.

    Records a snapshot each time a metric is fetched (~every 15 min).
    Pruned to 90 days to keep the table small.
    """
    __tablename__ = "metric_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    metric_name = Column(String, nullable=False, index=True)
    value = Column(Float, nullable=False)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class PropFirmState(Base):
    """
    Tracks equity state for prop firm accounts across restarts.

    Persists kill switch status, daily/total drawdown tracking, and
    equity snapshots needed by PropGuard safety middleware.
    One row per prop firm account.
    """
    __tablename__ = "prop_firm_state"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )

    # Starting capital for total drawdown calculation
    initial_deposit = Column(Float, nullable=False, default=0.0)

    # Daily reset tracking (resets at 17:00 EST)
    daily_start_equity = Column(Float, nullable=True)
    daily_start_timestamp = Column(DateTime, nullable=True)

    # Current equity tracking
    current_equity = Column(Float, nullable=True)
    current_equity_timestamp = Column(DateTime, nullable=True)

    # Kill switch state
    is_killed = Column(Boolean, default=False)
    kill_reason = Column(String, nullable=True)
    kill_timestamp = Column(DateTime, nullable=True)

    # Running P&L totals
    daily_pnl = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    account = relationship("Account")


class PropFirmEquitySnapshot(Base):
    """
    Time-series equity snapshots for prop firm accounts.

    Recorded every monitor cycle (~30s) to allow charting
    equity trajectory and drawdown history over time.
    """
    __tablename__ = "prop_firm_equity_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    equity = Column(Float, nullable=False)
    daily_drawdown_pct = Column(Float, default=0.0)
    total_drawdown_pct = Column(Float, default=0.0)
    daily_pnl = Column(Float, default=0.0)
    is_killed = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class ReportGoal(Base):
    """
    User financial targets for tracking in reports.

    Goals define balance or profit targets with time horizons,
    and progress is calculated in each generated report.
    """
    __tablename__ = "report_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    name = Column(String, nullable=False)  # e.g. "Reach 1 BTC"
    target_type = Column(String, nullable=False)  # "balance" / "profit" / "both"
    target_currency = Column(String, nullable=False, default="USD")  # "USD" / "BTC"
    target_value = Column(Float, nullable=False)  # Primary target (for balance or profit)
    target_balance_value = Column(Float, nullable=True)  # When target_type="both"
    target_profit_value = Column(Float, nullable=True)  # When target_type="both"
    income_period = Column(String, nullable=True)  # "daily"/"weekly"/"monthly"/"yearly" (for income goals)
    lookback_days = Column(Integer, nullable=True)  # null=all-time; 7/14/30/90/365
    time_horizon_months = Column(Integer, nullable=False)  # 1, 6, 12, 24, 60, 120
    start_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    target_date = Column(DateTime, nullable=False)  # Computed: start_date + horizon
    is_active = Column(Boolean, default=True)
    achieved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Expenses goal fields
    expense_period = Column(String, nullable=True)  # weekly/monthly/quarterly/yearly
    tax_withholding_pct = Column(Float, nullable=True, default=0)  # 0-100
    expense_sort_mode = Column(String, default="custom")  # amount_asc | amount_desc | custom

    # Chart display settings
    chart_horizon = Column(String, default="auto")  # "auto", "full", or integer days as string
    show_minimap = Column(Boolean, default=True)
    minimap_threshold_days = Column(Integer, default=90)  # Show minimap when >N days from target

    # Relationships
    user = relationship("User", back_populates="report_goals")
    schedule_links = relationship(
        "ReportScheduleGoal", back_populates="goal", cascade="all, delete-orphan"
    )
    progress_snapshots = relationship(
        "GoalProgressSnapshot", back_populates="goal", cascade="all, delete-orphan"
    )
    expense_items = relationship(
        "ExpenseItem", back_populates="goal", cascade="all, delete-orphan"
    )


class ExpenseItem(Base):
    """
    Individual expense line items for expenses-type goals.

    Each item has its own frequency; all are normalized to the goal's
    expense_period for coverage calculations.
    """
    __tablename__ = "expense_items"

    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(
        Integer, ForeignKey("report_goals.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    category = Column(String, nullable=False)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    frequency = Column(String, nullable=False)  # daily/weekly/biweekly/every_n_days/monthly/quarterly/yearly
    frequency_n = Column(Integer, nullable=True)  # Only for every_n_days
    frequency_anchor = Column(String, nullable=True)  # Start date for every_n_days (YYYY-MM-DD)
    due_day = Column(Integer, nullable=True)  # Day of month (1-31, -1 for last day)
    due_month = Column(Integer, nullable=True)  # Month (1-12) for quarterly/semi_annual/yearly
    login_url = Column(String, nullable=True)  # URL to payment/login page
    amount_mode = Column(String, default="fixed")  # 'fixed' or 'percent_of_income'
    percent_of_income = Column(Float, nullable=True)  # e.g. 10.0 for 10%
    percent_basis = Column(String, nullable=True)  # 'pre_tax' or 'post_tax'
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    goal = relationship("ReportGoal", back_populates="expense_items")
    user = relationship("User")


class GoalProgressSnapshot(Base):
    """
    Daily snapshot of goal progress for trend line visualization.

    Captured during the daily account snapshot cycle. One row per goal per day.
    Used to render actual-vs-ideal progress charts on the Goals tab.
    """
    __tablename__ = "goal_progress_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(
        Integer, ForeignKey("report_goals.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    snapshot_date = Column(DateTime, nullable=False, index=True)
    current_value = Column(Float, nullable=False, default=0.0)
    target_value = Column(Float, nullable=False, default=0.0)
    progress_pct = Column(Float, nullable=False, default=0.0)
    on_track = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("goal_id", "snapshot_date", name="uq_goal_snapshot_date"),
    )

    # Relationships
    goal = relationship("ReportGoal", back_populates="progress_snapshots")
    user = relationship("User")


class ReportSchedule(Base):
    """
    Report delivery configuration — defines when and how reports are generated.

    Each schedule can link to multiple goals and deliver to multiple recipients.
    """
    __tablename__ = "report_schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)  # null = all accounts
    name = Column(String, nullable=False)  # e.g. "Weekly Performance Report"
    periodicity = Column(String, nullable=False)  # Human-readable label (derived)
    schedule_type = Column(String, nullable=True)  # daily/weekly/monthly/quarterly/yearly
    schedule_days = Column(String, nullable=True)  # JSON: weekday ints, day-of-month ints, etc.
    quarter_start_month = Column(Integer, nullable=True)  # 1-12, for quarterly schedules
    period_window = Column(String, default="full_prior")  # full_prior/wtd/mtd/qtd/ytd/trailing
    lookback_value = Column(Integer, nullable=True)  # N for trailing window
    lookback_unit = Column(String, nullable=True)  # days/weeks/months/years for trailing
    force_standard_days = Column(String, nullable=True)  # JSON: days that skip auto-prior wrap-up
    show_expense_lookahead = Column(Boolean, default=True)
    is_enabled = Column(Boolean, default=True)
    recipients = Column(JSON, nullable=True)  # List of email addresses
    ai_provider = Column(String, nullable=True)  # claude/openai/gemini — null = user's default
    generate_ai_summary = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Chart display settings
    chart_horizon = Column(String, default="auto")  # "auto", "elapsed", "full", or integer days
    chart_lookahead_multiplier = Column(Float, default=1.0)  # For auto/elapsed: multiplier × base
    show_minimap = Column(Boolean, default=True)  # Show minimap when chart doesn't reach target

    # Relationships
    user = relationship("User", back_populates="report_schedules")
    account = relationship("Account")
    goal_links = relationship(
        "ReportScheduleGoal", back_populates="schedule", cascade="all, delete-orphan"
    )
    reports = relationship("Report", back_populates="schedule")


class ReportScheduleGoal(Base):
    """Junction table linking report schedules to goals (many-to-many)."""
    __tablename__ = "report_schedule_goals"

    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(
        Integer, ForeignKey("report_schedules.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    goal_id = Column(
        Integer, ForeignKey("report_goals.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("schedule_id", "goal_id", name="uq_schedule_goal"),
    )

    # Relationships
    schedule = relationship("ReportSchedule", back_populates="goal_links")
    goal = relationship("ReportGoal", back_populates="schedule_links")


class Report(Base):
    """
    Generated report instance — stores metrics, HTML, PDF, and AI summary.

    Reports are created either manually (on-demand) or by the scheduler,
    and can be viewed in-app or downloaded as PDF.
    """
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    schedule_id = Column(Integer, ForeignKey("report_schedules.id", ondelete="SET NULL"), nullable=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    periodicity = Column(String, nullable=False)  # Frozen copy from schedule
    report_data = Column(JSON, nullable=True)  # All numeric metrics
    html_content = Column(Text, nullable=True)  # Full rendered HTML
    pdf_content = Column(LargeBinary, nullable=True)  # PDF bytes
    ai_summary = Column(Text, nullable=True)  # AI-generated analysis
    ai_provider_used = Column(String, nullable=True)  # Which provider generated summary
    delivery_status = Column(String, nullable=False, default="pending")  # pending/sent/failed/manual
    delivered_at = Column(DateTime, nullable=True)
    delivery_recipients = Column(JSON, nullable=True)  # Snapshot of who received it
    delivery_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="reports")
    schedule = relationship("ReportSchedule", back_populates="reports")


class AccountTransfer(Base):
    """
    Deposit/withdrawal tracking for accurate P&L calculation.

    Records are created either by syncing with the Coinbase API or by manual entry.
    Used to distinguish real trading gains from capital injections/withdrawals in
    reports, dashboard projections, and account value charts.
    """
    __tablename__ = "account_transfers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    account_id = Column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    external_id = Column(String, unique=True, nullable=True)  # Coinbase txn ID (dedup)
    transfer_type = Column(String, nullable=False)  # 'deposit' or 'withdrawal'
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False)  # 'USD', 'BTC', etc.
    amount_usd = Column(Float, nullable=True)  # USD equivalent at time of transfer
    occurred_at = Column(DateTime, nullable=False, index=True)
    source = Column(String, default="coinbase_api")  # 'coinbase_api' or 'manual'
    original_type = Column(String, nullable=True)  # Coinbase txn type: cardspend, fiat_withdrawal, etc.
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="account_transfers")
    account = relationship("Account")
