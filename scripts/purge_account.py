#!/usr/bin/env python3
"""Purge an account's trading history (trades, orders, positions, snapshots).

The authoritative, tested path is app.services.account_purge.purge_account_history;
this CLI is a thin wrapper around it. It does NOT sell holdings — liquidate first
if you want the wallet flat. Bots and the account survive; only history is wiped,
so the account can start fresh.

Run from backend/ with the venv:
    cd backend
    ./venv/bin/python3 ../scripts/purge_account.py <account_id>            # dry-run (counts only)
    ./venv/bin/python3 ../scripts/purge_account.py <account_id> --yes      # actually delete

Always back up first (prod is PostgreSQL):  pg_dump -Fc ... > backup.dump
"""
import argparse
import asyncio
import sys


async def _main(account_id: int, confirm: bool) -> int:
    from app.database import async_session_maker
    from app.services.account_purge import count_account_history, purge_account_history

    async with async_session_maker() as db:
        counts = await count_account_history(db, account_id)
        total = sum(counts.values())
        print(f"Account {account_id} history rows:")
        for name, n in counts.items():
            print(f"  {name:<26} {n}")
        print(f"  {'TOTAL':<26} {total}")

        if total == 0:
            print("Nothing to purge.")
            return 0
        if not confirm:
            print("\nDRY RUN — re-run with --yes to delete the above permanently.")
            return 0

        deleted = await purge_account_history(db, account_id)
        print(f"\nDeleted {sum(deleted.values())} rows. Account + bots preserved.")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purge an account's trading history.")
    parser.add_argument("account_id", type=int)
    parser.add_argument("--yes", action="store_true", help="actually delete (default is dry-run)")
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args.account_id, args.yes)))
