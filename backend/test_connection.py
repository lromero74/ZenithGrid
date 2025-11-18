#!/usr/bin/env python3
"""
Quick test script to verify Coinbase API connection and credentials
Run this before starting the bot to ensure everything is configured correctly
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.coinbase_unified_client import CoinbaseClient
from app.config import settings


async def test_connection():
    """Test Coinbase API connection and display account info"""

    print("=" * 60)
    print("ETH/BTC Trading Bot - Connection Test")
    print("=" * 60)
    print()

    # Check if credentials are set
    print("1. Checking credentials...")
    if not settings.coinbase_api_key or not settings.coinbase_api_secret:
        print("   ❌ ERROR: Coinbase API credentials not found in .env file")
        print("   Please add COINBASE_API_KEY and COINBASE_API_SECRET to .env")
        return False

    print(f"   ✅ API Key: {settings.coinbase_api_key[:8]}...")
    print(f"   ✅ API Secret: {'*' * 32}")
    print()

    # Initialize client
    print("2. Connecting to Coinbase...")
    client = CoinbaseClient()

    try:
        # Test connection
        connection_ok = await client.test_connection()
        if not connection_ok:
            print("   ❌ Connection failed")
            return False
        print("   ✅ Connected successfully")
        print()

        # Get account info
        print("3. Fetching account information...")
        accounts = await client.get_accounts()
        print(f"   ✅ Found {len(accounts)} accounts")
        print()

        # Get BTC balance
        print("4. Checking BTC balance...")
        btc_balance = await client.get_btc_balance()
        print(f"   ✅ BTC Balance: {btc_balance:.8f} BTC")
        print()

        # Get ETH balance
        print("5. Checking ETH balance...")
        eth_balance = await client.get_eth_balance()
        print(f"   ✅ ETH Balance: {eth_balance:.8f} ETH")
        print()

        # Get current prices
        print("6. Fetching current market prices...")
        eth_btc_price = await client.get_current_price("ETH-BTC")
        btc_usd_price = await client.get_btc_usd_price()
        print(f"   ✅ ETH/BTC: {eth_btc_price:.8f}")
        print(f"   ✅ BTC/USD: ${btc_usd_price:.2f}")
        print()

        # Calculate total value
        print("7. Calculating total account value...")
        total_btc = btc_balance + (eth_balance * eth_btc_price)
        total_usd = total_btc * btc_usd_price
        print(f"   ✅ Total Value: {total_btc:.8f} BTC (${total_usd:.2f} USD)")
        print()

        # Display trading parameters
        print("8. Current trading parameters:")
        print(f"   • Initial Buy: {settings.initial_btc_percentage}% of BTC")
        print(f"   • DCA Amount: {settings.dca_percentage}% of BTC")
        print(f"   • Max Usage: {settings.max_btc_usage_percentage}% per position")
        print(f"   • Min Profit: {settings.min_profit_percentage}% to sell")
        print(f"   • MACD: ({settings.macd_fast_period}, {settings.macd_slow_period}, {settings.macd_signal_period})")
        print()

        # Calculate example trade sizes
        print("9. Example trade sizes based on current balance:")
        initial_trade = btc_balance * (settings.initial_btc_percentage / 100)
        dca_trade = btc_balance * (settings.dca_percentage / 100)
        max_position = btc_balance * (settings.max_btc_usage_percentage / 100)

        print(f"   • Initial Buy: {initial_trade:.8f} BTC")
        print(f"   • DCA Buy: {dca_trade:.8f} BTC")
        print(f"   • Max Position Size: {max_position:.8f} BTC")
        print()

        print("=" * 60)
        print("✅ ALL TESTS PASSED - Ready to start trading!")
        print("=" * 60)
        print()
        print("To start the bot:")
        print("  1. Run: uvicorn app.main:app --reload")
        print("  2. Open the dashboard in your browser")
        print("  3. Click 'Start Bot'")
        print()

        return True

    except Exception as e:
        print(f"   ❌ ERROR: {str(e)}")
        print()
        print("Common issues:")
        print("  - Invalid API credentials")
        print("  - API key doesn't have 'Trade' permission")
        print("  - Network connectivity issues")
        print("  - API key is IP-restricted")
        print()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
