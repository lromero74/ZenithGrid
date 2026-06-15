"""
Align foreign-key ON DELETE policies on the live PostgreSQL schema with the models.

Financial-record FKs become RESTRICT (a stray parent delete can never silently
cascade away trading history); nullable analysis-link FKs become SET NULL (keep the
analysis row, just unlink it); derived snapshots stay CASCADE. This mirrors the
explicit ``ondelete=`` declarations now carried on the SQLAlchemy models (see
backend/tests/test_fk_delete_policies.py) and the raw SQL in setup.py, so all three
init paths agree.

PostgreSQL only. On SQLite (the dev default) this is a no-op: SQLite can't ALTER a
foreign-key constraint without rebuilding the table, and fresh SQLite installs already
get the correct policy from Base.metadata.create_all()/setup.py. Existing prod is
PostgreSQL, which is the database this migration exists to fix.

Idempotent: for each FK it reads the current delete_rule and only rewrites the
constraint when it differs from the target. Re-running is a cheap series of reads.
"""

from migrations.db_utils import get_migration_connection, is_postgres

SCHEMA = "trading"

# (table, column, parent_table, target_rule). Parent is always <parent_table>.id.
FK_POLICIES = [
    # RESTRICT — financial records must never be cascaded away.
    ("trades", "position_id", "positions", "RESTRICT"),
    ("positions", "account_id", "accounts", "RESTRICT"),
    ("positions", "bot_id", "bots", "RESTRICT"),
    ("pending_orders", "position_id", "positions", "RESTRICT"),
    ("pending_orders", "bot_id", "bots", "RESTRICT"),
    ("order_history", "bot_id", "bots", "RESTRICT"),
    # SET NULL — analysis rows outlive the parent they referenced, just unlinked.
    ("signals", "position_id", "positions", "SET NULL"),
    ("order_history", "position_id", "positions", "SET NULL"),
    ("ai_opinion_log", "account_id", "accounts", "SET NULL"),
    ("ai_opinion_log", "bot_id", "bots", "SET NULL"),
    ("ai_opinion_log", "position_id", "positions", "SET NULL"),
]


def _existing_fk(cursor, table, column):
    """Return (constraint_name, delete_rule) for the single-column FK on
    schema.table(column), or (None, None) if no such FK exists."""
    cursor.execute(
        """
        SELECT tc.constraint_name, rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.referential_constraints rc
          ON tc.constraint_name = rc.constraint_name
         AND tc.constraint_schema = rc.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = %s
          AND tc.table_name = %s
          AND kcu.column_name = %s
        """,
        (SCHEMA, table, column),
    )
    row = cursor.fetchone()
    return (row[0], row[1]) if row else (None, None)


def run():
    print("Migration set_fk_delete_policies: aligning FK ON DELETE rules...")

    if not is_postgres():
        print("  SQLite detected — no-op (create_all/setup.py already set the policy).")
        return

    conn = get_migration_connection()
    cursor = conn.cursor()
    changed = 0
    try:
        for table, column, parent, target_rule in FK_POLICIES:
            name, current_rule = _existing_fk(cursor, table, column)
            canonical = f"{table}_{column}_fkey"

            # information_schema reports SET NULL as "SET NULL", RESTRICT as
            # "RESTRICT". A plain FK (no ondelete) reports "NO ACTION".
            if name is not None and current_rule == target_rule:
                print(f"  {table}.{column}: already {target_rule}, skipping")
                continue

            if name is not None:
                cursor.execute(
                    f'ALTER TABLE {SCHEMA}.{table} DROP CONSTRAINT "{name}"'
                )

            cursor.execute(
                f'ALTER TABLE {SCHEMA}.{table} '
                f'ADD CONSTRAINT "{canonical}" '
                f'FOREIGN KEY ({column}) REFERENCES {SCHEMA}.{parent}(id) '
                f'ON DELETE {target_rule}'
            )
            conn.commit()
            verb = "set" if name is None else f"changed {current_rule} ->"
            print(f"  {table}.{column}: {verb} {target_rule}")
            changed += 1
    except Exception as e:
        conn.rollback()
        print(f"  Failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

    print(f"Migration set_fk_delete_policies complete ({changed} constraint(s) updated)")


if __name__ == "__main__":
    run()
