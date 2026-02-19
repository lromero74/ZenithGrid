#!/usr/bin/env python3
"""
Quick test script to verify Coinbase v2 /transactions endpoint works
with our auth. Run from project root:

    backend/venv/bin/python3 scripts/test_coinbase_transfers.py
"""

import asyncio
import os
import sys

# Add backend to path and chdir so relative DB path resolves
backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

from app.coinbase_api import transaction_api  # noqa: E402, F401


async def main():
    # Load credentials from first active account in DB
    from app.database import async_session_maker, init_db
    from app.models import Account
    from sqlalchemy import select

    await init_db()

    async with async_session_maker() as db:
        result = await db.execute(
            select(Account).where(
                Account.is_active.is_(True),
                Account.is_paper_trading.is_(False),
            ).limit(1)
        )
        account = result.scalar_one_or_none()

        if not account:
            print("No active non-paper account found")
            return

        print(f"Using account: {account.name} (id={account.id})")

        # Get credentials
        from app.services.exchange_service import get_coinbase_for_account
        adapter = await get_coinbase_for_account(account)
        # The adapter wraps a CoinbaseUnifiedClient — get the raw client
        client = adapter._client

        print(f"Auth type: {client.auth_type}")

        # Step 1: Get Coinbase account UUIDs
        print("\n--- Fetching Coinbase accounts ---")
        try:
            cb_accounts = await client.get_accounts(force_fresh=True)
            print(f"Found {len(cb_accounts)} Coinbase accounts")

            # Show first few
            for acct in cb_accounts[:5]:
                bal = acct.get("available_balance", {})
                print(
                    f"  {acct.get('currency', '?'):6s} "
                    f"uuid={acct.get('uuid', '?')[:12]}... "
                    f"balance={bal.get('value', '0')}"
                )
        except Exception as e:
            print(f"ERROR fetching accounts: {e}")
            return

        # Step 2: Try v2 transactions endpoint on the USD account
        print("\n--- Testing v2 transactions endpoint ---")

        # Find USD or USDC account (most likely to have deposits)
        target_accts = [
            a for a in cb_accounts
            if a.get("currency") in ("USD", "USDC", "BTC")
        ]

        if not target_accts:
            print("No USD/USDC/BTC accounts found")
            return

        for cb_acct in target_accts[:3]:
            uuid = cb_acct.get("uuid")
            currency = cb_acct.get("currency")
            print(f"\n  Checking {currency} account ({uuid[:12]}...):")

            try:
                transfers = await client.get_deposit_withdrawals(uuid)
                print(f"    Found {len(transfers)} transfers")
                for t in transfers[:3]:
                    print(
                        f"    {t['transfer_type']:12s} "
                        f"{t['amount']:>12.4f} {t['currency']:5s} "
                        f"(${t.get('amount_usd', 'N/A')}) "
                        f"at {t['occurred_at'][:19]}"
                    )
                if not transfers:
                    print("    (no deposits/withdrawals found)")
            except Exception as e:
                print(f"    ERROR: {e}")
                import traceback
                traceback.print_exc()

        print("\n--- Done ---")


if __name__ == "__main__":
    asyncio.run(main())
