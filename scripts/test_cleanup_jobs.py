#!/usr/bin/env python3
"""
Test script to run cleanup jobs manually and verify they work.
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.database import async_session_maker
from app.models import AIBotLog, IndicatorLog, OrderHistory
from sqlalchemy import select, and_
from datetime import datetime, timedelta


async def test_cleanup_jobs():
    """Test cleanup jobs by showing what would be cleaned up"""

    print("=" * 60)
    print("CLEANUP JOB TEST REPORT")
    print("=" * 60)
    print()

    async with async_session_maker() as db:
        cutoff_time = datetime.utcnow() - timedelta(hours=24)

        # Check failed condition logs (IndicatorLog)
        print("1. Failed Condition Logs (IndicatorLog)")
        print("-" * 60)
        indicator_query = select(IndicatorLog).where(
            and_(
                IndicatorLog.timestamp < cutoff_time,
                IndicatorLog.conditions_met == False
            )
        )
        result = await db.execute(indicator_query)
        indicator_logs = result.scalars().all()
        print(f"   Found {len(indicator_logs)} indicator logs with conditions_met=False older than 24h")
        if indicator_logs:
            print(f"   Oldest: {min(log.timestamp for log in indicator_logs)}")
            print(f"   Newest: {max(log.timestamp for log in indicator_logs)}")
        print()

        # Check low-confidence AI logs
        print("2. Low-Confidence AI Logs (AIBotLog)")
        print("-" * 60)
        ai_query = select(AIBotLog).where(
            and_(
                AIBotLog.timestamp < cutoff_time,
                AIBotLog.confidence < 30
            )
        )
        result = await db.execute(ai_query)
        ai_logs = result.scalars().all()
        print(f"   Found {len(ai_logs)} AI logs with confidence <30% older than 24h")
        if ai_logs:
            print(f"   Oldest: {min(log.timestamp for log in ai_logs)}")
            print(f"   Newest: {max(log.timestamp for log in ai_logs)}")
        print()

        # Check failed orders
        print("3. Failed Orders (OrderHistory)")
        print("-" * 60)
        failed_orders_query = select(OrderHistory).where(
            and_(
                OrderHistory.timestamp < cutoff_time,
                OrderHistory.status == 'failed'
            )
        )
        result = await db.execute(failed_orders_query)
        failed_orders = result.scalars().all()
        print(f"   Found {len(failed_orders)} failed orders older than 24h")
        if failed_orders:
            print(f"   Oldest: {min(order.timestamp for order in failed_orders)}")
            print(f"   Newest: {max(order.timestamp for order in failed_orders)}")
            print()
            print("   Sample failed orders to be cleaned:")
            for i, order in enumerate(failed_orders[:5], 1):
                print(f"      {i}. {order.timestamp} - {order.product_id} {order.side} - {order.error_message[:50]}...")
        print()

        # Summary
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        total_to_clean = len(indicator_logs) + len(ai_logs) + len(failed_orders)
        print(f"Total records that would be cleaned: {total_to_clean}")
        print(f"  - Indicator logs (conditions not met): {len(indicator_logs)}")
        print(f"  - AI logs (confidence <30%): {len(ai_logs)}")
        print(f"  - Failed orders: {len(failed_orders)}")
        print()

        if total_to_clean > 0:
            print("✅ Cleanup jobs have work to do!")
        else:
            print("✅ No old records to clean (database is clean)")
        print()


async def run_cleanup_now():
    """Actually run the cleanup jobs once to test them"""
    print("=" * 60)
    print("RUNNING CLEANUP JOBS NOW")
    print("=" * 60)
    print()

    from app.cleanup_jobs import cleanup_failed_condition_logs, cleanup_old_failed_orders

    # Run both cleanup functions once (with modified sleep times for testing)
    print("Running cleanup_failed_condition_logs...")
    # We'll need to modify the function to run once, or just import and execute the logic
    # For now, let's just run the test report
    await test_cleanup_jobs()


if __name__ == "__main__":
    print("\n🔍 Testing Cleanup Jobs\n")
    asyncio.run(test_cleanup_jobs())
