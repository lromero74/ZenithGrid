"""
Tests for Phase 2.1 — Domain-scoped PostgreSQL schemas.

TDD: Written BEFORE implementation. On SQLite these tests are skipped
(pytestmark). On PostgreSQL, verifies:
  1. TestSchemaAssignments  — physical DB: each table lives in the right schema
  2. TestSQLAlchemySchemaMetadata — ORM: __table__.schema is set correctly
"""
import pytest
from app.config import settings

pytestmark = pytest.mark.skipif(
    not settings.is_postgres,
    reason="Schema isolation is PostgreSQL-only",
)

# Master map: schema → list of tables that should live there
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


class TestSchemaAssignments:
    """Verify physical DB placement of every table (PostgreSQL only)."""

    def test_all_schemas_exist(self, db_sync_conn):
        """Happy path: all 6 domain schemas exist in the database."""
        cur = db_sync_conn.cursor()
        for schema in SCHEMA_TABLES:
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (schema,)
            )
            assert cur.fetchone(), f"Schema '{schema}' does not exist"
        cur.close()

    @pytest.mark.parametrize("schema,tables", SCHEMA_TABLES.items())
    def test_tables_in_correct_schema(self, db_sync_conn, schema, tables):
        """Happy path: every table is in its assigned schema, not in public."""
        cur = db_sync_conn.cursor()
        for table in tables:
            cur.execute(
                "SELECT table_schema FROM information_schema.tables "
                "WHERE table_name = %s AND table_schema NOT IN "
                "('information_schema', 'pg_catalog')",
                (table,)
            )
            row = cur.fetchone()
            assert row is not None, f"Table '{table}' not found in any schema"
            assert row[0] == schema, (
                f"Table '{table}' is in schema '{row[0]}', expected '{schema}'"
            )
        cur.close()

    def test_no_app_tables_in_public(self, db_sync_conn):
        """Edge case: public schema contains no application tables."""
        all_app_tables = [t for tables in SCHEMA_TABLES.values() for t in tables]
        cur = db_sync_conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY(%s)",
            (all_app_tables,)
        )
        leftover = [row[0] for row in cur.fetchall()]
        assert leftover == [], f"Tables still in public schema: {leftover}"
        cur.close()


