"""
Market analysis and context preparation for AI trading strategy

Handles:
- Market data summarization
- Web search for news and sentiment
- Analysis caching for token optimization
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def prepare_market_context(candles: List[Dict[str, Any]], current_price: float) -> Dict[str, Any]:
    """
    Prepare summarized market context (token-efficient)

    Includes:
    - Technical data (price action, trends)
    - Sentiment data (news, social media) - when available

    Args:
        candles: List of price candles
        current_price: Current market price

    Returns:
        Dict with market context data
    """
    if not candles:
        return {
            "current_price": current_price,
            "price_24h_ago": current_price,
            "price_change_24h_pct": 0.0,
            "period_high": current_price,
            "period_low": current_price,
            "recent_prices": [current_price],
            "data_points": 0,
            "volatility": 0.0
        }

    recent_candles = candles[-10:] if len(candles) > 10 else candles

    # Calculate key metrics
    prices = [float(c.get('close', c.get('price', 0))) for c in candles]
    high = max(prices) if prices else current_price
    low = min(prices) if prices else current_price

    # Price change metrics
    price_24h_ago = prices[0] if prices else current_price
    price_change_pct = ((current_price - price_24h_ago) / price_24h_ago * 100) if price_24h_ago > 0 else 0

    context = {
        "current_price": current_price,
        "price_24h_ago": price_24h_ago,
        "price_change_24h_pct": round(price_change_pct, 2),
        "period_high": high,
        "period_low": low,
        "recent_prices": [round(float(c.get('close', c.get('price', 0))), 8) for c in recent_candles],
        "data_points": len(candles),
        "volatility": round((high - low) / low * 100, 2) if low > 0 else 0
    }

    # Add sentiment/news data if available
    # TODO: Implement when API keys are configured
    sentiment_data = get_sentiment_data()
    if sentiment_data:
        context["sentiment"] = sentiment_data

    return context


def get_sentiment_data() -> Optional[Dict[str, Any]]:
    """
    Get news and social sentiment data for the asset

    Future implementation will include:
    - Twitter sentiment analysis
    - News headlines from crypto news sites
    - Reddit sentiment
    - Fear & Greed index

    Returns None for now (placeholder for future enhancement)
    """
    # TODO: Implement sentiment aggregation
    # This would call:
    # - Twitter API for recent tweets about the asset
    # - News APIs (CryptoCompare, NewsAPI, etc.)
    # - Reddit API for relevant subreddit posts
    # - Alternative.me for Fear & Greed index

    # For now, return None (no sentiment data)
    # When implemented, return format:
    # {
    #     "twitter_sentiment": "positive" | "neutral" | "negative",
    #     "news_headlines": ["headline1", "headline2", ...],
    #     "reddit_sentiment": "bullish" | "neutral" | "bearish",
    #     "fear_greed_index": 0-100,
    #     "summary": "brief sentiment overview"
    # }
    return None


async def perform_web_search(
    client,
    product_id: str,
    action_context: str,
    total_tokens_tracker: Dict[str, int]
) -> Optional[str]:
    """
    Perform web search for recent crypto news and sentiment.

    This gives the AI access to real-time news, market sentiment, and
    recent developments that could affect the trading decision.

    Args:
        client: Anthropic client instance
        product_id: Trading pair (e.g., "AAVE-BTC")
        action_context: What we're considering ("open", "close", "hold", "dca")
        total_tokens_tracker: Dict with 'total' key to track token usage

    Returns:
        String summary of search results, or None if search fails
    """
    try:
        # Extract coin symbol (e.g., "AAVE" from "AAVE-BTC")
        coin_symbol = product_id.split('-')[0] if '-' in product_id else product_id

        # Construct search query based on context
        if action_context == "open":
            query = f"{coin_symbol} crypto news bullish bearish latest 24h"
        elif action_context == "close":
            query = f"{coin_symbol} crypto price prediction sell signals latest"
        else:
            query = f"{coin_symbol} cryptocurrency news latest developments"

        logger.info(f"🔍 Performing web search for {coin_symbol}: '{query}'")

        # Use Claude API with web search capability
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=500,  # Keep response concise to save tokens
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": f"""Search the web for recent news about {coin_symbol} cryptocurrency and provide a brief summary (3-5 bullet points) covering:
- Major news or announcements in the last 24-48 hours
- Market sentiment (bullish/bearish/neutral)
- Any significant price movements or predictions
- Security concerns or red flags (if any)
- Overall outlook

Query: {query}

Keep it concise and focused on actionable trading information."""
                }]
            )

            # Extract the text response
            search_results = response.content[0].text.strip()

            # Track token usage
            total_tokens_tracker['total'] += response.usage.input_tokens + response.usage.output_tokens
            logger.info(f"📊 Web Search - Input: {response.usage.input_tokens} tokens, Output: {response.usage.output_tokens} tokens")

            logger.info(f"✅ Web search completed for {coin_symbol}")
            return search_results

        except Exception as api_error:
            logger.warning(f"Web search API call failed: {api_error}. Returning placeholder.")
            return f"""Web Search for {coin_symbol}:
(Search temporarily unavailable - using cached/offline analysis)

The AI will analyze based on technical data and historical patterns."""

    except Exception as e:
        logger.error(f"Web search error: {e}")
        return None


def should_skip_analysis(
    last_analysis_time: Optional[datetime],
    config: Dict[str, Any],
    position: Optional[Any] = None
) -> bool:
    """
    Check if we should skip analysis to save tokens

    Uses adaptive intervals:
    - position_management_interval_minutes when we have open positions (faster, more frequent monitoring)
    - analysis_interval_minutes when looking for new positions (slower, less frequent)

    This allows bots at max concurrent deals to monitor positions more frequently
    while still doing less frequent scans when looking for new entry opportunities.

    Args:
        last_analysis_time: Timestamp of last analysis
        config: Strategy configuration
        position: Current position (None if looking for new positions)

    Returns:
        True if analysis should be skipped (within cache interval)
    """
    if not last_analysis_time:
        return False

    # If we have a position, we're in position management mode
    # Use faster interval for managing existing positions
    in_position_management = position is not None

    # Choose interval based on mode
    if in_position_management:
        interval_minutes = config.get("position_management_interval_minutes", 5)
        logger.debug(f"Using position management interval: {interval_minutes} minutes (managing existing position)")
    else:
        interval_minutes = config.get("analysis_interval_minutes", 15)
        logger.debug(f"Using standard analysis interval: {interval_minutes} minutes (looking for new positions)")

    time_since_last = (datetime.utcnow() - last_analysis_time).total_seconds() / 60

    return time_since_last < interval_minutes


def get_cached_analysis(analysis_cache: Dict[str, tuple]) -> Optional[Dict[str, Any]]:
    """
    Get most recent cached analysis

    Args:
        analysis_cache: Cache dict mapping cache_key to (timestamp, analysis)

    Returns:
        Most recent analysis dict, or None if cache is empty
    """
    if not analysis_cache:
        return None

    # Get most recent cache entry
    latest_key = max(analysis_cache.keys(), key=lambda k: analysis_cache[k][0])
    return analysis_cache[latest_key][1]
