"""
Migration 069: Account sharing tables.

Creates three new tables in the auth schema:
  auth.account_memberships        — Maps users to accounts with a role
  auth.account_invitations        — One-time, expiring invitation tokens
  auth.account_membership_events  — Audit log for membership changes

SQLite: uses plain table names (no schema prefix) via schema_translate_map.
Idempotent: CREATE TABLE IF NOT EXISTS on all tables.
"""

from migrations.db_utils import get_migration_connection, is_postgres


def run():
    conn = get_migration_connection()
    cur = conn.cursor()

    try:
        if is_postgres():
            _run_postgres(cur)
        else:
            _run_sqlite(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _run_postgres(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth.account_memberships (
            id                  SERIAL PRIMARY KEY,
            account_id          INTEGER NOT NULL
                REFERENCES trading.accounts(id) ON DELETE CASCADE,
            user_id             INTEGER NOT NULL
                REFERENCES auth.users(id) ON DELETE CASCADE,
            role                VARCHAR(20) NOT NULL
                CHECK (role IN ('manager', 'observer')),
            invited_by_user_id  INTEGER
                REFERENCES auth.users(id) ON DELETE SET NULL,
            joined_at           TIMESTAMP NOT NULL DEFAULT NOW(),
            expires_at          TIMESTAMP,
            CONSTRAINT uq_account_membership UNIQUE (account_id, user_id)
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_memberships_user "
        "ON auth.account_memberships(user_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_memberships_account "
        "ON auth.account_memberships(account_id)"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth.account_invitations (
            id                  SERIAL PRIMARY KEY,
            account_id          INTEGER NOT NULL
                REFERENCES trading.accounts(id) ON DELETE CASCADE,
            invited_email       VARCHAR(255) NOT NULL,
            invited_by_user_id  INTEGER NOT NULL
                REFERENCES auth.users(id) ON DELETE CASCADE,
            role                VARCHAR(20) NOT NULL
                CHECK (role IN ('manager', 'observer')),
            token               VARCHAR(64) UNIQUE NOT NULL,
            expires_at          TIMESTAMP NOT NULL,
            accepted_at         TIMESTAMP,
            declined_at         TIMESTAMP,
            revoked_at          TIMESTAMP,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_invitations_email "
        "ON auth.account_invitations(invited_email)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_invitations_token "
        "ON auth.account_invitations(token)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_invitations_account "
        "ON auth.account_invitations(account_id)"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth.account_membership_events (
            id              SERIAL PRIMARY KEY,
            account_id      INTEGER NOT NULL
                REFERENCES trading.accounts(id) ON DELETE CASCADE,
            actor_user_id   INTEGER
                REFERENCES auth.users(id) ON DELETE SET NULL,
            target_user_id  INTEGER
                REFERENCES auth.users(id) ON DELETE SET NULL,
            event_type      VARCHAR(30) NOT NULL,
            old_role        VARCHAR(20),
            new_role        VARCHAR(20),
            notes           VARCHAR(255),
            created_at      TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_membership_events_account "
        "ON auth.account_membership_events(account_id)"
    )

    # Grant privileges to app role
    app_role = "zenithgrid_app"
    for table in ["account_memberships", "account_invitations", "account_membership_events"]:
        cur.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE "
            f"ON auth.{table} TO {app_role}"
        )
        cur.execute(
            f"GRANT USAGE, SELECT ON SEQUENCE auth.{table}_id_seq TO {app_role}"
        )


def _run_sqlite(cur):
    """SQLite versions — no schema prefix, no sequences, no CHECK constraints."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS account_memberships (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id          INTEGER NOT NULL,
            user_id             INTEGER NOT NULL,
            role                VARCHAR(20) NOT NULL,
            invited_by_user_id  INTEGER,
            joined_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at          TIMESTAMP,
            UNIQUE (account_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS account_invitations (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id          INTEGER NOT NULL,
            invited_email       VARCHAR(255) NOT NULL,
            invited_by_user_id  INTEGER NOT NULL,
            role                VARCHAR(20) NOT NULL,
            token               VARCHAR(64) UNIQUE NOT NULL,
            expires_at          TIMESTAMP NOT NULL,
            accepted_at         TIMESTAMP,
            declined_at         TIMESTAMP,
            revoked_at          TIMESTAMP,
            created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS account_membership_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id      INTEGER NOT NULL,
            actor_user_id   INTEGER,
            target_user_id  INTEGER,
            event_type      VARCHAR(30) NOT NULL,
            old_role        VARCHAR(20),
            new_role        VARCHAR(20),
            notes           VARCHAR(255),
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
