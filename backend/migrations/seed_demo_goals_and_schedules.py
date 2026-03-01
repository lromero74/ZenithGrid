"""
Seed demo user goals and report schedules.

Each demo user (demo_usd, demo_btc, demo_both) gets:
- 2 balance goals (USD + BTC targets appropriate to their paper balances)
- 1 expense goal with sample expense items
- 2 schedules (weekly + monthly) with no email recipients

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

# Demo user configs: (email, account_name_pattern, goals, expenses)
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
                "target_value": 90.0,  # Will be recalculated from items
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

        # Link all goals to both schedules
        for schedule_id in [weekly_schedule_id, monthly_schedule_id]:
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
            f"Seeded {email}: {len(goal_ids)} goals, 2 schedules"
        )

    await db.commit()
    logger.info("Demo goals and schedules seeding complete")
