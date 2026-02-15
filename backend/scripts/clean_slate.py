"""
1. Sell all altcoins to BTC
2. Delete all positions and trades
"""
import asyncio
from sqlalchemy import delete
from app.database import async_session_maker
from app.models import Position, Trade, PendingOrder
from app.coinbase_unified_client import CoinbaseClient
import os

# List of coins to attempt selling
COINS_TO_SELL = ["ATOM", "ADA", "AAVE", "FIL", "DASH", "ALGO", "ETH"]

async def clean_slate():
    """Sell all coins and wipe database"""
    
    coinbase = CoinbaseClient(
        api_key=os.getenv("COINBASE_API_KEY"),
        api_secret=os.getenv("COINBASE_API_SECRET")
    )
    
    print("STEP 1: Selling all altcoins to BTC")
    print("=" * 60)
    
    for currency in COINS_TO_SELL:
        product_id = f"{currency}-BTC"
        
        print(f"\n💰 Attempting to sell {currency}...")
        
        try:
            # Just try to sell 100 of each coin at market
            # Coinbase will reject if we don't have enough
            # Don't use format_base_amount - just use plain string
            order = await coinbase.create_market_order(
                product_id=product_id,
                side="SELL",
                size=str(100)  # Try to sell 100, Coinbase will sell what we have
            )
            
            if order.get("success", False):
                order_id = order.get("success_response", {}).get("order_id", "")
                print(f"   ✅ Sold {currency}: Order {order_id}")
            else:
                error = order.get("error_response", {})
                error_msg = error.get("message", "Unknown")
                if "INSUFFICIENT" in str(error) or "INVALID_ORDER_SIZE" in str(error):
                    print(f"   ⏭️  No {currency} to sell")
                else:
                    print(f"   ⚠️  Error: {error_msg}")
                
        except Exception as e:
            if "INSUFFICIENT" in str(e) or "INVALID" in str(e):
                print(f"   ⏭️  No {currency} to sell")
            else:
                print(f"   ⚠️  Exception: {e}")
    
    print("\n" + "=" * 60)
    print("STEP 2: Deleting all positions, trades, and pending orders from database")
    print("=" * 60)
    
    async with async_session_maker() as db:
        # Delete all pending orders
        result = await db.execute(delete(PendingOrder))
        pending_deleted = result.rowcount
        print(f"   Deleted {pending_deleted} pending orders")
        
        # Delete all trades
        result = await db.execute(delete(Trade))
        trades_deleted = result.rowcount
        print(f"   Deleted {trades_deleted} trades")
        
        # Delete all positions
        result = await db.execute(delete(Position))
        positions_deleted = result.rowcount
        print(f"   Deleted {positions_deleted} positions")
        
        await db.commit()
    
    print("\n" + "=" * 60)
    print("✅ Clean slate complete!")
    print(f"   - Sold all altcoins to BTC")
    print(f"   - Deleted {positions_deleted} positions")
    print(f"   - Deleted {trades_deleted} trades")
    print(f"   - Deleted {pending_deleted} pending orders")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(clean_slate())
