"""
AI-Dynamic Grid Optimizer

Uses AI to continuously analyze grid performance and optimize parameters.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_service import get_ai_client
from app.exchange_clients.base import ExchangeClient
from app.models import Bot, PendingOrder, Position, Trade

logger = logging.getLogger(__name__)


async def analyze_grid_performance(
    bot: Bot,
    position: Position,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Analyze grid trading performance metrics.

    Returns metrics like fill rate, profit per level, breakout frequency, etc.
    """
    grid_state = bot.strategy_config.get("grid_state", {})

    # Get all trades for this position
    trades_query = select(Trade).where(Trade.position_id == position.id)
    trades_result = await db.execute(trades_query)
    trades = trades_result.scalars().all()

    # Get pending orders
    pending_query = select(PendingOrder).where(
        PendingOrder.bot_id == bot.id,
        PendingOrder.position_id == position.id
    )
    pending_result = await db.execute(pending_query)
    pending_orders = pending_result.scalars().all()

    # Calculate metrics
    total_levels = len(grid_state.get("grid_levels", []))
    filled_levels = sum(1 for level in grid_state.get("grid_levels", []) if level.get("status") == "filled")
    pending_levels = sum(1 for order in pending_orders if order.status == "pending")

    fill_rate = (filled_levels / total_levels * 100) if total_levels > 0 else 0

    # Calculate profit per level
    total_profit = grid_state.get("total_profit_quote", 0)
    avg_profit_per_level = (total_profit / filled_levels) if filled_levels > 0 else 0

    # Time since initialization
    initialized_at = datetime.fromisoformat(grid_state["initialized_at"]) if "initialized_at" in grid_state else datetime.utcnow()
    hours_running = (datetime.utcnow() - initialized_at).total_seconds() / 3600

    # Breakout frequency
    breakout_count = grid_state.get("breakout_count", 0)
    breakouts_per_day = (breakout_count / hours_running * 24) if hours_running > 0 else 0

    return {
        "total_levels": total_levels,
        "filled_levels": filled_levels,
        "pending_levels": pending_levels,
        "fill_rate_percent": fill_rate,
        "total_profit_quote": total_profit,
        "avg_profit_per_level": avg_profit_per_level,
        "hours_running": hours_running,
        "breakout_count": breakout_count,
        "breakouts_per_day": breakouts_per_day,
        "trades_count": len(trades),
    }


