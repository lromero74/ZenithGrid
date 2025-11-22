"""Sell all altcoins to BTC"""
import asyncio
from app.coinbase_unified_client import CoinbaseClient
from app.currency_utils import format_base_amount
import os

async def sell_all_to_btc():
    """Get all balances and sell altcoins to BTC"""
    
    coinbase = CoinbaseClient(
        api_key=os.getenv("COINBASE_API_KEY"),
        api_secret=os.getenv("COINBASE_API_SECRET")
    )
    
    # Get portfolio
    portfolio = await coinbase.get_portfolio_breakdown()

    print("Current portfolio balances:")
    print("=" * 60)

    breakdown = portfolio.get("breakdown", {})
    balances = breakdown.get("spot_positions", [])
    
    # Track what we need to sell
    to_sell = []

    for position in balances:
        currency = position.get("asset", "")
        available_str = position.get("available_to_trade_fiat", "0")
        available = float(available_str) if available_str else 0

        if available > 0:
            print(f"{currency}: {available:.8f}")

            # Skip BTC and USD - we're converting TO BTC
            if currency not in ["BTC", "USD"]:
                to_sell.append((currency, available))
    
    print("\n" + "=" * 60)
    print(f"Found {len(to_sell)} altcoins to sell for BTC")
    print("=" * 60)
    
    if not to_sell:
        print("No altcoins to sell - you only have BTC/USD")
        return
    
    # Sell each coin for BTC
    for currency, amount in to_sell:
        product_id = f"{currency}-BTC"
        
        # Sell 99% to avoid insufficient balance errors
        sell_amount = amount * 0.99
        
        print(f"\n💰 Selling {sell_amount:.8f} {currency} for BTC...")
        print(f"   Product: {product_id}")
        
        try:
            # Create market sell order
            order = await coinbase.create_market_order(
                product_id=product_id,
                side="SELL",
                size=format_base_amount(sell_amount, currency)
            )
            
            if order.get("success", False):
                order_id = order.get("success_response", {}).get("order_id", "")
                print(f"   ✅ Order placed: {order_id}")
            else:
                error = order.get("error_response", {})
                print(f"   ❌ Error: {error}")
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
    
    print("\n" + "=" * 60)
    print("Sell-all complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(sell_all_to_btc())
