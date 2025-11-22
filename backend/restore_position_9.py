"""Restore position 9 data based on Coinbase transaction history"""
import asyncio
from sqlalchemy import select, update
from app.database import async_session_maker
from app.models import Trade, Position

async def restore_position_9():
    async with async_session_maker() as db:
        # Restore trade amounts based on Coinbase screenshot
        # Trade 9: 2.8 ATOM
        await db.execute(
            update(Trade).where(Trade.id == 9).values(
                base_amount=2.8,
                quote_amount=0.00008470,
                price=0.00008470 / 2.8
            )
        )
        
        # Trade 18: 10.8 ATOM  
        await db.execute(
            update(Trade).where(Trade.id == 18).values(
                base_amount=10.8,
                quote_amount=0.00032185,
                price=0.00032185 / 10.8
            )
        )
        
        # Trade 21: 12.8 ATOM
        await db.execute(
            update(Trade).where(Trade.id == 21).values(
                base_amount=12.8,
                quote_amount=0.00038622,
                price=0.00038622 / 12.8
            )
        )
        
        # Trade 22: 15 ATOM
        await db.execute(
            update(Trade).where(Trade.id == 22).values(
                base_amount=15.0,
                quote_amount=0.00045058,
                price=0.00045058 / 15.0
            )
        )
        
        # Total: 41.4 ATOM, 0.00124335 BTC
        await db.execute(
            update(Position).where(Position.id == 9).values(
                total_base_acquired=41.4,
                total_quote_spent=0.00124335,
                average_buy_price=0.00124335 / 41.4
            )
        )
        
        await db.commit()
        print("✅ Position 9 restored successfully")
        print(f"   Total: 41.4 ATOM, 0.00124335 BTC")

if __name__ == "__main__":
    asyncio.run(restore_position_9())
