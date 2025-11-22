"""Check all Coinbase accounts to see what we have"""
import asyncio
from app.coinbase_unified_client import CoinbaseClient
import os
import json

async def check_all():
    coinbase = CoinbaseClient(
        api_key=os.getenv("COINBASE_API_KEY"),
        api_secret=os.getenv("COINBASE_API_SECRET")
    )

    print("=" * 80)
    print("ALL COINBASE ACCOUNTS")
    print("=" * 80)

    accounts = await coinbase.get_accounts()

    print(f"\nTotal accounts: {len(accounts)}\n")

    for account in accounts:
        currency = account.get("currency", "")
        available = float(account.get("available_balance", {}).get("value", "0"))
        hold = float(account.get("hold", {}).get("value", "0"))

        if available > 0 or hold > 0:
            print(f"{currency}:")
            print(f"  Available: {available}")
            print(f"  Hold: {hold}")
            print()

if __name__ == "__main__":
    asyncio.run(check_all())
