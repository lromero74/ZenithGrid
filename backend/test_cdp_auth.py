"""
Test CDP authentication with user's API key
"""

import asyncio
from app.coinbase_unified_client import CoinbaseClient


async def test_cdp_auth():
    """Test CDP client authentication"""
    try:
        # Load from the downloaded key file (update path as needed)
        # For production, credentials are loaded from settings/environment
        import os
        key_file = os.environ.get("CDP_KEY_FILE", f"{os.path.expanduser('~')}/cdp_api_key.json")
        client = CoinbaseClient(key_file_path=key_file)

        print("Testing CDP authentication...")

        # Test connection
        try:
            accounts = await client.get_accounts()
            connected = True
            print(f"Connection test: ✅ SUCCESS")
        except Exception as conn_error:
            connected = False
            print(f"Connection test: ❌ FAILED")
            print(f"Error details: {conn_error}")
            import traceback
            traceback.print_exc()
            return

        if connected:
            # Get accounts
            accounts = await client.get_accounts()
            print(f"\nFound {len(accounts)} accounts:")
            for acc in accounts:
                currency = acc.get('currency', 'Unknown')
                available = acc.get('available_balance', {}).get('value', '0')
                print(f"  - {currency}: {available}")

            # Get BTC balance
            btc_balance = await client.get_btc_balance()
            print(f"\nBTC Balance: {btc_balance}")

            # Get ETH balance
            eth_balance = await client.get_eth_balance()
            print(f"ETH Balance: {eth_balance}")

            # Get current ETH/BTC price
            try:
                price = await client.get_current_price("ETH-BTC")
                print(f"\nCurrent ETH/BTC price: {price:.8f}")
            except Exception as e:
                print(f"\nCould not get ETH/BTC price: {e}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_cdp_auth())
