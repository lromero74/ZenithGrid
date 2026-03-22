# PRP: Phase 2.1 — Domain-scoped PostgreSQL Schemas

## Overview

Move all PostgreSQL tables from `public` into 6 named domain schemas:
`auth`, `trading`, `reporting`, `social`, `content`, `system`.

This is Phase 2.1 of `docs/SCALABILITY_ROADMAP.md`. Zero behavior change today. In Phase 3, each schema becomes the blast radius of a microservice extraction.

**Branch**: `feature/phase2-domain-schemas`
**Version bump**: minor (v2.132.0)
**Risk**: Medium-high. Requires service stop + DB migration. Full TDD with schema verification tests.

---

## Context & Background

### Why named schemas?
PostgreSQL schemas are namespaces within a single database. Today all ~70 tables live in `public`. Named schemas:
- Let each future microservice's DB role be `GRANT`ed only its own schema
- Make cross-domain queries explicit and auditable
- Enable Phase 3 extraction without data movement (schema-per-service on same PG instance first)

### What changes
1. **Migration 068** — `CREATE SCHEMA IF NOT EXISTS` × 6, then `ALTER TABLE public.X SET SCHEMA Y` for every table
2. **7 model files** — add `schema=` to every model's `__table_args__`, update cross-schema FK strings
3. **setup.py** — create schemas before `Base.metadata.create_all()`
4. **database.py** — add `search_path` to connection string for ad-hoc psql compatibility
5. **Tests** — verify each table is in its correct schema (PostgreSQL) or skip (SQLite)

---

## Schema-to-File Mapping

| Schema | File | Tables |
|--------|------|--------|
| `auth` | `models/auth.py` | users, groups, roles, permissions, user_groups, group_roles, role_permissions, trusted_devices, email_verification_tokens, revoked_tokens, active_sessions, rate_limit_attempts |
| `trading` | `models/trading.py` | accounts, bots, bot_products, bot_templates, bot_template_products, positions, trades, signals, pending_orders, order_history, blacklisted_coins |
| `reporting` | `models/reporting.py` + `models/donations.py` | account_value_snapshots, metric_snapshots, prop_firm_state, prop_firm_equity_snapshots, report_goals, expense_items, goal_progress_snapshots, report_schedules, report_schedule_goals, reports, account_transfers, donations |
| `social` | `models/social.py` | friendships, friend_requests, blocked_users, game_results, game_result_players, game_history_visibility, game_high_scores, tournaments, tournament_players, tournament_delete_votes, chat_channels, chat_channel_members, chat_messages, chat_message_reactions |
| `content` | `models/content.py` | ai_provider_credentials, news_articles, video_articles, content_sources, user_source_subscriptions, article_tts, user_voice_subscriptions, user_article_tts_history, user_content_seen_status |
| `system` | `models/system.py` | settings, market_data, ai_bot_logs, scanner_logs, indicator_logs |

---

## Cross-Schema FK Reference Map

**Rule**: FKs within the SAME schema keep their current unqualified name. FKs crossing schemas must use `schema.table.column` format.

### FK strings that CHANGE (cross-schema references):

**`models/auth.py`** — no cross-schema FKs (auth is self-contained)

**`models/trading.py`** — all models reference `users.id` which moves to `auth`:
- `Account.user_id`: `"users.id"` → `"auth.users.id"`
- `Bot.user_id`: `"users.id"` → `"auth.users.id"`
- `BotTemplate.user_id`: `"users.id"` → `"auth.users.id"`
- `Position.user_id`: `"users.id"` → `"auth.users.id"`
- `BlacklistedCoin.user_id`: `"users.id"` → `"auth.users.id"`
- Intra-trading FKs (accounts.id, bots.id, positions.id): **no change**

**`models/reporting.py`** — references auth.users + trading.accounts:
- Every model with `user_id` FK: `"users.id"` → `"auth.users.id"`
- Every model with `account_id` FK: `"accounts.id"` → `"trading.accounts.id"`
- Every model with `report_goals.id`, `report_schedules.id`: **no change** (both in reporting)

**`models/donations.py`** (→ reporting schema):
- `Donation.user_id`: `"users.id"` → `"auth.users.id"`
- `Donation.confirmed_by`: `"users.id"` → `"auth.users.id"`