class TestSQLAlchemySchemaMetadata:
    """Verify ORM model __table__.schema settings (no DB connection needed)."""

    def test_user_model_schema(self):
        """Happy path: User model has schema='auth'."""
        from app.models.auth import User
        assert User.__table__.schema == "auth"

    def test_group_model_schema(self):
        from app.models.auth import Group
        assert Group.__table__.schema == "auth"

    def test_role_model_schema(self):
        from app.models.auth import Role
        assert Role.__table__.schema == "auth"

    def test_permission_model_schema(self):
        from app.models.auth import Permission
        assert Permission.__table__.schema == "auth"

    def test_trusted_device_model_schema(self):
        from app.models.auth import TrustedDevice
        assert TrustedDevice.__table__.schema == "auth"

    def test_revoked_token_model_schema(self):
        from app.models.auth import RevokedToken
        assert RevokedToken.__table__.schema == "auth"

    def test_active_session_model_schema(self):
        from app.models.auth import ActiveSession
        assert ActiveSession.__table__.schema == "auth"

    def test_rate_limit_attempt_model_schema(self):
        from app.models.auth import RateLimitAttempt
        assert RateLimitAttempt.__table__.schema == "auth"

    def test_account_model_schema(self):
        from app.models.trading import Account
        assert Account.__table__.schema == "trading"

    def test_bot_model_schema(self):
        from app.models.trading import Bot
        assert Bot.__table__.schema == "trading"

    def test_position_model_schema(self):
        from app.models.trading import Position
        assert Position.__table__.schema == "trading"

    def test_trade_model_schema(self):
        from app.models.trading import Trade
        assert Trade.__table__.schema == "trading"

    def test_report_model_schema(self):
        from app.models.reporting import Report
        assert Report.__table__.schema == "reporting"

    def test_report_goal_model_schema(self):
        from app.models.reporting import ReportGoal
        assert ReportGoal.__table__.schema == "reporting"

    def test_account_transfer_model_schema(self):
        from app.models.reporting import AccountTransfer
        assert AccountTransfer.__table__.schema == "reporting"

    def test_donation_model_schema(self):
        """donations.py uses the reporting schema."""
        from app.models.donations import Donation
        assert Donation.__table__.schema == "reporting"

    def test_friendship_model_schema(self):
        from app.models.social import Friendship
        assert Friendship.__table__.schema == "social"

    def test_tournament_model_schema(self):
        from app.models.social import Tournament
        assert Tournament.__table__.schema == "social"

    def test_chat_message_model_schema(self):
        from app.models.social import ChatMessage
        assert ChatMessage.__table__.schema == "social"

    def test_news_article_model_schema(self):
        from app.models.content import NewsArticle
        assert NewsArticle.__table__.schema == "content"

    def test_ai_provider_credential_model_schema(self):
        from app.models.content import AIProviderCredential
        assert AIProviderCredential.__table__.schema == "content"

    def test_content_source_model_schema(self):
        from app.models.content import ContentSource
        assert ContentSource.__table__.schema == "content"

    def test_settings_model_schema(self):
        from app.models.system import Settings
        assert Settings.__table__.schema == "system"

    def test_ai_bot_log_model_schema(self):
        from app.models.system import AIBotLog
        assert AIBotLog.__table__.schema == "system"

    def test_junction_table_schemas(self):
        """Edge case: junction Table() objects have schema='auth'."""
        from app.models.auth import user_groups, group_roles, role_permissions
        assert user_groups.schema == "auth", "user_groups missing schema='auth'"
        assert group_roles.schema == "auth", "group_roles missing schema='auth'"
        assert role_permissions.schema == "auth", "role_permissions missing schema='auth'"

    def test_cross_schema_fk_account_to_auth_users(self):
        """Edge case: Account.user_id FK references auth.users (cross-schema)."""
        from app.models.trading import Account
        fk = list(Account.__table__.c.user_id.foreign_keys)[0]
        assert fk.target_fullname == "auth.users.id", (
            f"Expected FK to auth.users.id, got {fk.target_fullname}"
        )

    def test_cross_schema_fk_position_to_auth_users(self):
        """Edge case: Position.user_id FK references auth.users."""
        from app.models.trading import Position
        fk = list(Position.__table__.c.user_id.foreign_keys)[0]
        assert fk.target_fullname == "auth.users.id"

    def test_cross_schema_fk_reporting_account_to_trading(self):
        """Edge case: AccountValueSnapshot.account_id FK references trading.accounts."""
        from app.models.reporting import AccountValueSnapshot
        fk = list(AccountValueSnapshot.__table__.c.account_id.foreign_keys)[0]
        assert fk.target_fullname == "trading.accounts.id"

    def test_cross_schema_fk_system_botlog_to_trading(self):
        """Edge case: AIBotLog.bot_id FK references trading.bots (cross-schema)."""
        from app.models.system import AIBotLog
        fk = list(AIBotLog.__table__.c.bot_id.foreign_keys)[0]
        assert fk.target_fullname == "trading.bots.id"

    def test_cross_schema_fk_system_botlog_position_to_trading(self):
        """Edge case: AIBotLog.position_id FK references trading.positions."""
        from app.models.system import AIBotLog
        fk = list(AIBotLog.__table__.c.position_id.foreign_keys)[0]
        assert fk.target_fullname == "trading.positions.id"

    def test_intra_trading_fk_not_changed(self):
        """Edge case: intra-trading FKs (Bot.account_id) remain unqualified."""
        from app.models.trading import Bot
        fk = list(Bot.__table__.c.account_id.foreign_keys)[0]
        # Should still be trading.accounts.id in the qualified sense
        # but the FK target table is in the same schema, so check it resolves
        assert "accounts" in fk.target_fullname

    def test_intra_social_fk_not_changed(self):
        """Edge case: intra-social FKs (TournamentPlayer.tournament_id) stay unqualified."""
        from app.models.social import TournamentPlayer
        fk = list(TournamentPlayer.__table__.c.tournament_id.foreign_keys)[0]
        assert "tournaments" in fk.target_fullname


class TestDatabaseEngineConfig:
    """Verify asyncpg connect_args use server_settings (not psycopg2-style options).

    asyncpg's connect() does not accept an 'options' kwarg — that's psycopg2 syntax.
    The correct asyncpg form is server_settings={"search_path": "..."}.
    This class prevents regressions to the broken form.
    """

    def test_connect_args_uses_server_settings_not_options(self):
        """Happy path: connect_args has server_settings dict, not options string."""
        import app.database as db_module
        connect_args = db_module._engine_kwargs.get("connect_args", {})
        assert "options" not in connect_args, (
            "connect_args must not use 'options' (psycopg2 syntax) — asyncpg uses server_settings"
        )
        assert "server_settings" in connect_args, (
            "connect_args must have 'server_settings' for asyncpg search_path"
        )

    def test_search_path_contains_all_domain_schemas(self):
        """Happy path: search_path lists all 6 domain schemas."""
        import app.database as db_module
        connect_args = db_module._engine_kwargs.get("connect_args", {})
        search_path = connect_args.get("server_settings", {}).get("search_path", "")
        for schema in ("auth", "trading", "reporting", "social", "content", "system"):
            assert schema in search_path, f"'{schema}' missing from search_path: {search_path!r}"

    def test_search_path_includes_public_fallback(self):
        """Edge case: public is last in search_path for migrations and pg_catalog access."""
        import app.database as db_module
        connect_args = db_module._engine_kwargs.get("connect_args", {})
        search_path = connect_args.get("server_settings", {}).get("search_path", "")
        assert "public" in search_path, f"'public' fallback missing from search_path: {search_path!r}"


