"""
Weekly Coin Review Service

Uses Claude API to analyze tracked coins and update their status/reasons.
Runs weekly via systemd timer.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Any

from anthropic import AsyncAnthropic
from sqlalchemy import select, delete

from app.config import settings
from app.database import async_session_maker, init_db
from app.models import Bot, BlacklistedCoin

logger = logging.getLogger(__name__)

# Review history table would be nice but for now we'll just log
COIN_REVIEW_PROMPT = """You are a cryptocurrency analyst evaluating coins for a BTC-denominated trading bot.

Analyze each coin and categorize it into one of four categories:
- APPROVED: Legitimate projects with strong fundamentals, active development, clear utility
- BORDERLINE: Projects with concerns but not outright bad - declining relevance, slow development, etc.
- QUESTIONABLE: Projects with significant red flags - unclear utility, heavy selling pressure, overshadowed by competitors
- BLACKLISTED: Projects with serious issues - SEC problems, abandoned, security vulnerabilities, scams, meme coins

For each coin, provide:
1. A category (APPROVED, BORDERLINE, QUESTIONABLE, or BLACKLISTED)
2. A brief reason (max 60 chars) explaining the categorization

Consider factors like:
- Development activity and roadmap progress
- Regulatory status and legal issues
- Security history (hacks, 51% attacks)
- Real utility vs hype
- Market position vs competitors
- Team credibility and project longevity
- Tokenomics and unlock schedules

Here are the coins to analyze (all trade against BTC on Coinbase):
{coins_list}

Respond with ONLY valid JSON in this exact format:
{{
  "ETH": {{"category": "APPROVED", "reason": "#2 crypto, massive ecosystem, DeFi foundation"}},
  "DOGE": {{"category": "BLACKLISTED", "reason": "Meme coin, no real utility"}},
  ...
}}

Include ALL coins from the list. Be concise but specific in reasons."""


async def get_tracked_coins() -> List[str]:
    """Get all unique coin symbols tracked by bots."""
    async with async_session_maker() as db:
        result = await db.execute(select(Bot))
        bots = result.scalars().all()

        symbols = set()
        for bot in bots:
            if bot.product_id and '-BTC' in bot.product_id:
                symbols.add(bot.product_id.split('-')[0])
            if bot.product_ids:
                for pid in bot.product_ids:
                    if '-BTC' in pid:
                        symbols.add(pid.split('-')[0])

        return sorted(symbols)


async def call_claude_for_review(coins: List[str]) -> Dict[str, Dict[str, str]]:
    """Call Claude API to analyze coins."""
    api_key = settings.anthropic_api_key
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    coins_list = ", ".join(coins)
    prompt = COIN_REVIEW_PROMPT.format(coins_list=coins_list)

    client = AsyncAnthropic(api_key=api_key)

    logger.info(f"Calling Claude API to review {len(coins)} coins...")

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = response.content[0].text.strip()

    # Remove markdown if present
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
        response_text = response_text.strip()

    analysis = json.loads(response_text)

    logger.info(f"Claude API response - Input: {response.usage.input_tokens}, Output: {response.usage.output_tokens} tokens")

    return analysis


async def update_coin_statuses(analysis: Dict[str, Dict[str, str]]) -> Dict[str, int]:
    """Update blacklisted_coins table with Claude's analysis."""
    stats = {"added": 0, "updated": 0, "unchanged": 0}

    category_prefix = {
        "APPROVED": "[APPROVED]",
        "BORDERLINE": "[BORDERLINE]",
        "QUESTIONABLE": "[QUESTIONABLE]",
        "BLACKLISTED": "",  # No prefix for blacklisted
    }

    async with async_session_maker() as db:
        for symbol, data in analysis.items():
            category = data.get("category", "BLACKLISTED").upper()
            reason = data.get("reason", "No reason provided")

            # Build full reason with prefix
            prefix = category_prefix.get(category, "")
            full_reason = f"{prefix} {reason}".strip() if prefix else reason

            # Check if coin exists
            query = select(BlacklistedCoin).where(BlacklistedCoin.symbol == symbol.upper())
            result = await db.execute(query)
            existing = result.scalars().first()

            if existing:
                if existing.reason != full_reason:
                    existing.reason = full_reason
                    stats["updated"] += 1
                    logger.info(f"  Updated {symbol}: {full_reason}")
                else:
                    stats["unchanged"] += 1
            else:
                entry = BlacklistedCoin(symbol=symbol.upper(), reason=full_reason)
                db.add(entry)
                stats["added"] += 1
                logger.info(f"  Added {symbol}: {full_reason}")

        await db.commit()

    return stats


async def run_weekly_review() -> Dict[str, Any]:
    """
    Main entry point for weekly coin review.

    Returns dict with review results.
    """
    start_time = datetime.utcnow()
    logger.info("=" * 60)
    logger.info(f"Starting weekly coin review at {start_time.isoformat()}")
    logger.info("=" * 60)

    try:
        # Initialize database
        await init_db()

        # Get tracked coins
        coins = await get_tracked_coins()
        logger.info(f"Found {len(coins)} tracked coins: {', '.join(coins)}")

        if not coins:
            logger.warning("No tracked coins found!")
            return {"status": "error", "message": "No tracked coins found"}

        # Call Claude for analysis
        analysis = await call_claude_for_review(coins)
        logger.info(f"Received analysis for {len(analysis)} coins")

        # Update database
        stats = await update_coin_statuses(analysis)

        # Summary
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        # Count by category
        category_counts = {"APPROVED": 0, "BORDERLINE": 0, "QUESTIONABLE": 0, "BLACKLISTED": 0}
        for symbol, data in analysis.items():
            category = data.get("category", "BLACKLISTED").upper()
            if category in category_counts:
                category_counts[category] += 1

        logger.info("=" * 60)
        logger.info("Weekly Coin Review Complete!")
        logger.info(f"  Duration: {duration:.1f}s")
        logger.info(f"  Coins analyzed: {len(analysis)}")
        logger.info(f"  Added: {stats['added']}, Updated: {stats['updated']}, Unchanged: {stats['unchanged']}")
        logger.info(f"  Categories: {category_counts}")
        logger.info("=" * 60)

        return {
            "status": "success",
            "timestamp": end_time.isoformat(),
            "duration_seconds": duration,
            "coins_analyzed": len(analysis),
            "stats": stats,
            "categories": category_counts,
            "analysis": analysis,
        }

    except Exception as e:
        logger.error(f"Weekly coin review failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


# CLI entry point
if __name__ == "__main__":
    import sys

    # Set up logging for CLI
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    result = asyncio.run(run_weekly_review())

    if result["status"] == "error":
        print(f"\nError: {result.get('message', 'Unknown error')}")
        sys.exit(1)
    else:
        print(f"\nReview complete! Categories: {result['categories']}")
        sys.exit(0)
