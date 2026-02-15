"""Sell all altcoins to BTC - simple version using actual account list"""
import asyncio
from app.coinbase_unified_client import CoinbaseClient
from app.currency_utils import format_base_amount
import os

# List of coins to sell (everything except BTC)
COINS_TO_SELL = ["ATOM", "ADA", "AAVE", "FIL", "DASH", "ALGO", "ETH"]

async def sell_all_to_btc():
    """Sell specific list of coins to BTC"""
    
    coinbase = CoinbaseClient(
        api_key=os.getenv("COINBASE_API_KEY"),
        api_secret=os.getenv("COINBASE_API_SECRET")
    )
    
    print("Attempting to sell all altcoins for BTC...")
    print("=" * 60)
    
    for currency in COINS_TO_SELL:
        product_id = f"{currency}-BTC"
        
        print(f"\n💰 Checking {currency}...")
        
        try:
            # Get current balance for this currency
            # Try to get account balances
            try:
                balance_info = await coinbase.get_account_balances()
                # Extract balance for this currency
                balance = 0
                for acct in balance_info.get("accounts", []):
                    if acct.get("currency") == currency:
                        balance = float(acct.get("available_balance", {}).get("value", 0))
                        break
            except:
                # Fallback: just try to sell and let Coinbase reject if no balance
                balance = 1.0  # dummy value to trigger sell attempt
            
            if balance <= 0:
                print(f"   ⏭️  No {currency} balance, skipping")
                continue
                
            # Sell 99% to avoid insufficient balance errors
            sell_amount = balance * 0.99
            
            print(f"   Selling {sell_amount:.8f} {currency} for BTC...")
            
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
                error_msg = error.get("message", "Unknown error")
                # If it's just "no balance", that's fine
                if "INSUFFICIENT" in str(error):
                    print(f"   ⏭️  Skipping (no balance)")
                else:
                    print(f"   ❌ Error: {error_msg}")
                
        except Exception as e:
            error_str = str(e)
            if "INSUFFICIENT" in error_str:
                print(f"   ⏭️  Skipping (no balance)")
            else:
                print(f"   ❌ Exception: {e}")
    
    print("\n" + "=" * 60)
    print("Sell-all complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(sell_all_to_btc())