async def calculate_market_metrics(
    product_id: str,
    exchange_client: ExchangeClient,
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Calculate current market conditions for AI analysis.
    """
    try:
        # Get recent candles for volatility
        candles = await exchange_client.get_candles(
            product_id,
            granularity="ONE_HOUR",
            lookback_hours=lookback_hours
        )

        if not candles or len(candles) < 7:
            return {"error": "Insufficient market data"}

        # Calculate volatility (standard deviation of returns)
        prices = [float(c["close"]) for c in candles]
        returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]

        import statistics
        volatility = statistics.stdev(returns) * 100 if len(returns) > 1 else 0

        # Price range
        high_24h = max(float(c["high"]) for c in candles)
        low_24h = min(float(c["low"]) for c in candles)
        current_price = prices[-1]
        price_range_percent = ((high_24h - low_24h) / current_price) * 100

        # Trend detection (simple: compare first half avg to second half avg)
        mid = len(prices) // 2
        first_half_avg = sum(prices[:mid]) / mid
        second_half_avg = sum(prices[mid:]) / (len(prices) - mid)
        trend = "upward" if second_half_avg > first_half_avg * 1.02 else "downward" if second_half_avg < first_half_avg * 0.98 else "sideways"

        return {
            "current_price": current_price,
            "volatility_percent": volatility,
            "high_24h": high_24h,
            "low_24h": low_24h,
            "price_range_percent": price_range_percent,
            "trend": trend,
        }

    except Exception as e:
        logger.error(f"Error calculating market metrics: {e}")
        return {"error": str(e)}


async def get_ai_grid_recommendations(
    bot: Bot,
    position: Position,
    grid_performance: Dict[str, Any],
    market_metrics: Dict[str, Any],
    db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Use AI to analyze grid and recommend optimizations.

    Returns dict with recommended adjustments or None if no AI configured.
    """
    # Check if AI optimization is enabled
    if not bot.strategy_config.get("enable_ai_optimization", False):
        return None

    # Get AI provider settings
    ai_provider = bot.strategy_config.get("ai_provider", "anthropic")
    ai_model = bot.strategy_config.get("ai_model", "claude-sonnet-4.5")
    analysis_depth = bot.strategy_config.get("ai_analysis_depth", "standard")

    # Get AI client (use user's API key if configured)
    try:
        ai_client = await get_ai_client(
            provider=ai_provider,
            model=ai_model,
            db=db,
            user_id=bot.user_id
        )
    except Exception as e:
        logger.error(f"Failed to get AI client for grid optimization: {e}")
        return None

    # Build AI prompt
    current_config = bot.strategy_config
    grid_state = current_config.get("grid_state", {})

    prompt = f"""Analyze this grid trading bot's performance and recommend optimizations.

**Current Grid Configuration:**
- Product: {bot.product_id}
- Grid Type: {current_config.get('grid_type', 'arithmetic')}
- Grid Mode: {current_config.get('grid_mode', 'neutral')}
- Range: {grid_state.get('current_range_lower', 'N/A')} - {grid_state.get('current_range_upper', 'N/A')}
- Number of Levels: {current_config.get('num_grid_levels', 'N/A')}
- Total Investment: {current_config.get('total_investment_quote', 'N/A')} {bot.product_id.split('-')[1]}

**Performance Metrics (Last {grid_performance.get('hours_running', 0):.1f} hours):**
- Fill Rate: {grid_performance.get('fill_rate_percent', 0):.1f}%
- Filled Levels: {grid_performance['filled_levels']} / {grid_performance['total_levels']}
- Total Profit: {grid_performance.get('total_profit_quote', 0):.8f} {bot.product_id.split('-')[1]}
- Avg Profit per Level: {grid_performance.get('avg_profit_per_level', 0):.8f} {bot.product_id.split('-')[1]}
- Breakouts: {grid_performance['breakout_count']} ({grid_performance.get('breakouts_per_day', 0):.2f} per day)
- Total Trades: {grid_performance['trades_count']}

**Market Conditions (24h):**
- Current Price: {market_metrics.get('current_price', 'N/A')}
- Volatility: {market_metrics.get('volatility_percent', 0):.2f}%
- 24h Range: {market_metrics.get('price_range_percent', 0):.2f}%
- Trend: {market_metrics.get('trend', 'unknown')}
- High: {market_metrics.get('high_24h', 'N/A')}
- Low: {market_metrics.get('low_24h', 'N/A')}

**Analysis Depth:** {analysis_depth}

**Instructions:**
Analyze this grid's performance and market conditions. Recommend specific adjustments to optimize profitability.

Consider:
1. **Grid Level Count**: Is {current_config.get('num_grid_levels')} optimal? Should we increase (capture more small moves) or decrease (reduce capital lock-up)?
2. **Grid Type**: Should we switch between arithmetic/geometric based on volatility?
3. **Range Adjustment**: Is the current range too tight (frequent breakouts) or too wide (low fill rate)?
4. **Grid Mode**: Given the {market_metrics.get('trend', 'unknown')} trend, should we switch between neutral/long?
5. **Breakout Threshold**: With {grid_performance.get('breakouts_per_day', 0):.2f} breakouts/day, should we adjust sensitivity?

**Output Format (JSON):**
```json
{{
  "recommendation_summary": "Brief explanation of suggested changes",
  "confidence": 0-100,
  "adjustments": {{
    "num_grid_levels": <new_count or null>,
    "grid_type": "<arithmetic/geometric or null>",
    "upper_limit": <new_upper or null>,
    "lower_limit": <new_lower or null>,
    "breakout_threshold_percent": <new_threshold or null>,
    "grid_mode": "<neutral/long or null>"
  }},
  "reasoning": "Detailed explanation of why these changes will improve performance",
  "expected_impact": "What improvement to expect (e.g., 'Increase fill rate by 15%')"
}}
```

Only suggest changes that will meaningfully improve performance. Use null for parameters that should remain unchanged.
"""

    # Get AI recommendation
    try:
        logger.info(f"Requesting AI grid optimization for bot {bot.id}...")
        response = await ai_client.analyze(prompt)

        # Parse JSON response
        import json
        import re

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON without code blocks
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                logger.warning(f"AI response did not contain valid JSON: {response[:200]}")
                return None

        recommendations = json.loads(json_str)

        logger.info(f"AI recommendations for bot {bot.id}: {recommendations.get('recommendation_summary', 'N/A')}")

        return recommendations

    except Exception as e:
        logger.error(f"Error getting AI recommendations: {e}", exc_info=True)
        return None


async def apply_ai_recommendations(
    bot: Bot,
    position: Position,
    recommendations: Dict[str, Any],
    exchange_client: ExchangeClient,
    db: AsyncSession
) -> bool:
    """
    Apply AI-recommended adjustments to the grid.

    Returns True if adjustments were applied successfully.
    """
    adjustments = recommendations.get("adjustments", {})

    # Filter out null adjustments
    adjustments = {k: v for k, v in adjustments.items() if v is not None}

    if not adjustments:
        logger.info(f"No adjustments recommended by AI for bot {bot.id}")
        return False

    logger.info(f"Applying AI recommendations to bot {bot.id}: {adjustments}")

    # Check confidence threshold
    confidence = recommendations.get("confidence", 0)
    if confidence < 50:
        logger.warning(f"AI confidence too low ({confidence}%) - skipping adjustments")
        return False

    # Apply adjustments to config
    for key, value in adjustments.items():
        bot.strategy_config[key] = value

    # Log AI decision
    grid_state = bot.strategy_config.get("grid_state", {})
    if "ai_adjustments" not in grid_state:
        grid_state["ai_adjustments"] = []

    grid_state["ai_adjustments"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "confidence": confidence,
        "adjustments": adjustments,
        "reasoning": recommendations.get("reasoning", ""),
        "expected_impact": recommendations.get("expected_impact", ""),
    })

    bot.strategy_config["grid_state"] = grid_state

    # Trigger grid rebalance to apply new parameters
    # This will cancel old orders and place new ones with updated config
    from app.services.grid_trading_service import rebalance_grid_on_breakout

    current_price = await exchange_client.get_current_price(bot.product_id)

    # Calculate new levels with updated config
    from app.strategies.grid_trading import calculate_arithmetic_levels, calculate_geometric_levels

    grid_type = bot.strategy_config.get("grid_type", "arithmetic")
    upper = bot.strategy_config.get("upper_limit")
    lower = bot.strategy_config.get("lower_limit")
    num_levels = bot.strategy_config.get("num_grid_levels", 20)

    if grid_type == "arithmetic":
        new_levels = calculate_arithmetic_levels(lower, upper, num_levels)
    else:
        new_levels = calculate_geometric_levels(lower, upper, num_levels)

    # Rebalance with new parameters
    await rebalance_grid_on_breakout(
        bot=bot,
        position=position,
        exchange_client=exchange_client,
        db=db,
        breakout_direction="ai_optimization",
        current_price=current_price,
        new_levels=new_levels,
        new_upper=upper,
        new_lower=lower,
    )

    await db.commit()

    logger.info(f"✅ AI adjustments applied to bot {bot.id}: {recommendations.get('recommendation_summary', '')}")

    return True


