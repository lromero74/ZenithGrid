"""Test buy ADA-BTC with market order to verify order execution and position creation"""
import asyncio
from app.coinbase_unified_client import CoinbaseClient
import os
import json

async def test_buy():
    coinbase = CoinbaseClient(
        api_key=os.getenv("COINBASE_API_KEY"),
        api_secret=os.getenv("COINBASE_API_SECRET")
    )

    print("=" * 60)
    print("Buying 0.00015 BTC worth of ADA (market order)")
    print("=" * 60)

    # Place market buy order
    order = await coinbase.create_market_order(
        product_id="ADA-BTC",
        side="BUY",
        funds="0.00015"  # 0.00015 BTC worth (above 0.0001 minimum)
    )

    print("\n📋 Order Response:")
    print(json.dumps(order, indent=2))

    # Check if successful
    if order.get("success", False):
        order_id = order.get("success_response", {}).get("order_id", "")
        print(f"\n✅ Order placed successfully!")
        print(f"   Order ID: {order_id}")

        # Wait a moment for fill
        print("\n⏳ Waiting 3 seconds for order to fill...")
        await asyncio.sleep(3)

        # Get order details
        print("\n📊 Fetching order details...")
        order_details = await coinbase.get_order(order_id)

        print("\n📋 Order Details:")
        print(json.dumps(order_details, indent=2))

        # Extract fill information
        status = order_details.get("status", "")
        filled_size = order_details.get("filled_size", "0")
        filled_value = order_details.get("filled_value", "0")
        avg_price = order_details.get("average_filled_price", "0")

        print("\n" + "=" * 60)
        print("FILL INFORMATION:")
        print("=" * 60)
        print(f"Status: {status}")
        print(f"Filled Size (ADA): {filled_size}")
        print(f"Filled Value (BTC): {filled_value}")
        print(f"Average Price: {avg_price}")
        print("=" * 60)

    else:
        error = order.get("error_response", {})
        print(f"\n❌ Order failed: {error}")

if __name__ == "__main__":
    asyncio.run(test_buy())
