#!/usr/bin/env python3
"""
SQLite → PostgreSQL Data Migration
====================================

Reads all data from the SQLite trading.db and bulk-inserts into PostgreSQL.
Tables are migrated in foreign-key dependency order. After migration,
PostgreSQL sequences are reset to MAX(id) for each table.

Usage:
    cd /home/ec2-user/ZenithGrid/backend
    ./venv/bin/python3 scripts/migrate_sqlite_to_postgres.py

Prerequisites:
    - PostgreSQL database and user already created
    - DATABASE_URL in .env points to the PostgreSQL target
    - SQLite trading.db exists in the backend/ directory
"""

import os
import sys
import time

# Add parent dir to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import Boolean, create_engine, inspect, text, MetaData  # noqa: E402

# Import Base to get all table metadata
from app.database import Base  # noqa: E402
from app.models import *  # noqa: F401,F403,E402 — registers all models with Base

# ── Configuration ──────────────────────────────────────────────────────────

SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trading.db")

# Read PG URL from .env
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def get_pg_url():
    """Read DATABASE_URL from .env and convert to sync psycopg2 URL."""
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith("DATABASE_URL=") and "postgresql" in line:
                url = line.split("=", 1)[1]
                # Convert async driver to sync
                return url.replace("+asyncpg", "+psycopg2")
    return None


# Tables in FK-dependency order (leaves first, parents first)
TABLE_ORDER = [
    # Phase 1: Root & reference tables
    "settings",
    "market_data",
    "metric_snapshots",
    "roles",
    "permissions",
    "groups",

    # Phase 2: Users & RBAC
    "users",
    "user_groups",
    "group_roles",
    "role_permissions",
    "trusted_devices",
    "email_verification_tokens",
    "revoked_tokens",
    "active_sessions",

    # Phase 3: Accounts & content
    "accounts",
    "content_sources",
    "ai_provider_credentials",

    # Phase 4: Content
    "news_articles",
    "video_articles",
    "article_tts",
    "user_voice_subscriptions",
    "user_article_tts_history",
    "user_content_seen_status",
    "user_source_subscriptions",

    # Phase 5: Trading setup
    "bot_templates",
    "bot_template_products",
    "bots",
    "bot_products",
    "blacklisted_coins",

    # Phase 6: Trading data
    "positions",
    "trades",
    "signals",
    "pending_orders",
    "order_history",

    # Phase 7: System logs
    "ai_bot_logs",
    "scanner_logs",
    "indicator_logs",

    # Phase 8: Reporting
    "account_value_snapshots",
    "prop_firm_state",
    "prop_firm_equity_snapshots",
    "report_goals",
    "expense_items",
    "goal_progress_snapshots",
    "report_schedules",
    "report_schedule_goals",
    "reports",
    "account_transfers",
]

BATCH_SIZE = 500


