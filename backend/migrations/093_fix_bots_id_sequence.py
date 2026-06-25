"""Restore the auto-increment sequence/default on bots.id (PostgreSQL).

On some PostgreSQL installs the ``bots`` table lost its serial sequence (a past
out-of-band table rebuild left ``bots.id`` with no ``DEFAULT``), which makes every
``INSERT`` that omits ``id`` fail with a NOT NULL violation — breaking bot creation
and cloning from the UI. This migration recreates ``bots_id_seq``, attaches it to
``bots.id`` as the column default, and fast-forwards it past the current max id.

Idempotent and PostgreSQL-only:
- SQLite uses ``INTEGER PRIMARY KEY`` (rowid alias) and needs no sequence — skipped.
- If ``bots.id`` already has a ``nextval(...)`` default, the migration is a no-op.
"""

from migrations.db_utils import get_migration_connection, is_postgres


def run():
    if not is_postgres():
        print("  SQLite: bots.id is a rowid alias (auto-assigned) — nothing to do")
        return

    conn = get_migration_connection()
    cursor = conn.cursor()
    try:
        # Does bots.id already have a default (i.e. the sequence is wired up)?
        cursor.execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_schema = 'trading' AND table_name = 'bots' AND column_name = 'id'"
        )
        row = cursor.fetchone()
        current_default = row[0] if row else None

        if current_default and "nextval" in current_default:
            print("  bots.id already has a sequence default — skipping")
            return

        # Create + attach the sequence, fast-forward past the current max id, set default.
        cursor.execute("CREATE SEQUENCE IF NOT EXISTS trading.bots_id_seq")
        cursor.execute("ALTER SEQUENCE trading.bots_id_seq OWNED BY trading.bots.id")
        cursor.execute(
            "SELECT setval('trading.bots_id_seq', "
            "(SELECT COALESCE(MAX(id), 1) FROM trading.bots), "
            "(SELECT COUNT(*) > 0 FROM trading.bots))"
        )
        cursor.execute(
            "ALTER TABLE trading.bots ALTER COLUMN id "
            "SET DEFAULT nextval('trading.bots_id_seq'::regclass)"
        )
        conn.commit()
        print("  Restored bots.id sequence default (bots_id_seq)")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    run()
