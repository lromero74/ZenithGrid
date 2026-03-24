"""
Migration 070: Add savings target fields to expense_items table.

Adds 7 new columns to reporting.expense_items to support savings target items
(item_type = 'savings_target') alongside regular expense items.

Idempotent: each column is added only if it doesn't already exist.
"""

from migrations.db_utils import get_migration_connection, is_postgres


def run():
    conn = get_migration_connection()
    cur = conn.cursor()

    try:
        if is_postgres():
            _run_postgres(cur)
        else:
            _run_sqlite(cur, conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _run_postgres(cur):
    columns = [
        ("item_type",                 "VARCHAR(20) NOT NULL DEFAULT 'expense'"),
        ("savings_target_amount",     "DOUBLE PRECISION"),
        ("savings_target_date",       "DATE"),
        ("savings_is_recurring",      "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("savings_recurrence_months", "INTEGER"),
        ("assumed_growth_rate_pct",   "DOUBLE PRECISION"),
        ("savings_current_balance",   "DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
    ]
    for col_name, col_def in columns:
        cur.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'reporting'
                      AND table_name   = 'expense_items'
                      AND column_name  = '{col_name}'
                ) THEN
                    ALTER TABLE reporting.expense_items
                        ADD COLUMN {col_name} {col_def};
                END IF;
            END $$;
        """)


def _run_sqlite(cur, conn):
    cur.execute("PRAGMA table_info(expense_items)")
    existing = {row[1] for row in cur.fetchall()}

    additions = [
        ("item_type",                 "TEXT NOT NULL DEFAULT 'expense'"),
        ("savings_target_amount",     "REAL"),
        ("savings_target_date",       "TEXT"),
        ("savings_is_recurring",      "INTEGER NOT NULL DEFAULT 0"),
        ("savings_recurrence_months", "INTEGER"),
        ("assumed_growth_rate_pct",   "REAL"),
        ("savings_current_balance",   "REAL NOT NULL DEFAULT 0.0"),
    ]
    for col_name, col_def in additions:
        if col_name not in existing:
            cur.execute(
                f"ALTER TABLE expense_items ADD COLUMN {col_name} {col_def}"
            )
            conn.commit()


if __name__ == "__main__":
    run()
    print("Migration 071 complete.")
