"""
Migration 070: Enable email MFA by default for all existing verified users.

Email MFA is now on by default for all accounts. New users get mfa_email_enabled=True
at signup. This migration backfills existing users who have verified their email so
they are also enrolled automatically.

Unverified users are intentionally skipped — email MFA only activates at login once
email_verified is True, so backfilling unverified addresses would cause MFA prompts
to send to addresses we haven't confirmed exist.

Idempotent: UPDATE ... WHERE ... = False is a no-op if already True.
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
        UPDATE auth.users
        SET mfa_email_enabled = TRUE
        WHERE email_verified = TRUE
          AND mfa_email_enabled = FALSE
          AND email LIKE '%@%'
    """)
    print(f"[070] Enabled email MFA for {cur.rowcount} existing verified user(s) (PostgreSQL)")


def _run_sqlite(cur):
    cur.execute("""
        UPDATE users
        SET mfa_email_enabled = 1
        WHERE email_verified = 1
          AND mfa_email_enabled = 0
          AND email LIKE '%@%'
    """)
    print(f"[070] Enabled email MFA for {cur.rowcount} existing verified user(s) (SQLite)")


if __name__ == "__main__":
    run()