def migrate():
    pg_url = get_pg_url()
    if not pg_url:
        print("ERROR: No PostgreSQL DATABASE_URL found in .env")
        print("       Set DATABASE_URL=postgresql+asyncpg://user:pass@localhost/zenithgrid first.")
        sys.exit(1)

    if not os.path.exists(SQLITE_PATH):
        print(f"ERROR: SQLite database not found at {SQLITE_PATH}")
        sys.exit(1)

    sqlite_url = f"sqlite:///{SQLITE_PATH}"
    print(f"Source:  {sqlite_url}")
    print(f"Target:  {pg_url.replace(pg_url.split('@')[0].split('://')[-1].split(':')[-1], '****')}")
    print()

    # Connect to both databases
    sqlite_engine = create_engine(sqlite_url)
    pg_engine = create_engine(pg_url)

    # Get list of tables that actually exist in SQLite
    sqlite_inspector = inspect(sqlite_engine)
    existing_sqlite_tables = set(sqlite_inspector.get_table_names())

    # Create all tables on PostgreSQL
    print("Creating PostgreSQL schema...")
    Base.metadata.create_all(pg_engine)
    print("  Schema created.\n")

    # Reflect SQLite metadata for column info
    sqlite_meta = MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)

    # Build map of boolean columns per table from SQLAlchemy model metadata
    # SQLite stores booleans as 0/1 integers; PostgreSQL needs True/False
    bool_cols_map = {}
    for table_name_key, table_obj in Base.metadata.tables.items():
        bool_cols = set()
        for col in table_obj.columns:
            if isinstance(col.type, Boolean):
                bool_cols.add(col.name)
        if bool_cols:
            bool_cols_map[table_name_key] = bool_cols

    total_rows = 0
    table_stats = {}
    start = time.time()

    for table_name in TABLE_ORDER:
        if table_name not in existing_sqlite_tables:
            print(f"  SKIP {table_name} (not in SQLite)")
            continue

        # Read from SQLite
        with sqlite_engine.connect() as src:
            rows = src.execute(text(f"SELECT * FROM {table_name}")).fetchall()
            if not rows:
                print(f"  SKIP {table_name} (empty)")
                table_stats[table_name] = 0
                continue

            # Get column names from SQLite
            cols = src.execute(text(f"SELECT * FROM {table_name} LIMIT 1")).keys()
            col_names = list(cols)

        # Insert into PostgreSQL in batches
        with pg_engine.begin() as dest:
            # Truncate target table first (in case of re-run)
            dest.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
            # Disable FK checks during bulk insert (SQLite doesn't enforce FK
            # cascades, so orphaned rows may exist)
            dest.execute(text(f"ALTER TABLE {table_name} DISABLE TRIGGER ALL"))

            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i + BATCH_SIZE]
                # Build parameterized INSERT
                placeholders = ", ".join([f":{c}" for c in col_names])
                col_list = ", ".join([f'"{c}"' for c in col_names])
                insert_sql = f'INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})'

                bool_cols = bool_cols_map.get(table_name, set())
                values = []
                for row in batch:
                    row_dict = {}
                    for j, col in enumerate(col_names):
                        val = row[j]
                        # Coerce SQLite integer booleans to Python bools for PG
                        if col in bool_cols and isinstance(val, int):
                            val = bool(val)
                        row_dict[col] = val
                    values.append(row_dict)

                dest.execute(text(insert_sql), values)

            # Re-enable FK checks
            dest.execute(text(f"ALTER TABLE {table_name} ENABLE TRIGGER ALL"))

        count = len(rows)
        total_rows += count
        table_stats[table_name] = count
        print(f"  {table_name}: {count} rows")

    # Reset sequences for all tables with an 'id' column
    print("\nResetting PostgreSQL sequences...")
    with pg_engine.begin() as conn:
        pg_inspector = inspect(pg_engine)
        for table_name in TABLE_ORDER:
            if table_name not in existing_sqlite_tables:
                continue
            columns = [c["name"] for c in pg_inspector.get_columns(table_name)]
            if "id" in columns and table_stats.get(table_name, 0) > 0:
                seq_name = f"{table_name}_id_seq"
                try:
                    conn.execute(text(
                        f"SELECT setval('{seq_name}', COALESCE((SELECT MAX(id) FROM {table_name}), 1))"
                    ))
                    print(f"  {seq_name} reset")
                except Exception as e:
                    print(f"  {seq_name} skip ({e})")

    elapsed = time.time() - start

    # Verify row counts
    print("\nVerifying row counts...")
    mismatches = []
    with sqlite_engine.connect() as src, pg_engine.connect() as dest:
        for table_name in TABLE_ORDER:
            if table_name not in existing_sqlite_tables:
                continue
            src_count = src.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            dest_count = dest.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            if src_count != dest_count:
                mismatches.append((table_name, src_count, dest_count))
                print(f"  MISMATCH {table_name}: SQLite={src_count}, PG={dest_count}")

    print(f"\n{'=' * 60}")
    print(f"Migration complete in {elapsed:.1f}s")
    print(f"Total rows migrated: {total_rows}")
    print(f"Tables: {len([v for v in table_stats.values() if v > 0])} with data, "
          f"{len([v for v in table_stats.values() if v == 0])} empty")
    if mismatches:
        print(f"WARNINGS: {len(mismatches)} row count mismatches!")
    else:
        print("All row counts verified OK.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    migrate()
