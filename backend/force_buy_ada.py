"""Force a strong buy signal for ADA-BTC to test order execution"""
import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.database import get_db, engine
from app.models import Bot
from app.trading_engine_v2 import StrategyTradingEngine


async def force_buy_ada():
    """Force a buy order for ADA-BTC with strong signal"""

    # Get Gemini bot (ID: 1)
    async with AsyncSession(engine) as db:
        result = await db.execute(select(Bot).where(Bot.id == 1))
        bot = result.scalar_one()

        print(f"🤖 Bot: {bot.name}")
        print(f"📊 Budget: {bot.budget_percentage}%")
        print(f"🎯 Product: ADA-BTC")
        print()

        # Create trading engine
        engine_instance = StrategyTradingEngine(bot)

        # Create strong buy signal
        signal_data = {
            'signal_type': 'buy',
            'confidence': 95,  # Very high confidence
            'reasoning': 'Manual test: Strong buy signal for ADA-BTC to test order execution and position creation',
            'suggested_allocation_pct': 50,  # Allocate 50% of per-position budget
            'expected_profit_pct': 5,
            'current_price': 0.000004,  # Approximate ADA-BTC price
            '_already_logged': False
        }

        print("📈 Strong BUY signal created:")
        print(f"   Confidence: {signal_data['confidence']}%")
        print(f"   Allocation: {signal_data['suggested_allocation_pct']}%")
        print(f"   Reasoning: {signal_data['reasoning']}")
        print()

        # Call should_buy to check if it returns True and calculate order amount
        print("🔍 Calling should_buy()...")
        should_buy, amount, reason = await engine_instance.should_buy(
            db=db,
            product_id='ADA-BTC',
            signal_data=signal_data
        )

        print(f"✅ Should buy: {should_buy}")
        print(f"💰 Order amount: {amount:.8f} BTC")
        print(f"📝 Reason: {reason}")
        print()

        if should_buy and amount > 0:
            print("🚀 Executing buy order...")
            try:
                position = await engine_instance.execute_buy(
                    db=db,
                    product_id='ADA-BTC',
                    amount=amount,
                    reason=reason,
                    signal_data=signal_data
                )

                if position:
                    print("✅ ORDER EXECUTED SUCCESSFULLY!")
                    print(f"   Position ID: {position.id}")
                    print(f"   Product: {position.product_id}")
                    print(f"   Status: {position.status}")
                    print(f"   Quote spent: {position.total_quote_spent:.8f} BTC")
                    print(f"   Base acquired: {position.total_base_acquired:.8f} ADA")
                else:
                    print("❌ Order execution returned None (check logs for errors)")

            except Exception as e:
                print(f"❌ Order execution failed: {str(e)}")
                import traceback
                traceback.print_exc()
        else:
            print("❌ should_buy returned False or zero amount")


if __name__ == '__main__':
    asyncio.run(force_buy_ada())
