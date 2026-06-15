"""
Align foreign-key ON DELETE policies on the live PostgreSQL schema with the models.

Financial-record FKs become RESTRICT (a stray parent delete can never silently
cascade away trading history); analysis-link FKs become SET NULL (keep the analysis
row, just unlink it); derived snapshots stay CASCADE. This mirrors the explicit
``ondelete=`` declarations on the SQLAlchemy models (see
backend/tests/test_fk_delete_policies.py) and the raw SQL in setup.py, so all three
init paths agree.

Pre-existing referential debt
-----------------------------
The original schema used unenforced FKs (and the SQLite->Postgres bulk load never
validated them), so the live DB accumulated orphan rows whose FK points at a parent
that no longer exists. PostgreSQL validates rows when ADDing a constraint, so this
migration first cleans orphans per the column's policy, then rewrites the constraint:

  * SET NULL columns we keep (order_history.position_id/bot_id, ai_opinion_log.*):
    null the orphan's FK value — exactly what a future parent delete would do.
  * signals.position_id: the FK is SET NULL going forward, but a signal's whole
    meaning is its position, so the millions of pre-existing context-less orphans are
    DELETED rather than kept as NULL-linked noise (owner decision, 2026-06-15).
  * pending_orders (RESTRICT, NOT NULL): orphans can't be nulled, so terminal-status
    orphans are DELETED. A non-terminal orphan (possible live exchange order) makes the
    migration REFUSE and stop — never silently drop a live order.
  * trades/positions (RESTRICT): must already be clean; orphans here would mean
    corrupted financial records, so the migration stops rather than delete them.

order_history.bot_id additionally has its NOT NULL dropped (it becomes a nullable
SET NULL link, consistent with order_history.position_id — an audit row outlives the
bot it referenced).

PostgreSQL only. On SQLite (the dev default) this is a no-op: SQLite can't ALTER a
foreign-key constraint without rebuilding the table, and fresh SQLite installs already
get the correct policy from Base.metadata.create_all()/setup.py.

Idempotent: a constraint whose delete_rule already matches the target is skipped, so
re-running after success is a cheap series of reads.
"""

from migrations.db_utils import get_migration_connection, is_postgres

SCHEMA = "trading"

# Statuses in which a pending_order is finished — safe to delete if orphaned.
# Anything else (pending / partially_filled / ...) may map to a live exchange order.
TERMINAL_PENDING_STATUSES = ("canceled", "cancelled", "filled", "expired", "failed", "rejected")

# (table, column, parent_table, target_rule, orphan_strategy)
#   orphan_strategy: how to clean pre-existing orphans before ADDing the constraint
#     "require_clean" — must already be 0; raise otherwise (protects financial records)
#     "null"          — set the orphan FK to NULL (keep the row, unlink)
#     "delete"        — delete the orphan rows
#     "pending"       — special: delete terminal orphans, refuse on a live one
FK_POLICIES = [
    ("trades", "position_id", "positions", "RESTRICT", "require_clean"),
    ("positions", "account_id", "accounts", "RESTRICT", "require_clean"),
    ("positions", "bot_id", "bots", "RESTRICT", "require_clean"),
    ("pending_orders", "position_id", "positions", "RESTRICT", "pending"),
    ("pending_orders", "bot_id", "bots", "RESTRICT", "pending"),
    ("order_history", "bot_id", "bots", "SET NULL", "null"),
    ("signals", "position_id", "positions", "SET NULL", "delete"),
    ("order_history", "position_id", "positions", "SET NULL", "null"),
    ("ai_opinion_log", "account_id", "accounts", "SET NULL", "null"),
    ("ai_opinion_log", "bot_id", "bots", "SET NULL", "null"),
    ("ai_opinion_log", "position_id", "positions", "SET NULL", "null"),
]

# Columns whose NOT NULL must be dropped so SET NULL is valid.
DROP_NOT_NULL = {("order_history", "bot_id")}


def _orphan_predicate(table, column, parent):
    """SQL predicate selecting rows whose non-null FK has no matching parent."""
    return (
        f"{column} IS NOT NULL AND NOT EXISTS "
        f"(SELECT 1 FROM {SCHEMA}.{parent} p WHERE p.id = {SCHEMA}.{table}.{column})"
    )


def _count_orphans(cur, table, column, parent):
    cur.execute(f"SELECT count(*) FROM {SCHEMA}.{table} WHERE {_orphan_predicate(table, column, parent)}")
    return cur.fetchone()[0]


