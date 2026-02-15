"""
Update trade records with actual fill data from Coinbase
"""
import asyncio
from sqlalchemy import select
from app.database import async_session_maker
from app.models import Trade, Position
from app.coinbase_unified_client import CoinbaseClient
import os

async def update_trade_fills():
    """Fetch actual fill data from Coinbase and update trade records"""

    # Initialize Coinbase client
    coinbase = CoinbaseClient(
        api_key=os.getenv("COINBASE_API_KEY"),
        api_secret=os.getenv("COINBASE_API_SECRET")
    )

    async with async_session_maker() as db:
        # Get all buy trades that have order_ids
        query = select(Trade).where(
            Trade.side == "buy",
            Trade.order_id != None,
            Trade.order_id != ""
        ).order_by(Trade.timestamp)
        
        result = await db.execute(query)
        trades = result.scalars().all()
        
        print(f"Found {len(trades)} buy trades with order IDs")
        
        updated_count = 0
        error_count = 0
        
        for trade in trades:
            try:
                print(f"\nChecking trade {trade.id} (order {trade.order_id})...")
                
                # Get order details from Coinbase
                order_data = await coinbase.get_order(trade.order_id)
                
                # Extract actual fill data
                filled_size = order_data.get("filled_size", "0")
                filled_value = order_data.get("filled_value", "0")
                average_filled_price = order_data.get("average_filled_price", "0")
                
                actual_base_amount = float(filled_size)
                actual_quote_amount = float(filled_value)
                actual_price = float(average_filled_price)
                
                # Compare with recorded amounts
                base_diff = actual_base_amount - trade.base_amount
                quote_diff = actual_quote_amount - trade.quote_amount
                
                print(f"  Recorded: {trade.base_amount:.8f} base, {trade.quote_amount:.8f} quote")
                print(f"  Actual:   {actual_base_amount:.8f} base, {actual_quote_amount:.8f} quote")
                print(f"  Diff:     {base_diff:+.8f} base, {quote_diff:+.8f} quote")
                
                # Update trade record
                trade.base_amount = actual_base_amount
                trade.quote_amount = actual_quote_amount
                trade.price = actual_price
                
                updated_count += 1
                
            except Exception as e:
                print(f"  Error: {e}")
                error_count += 1
                continue
        
        # Now recalculate position totals
        query = select(Position).where(Position.status == "open")
        result = await db.execute(query)
        positions = result.scalars().all()
        
        print(f"\n\nRecalculating totals for {len(positions)} open positions...")
        
        for position in positions:
            # Get all buy trades for this position
            trades_query = select(Trade).where(
                Trade.position_id == position.id,
                Trade.side == "buy"
            )
            trades_result = await db.execute(trades_query)
            pos_trades = trades_result.scalars().all()
            
            # Recalculate totals from actual fills
            total_base = sum(t.base_amount for t in pos_trades)
            total_quote = sum(t.quote_amount for t in pos_trades)
            
            old_base = position.total_base_acquired
            old_quote = position.total_quote_spent
            
            position.total_base_acquired = total_base
            position.total_quote_spent = total_quote
            
            if total_base > 0:
                position.average_buy_price = total_quote / total_base
            
            print(f"\nPosition {position.id} ({position.product_id}):")
            print(f"  Old totals: {old_base:.8f} base, {old_quote:.8f} quote")
            print(f"  New totals: {total_base:.8f} base, {total_quote:.8f} quote")
            print(f"  Difference: {total_base - old_base:+.8f} base, {total_quote - old_quote:+.8f} quote")
        
        # Commit all changes
        await db.commit()
        
        print(f"\n\n✅ Summary:")
        print(f"   Updated {updated_count} trades")
        print(f"   Errors: {error_count}")
        print(f"   Recalculated {len(positions)} positions")

if __name__ == "__main__":
    asyncio.run(update_trade_fills())