**`models/social.py`** — only cross-schema FK is to auth.users:
- All `user_id`, `from_user_id`, `to_user_id`, `blocker_id`, `blocked_id`, `creator_id`, `sender_id`, `created_by` FKs to `"users.id"` → `"auth.users.id"`
- Intra-social FKs (tournaments.id, game_results.id, chat_channels.id, chat_messages.id): **no change**

**`models/content.py`** — only cross-schema FK is to auth.users:
- All `user_id` FKs to `"users.id"` → `"auth.users.id"`
- `ArticleTTS.created_by_user_id`: `"users.id"` → `"auth.users.id"`
- Intra-content FKs (content_sources.id, news_articles.id): **no change**

**`models/system.py`** — references both auth.users and trading:
- `AIBotLog.bot_id`: `"bots.id"` → `"trading.bots.id"`
- `AIBotLog.position_id`: `"positions.id"` → `"trading.positions.id"`
- `ScannerLog.bot_id`: `"bots.id"` → `"trading.bots.id"`
- `IndicatorLog.bot_id`: `"bots.id"` → `"trading.bots.id"`

---

## `__table_args__` Patterns

### Models with NO existing `__table_args__` → add schema dict:
```python
__table_args__ = {'schema': 'SCHEMA_NAME'}
```

### Models with existing tuple-form `__table_args__` → merge schema into tuple:
```python
# BEFORE:
__table_args__ = (UniqueConstraint("user_id", "friend_id", name="uq_friendship"),)
# AFTER:
__table_args__ = (UniqueConstraint("user_id", "friend_id", name="uq_friendship"), {'schema': 'social'})
```

### Junction `Table()` objects in auth.py → add `schema=` kwarg:
```python
# BEFORE:
user_groups = Table("user_groups", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)
# AFTER:
user_groups = Table("user_groups", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    schema="auth",
)
```
(FKs within the auth schema stay unqualified — `users.id` not `auth.users.id` — because both tables are in the same schema.)

### Models that need `__table_args__` tuple-merge (already have constraints):

**trading.py**:
- `Bot`: `(UniqueConstraint("user_id", "name", name="uq_bot_user_name"),)` → add `{'schema': 'trading'}`
- `BotProduct`: `(UniqueConstraint("bot_id", "product_id", name="uq_bot_product"),)` → add schema
- `BotTemplateProduct`: `(UniqueConstraint("template_id", "product_id", name="uq_template_product"),)` → add schema

**reporting.py**:
- `AccountValueSnapshot`: `(UniqueConstraint("account_id", "snapshot_date", name="uq_account_snapshot_date"),)` → add schema
- `GoalProgressSnapshot`: `(UniqueConstraint("goal_id", "snapshot_date", name="uq_goal_snapshot_date"),)` → add schema
- `ReportScheduleGoal`: `(UniqueConstraint("schedule_id", "goal_id", name="uq_schedule_goal"),)` → add schema

**social.py**:
- `Friendship`, `FriendRequest`, `BlockedUser`, `GameHighScore`, `TournamentPlayer`, `TournamentDeleteVote`, `ChatChannelMember`, `ChatMessageReaction` — all have single UniqueConstraint tuples → add schema
- `ChatMessage` — has `(Index("ix_chat_messages_channel_created", "channel_id", "created_at"),)` → add schema

**content.py**:
- `UserSourceSubscription`, `ArticleTTS`, `UserVoiceSubscription`, `UserArticleTTSHistory` — single UniqueConstraint → add schema
- `UserContentSeenStatus` — has `(UniqueConstraint(...), Index(...))` → add schema as third element

---

## Migration 068

File: `backend/migrations/068_domain_schemas.py`

```python
"""
Migration 068: Domain-scoped PostgreSQL schemas.

Creates 6 named schemas and moves all tables from public into them:
  auth      — users, auth, sessions, tokens
  trading   — accounts, bots, positions, trades, orders
  reporting — snapshots, goals, reports, transfers, donations
  social    — friendships, games, tournaments, chat
  content   — articles, videos, sources, TTS
  system    — settings, logs, market_data

SQLite: no-op (schema isolation is PostgreSQL-only).
Idempotent: only moves tables that are still in public.

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
        print("  Created 6 domain schemas.")

        # 2. Move tables (idempotent: only if still in public)
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
        conn.commit()

        # 3. Grant schema usage + table privileges to the app role
        for schema in SCHEMA_TABLES:
            cur.execute(f"GRANT USAGE ON SCHEMA {schema} TO zenithgrid_app")
            cur.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} "
                f"TO zenithgrid_app"
            )
        conn.commit()
        print("  Granted schema privileges to zenithgrid_app.")

        # 4. Update search_path on the app role for ad-hoc psql compatibility
        search_path = "auth, trading, reporting, social, content, system, public"
        cur.execute(f"ALTER ROLE zenithgrid_app SET search_path TO {search_path}")
        conn.commit()
        print(f"  Set search_path: {search_path}")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    run()
    print("Migration 068 complete.")
```

