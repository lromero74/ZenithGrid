"""
Migration 075: Rename account-sharing role 'observer' to 'shadow'.

The term 'observer' collided with the 'Observers' RBAC group name used for
demo accounts.  The account-sharing membership role is now called 'shadow'
to distinguish it from the RBAC concept.

Tables updated:
  - auth.account_memberships        role column
  - auth.account_invitations        role column
  - auth.account_membership_events  old_role and new_role columns

Idempotent: updates only rows that still have role='observer'.
"""

from migrations.db_utils import get_migration_connection, is_postgres


def run():
    conn = get_migration_connection()
    pg = is_postgres()
    try:
        cur = conn.cursor()

        if pg:
            # account_memberships
            cur.execute("""
                UPDATE auth.account_memberships
                SET role = 'shadow'
                WHERE role = 'observer'
            """)

            # account_invitations
            cur.execute("""
                UPDATE auth.account_invitations
                SET role = 'shadow'
                WHERE role = 'observer'
            """)

            # account_membership_events — old_role
            cur.execute("""
                UPDATE auth.account_membership_events
                SET old_role = 'shadow'
                WHERE old_role = 'observer'
            """)

            # account_membership_events — new_role
            cur.execute("""
                UPDATE auth.account_membership_events
                SET new_role = 'shadow'
                WHERE new_role = 'observer'
            """)
        else:
            cur.execute("UPDATE account_memberships SET role='shadow' WHERE role='observer'")
            cur.execute("UPDATE account_invitations SET role='shadow' WHERE role='observer'")
            cur.execute(
                "UPDATE account_membership_events SET old_role='shadow' WHERE old_role='observer'"
            )
            cur.execute(
                "UPDATE account_membership_events SET new_role='shadow' WHERE new_role='observer'"
            )

        conn.commit()
        print("Migration 075: renamed observer→shadow in membership tables.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