def _existing_fk(cur, table, column):
    """(constraint_name, delete_rule) for the single-column FK on schema.table(column),
    or (None, None) if no such FK exists."""
    cur.execute(
        """
        SELECT tc.constraint_name, rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.referential_constraints rc
          ON tc.constraint_name = rc.constraint_name AND tc.constraint_schema = rc.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = %s AND tc.table_name = %s AND kcu.column_name = %s
        """,
        (SCHEMA, table, column),
    )
    row = cur.fetchone()
    return (row[0], row[1]) if row else (None, None)


def _clean_orphans(conn, cur, table, column, parent, strategy):
    """Pre-clean orphans per strategy. Returns a short human description of what it did."""
    n = _count_orphans(cur, table, column, parent)
    if n == 0:
        return "no orphans"

    if strategy == "require_clean":
        raise RuntimeError(
            f"{n} orphaned {table}.{column} -> {parent} (financial records) — refusing to "
            f"add RESTRICT over corrupted references; investigate before re-running."
        )

    if strategy == "null":
        cur.execute(f"UPDATE {SCHEMA}.{table} SET {column} = NULL WHERE {_orphan_predicate(table, column, parent)}")
        conn.commit()
        return f"nulled {n} orphan(s)"

    if strategy == "delete":
        # Batch to keep the transaction / WAL bounded on a small box.
        deleted = 0
        while True:
            cur.execute(
                f"DELETE FROM {SCHEMA}.{table} WHERE id IN "
                f"(SELECT id FROM {SCHEMA}.{table} WHERE {_orphan_predicate(table, column, parent)} LIMIT 50000)"
            )
            batch = cur.rowcount
            conn.commit()
            deleted += batch
            if batch == 0:
                break
        return f"deleted {deleted} orphan(s)"

    if strategy == "pending":
        active = _count_orphans_active_pending(cur)
        if active:
            raise RuntimeError(
                f"{active} orphaned pending_orders in a non-terminal status — refusing to delete "
                f"(possible live exchange orders); investigate before re-running."
            )
        cur.execute(
            f"DELETE FROM {SCHEMA}.pending_orders po WHERE "
            f"(po.position_id IS NOT NULL AND NOT EXISTS "
            f"(SELECT 1 FROM {SCHEMA}.positions p WHERE p.id = po.position_id)) "
            f"OR (po.bot_id IS NOT NULL AND NOT EXISTS "
            f"(SELECT 1 FROM {SCHEMA}.bots b WHERE b.id = po.bot_id))"
        )
        deleted = cur.rowcount
        conn.commit()
        return f"deleted {deleted} terminal orphan(s)"

    raise ValueError(f"unknown orphan strategy {strategy!r}")


def _count_orphans_active_pending(cur):
    placeholders = ", ".join(["%s"] * len(TERMINAL_PENDING_STATUSES))
    cur.execute(
        f"SELECT count(*) FROM {SCHEMA}.pending_orders po WHERE po.status NOT IN ({placeholders}) AND ("
        f"(po.position_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.positions p WHERE p.id = po.position_id)) "
        f"OR (po.bot_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.bots b WHERE b.id = po.bot_id)))",
        TERMINAL_PENDING_STATUSES,
    )
    return cur.fetchone()[0]


def run():
    print("Migration set_fk_delete_policies: aligning FK ON DELETE rules...")

    if not is_postgres():
        print("  SQLite detected — no-op (create_all/setup.py already set the policy).")
        return

    conn = get_migration_connection()
    cur = conn.cursor()
    changed = 0
    try:
        for table, column, parent, target_rule, strategy in FK_POLICIES:
            name, current_rule = _existing_fk(cur, table, column)
            if name is not None and current_rule == target_rule:
                print(f"  {table}.{column}: already {target_rule}, skipping")
                continue

            note = _clean_orphans(conn, cur, table, column, parent, strategy)

            if (table, column) in DROP_NOT_NULL:
                cur.execute(f"ALTER TABLE {SCHEMA}.{table} ALTER COLUMN {column} DROP NOT NULL")

            if name is not None:
                cur.execute(f'ALTER TABLE {SCHEMA}.{table} DROP CONSTRAINT "{name}"')
            canonical = f"{table}_{column}_fkey"
            cur.execute(
                f'ALTER TABLE {SCHEMA}.{table} ADD CONSTRAINT "{canonical}" '
                f"FOREIGN KEY ({column}) REFERENCES {SCHEMA}.{parent}(id) ON DELETE {target_rule}"
            )
            conn.commit()
            verb = "set" if name is None else f"changed {current_rule} ->"
            print(f"  {table}.{column}: {note}; {verb} {target_rule}")
            changed += 1
    except Exception as e:
        conn.rollback()
        print(f"  Failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()

    print(f"Migration set_fk_delete_policies complete ({changed} constraint(s) updated)")


if __name__ == "__main__":
    run()
