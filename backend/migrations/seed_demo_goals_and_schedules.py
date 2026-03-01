"""
Seed demo user goals and report schedules.

Each demo user (demo_usd, demo_btc, demo_both) gets:
- 2 balance goals (currency-appropriate targets)
- 1 small expense goal with sample items
- 1 large expense-covering goal with realistic household items + 25% tax
- 3 schedules (weekly, monthly, semi-monthly expense) with no email recipients

Idempotent: skips users who already have goals.
"""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)

MIGRATION_NAME = "seed_demo_goals_and_schedules"

# Target date: ~12 months from now
TARGET_DATE = (datetime.utcnow() + timedelta(days=365)).strftime("%Y-12-31 23:59:59")
NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

# Demo user configs — each user has a distinct expense personality
DEMO_CONFIGS = {
    "demo_usd": {
        "goals": [
            {
                "name": "Grow Paper Portfolio to $2,000",
                "target_type": "balance",
                "target_currency": "USD",
                "target_value": 2000.0,
                "time_horizon_months": 12,
            },
            {
                "name": "Build $500 Emergency Fund",
                "target_type": "balance",
                "target_currency": "USD",
                "target_value": 500.0,
                "time_horizon_months": 12,
            },
            {
                "name": "Cover Monthly Basics",
                "target_type": "expenses",
                "target_currency": "USD",
                "target_value": 90.0,
                "time_horizon_months": 12,
                "expense_period": "monthly",
                "tax_withholding_pct": 0.0,
                "expenses": [
                    {"name": "Streaming Services", "amount": 15.99,
                     "category": "Entertainment",
                     "frequency": "monthly", "due_day": 5},
                    {"name": "Cloud Storage", "amount": 9.99,
                     "category": "Utilities",
                     "frequency": "monthly", "due_day": 12},
                    {"name": "Phone Plan", "amount": 25.00,
                     "category": "Utilities",
                     "frequency": "monthly", "due_day": 19},
                    {"name": "Coffee Fund", "amount": 40.00,
                     "category": "Food",
                     "frequency": "monthly", "due_day": 1},
                ],
            },
            # Renter lifestyle — car payment, student loans, vacation fund
            {
                "name": "Cover Monthly Household Expenses",
                "target_type": "expenses",
                "target_currency": "USD",
                "target_value": 3761.47,
                "time_horizon_months": 12,
                "expense_period": "monthly",
                "tax_withholding_pct": 25.0,
                "expenses": [
                    {"name": "Rent / Mortgage", "amount": 1450.00,
                     "category": "Housing", "frequency": "monthly", "due_day": 1},
                    {"name": "Electric & Gas", "amount": 145.00,
                     "category": "Utilities", "frequency": "monthly", "due_day": 5},
                    {"name": "Water & Sewer", "amount": 55.00,
                     "category": "Utilities", "frequency": "monthly", "due_day": 10},
                    {"name": "Internet & Cable", "amount": 89.99,
                     "category": "Utilities", "frequency": "monthly", "due_day": 3},
                    {"name": "Cell Phone", "amount": 65.00,
                     "category": "Utilities", "frequency": "monthly", "due_day": 19},
                    {"name": "Health Insurance", "amount": 320.00,
                     "category": "Insurance", "frequency": "monthly", "due_day": 1},
                    {"name": "Auto Insurance", "amount": 148.00,
                     "category": "Insurance", "frequency": "monthly", "due_day": 15},
                    {"name": "Renters / Home Insurance", "amount": 42.00,
                     "category": "Insurance", "frequency": "monthly", "due_day": 1},
                    {"name": "Groceries", "amount": 150.00,
                     "category": "Food", "frequency": "weekly", "due_day": 5},
                    {"name": "Car Payment", "amount": 385.00,
                     "category": "Transportation", "frequency": "monthly", "due_day": 12},
                    {"name": "Gas & Fuel", "amount": 120.00,
                     "category": "Transportation", "frequency": "monthly", "due_day": None},
                    {"name": "Netflix", "amount": 15.49,
                     "category": "Entertainment", "frequency": "monthly", "due_day": 8},
                    {"name": "Spotify", "amount": 10.99,
                     "category": "Entertainment", "frequency": "monthly", "due_day": 8},
                    {"name": "Dining Out", "amount": 100.00,
                     "category": "Entertainment", "frequency": "monthly", "due_day": None},
                    {"name": "Prescriptions", "amount": 35.00,
                     "category": "Healthcare", "frequency": "monthly", "due_day": 20},
                    {"name": "Emergency Fund Contribution", "amount": 200.00,
                     "category": "Invest", "frequency": "monthly", "due_day": 1},
                    {"name": "Vacation Fund", "amount": 150.00,
                     "category": "Other", "frequency": "monthly", "due_day": 1},
                    {"name": "Student Loan Payment", "amount": 280.00,
                     "category": "Education", "frequency": "monthly", "due_day": 25},
                ],
            },
        ],
    },
    "demo_btc": {
        "goals": [
            {
                "name": "Stack 0.05 BTC",
                "target_type": "balance",
                "target_currency": "BTC",
                "target_value": 0.05,
                "time_horizon_months": 12,
            },
            {
                "name": "Accumulate 0.02 BTC Reserve",
                "target_type": "balance",
                "target_currency": "BTC",
                "target_value": 0.02,
                "time_horizon_months": 12,
            },
            {
                "name": "Monthly Running Costs",
                "target_type": "expenses",
                "target_currency": "USD",
                "target_value": 150.0,
                "time_horizon_months": 12,
                "expense_period": "monthly",
                "tax_withholding_pct": 0.0,
                "expenses": [
                    {"name": "Gym Membership", "amount": 30.00,
                     "category": "Healthcare",
                     "frequency": "monthly", "due_day": 1},
                    {"name": "App Subscriptions", "amount": 19.99,
                     "category": "Entertainment",
                     "frequency": "monthly", "due_day": 8},
                    {"name": "Savings Goal", "amount": 100.00,
                     "category": "Invest",
                     "frequency": "monthly", "due_day": 15},
                ],
            },
            # Urban minimalist — studio, metro, gaming, courses, Roth IRA
            {
                "name": "Replace Day Job Income",
                "target_type": "expenses",
                "target_currency": "USD",
                "target_value": 2285.95,
                "time_horizon_months": 12,
                "expense_period": "monthly",
                "tax_withholding_pct": 25.0,
                "expenses": [
                    {"name": "Studio Apartment", "amount": 975.00,
                     "category": "Housing", "frequency": "monthly", "due_day": 1},
                    {"name": "Electric", "amount": 85.00,
                     "category": "Utilities", "frequency": "monthly", "due_day": 5},
                    {"name": "Internet (Fiber)", "amount": 69.99,
                     "category": "Utilities", "frequency": "monthly", "due_day": 3},
                    {"name": "Phone Plan", "amount": 45.00,
                     "category": "Utilities", "frequency": "monthly", "due_day": 19},
                    {"name": "Health Insurance (Marketplace)", "amount": 275.00,
                     "category": "Insurance", "frequency": "monthly", "due_day": 1},
                    {"name": "Grocery Budget", "amount": 100.00,
                     "category": "Food", "frequency": "weekly", "due_day": 5},
                    {"name": "Metro Pass", "amount": 127.00,
                     "category": "Transportation", "frequency": "monthly", "due_day": 1},
                    {"name": "YouTube Premium", "amount": 13.99,
                     "category": "Entertainment", "frequency": "monthly", "due_day": 12},
                    {"name": "Gaming Subscription", "amount": 14.99,
                     "category": "Entertainment", "frequency": "monthly", "due_day": 12},
                    {"name": "Weekend Activities", "amount": 80.00,
                     "category": "Entertainment", "frequency": "monthly", "due_day": None},
                    {"name": "Gym Membership", "amount": 49.99,
                     "category": "Healthcare", "frequency": "monthly", "due_day": 1},
                    {"name": "Coffee & Snacks", "amount": 60.00,
                     "category": "Food", "frequency": "monthly", "due_day": None},
                    {"name": "Online Courses", "amount": 39.99,
                     "category": "Education", "frequency": "monthly", "due_day": 15},
                    {"name": "Roth IRA Contribution", "amount": 250.00,
                     "category": "Invest", "frequency": "monthly", "due_day": 1},
                    {"name": "Travel Fund", "amount": 100.00,
                     "category": "Other", "frequency": "monthly", "due_day": 1},
                ],
            },
        ],
    },
    "demo_both": {
        "goals": [
            {
                "name": "Reach $1,500 USD",
                "target_type": "balance",
                "target_currency": "USD",
                "target_value": 1500.0,
                "time_horizon_months": 12,
            },
            {
                "name": "Accumulate 0.025 BTC",
                "target_type": "balance",
                "target_currency": "BTC",
                "target_value": 0.025,
                "time_horizon_months": 12,
            },
            {
                "name": "Monthly Budget",
                "target_type": "expenses",
                "target_currency": "USD",
                "target_value": 110.0,
                "time_horizon_months": 12,
                "expense_period": "monthly",
                "tax_withholding_pct": 0.0,
                "expenses": [
                    {"name": "Internet Service", "amount": 59.99,
                     "category": "Utilities",
                     "frequency": "monthly", "due_day": 3},
                    {"name": "Cloud Backup", "amount": 9.99,
                     "category": "Utilities",
                     "frequency": "monthly", "due_day": 10},
                    {"name": "Lunch Fund", "amount": 40.00,
                     "category": "Food",
                     "frequency": "monthly", "due_day": 1},
                ],
            },
            # Family household — mortgage, HOA, 2 cars, kids, 401k, charity
            {
                "name": "Achieve Financial Freedom",
                "target_type": "expenses",
                "target_currency": "USD",
                "target_value": 6334.98,
                "time_horizon_months": 12,
                "expense_period": "monthly",
                "tax_withholding_pct": 25.0,
                "expenses": [
                    {"name": "Mortgage", "amount": 1850.00,
                     "category": "Housing", "frequency": "monthly", "due_day": 1},
                    {"name": "HOA Fees", "amount": 185.00,
                     "category": "Housing", "frequency": "monthly", "due_day": 1},
                    {"name": "Electric & Gas", "amount": 175.00,
                     "category": "Utilities", "frequency": "monthly", "due_day": 5},
                    {"name": "Water & Trash", "amount": 65.00,
                     "category": "Utilities", "frequency": "monthly", "due_day": 10},
                    {"name": "Internet", "amount": 79.99,
                     "category": "Utilities", "frequency": "monthly", "due_day": 3},
                    {"name": "Family Phone Plan", "amount": 140.00,
                     "category": "Utilities", "frequency": "monthly", "due_day": 19},
                    {"name": "Family Health Insurance", "amount": 580.00,
                     "category": "Insurance", "frequency": "monthly", "due_day": 1},
                    {"name": "Auto Insurance (2 cars)", "amount": 265.00,
                     "category": "Insurance", "frequency": "monthly", "due_day": 15},
                    {"name": "Home Insurance", "amount": 125.00,
                     "category": "Insurance", "frequency": "monthly", "due_day": 1},
                    {"name": "Life Insurance", "amount": 45.00,
                     "category": "Insurance", "frequency": "monthly", "due_day": 1},
                    {"name": "Family Groceries", "amount": 250.00,
                     "category": "Food", "frequency": "weekly", "due_day": 5},
                    {"name": "Car Payment #1", "amount": 425.00,
                     "category": "Transportation", "frequency": "monthly", "due_day": 10},
                    {"name": "Car Payment #2", "amount": 310.00,
                     "category": "Transportation", "frequency": "monthly", "due_day": 18},
                    {"name": "Gas (2 vehicles)", "amount": 200.00,
                     "category": "Transportation", "frequency": "monthly",
                     "due_day": None},
                    {"name": "After-School Programs", "amount": 180.00,
                     "category": "Education", "frequency": "monthly", "due_day": 1},
                    {"name": "College Savings (529)", "amount": 200.00,
                     "category": "Education", "frequency": "monthly", "due_day": 1},
                    {"name": "Streaming Bundle", "amount": 29.99,
                     "category": "Entertainment", "frequency": "monthly", "due_day": 8},
                    {"name": "Family Dining Out", "amount": 200.00,
                     "category": "Entertainment", "frequency": "monthly",
                     "due_day": None},
                    {"name": "Dental & Vision", "amount": 75.00,
                     "category": "Healthcare", "frequency": "monthly", "due_day": 1},
                    {"name": "Prescriptions", "amount": 55.00,
                     "category": "Healthcare", "frequency": "monthly", "due_day": 20},
                    {"name": "401k Match Contribution", "amount": 500.00,
                     "category": "Invest", "frequency": "monthly", "due_day": 1},
                    {"name": "Family Vacation Fund", "amount": 300.00,
                     "category": "Other", "frequency": "monthly", "due_day": 1},
                    {"name": "Charitable Giving", "amount": 100.00,
                     "category": "Donations", "frequency": "monthly", "due_day": 1},
                ],
            },
        ],
    },
}


