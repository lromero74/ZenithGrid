"""
Migration 074: Superuser manager memberships on Observer demo accounts.

The "Observers" RBAC group contains demo users (demo_usd, demo_btc, demo_both)
whose paper-trading accounts serve as public showcases.  The superuser (platform
admin) needs manager-level access to those accounts so they can configure bots,
goals, expense items, and report schedules for the demo.

What this migration does:
  1. Find the first superuser (is_superuser = TRUE).
  2. Find the Observers group.
  3. Find every account owned by a member of the Observers group.
  4. Insert an auth.account_memberships row with role='manager' for the
     superuser on each of those accounts.

Idempotent: uses ON CONFLICT DO NOTHING (Postgres) / INSERT OR IGNORE (SQLite)
so it is safe to run multiple times.
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
    # 1. Find the primary superuser (earliest id = platform owner)
    cur.execute("SELECT id FROM auth.users WHERE is_superuser = TRUE ORDER BY id LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("  [074] No superuser found — skipping")
        return
    superuser_id = row[0]
    print(f"  [074] Superuser id={superuser_id}")

    # 2. Find the Observers group
    cur.execute("SELECT id FROM auth.groups WHERE name = 'Observers' LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("  [074] Observers group not found — skipping")
        return
    observers_group_id = row[0]
    print(f"  [074] Observers group id={observers_group_id}")

    # 3. Find accounts owned by Observer group members (excluding the superuser's own accounts)
    cur.execute("""
        SELECT DISTINCT a.id
        FROM trading.accounts a
        JOIN auth.user_groups ug ON ug.user_id = a.user_id
        WHERE ug.group_id = %s
          AND a.user_id != %s
    """, (observers_group_id, superuser_id))
    account_ids = [r[0] for r in cur.fetchall()]
    print(f"  [074] Observer-owned accounts: {account_ids}")

    if not account_ids:
        print("  [074] No Observer accounts found — skipping")
        return

    # 4. Insert manager memberships for the superuser (idempotent)
    inserted = 0
    for acct_id in account_ids:
        cur.execute("""
            INSERT INTO auth.account_memberships (account_id, user_id, role, invited_by_user_id, joined_at)
            SELECT %s, %s, 'manager', %s, NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM auth.account_memberships
                WHERE account_id = %s AND user_id = %s
            )
        """, (acct_id, superuser_id, superuser_id, acct_id, superuser_id))
        if cur.rowcount:
            inserted += 1
            print(f"  [074] Added manager membership: account_id={acct_id} user_id={superuser_id}")
        else:
            print(f"  [074] Membership already exists: account_id={acct_id} user_id={superuser_id}")

    print(f"  [074] Done — {inserted} new memberships created")


def _run_sqlite(cur):
    # 1. Find the superuser
    cur.execute("SELECT id FROM users WHERE is_superuser = 1 LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("  [074] No superuser found — skipping")
        return
    superuser_id = row[0]
    print(f"  [074] Superuser id={superuser_id}")

    # 2. Find the Observers group
    cur.execute("SELECT id FROM groups WHERE name = 'Observers' LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("  [074] Observers group not found — skipping")
        return
    observers_group_id = row[0]
    print(f"  [074] Observers group id={observers_group_id}")

    # 3. Find accounts owned by Observer group members (excluding the superuser)
    cur.execute("""
        SELECT DISTINCT a.id
        FROM accounts a
        JOIN user_groups ug ON ug.user_id = a.user_id
        WHERE ug.group_id = ?
          AND a.user_id != ?
    """, (observers_group_id, superuser_id))
    account_ids = [r[0] for r in cur.fetchall()]
    print(f"  [074] Observer-owned accounts: {account_ids}")

    if not account_ids:
        print("  [074] No Observer accounts found — skipping")
        return

    # 4. Insert manager memberships for the superuser (idempotent)
    inserted = 0
    for acct_id in account_ids:
        cur.execute("""
            INSERT OR IGNORE INTO account_memberships (account_id, user_id, role, invited_by_user_id)
            VALUES (?, ?, 'manager', ?)
        """, (acct_id, superuser_id, superuser_id))
        if cur.rowcount:
            inserted += 1
            print(f"  [074] Added manager membership: account_id={acct_id} user_id={superuser_id}")
        else:
            print(f"  [074] Membership already exists: account_id={acct_id} user_id={superuser_id}")

    print(f"  [074] Done — {inserted} new memberships created")