---

## setup.py Changes

Find the section in `setup.py` where PostgreSQL tables are created (the `create_all` call). Before it, add schema creation:

```python
# Add before Base.metadata.create_all() in setup.py
# Create domain schemas (PostgreSQL only)
if database_url and "postgresql" in database_url:
    with engine.connect() as conn:
        for schema in ["auth", "trading", "reporting", "social", "content", "system"]:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        conn.commit()
```

---

## database.py Changes

Add `options` to the connection for PostgreSQL to set search_path as a fallback for any unqualified references:

```python
# In _engine_kwargs for PostgreSQL, add connect_args with options:
if settings.is_postgres:
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 3
    _engine_kwargs["pool_timeout"] = 10
    _engine_kwargs["connect_args"] = {
        "options": "-csearch_path=auth,trading,reporting,social,content,system,public"
    }
```

---

## TDD Test Plan

File: `backend/tests/test_domain_schemas.py`

Tests to write FIRST (before model changes):

```python
"""
Tests for Phase 2.1 — Domain-scoped PostgreSQL schemas.

TDD: Written before implementation. On SQLite these tests skip.
On PostgreSQL, verifies each table is in its correct schema.
"""
import pytest
from app.config import settings

pytestmark = pytest.mark.skipif(
    not settings.is_postgres, reason="Schema isolation is PostgreSQL-only"
)

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

    def test_all_schemas_exist(self, db_sync_conn):
        """Happy path: all 6 domain schemas exist in the database."""
        for schema in SCHEMA_TABLES:
            cur = db_sync_conn.cursor()
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (schema,)
            )
            assert cur.fetchone(), f"Schema '{schema}' does not exist"

    @pytest.mark.parametrize("schema,tables", SCHEMA_TABLES.items())
    def test_tables_in_correct_schema(self, db_sync_conn, schema, tables):
        """Happy path: every table is in its assigned schema, not in public."""
        cur = db_sync_conn.cursor()
        for table in tables:
            cur.execute(
                "SELECT table_schema FROM information_schema.tables "
                "WHERE table_name = %s AND table_schema != 'information_schema'",
                (table,)
            )
            row = cur.fetchone()
            assert row is not None, f"Table '{table}' not found in any schema"
            assert row[0] == schema, (
                f"Table '{table}' is in schema '{row[0]}', expected '{schema}'"
            )

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


class TestSQLAlchemySchemaMetadata:

    def test_user_model_schema(self):
        """Happy path: User model has schema='auth' in __table_args__."""
        from app.models.auth import User
        assert User.__table__.schema == "auth"

    def test_account_model_schema(self):
        from app.models.trading import Account
        assert Account.__table__.schema == "trading"

    def test_bot_model_schema(self):
        from app.models.trading import Bot
        assert Bot.__table__.schema == "trading"

    def test_position_model_schema(self):
        from app.models.trading import Position
        assert Position.__table__.schema == "trading"

    def test_report_model_schema(self):
        from app.models.reporting import Report
        assert Report.__table__.schema == "reporting"

    def test_donation_model_schema(self):
        from app.models.donations import Donation
        assert Donation.__table__.schema == "reporting"

    def test_friendship_model_schema(self):
        from app.models.social import Friendship
        assert Friendship.__table__.schema == "social"

    def test_news_article_model_schema(self):
        from app.models.content import NewsArticle
        assert NewsArticle.__table__.schema == "content"

    def test_settings_model_schema(self):
        from app.models.system import Settings
        assert Settings.__table__.schema == "system"

    def test_junction_table_schema(self):
        """Edge case: junction Table() objects have schema set."""
        from app.models.auth import user_groups, group_roles, role_permissions
        assert user_groups.schema == "auth"
        assert group_roles.schema == "auth"
        assert role_permissions.schema == "auth"

    def test_cross_schema_fk_account_to_users(self):
        """Edge case: Account.user_id FK references auth.users."""
        from app.models.trading import Account
        fk = list(Account.__table__.c.user_id.foreign_keys)[0]
        assert fk.target_fullname == "auth.users.id"

    def test_cross_schema_fk_system_to_trading(self):
        """Edge case: AIBotLog.bot_id FK references trading.bots."""
        from app.models.system import AIBotLog
        fk = list(AIBotLog.__table__.c.bot_id.foreign_keys)[0]
        assert fk.target_fullname == "trading.bots.id"
```

