"""Verify Coinbase balances match database positions"""
import asyncio
from app.coinbase_unified_client import CoinbaseClient
import os
import sqlite3

async def verify_balances():
    coinbase = CoinbaseClient(
        api_key=os.getenv("COINBASE_API_KEY"),
        api_secret=os.getenv("COINBASE_API_SECRET")
    )

    # Get accounts from Coinbase
    print("=" * 80)
    print("FETCHING COINBASE ACCOUNT BALANCES")
    print("=" * 80)

    accounts = await coinbase.get_accounts()

    # Filter for BCH, COMP, ALGO
    target_currencies = ["BCH", "COMP", "ALGO"]
    holdings = {}

    for account in accounts:
        currency = account.get("currency", "")
        if currency in target_currencies:
            available = float(account.get("available_balance", {}).get("value", "0"))
            holdings[currency] = available
            print(f"{currency}: {available}")

    print("\n" + "=" * 80)
    print("DATABASE POSITIONS")
    print("=" * 80)

    conn = sqlite3.connect('trading.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, product_id, total_base_acquired
        FROM positions
        WHERE id IN (1,2,3) AND status = 'open'
        ORDER BY id
    ''')

    db_holdings = {}
    for pos_id, product_id, base_acquired in cursor.fetchall():
        base_currency = product_id.split('-')[0]  # BCH from BCH-BTC
        db_holdings[base_currency] = base_acquired
        print(f"Position {pos_id} ({product_id}): {base_acquired} {base_currency}")

    conn.close()

    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)

    all_match = True
    for currency in target_currencies:
        coinbase_amount = holdings.get(currency, 0)
        db_amount = db_holdings.get(currency, 0)
        match = abs(coinbase_amount - db_amount) < 0.00001  # Allow small floating point differences

        status = "✅ MATCH" if match else "❌ MISMATCH"
        print(f"{currency}:")
        print(f"  Coinbase: {coinbase_amount}")
        print(f"  Database: {db_amount}")
        print(f"  {status}")

        if not match:
            all_match = False

    if all_match:
        print("\n✅ All balances match!")
    else:
        print("\n⚠️  Some balances don't match - may need update")

if __name__ == "__main__":
    asyncio.run(verify_balances())
