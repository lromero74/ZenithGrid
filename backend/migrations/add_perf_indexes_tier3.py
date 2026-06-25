"""
Add missing performance indexes found in the 2026-06-25 code-review sweep (tier 3).

These columns are filtered on hot paths but had no supporting index on prod
(verified against pg_indexes); without them the planner does full table scans
that worsen as the tables grow:

- ai_opinion_log(account_id)
    Per-account AI win-rate / speculative-calibration lookups scope by account_id.
- pending_orders(bot_id)
    Bot stop/cleanup and pending-order checks filter open orders by bot.
- speculative_weights_proposals(account_id)
    "Latest applied proposal per account" drives every speculative scoring run.
- rate_limit_attempts(category, key, attempted_at)
    The auth rate limiter counts on all three columns on every login/attempt;
    only individual indexes on category/key existed, forcing an index intersection.

Idempotent: skips any index that already exists (CREATE INDEX IF NOT EXISTS via a
name check), so it's safe to re-run. Table names are unqualified — the connection's
search_path resolves trading/auth.
"""

from migrations.db_utils import get_migration_connection, is_postgres


def _index_exists(conn, index_name):
    cursor = conn.cursor()
    try:
        if is_postgres():
            cursor.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index_name,))
        else:
            cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (index_name,)
            )
        return cursor.fetchone() is not None
    finally:
        cursor.close()


def _create_index(conn, index_name, table, columns):
    if _index_exists(conn, index_name):
        print(f"  Index {index_name} already exists, skipping")
        return False
    col_list = ", ".join(columns)
    cursor = conn.cursor()
    try:
        cursor.execute(f"CREATE INDEX {index_name} ON {table} ({col_list})")
        conn.commit()
        print(f"  Created index {index_name} on {table}({col_list})")
        return True
    except Exception as e:
        conn.rollback()
        print(f"  Failed to create index {index_name}: {e}")
        return False
    finally:
        cursor.close()


def run():
    print("Migration add_perf_indexes_tier3: adding missing performance indexes...")
    conn = get_migration_connection()

    indexes = [
        ("ix_ai_opinion_log_account_id", "ai_opinion_log", ["account_id"]),
        ("ix_pending_orders_bot_id", "pending_orders", ["bot_id"]),
        ("ix_spec_prop_account_id", "speculative_weights_proposals", ["account_id"]),
        ("ix_rate_limit_attempts_cat_key_at", "rate_limit_attempts",
         ["category", "key", "attempted_at"]),
    ]

    created = 0
    for index_name, table, columns in indexes:
        if _create_index(conn, index_name, table, columns):
            created += 1

    conn.close()
    print(f"Migration add_perf_indexes_tier3 complete: {created} index(es) created")


if __name__ == "__main__":
    run()