async def run_ai_grid_optimization(
    bot: Bot,
    position: Position,
    exchange_client: ExchangeClient,
    db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Main function to run AI grid optimization.

    Called periodically by the bot monitoring system.
    Returns AI recommendations if any were made.
    """
    if not bot.strategy_config.get("enable_ai_optimization", False):
        return None

    # Check if enough time has passed since last AI check
    grid_state = bot.strategy_config.get("grid_state", {})
    last_ai_check = grid_state.get("last_ai_check")
    interval_minutes = bot.strategy_config.get("ai_adjustment_interval_minutes", 120)

    if last_ai_check:
        last_check_time = datetime.fromisoformat(last_ai_check)
        minutes_elapsed = (datetime.utcnow() - last_check_time).total_seconds() / 60

        if minutes_elapsed < interval_minutes:
            # Not yet time for AI check
            return None

    logger.info(f"🤖 Running AI grid optimization for bot {bot.id}...")

    # Gather performance metrics
    grid_performance = await analyze_grid_performance(bot, position, db)

    # Gather market metrics
    market_metrics = await calculate_market_metrics(
        bot.product_id,
        exchange_client,
        lookback_hours=24
    )

    # Get AI recommendations
    recommendations = await get_ai_grid_recommendations(
        bot, position, grid_performance, market_metrics, db
    )

    if not recommendations:
        logger.info(f"No AI recommendations generated for bot {bot.id}")
        grid_state["last_ai_check"] = datetime.utcnow().isoformat()
        bot.strategy_config["grid_state"] = grid_state
        await db.commit()
        return None

    # Apply recommendations if confidence is high enough
    applied = await apply_ai_recommendations(
        bot, position, recommendations, exchange_client, db
    )

    # Update last check time
    grid_state["last_ai_check"] = datetime.utcnow().isoformat()
    bot.strategy_config["grid_state"] = grid_state
    await db.commit()

    return recommendations if applied else None
