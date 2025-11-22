"""Check actual fill information from Coinbase for the three orders"""
import asyncio
from app.coinbase_unified_client import CoinbaseClient
import os
import json

async def check_fills():
    coinbase = CoinbaseClient(
        api_key=os.getenv("COINBASE_API_KEY"),
        api_secret=os.getenv("COINBASE_API_SECRET")
    )

    orders = [
        ("1", "BCH-BTC", "2419d658-4d5e-43fe-b411-608aca67f206"),
        ("2", "COMP-BTC", "02aea64e-56bf-4c95-9998-3aff31e0d073"),
        ("3", "ALGO-BTC", "ff39eb4e-7665-42f9-8c9d-5822cd2ab9ef"),
    ]

    print("=" * 80)
    print("CHECKING COINBASE FOR ACTUAL FILL INFORMATION")
    print("=" * 80)

    for pos_id, product_id, order_id in orders:
        print(f"\n{'=' * 80}")
        print(f"Position {pos_id} ({product_id})")
        print(f"Order ID: {order_id}")
        print('=' * 80)

        try:
            order_details = await coinbase.get_order(order_id)

            if "order" in order_details:
                order = order_details["order"]
                status = order.get("status", "")
                filled_size = order.get("filled_size", "0")
                filled_value = order.get("filled_value", "0")
                avg_price = order.get("average_filled_price", "0")
                total_fees = order.get("total_fees", "0")

                print(f"Status: {status}")
                print(f"Filled Size: {filled_size}")
                print(f"Filled Value (BTC): {filled_value}")
                print(f"Average Price: {avg_price}")
                print(f"Total Fees: {total_fees}")

                if status == "FILLED":
                    print(f"\n✅ Order filled successfully!")
                    print(f"   Need to update database:")
                    print(f"   - total_quote_spent = {filled_value}")
                    print(f"   - total_base_acquired = {filled_size}")
                    print(f"   - average_buy_price = {avg_price}")
                else:
                    print(f"\n⚠️  Order status: {status}")
            else:
                print("❌ Could not retrieve order details")
                print(json.dumps(order_details, indent=2))

        except Exception as e:
            print(f"❌ Error checking order: {str(e)}")

if __name__ == "__main__":
    asyncio.run(check_fills())