class TestIntraSchemaFKsAreQualified:
    """Verify all intra-schema FKs use schema-qualified names.

    When a table has schema='X' in __table_args__, all ForeignKey() strings pointing
    to tables in the SAME schema must also be qualified (ForeignKey("X.table.id")).
    SQLAlchemy registers tables as 'schema.table' in metadata, so unqualified FKs
    cause NoReferencedTableError during mapper configuration on startup.
    This class prevents regressions where an intra-schema FK is accidentally added
    without a schema prefix.
    """

    def _collect_fk_strings(self, table):
        """Return all FK target strings for columns in a table."""
        fks = []
        for col in table.columns:
            for fk in col.foreign_keys:
                fks.append(fk.target_fullname)
        return fks

    def test_auth_intra_schema_fks_are_qualified(self):
        """Happy path: all auth→auth FKs use auth.X.id format."""
        from app.models.auth import user_groups, group_roles, role_permissions
        from app.models.auth import TrustedDevice, EmailVerificationToken, RevokedToken, ActiveSession
        for table in (user_groups, group_roles, role_permissions):
            for fk_str in self._collect_fk_strings(table):
                if not fk_str.startswith("auth."):
                    pytest.fail(f"Junction table FK not schema-qualified: {fk_str!r}")
        for model in (TrustedDevice, EmailVerificationToken, RevokedToken, ActiveSession):
            for fk_str in self._collect_fk_strings(model.__table__):
                assert fk_str.startswith("auth."), (
                    f"{model.__tablename__} FK not schema-qualified: {fk_str!r}"
                )

    def test_trading_intra_schema_fks_are_qualified(self):
        """Happy path: all trading→trading FKs use trading.X.id format."""
        from app.models.trading import (
            Bot, BotProduct, BotTemplate, BotTemplateProduct,
            Position, Trade, Signal, PendingOrder, OrderHistory, BlacklistedCoin,
        )
        for model in (Bot, BotProduct, BotTemplate, BotTemplateProduct,
                      Position, Trade, Signal, PendingOrder, OrderHistory, BlacklistedCoin):
            for fk_str in self._collect_fk_strings(model.__table__):
                schema = fk_str.split(".")[0]
                assert schema in ("trading", "auth"), (
                    f"{model.__tablename__} FK has unexpected schema: {fk_str!r}"
                )

    def test_content_intra_schema_fks_are_qualified(self):
        """Happy path: all content→content FKs use content.X.id format."""
        from app.models.content import (
            NewsArticle, VideoArticle, UserSourceSubscription,
            ArticleTTS, UserVoiceSubscription, UserArticleTTSHistory, UserContentSeenStatus,
        )
        for model in (NewsArticle, VideoArticle, UserSourceSubscription,
                      ArticleTTS, UserVoiceSubscription, UserArticleTTSHistory, UserContentSeenStatus):
            for fk_str in self._collect_fk_strings(model.__table__):
                schema = fk_str.split(".")[0]
                assert schema in ("content", "auth"), (
                    f"{model.__tablename__} FK has unexpected schema: {fk_str!r}"
                )

    def test_reporting_intra_schema_fks_are_qualified(self):
        """Happy path: all reporting→reporting FKs use reporting.X.id format."""
        from app.models.reporting import (
            GoalProgressSnapshot, ReportScheduleGoal, Report,
        )
        for model in (GoalProgressSnapshot, ReportScheduleGoal, Report):
            for fk_str in self._collect_fk_strings(model.__table__):
                schema = fk_str.split(".")[0]
                assert schema in ("reporting", "auth", "trading"), (
                    f"{model.__tablename__} FK has unexpected schema: {fk_str!r}"
                )

    def test_social_intra_schema_fks_are_qualified(self):
        """Happy path: all social→social FKs use social.X.id format."""
        from app.models.social import (
            GameResult, GameResultPlayer, TournamentPlayer, TournamentDeleteVote,
            ChatChannelMember, ChatMessage, ChatMessageReaction,
        )
        for model in (GameResult, GameResultPlayer, TournamentPlayer, TournamentDeleteVote,
                      ChatChannelMember, ChatMessage, ChatMessageReaction):
            for fk_str in self._collect_fk_strings(model.__table__):
                schema = fk_str.split(".")[0]
                assert schema in ("social", "auth"), (
                    f"{model.__tablename__} FK has unexpected schema: {fk_str!r}"
                )
