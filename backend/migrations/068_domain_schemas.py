"""
Migration 068: Domain-scoped PostgreSQL schemas.

Creates 6 named schemas and moves all tables from public into them:
  auth      — users, auth, sessions, tokens, RBAC
  trading   — accounts, bots, positions, trades, orders
  reporting — snapshots, goals, reports, transfers, donations
  social    — friendships, games, tournaments, chat
  content   — articles, videos, sources, TTS
  system    — settings, logs, market_data

SQLite: no-op (schema isolation is PostgreSQL-only).
Idempotent: only moves tables still in the public schema.

After moving tables, updates the app role's search_path so that
unqualified table names in ad-hoc psql queries still resolve.
"""

from migrations.db_utils import get_migration_connection, is_postgres

SCHEMA_TABLES = {
    "auth": [
        "users", "groups", "roles", "permissions",
        "user_groups", "group_roles", "role_permissions",
        "trusted_devices", "email_verification_tokens", "revoked_tokens",
        "active_sessions", "rate_limit_attempts",
    ],
    "trading": [
        "accounts", "bots", "bot_products", "bot_templates", "bot_template_products",
        "positions", "trades", "signals", "pending_orders", "order_history",
        "blacklisted_coins",
    ],
    "reporting": [
        "account_value_snapshots", "metric_snapshots", "prop_firm_state",
        "prop_firm_equity_snapshots", "report_goals", "expense_items",
        "goal_progress_snapshots", "report_schedules", "report_schedule_goals",
        "reports", "account_transfers", "donations",
    ],
    "social": [
        "friendships", "friend_requests", "blocked_users",
        "game_results", "game_result_players", "game_history_visibility",
        "game_high_scores", "tournaments", "tournament_players",
        "tournament_delete_votes", "chat_channels", "chat_channel_members",
        "chat_messages", "chat_message_reactions",
    ],
    "content": [
        "ai_provider_credentials", "news_articles", "video_articles",
        "content_sources", "user_source_subscriptions", "article_tts",
        "user_voice_subscriptions", "user_article_tts_history",
        "user_content_seen_status",
    ],
    "system": [
        "settings", "market_data", "ai_bot_logs", "scanner_logs", "indicator_logs",
    ],
}

_SEARCH_PATH = "auth, trading, reporting, social, content, system, public"
_APP_ROLE = "zenithgrid_app"


def run():
    conn = get_migration_connection()
    cur = conn.cursor()
    try:
        if not is_postgres():
            print("  Skipping: schema migration is PostgreSQL-only.")
            return

        # 1. Create schemas
        for schema in SCHEMA_TABLES:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        conn.commit()
        print("  Created 6 domain schemas (auth, trading, reporting, social, content, system).")

        # 2. Move tables (idempotent: only moves tables still in public)
        moved = 0
        for schema, tables in SCHEMA_TABLES.items():
            for table in tables:
                cur.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (table,)
                )
                if cur.fetchone():
                    cur.execute(f"ALTER TABLE public.{table} SET SCHEMA {schema}")
                    print(f"  Moved public.{table} → {schema}.{table}")
                    moved += 1
        conn.commit()
        print(f"  Moved {moved} tables to domain schemas.")

        # 3. Grant USAGE on schemas and DML on tables to the app role
        for schema in SCHEMA_TABLES:
            cur.execute(f"GRANT USAGE ON SCHEMA {schema} TO {_APP_ROLE}")
            cur.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE "
                f"ON ALL TABLES IN SCHEMA {schema} TO {_APP_ROLE}"
            )
        conn.commit()
        print(f"  Granted schema privileges to {_APP_ROLE}.")

        # 4. Update search_path on the app role for ad-hoc psql compatibility
        cur.execute(
            f"ALTER ROLE {_APP_ROLE} SET search_path TO {_SEARCH_PATH}"
        )
        conn.commit()
        print(f"  Set search_path: {_SEARCH_PATH}")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    run()
    print("Migration 068 complete.")
