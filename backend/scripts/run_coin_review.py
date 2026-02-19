#!/usr/bin/env python3
"""
Weekly Coin Review Runner (standalone)

The coin review now runs automatically as a backend background task.
This script is kept for manual/one-off runs only.

Usage:
    ./venv/bin/python scripts/run_coin_review.py
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add the backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.coin_review_service import run_weekly_review

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    print("=" * 60)
    print("Weekly Coin Review")
    print("Using Claude AI to analyze cryptocurrency fundamentals")
    print("=" * 60)

    result = asyncio.run(run_weekly_review(standalone=True))

    if result["status"] == "error":
        print(f"\n❌ Review failed: {result.get('message', 'Unknown error')}")
        sys.exit(1)
    else:
        print("\nReview complete!")
        print(f"   🟢 APPROVED: {result['categories'].get('APPROVED', 0)}")
        print(f"   🟡 BORDERLINE: {result['categories'].get('BORDERLINE', 0)}")
        print(f"   🟠 QUESTIONABLE: {result['categories'].get('QUESTIONABLE', 0)}")
        print(f"   🔴 BLACKLISTED: {result['categories'].get('BLACKLISTED', 0)}")
        sys.exit(0)