async def run_migration(db):
    """Seed demo user goals and schedules."""

    for email, config in DEMO_CONFIGS.items():
        # Get user ID and paper account ID
        result = await db.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        )
        row = result.fetchone()
        if not row:
            logger.info(f"Demo user '{email}' not found, skipping")
            continue
        user_id = row[0]

        # Check if user already has goals (idempotent)
        result = await db.execute(
            text("SELECT COUNT(*) FROM report_goals WHERE user_id = :uid"),
            {"uid": user_id},
        )
        existing = result.scalar()
        if existing and existing > 0:
            logger.info(
                f"Demo user '{email}' already has {existing} goals, skipping"
            )
            continue

        # Get paper trading account ID
        result = await db.execute(
            text(
                "SELECT id FROM accounts "
                "WHERE user_id = :uid AND is_paper_trading = 1 LIMIT 1"
            ),
            {"uid": user_id},
        )
        acct_row = result.fetchone()
        account_id = acct_row[0] if acct_row else None

        goal_ids = []

        # Create goals
        for goal_cfg in config["goals"]:
            expense_period = goal_cfg.get("expense_period")
            tax_pct = goal_cfg.get("tax_withholding_pct", 0.0)

            # Recalculate expense target from items
            target_value = goal_cfg["target_value"]
            expenses = goal_cfg.get("expenses", [])
            if expenses:
                total = sum(e["amount"] for e in expenses)
                target_value = total

            await db.execute(
                text("""
                    INSERT INTO report_goals (
                        user_id, name, target_type, target_currency,
                        target_value, time_horizon_months,
                        start_date, target_date, account_id,
                        expense_period, tax_withholding_pct,
                        expense_sort_mode, chart_horizon,
                        show_minimap, created_at, updated_at
                    ) VALUES (
                        :user_id, :name, :target_type, :target_currency,
                        :target_value, :time_horizon_months,
                        :start_date, :target_date, :account_id,
                        :expense_period, :tax_pct,
                        :expense_sort_mode, 'auto',
                        1, :now, :now
                    )
                """),
                {
                    "user_id": user_id,
                    "name": goal_cfg["name"],
                    "target_type": goal_cfg["target_type"],
                    "target_currency": goal_cfg["target_currency"],
                    "target_value": target_value,
                    "time_horizon_months": goal_cfg["time_horizon_months"],
                    "start_date": NOW,
                    "target_date": TARGET_DATE,
                    "account_id": account_id,
                    "expense_period": expense_period,
                    "tax_pct": tax_pct,
                    "expense_sort_mode": (
                        "amount_asc" if expense_period else None
                    ),
                    "now": NOW,
                },
            )

            # Get the inserted goal ID
            result = await db.execute(
                text(
                    "SELECT id FROM report_goals "
                    "WHERE user_id = :uid AND name = :name"
                ),
                {"uid": user_id, "name": goal_cfg["name"]},
            )
            goal_row = result.fetchone()
            goal_id = goal_row[0] if goal_row else None
            if goal_id:
                goal_ids.append(goal_id)

            # Create expense items
            for idx, expense in enumerate(expenses):
                await db.execute(
                    text("""
                        INSERT INTO expense_items (
                            goal_id, user_id, category, name, amount,
                            frequency, due_day, sort_order,
                            created_at, updated_at
                        ) VALUES (
                            :goal_id, :user_id, :category, :name, :amount,
                            :frequency, :due_day, :sort_order,
                            :now, :now
                        )
                    """),
                    {
                        "goal_id": goal_id,
                        "user_id": user_id,
                        "category": expense["category"],
                        "name": expense["name"],
                        "amount": expense["amount"],
                        "frequency": expense["frequency"],
                        "due_day": expense.get("due_day"),
                        "sort_order": idx,
                        "now": NOW,
                    },
                )

        # Create schedules (no email recipients)
        # Weekly schedule (Mon + Thu) — WTD
        await db.execute(
            text("""
                INSERT INTO report_schedules (
                    user_id, name, periodicity, schedule_type,
                    schedule_days, period_window, is_enabled,
                    recipients, account_id, ai_provider,
                    generate_ai_summary, show_expense_lookahead,
                    chart_horizon, chart_lookahead_multiplier,
                    show_minimap, created_at, updated_at
                ) VALUES (
                    :user_id, 'Weekly Report',
                    'Every Mon (wrap-up), Thu - WTD',
                    'weekly', :schedule_days, 'wtd', 1, '[]',
                    :account_id, 'gemini', 1, 1, 'auto',
                    1.0, 1, :now, :now
                )
            """),
            {
                "user_id": user_id,
                "schedule_days": json.dumps([0, 3]),
                "account_id": account_id,
                "now": NOW,
            },
        )

        # Get weekly schedule ID for goal linking
        result = await db.execute(
            text(
                "SELECT id FROM report_schedules "
                "WHERE user_id = :uid AND name = 'Weekly Report'"
            ),
            {"uid": user_id},
        )
        weekly_id = result.fetchone()
        weekly_schedule_id = weekly_id[0] if weekly_id else None

        # Monthly schedule (1st + 15th) — MTD
        await db.execute(
            text("""
                INSERT INTO report_schedules (
                    user_id, name, periodicity, schedule_type,
                    schedule_days, period_window, is_enabled,
                    recipients, account_id, ai_provider,
                    generate_ai_summary, show_expense_lookahead,
                    chart_horizon, chart_lookahead_multiplier,
                    show_minimap, created_at, updated_at
                ) VALUES (
                    :user_id, 'Monthly Report',
                    'Monthly on 1st (wrap-up) & 15th - MTD',
                    'monthly', :schedule_days, 'mtd', 1, '[]',
                    :account_id, 'gemini', 1, 1, 'auto',
                    1.0, 1, :now, :now
                )
            """),
            {
                "user_id": user_id,
                "schedule_days": json.dumps([1, 15]),
                "account_id": account_id,
                "now": NOW,
            },
        )

        result = await db.execute(
            text(
                "SELECT id FROM report_schedules "
                "WHERE user_id = :uid AND name = 'Monthly Report'"
            ),
            {"uid": user_id},
        )
        monthly_id = result.fetchone()
        monthly_schedule_id = monthly_id[0] if monthly_id else None

        # Semi-monthly expense report (1st + 15th) — MTD
        await db.execute(
            text("""
                INSERT INTO report_schedules (
                    user_id, name, periodicity, schedule_type,
                    schedule_days, period_window, is_enabled,
                    recipients, account_id, ai_provider,
                    generate_ai_summary, show_expense_lookahead,
                    chart_horizon, chart_lookahead_multiplier,
                    show_minimap, created_at, updated_at
                ) VALUES (
                    :user_id, 'Semi-Monthly Expense Report',
                    'Monthly on 1st (wrap-up) & 15th - MTD',
                    'monthly', :schedule_days, 'mtd', 1, '[]',
                    :account_id, 'gemini', 1, 1, 'auto',
                    1.0, 1, :now, :now
                )
            """),
            {
                "user_id": user_id,
                "schedule_days": json.dumps([1, 15]),
                "account_id": account_id,
                "now": NOW,
            },
        )

        result = await db.execute(
            text(
                "SELECT id FROM report_schedules "
                "WHERE user_id = :uid AND name = 'Semi-Monthly Expense Report'"
            ),
            {"uid": user_id},
        )
        semi_monthly_id = result.fetchone()
        semi_monthly_schedule_id = semi_monthly_id[0] if semi_monthly_id else None

        # Link all goals to all schedules
        for schedule_id in [
            weekly_schedule_id, monthly_schedule_id, semi_monthly_schedule_id
        ]:
            if not schedule_id:
                continue
            for goal_id in goal_ids:
                await db.execute(
                    text("""
                        INSERT OR IGNORE INTO report_schedule_goals
                        (schedule_id, goal_id)
                        VALUES (:sid, :gid)
                    """),
                    {"sid": schedule_id, "gid": goal_id},
                )

        logger.info(
            f"Seeded {email}: {len(goal_ids)} goals, 3 schedules"
        )

    await db.commit()
    logger.info("Demo goals and schedules seeding complete")