The `db_sync_conn` fixture needs to be added to `conftest.py`:
```python
@pytest.fixture
def db_sync_conn():
    """Synchronous DB connection for schema inspection (PostgreSQL only)."""
    from migrations.db_utils import get_migration_connection
    conn = get_migration_connection()
    yield conn
    conn.close()
```

---

## Implementation Order (TDD)

1. **Write tests** (`test_domain_schemas.py`) — confirm they FAIL (ImportError or assertion errors on wrong schema)
2. **Run migration 068** on dev DB (stop services first)
3. **Update model files** — add schema to `__table_args__`, update cross-schema FK strings
4. **Update setup.py** — add schema creation before `create_all()`
5. **Update database.py** — add search_path to connect_args
6. **Run tests** — confirm they PASS
7. **Update SCALABILITY_ROADMAP.md** — mark Phase 2.1 done

---

## Detailed Model Changes

### `models/auth.py`

**Junction tables** — add `schema="auth"` kwarg:
```python
user_groups = Table("user_groups", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    schema="auth",
)

group_roles = Table("group_roles", Base.metadata,
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    schema="auth",
)

role_permissions = Table("role_permissions", Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    schema="auth",
)
```

**ORM models** — add `__table_args__ = {'schema': 'auth'}` to all 9 classes (User, Group, Role, Permission, TrustedDevice, EmailVerificationToken, RevokedToken, ActiveSession, RateLimitAttempt). No FK changes (all within auth).

### `models/trading.py`

**FK changes** (users.id → auth.users.id):
- `Account.user_id`: `ForeignKey("users.id")` → `ForeignKey("auth.users.id")`
- `Bot.user_id`: `ForeignKey("users.id")` → `ForeignKey("auth.users.id")`
- `BotTemplate.user_id`: `ForeignKey("users.id")` → `ForeignKey("auth.users.id")`
- `Position.user_id`: `ForeignKey("users.id")` → `ForeignKey("auth.users.id")`
- `BlacklistedCoin.user_id`: `ForeignKey("users.id")` → `ForeignKey("auth.users.id")`

**`__table_args__` changes**:
- Bot: `(UniqueConstraint(...),)` → `(UniqueConstraint(...), {'schema': 'trading'})`
- BotProduct: `(UniqueConstraint(...),)` → `(UniqueConstraint(...), {'schema': 'trading'})`
- BotTemplateProduct: `(UniqueConstraint(...),)` → `(UniqueConstraint(...), {'schema': 'trading'})`
- All others: add `__table_args__ = {'schema': 'trading'}`

### `models/reporting.py`

**FK changes**:
- All `ForeignKey("users.id")` → `ForeignKey("auth.users.id")`
- All `ForeignKey("accounts.id")` → `ForeignKey("trading.accounts.id")`
- `Report.schedule_id`: `ForeignKey("report_schedules.id", ...)` → stays (same schema)
- `AccountValueSnapshot.account_id`: `ForeignKey("accounts.id", ondelete="CASCADE")` → `ForeignKey("trading.accounts.id", ondelete="CASCADE")`

**`__table_args__` changes**: merge schema into all existing constraint tuples; add new ones where missing.

### `models/donations.py`

- Schema: `reporting` (same physical schema as reporting.py)
- `Donation.user_id`: `ForeignKey("users.id")` → `ForeignKey("auth.users.id")`
- `Donation.confirmed_by`: `ForeignKey("users.id")` → `ForeignKey("auth.users.id")`
- Add `__table_args__ = {'schema': 'reporting'}`

### `models/social.py`

**FK changes**: All `ForeignKey("users.id")` references → `ForeignKey("auth.users.id")`. Intra-social FKs stay as-is.

**`__table_args__` changes**: merge schema into all existing constraint tuples.

### `models/content.py`

**FK changes**: All `ForeignKey("users.id")` references → `ForeignKey("auth.users.id")`. Intra-content FKs stay as-is.

**`__table_args__` changes**: merge schema into all existing constraint tuples.

### `models/system.py`

