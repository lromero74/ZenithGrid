"""Add account_id to report_goals and reports tables for account-scoped filtering."""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Add account_id to report_goals
    try:
        cursor.execute(
            "ALTER TABLE report_goals ADD COLUMN "
            "account_id INTEGER REFERENCES accounts(id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_report_goals_account_id "
            "ON report_goals(account_id)"
        )
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise

    # Add account_id to reports
    try:
        cursor.execute(
            "ALTER TABLE reports ADD COLUMN "
            "account_id INTEGER REFERENCES accounts(id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_reports_account_id "
            "ON reports(account_id)"
        )
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise

    # Backfill: set account_id on existing goals to the user's default account
    try:
        cursor.execute("""
            UPDATE report_goals
            SET account_id = (
                SELECT a.id FROM accounts a
                WHERE a.user_id = report_goals.user_id
                  AND a.is_default = 1
                LIMIT 1
            )
            WHERE account_id IS NULL
        """)
    except Exception:
        pass  # Best-effort backfill

    # Backfill: set account_id on existing reports from their schedule's
    # account_id, falling back to the user's default account
    try:
        cursor.execute("""
            UPDATE reports
            SET account_id = COALESCE(
                (SELECT rs.account_id FROM report_schedules rs
                 WHERE rs.id = reports.schedule_id),
                (SELECT a.id FROM accounts a
                 WHERE a.user_id = reports.user_id
                   AND a.is_default = 1
                 LIMIT 1)
            )
            WHERE account_id IS NULL
        """)
    except Exception:
        pass  # Best-effort backfill

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
