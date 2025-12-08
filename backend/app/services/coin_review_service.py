"""
Weekly Coin Review Service

Uses AI API (Claude, Gemini, OpenAI, or Grok) to analyze tracked coins and update their status/reasons.
Runs weekly via systemd timer.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Any

from sqlalchemy import select

from app.config import settings
from app.database import async_session_maker, init_db
from app.models import Account, BlacklistedCoin
from app.coinbase_unified_client import CoinbaseClient
from app.exchange_clients.factory import create_exchange_client

logger = logging.getLogger(__name__)

# Review history table would be nice but for now we'll just log
COIN_REVIEW_PROMPT = """You are a cryptocurrency analyst evaluating coins for a trading bot.

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

Here are the coins to analyze (available on Coinbase across BTC, USD, and USDC markets):
{coins_list}

Respond with ONLY valid JSON in this exact format:
{{
  "ETH": {{"category": "APPROVED", "reason": "#2 crypto, massive ecosystem, DeFi foundation"}},
  "DOGE": {{"category": "BLACKLISTED", "reason": "Meme coin, no real utility"}},
  ...
}}

Include ALL coins from the list. Be concise but specific in reasons."""


async def get_coinbase_client_from_db() -> CoinbaseClient:
    """Get Coinbase client from the first active CEX account in the database."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Account).where(
                Account.type == "cex",
                Account.is_active.is_(True)
            ).order_by(Account.is_default.desc(), Account.created_at)
        )
        account = result.scalar_one_or_none()

        if not account or not account.api_key_name or not account.api_private_key:
            raise RuntimeError("No Coinbase account configured with valid credentials")

        return create_exchange_client(
            exchange_type="cex",
            coinbase_key_name=account.api_key_name,
            coinbase_private_key=account.api_private_key,
        )


async def get_tracked_coins() -> List[str]:
    """Get all unique coin symbols available on Coinbase across BTC, USD, USDC markets."""
    client = await get_coinbase_client_from_db()
    products = await client.list_products()

    symbols = set()
    quote_currencies = ["USD", "USDC", "BTC"]

    for product in products:
        product_id = product.get("product_id", "")
        status = product.get("status", "")

        # Only include online/active products
        if status != "online":
            continue

        # Only include USD, USDC, and BTC pairs
        for quote in quote_currencies:
            if product_id.endswith(f"-{quote}"):
                base = product.get("base_currency_id", "")
                # Skip BTC itself on BTC market
                if base != "BTC" or quote != "BTC":
                    symbols.add(base)
                break

    return sorted(symbols)


def _parse_ai_response(response_text: str) -> Dict[str, Dict[str, str]]:
    """Parse AI response, handling markdown code blocks."""
    response_text = response_text.strip()

    # Remove markdown if present
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
        response_text = response_text.strip()

    return json.loads(response_text)


async def _call_claude(prompt: str) -> str:
    """Call Claude API."""
    from anthropic import AsyncAnthropic

    api_key = settings.anthropic_api_key
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    client = AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    logger.info(f"  Claude tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out")
    return response.content[0].text


async def _call_openai(prompt: str) -> str:
    """Call OpenAI API."""
    from openai import AsyncOpenAI

    api_key = settings.openai_api_key
    if not api_key:
        raise ValueError("OPENAI_API_KEY not configured")

    client = AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=8192,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    usage = response.usage
    if usage:
        logger.info(f"  OpenAI tokens: {usage.prompt_tokens} in, {usage.completion_tokens} out")
    return response.choices[0].message.content or ""


async def _call_gemini(prompt: str) -> str:
    """Call Google Gemini API."""
    import google.generativeai as genai

    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-pro")
    response = await asyncio.to_thread(
        model.generate_content,
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0,
            max_output_tokens=8192,
        )
    )

    return response.text


async def _call_grok(prompt: str) -> str:
    """Call x.AI Grok API (OpenAI-compatible)."""
    from openai import AsyncOpenAI

    api_key = settings.grok_api_key
    if not api_key:
        raise ValueError("GROK_API_KEY not configured")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1"
    )
    response = await client.chat.completions.create(
        model="grok-2-latest",
        max_tokens=8192,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    usage = response.usage
    if usage:
        logger.info(f"  Grok tokens: {usage.prompt_tokens} in, {usage.completion_tokens} out")
    return response.choices[0].message.content or ""


async def call_ai_for_review(coins: List[str], batch_size: int = 50) -> Dict[str, Dict[str, str]]:
    """Call configured AI provider to analyze coins in batches."""
    provider = settings.system_ai_provider.lower()

    # Map provider to call function
    provider_funcs = {
        "claude": _call_claude,
        "openai": _call_openai,
        "chatgpt": _call_openai,  # Alias
        "gemini": _call_gemini,
        "grok": _call_grok,
    }

    call_func = provider_funcs.get(provider)
    if not call_func:
        raise ValueError(f"Unknown AI provider: {provider}. Valid options: claude, openai, gemini, grok")

    logger.info(f"Using AI provider: {provider}")
    all_analysis = {}

    # Process in batches
    total_batches = (len(coins) + batch_size - 1) // batch_size
    logger.info(f"Processing {len(coins)} coins in {total_batches} batches of {batch_size}...")

    for i in range(0, len(coins), batch_size):
        batch = coins[i:i + batch_size]
        batch_num = (i // batch_size) + 1

        coins_list = ", ".join(batch)
        prompt = COIN_REVIEW_PROMPT.format(coins_list=coins_list)

        logger.info(f"Batch {batch_num}/{total_batches}: Reviewing {len(batch)} coins...")

        response_text = await call_func(prompt)
        batch_analysis = _parse_ai_response(response_text)
        all_analysis.update(batch_analysis)

        logger.info(f"  Batch {batch_num}: Got {len(batch_analysis)} results")

        # Small delay between batches to avoid rate limits
        if i + batch_size < len(coins):
            await asyncio.sleep(1)

    logger.info(f"Total analysis: {len(all_analysis)} coins")
    return all_analysis


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

            # Check if global coin entry exists (user_id IS NULL)
            query = select(BlacklistedCoin).where(
                BlacklistedCoin.symbol == symbol.upper(),
                BlacklistedCoin.user_id.is_(None)
            )
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
                # Create global entry (user_id=None)
                entry = BlacklistedCoin(symbol=symbol.upper(), reason=full_reason, user_id=None)
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

        # Call AI provider for analysis
        analysis = await call_ai_for_review(coins)
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