**FK changes**:
- `AIBotLog.bot_id`: `ForeignKey("bots.id")` → `ForeignKey("trading.bots.id")`
- `AIBotLog.position_id`: `ForeignKey("positions.id")` → `ForeignKey("trading.positions.id")`
- `ScannerLog.bot_id`: `ForeignKey("bots.id")` → `ForeignKey("trading.bots.id")`
- `IndicatorLog.bot_id`: `ForeignKey("bots.id")` → `ForeignKey("trading.bots.id")`

Add `__table_args__ = {'schema': 'system'}` to all 5 models.

---

## SCALABILITY_ROADMAP.md Update

Add to Phase 2.1 section:
```
✅ DONE (v2.132.0)
- Migration 068: CREATE SCHEMA × 6, ALTER TABLE public.X SET SCHEMA Y for all ~70 tables
- All 7 model files updated with explicit schema= in __table_args__
- Junction Table() objects in auth.py updated with schema="auth" kwarg
- Cross-schema FK strings updated (total: ~45 FK strings changed)
- setup.py: CREATE SCHEMA IF NOT EXISTS before create_all()
- database.py: search_path connect_arg for ad-hoc psql compatibility
- Grant USAGE + table privileges to zenithgrid_app for each new schema
- Tests: TestSchemaAssignments (DB-level verification) + TestSQLAlchemySchemaMetadata (ORM-level)
- SQLite: no-op (single-file DB has no schema concept)
```

---

## Pre-flight Checklist

- [ ] `./bot.sh stop` before running migration
- [ ] Back up DB: `cp backend/trading.db backend/trading.db.bak.$(date +%s)` (for SQLite) or `pg_dump zenithgrid > /tmp/zenithgrid_pre_schema_$(date +%s).sql`
- [ ] Tests written first (TDD)
- [ ] `cd backend && ./venv/bin/python3 update.py --yes` runs migration
- [ ] `./bot.sh restart --prod` after migration + model updates
- [ ] Verify: `psql zenithgrid -c "\dt auth.*"` shows auth tables

---

## Validation Commands

```bash
# 1. Run focused tests (PostgreSQL-only tests skip on SQLite)
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest tests/test_domain_schemas.py -v

# 2. Flake8 lint all changed files
./venv/bin/python3 -m flake8 app/models/ --max-line-length=120

# 3. Verify schemas in PostgreSQL
PGPASSWORD=$PG_PASS psql -U zenithgrid_app -d zenithgrid -c "
SELECT table_schema, COUNT(*) as table_count
FROM information_schema.tables
WHERE table_schema IN ('auth','trading','reporting','social','content','system')
GROUP BY table_schema ORDER BY table_schema;"

# 4. Verify no app tables remain in public
PGPASSWORD=$PG_PASS psql -U zenithgrid_app -d zenithgrid -c "
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
```

---

## Gotchas

1. **PostgreSQL FK OIDs**: When `ALTER TABLE public.X SET SCHEMA Y`, existing FK constraints from other tables still work — PostgreSQL stores FKs by OID, not name. You do NOT need to drop/recreate FK constraints during migration.

2. **search_path matters for `update.py` migrations**: The migration runner executes SQL directly. After 068 runs, subsequent migrations may reference tables by unqualified name. The `ALTER ROLE ... SET search_path` ensures this keeps working.

3. **`__table_args__` must have the dict LAST in the tuple**: `(Constraint(...), {'schema': 'x'})` — dict always last.

4. **Junction `Table()` objects**: These use `schema=` as a keyword argument directly to `Table()`, NOT in a tuple. Different from ORM class `__table_args__`.

5. **SQLAlchemy relationship resolution**: After adding explicit schemas, relationship backrefs using string class names (`"User"`, `"Account"`) continue to work — SQLAlchemy resolves by class name, not table name.

6. **Fresh install** (`setup.py`): Must create schemas BEFORE `Base.metadata.create_all()`. Otherwise SQLAlchemy tries to create `auth.users` but schema `auth` doesn't exist yet → error.

7. **`conftest.py` `db_sync_conn` fixture**: Check if conftest already has a sync connection fixture. If not, add one. Scope to `function`.

8. **`report_goals` FK in `reporting.py`**: `ReportScheduleGoal.goal_id` references `report_goals.id` — both in `reporting` schema, so stays `ForeignKey("report_goals.id", ondelete="CASCADE")`.

---

PRP Confidence Score: **9/10** — comprehensive catalog of all changes, TDD approach, idempotent migration, all gotchas identified. One-pass success is high.
