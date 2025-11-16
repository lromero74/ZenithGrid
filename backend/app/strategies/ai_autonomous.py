"""
AI Autonomous Trading Strategy

Uses Claude AI to analyze markets and make autonomous trading decisions.
Maximizes profit while never selling at a loss.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import anthropic
import os

from app.strategies import TradingStrategy, StrategyDefinition, StrategyParameter, StrategyRegistry
from app.config import settings

logger = logging.getLogger(__name__)


@StrategyRegistry.register
class AIAutonomousStrategy(TradingStrategy):
    """
    AI-powered autonomous trading strategy using Claude.

    Features:
    - Analyzes market data with Claude AI
    - Makes intelligent buy/sell decisions
    - Never sells at a loss
    - Budget grows with profits
    - Token-optimized (caching, batching)
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # Lazy initialization of AI client (only when needed)
        self._client = None

        # Token optimization: Cache recent analyses
        self._analysis_cache: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}
        self._cache_ttl = 300  # 5 minutes cache

        # Track token usage
        self._total_tokens_used = 0
        self._last_analysis_time = None

    @property
    def client(self):
        """Lazy initialization of AI client based on selected provider"""
        if self._client is None:
            provider = self.config.get("ai_provider", "claude").lower()

            if provider == "claude":
                api_key = settings.anthropic_api_key
                if not api_key:
                    raise ValueError(
                        "ANTHROPIC_API_KEY not set in .env file. "
                        "Please add it to your .env file to use AI Autonomous trading with Claude."
                    )
                self._client = anthropic.Anthropic(api_key=api_key)
            elif provider == "gemini":
                # Gemini client will be initialized when needed
                # Import is deferred to avoid requiring google-generativeai for Claude users
                pass
            else:
                raise ValueError(f"Unknown AI provider: {provider}. Must be 'claude' or 'gemini'.")

        return self._client

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="ai_autonomous",
            name="AI Autonomous Trading",
            description="AI-powered autonomous trading that analyzes markets and makes intelligent decisions to maximize profit. Never sells at a loss.",
            parameters=[
                StrategyParameter(
                    name="ai_provider",
                    display_name="AI Provider",
                    description="Which AI model to use for market analysis",
                    type="string",
                    default="claude",
                    options=["claude", "gemini"]
                ),
                StrategyParameter(
                    name="max_concurrent_deals",
                    display_name="Max Concurrent Deals",
                    description="Maximum number of positions that can be open at the same time",
                    type="int",
                    default=1,
                    min_value=1,
                    max_value=10
                ),
                StrategyParameter(
                    name="market_focus",
                    display_name="Market Focus",
                    description="Which market pairs to analyze (BTC pairs or USD pairs)",
                    type="string",
                    default="BTC",
                    options=["BTC", "USD", "ALL"]
                ),
                StrategyParameter(
                    name="initial_budget_percentage",
                    display_name="Initial Budget %",
                    description="Percentage of balance to allocate initially",
                    type="float",
                    default=10.0,
                    min_value=1.0,
                    max_value=50.0
                ),
                StrategyParameter(
                    name="max_position_size_percentage",
                    display_name="Max Position Size %",
                    description="Maximum percentage of budget per position",
                    type="float",
                    default=25.0,
                    min_value=5.0,
                    max_value=100.0
                ),
                StrategyParameter(
                    name="risk_tolerance",
                    display_name="Risk Tolerance",
                    description="How aggressive should the AI be (conservative, moderate, aggressive)",
                    type="string",
                    default="moderate",
                    options=["conservative", "moderate", "aggressive"]
                ),
                StrategyParameter(
                    name="analysis_interval_minutes",
                    display_name="Analysis Interval (minutes)",
                    description="How often to ask Claude for new analysis (minimum 5 minutes to save tokens)",
                    type="int",
                    default=15,
                    min_value=5,
                    max_value=120
                ),
                StrategyParameter(
                    name="min_profit_percentage",
                    display_name="Minimum Profit % to Sell",
                    description="Only sell if profit is at least this percentage",
                    type="float",
                    default=1.0,
                    min_value=0.1,
                    max_value=10.0
                ),
                StrategyParameter(
                    name="profit_calculation_method",
                    display_name="Profit Calculation Method",
                    description="How to calculate profit: from average cost (cost_basis) or from initial entry (base_order)",
                    type="string",
                    default="cost_basis",
                    options=["cost_basis", "base_order"]
                ),
                StrategyParameter(
                    name="custom_instructions",
                    display_name="Custom Instructions (Optional)",
                    description="Additional instructions to guide the AI's trading decisions",
                    type="text",
                    default="",
                    required=False
                )
            ]
        )

    def validate_config(self):
        """Validate configuration parameters"""
        required = [
            "ai_provider",
            "market_focus",
            "initial_budget_percentage",
            "max_position_size_percentage",
            "risk_tolerance",
            "analysis_interval_minutes",
            "min_profit_percentage"
        ]

        for param in required:
            if param not in self.config:
                # Use defaults
                definition = self.get_definition()
                for p in definition.parameters:
                    if p.name == param:
                        self.config[param] = p.default
                        break

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        candles_by_timeframe: Optional[Dict[str, List[Dict[str, Any]]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Use Claude AI to analyze market data and generate trading signals

        Token Optimization:
        - Cache analyses for configured interval
        - Summarize data instead of sending raw candles
        - Use structured output for parsing
        """

        # Check if we should skip analysis (token optimization)
        if self._should_skip_analysis():
            logger.info("Skipping analysis (within cache interval)")
            return self._get_cached_analysis()

        try:
            # Prepare market context (summarized to save tokens)
            market_context = self._prepare_market_context(candles, current_price)

            # Call AI for analysis based on selected provider
            provider = self.config.get("ai_provider", "claude").lower()
            logger.info(f"🤖 Calling {provider.upper()} AI for market analysis...")

            if provider == "claude":
                analysis = await self._get_claude_analysis(market_context)
            elif provider == "gemini":
                analysis = await self._get_gemini_analysis(market_context)
            else:
                raise ValueError(f"Unknown AI provider: {provider}")

            # Cache the result
            cache_key = f"{current_price}_{len(candles)}"
            self._analysis_cache[cache_key] = (datetime.utcnow(), analysis)
            self._last_analysis_time = datetime.utcnow()

            return analysis

        except Exception as e:
            logger.error(f"Error in AI analysis: {e}", exc_info=True)
            return None

    def _should_skip_analysis(self) -> bool:
        """Check if we should skip analysis to save tokens"""
        if not self._last_analysis_time:
            return False

        interval_minutes = self.config.get("analysis_interval_minutes", 15)
        time_since_last = (datetime.utcnow() - self._last_analysis_time).total_seconds() / 60

        return time_since_last < interval_minutes

    def _get_cached_analysis(self) -> Optional[Dict[str, Any]]:
        """Get most recent cached analysis"""
        if not self._analysis_cache:
            return None

        # Get most recent cache entry
        latest_key = max(self._analysis_cache.keys(), key=lambda k: self._analysis_cache[k][0])
        return self._analysis_cache[latest_key][1]

    def _prepare_market_context(self, candles: List[Dict[str, Any]], current_price: float) -> Dict[str, Any]:
        """
        Prepare summarized market context for Claude (token-efficient)

        Includes:
        - Technical data (price action, trends)
        - Sentiment data (news, social media) - when available
        """
        if not candles:
            return {"current_price": current_price, "data_points": 0}

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
        sentiment_data = self._get_sentiment_data()
        if sentiment_data:
            context["sentiment"] = sentiment_data

        return context

    def _get_sentiment_data(self) -> Optional[Dict[str, Any]]:
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

    async def _get_claude_analysis(self, market_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call Claude API for market analysis

        Uses structured prompt to get concise, parseable responses
        """

        risk_tolerance = self.config.get("risk_tolerance", "moderate")
        market_focus = self.config.get("market_focus", "BTC")
        custom_instructions = self.config.get("custom_instructions", "").strip()

        sentiment_info = ""
        if "sentiment" in market_context:
            sent = market_context["sentiment"]
            sentiment_info = f"""
**Market Sentiment & News:**
- Twitter Sentiment: {sent.get('twitter_sentiment', 'N/A')}
- News Headlines: {', '.join(sent.get('news_headlines', [])[:3])}
- Reddit Sentiment: {sent.get('reddit_sentiment', 'N/A')}
- Fear & Greed Index: {sent.get('fear_greed_index', 'N/A')}/100
- Summary: {sent.get('summary', 'No sentiment data available')}
"""

        prompt = f"""You are an expert cryptocurrency trading AI analyzing market data.

**Current Market Data:**
- Current Price: {market_context['current_price']}
- 24h Change: {market_context['price_change_24h_pct']}%
- Period High: {market_context['period_high']}
- Period Low: {market_context['period_low']}
- Volatility: {market_context['volatility']}%
- Recent Price Trend: {market_context['recent_prices'][-5:]}
{sentiment_info}
**Trading Parameters:**
- Risk Tolerance: {risk_tolerance}
- Market Focus: {market_focus} pairs
{f"- Custom Instructions: {custom_instructions}" if custom_instructions else ""}

**Your Task:**
Analyze this data (including sentiment/news if provided) and provide a trading recommendation. Consider both technical patterns AND real-world sentiment/news. Respond ONLY with a JSON object (no markdown formatting) in this exact format:

{{
  "action": "buy" or "hold" or "sell",
  "confidence": 0-100,
  "reasoning": "brief explanation (1-2 sentences)",
  "suggested_allocation_pct": 0-100,
  "expected_profit_pct": 0-10
}}

Remember:
- Only suggest "buy" if you see clear profit opportunity
- Only suggest "sell" if you're confident price will drop
- Suggest "hold" if market is unclear
- Be {risk_tolerance} in your recommendations
- Keep reasoning concise to save tokens"""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",  # Claude Sonnet 4.5 (latest)
                max_tokens=1000,  # Allow for detailed reasoning
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Track token usage
            self._total_tokens_used += response.usage.input_tokens + response.usage.output_tokens
            logger.info(f"📊 Claude API - Input: {response.usage.input_tokens} tokens, Output: {response.usage.output_tokens} tokens, Total: {self._total_tokens_used}")

            # Parse response
            response_text = response.content[0].text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            analysis = json.loads(response_text)

            # Convert to our signal format
            signal_type = "none"
            if analysis["action"] == "buy":
                signal_type = "buy"
            elif analysis["action"] == "sell":
                signal_type = "sell"

            return {
                "signal_type": signal_type,
                "confidence": analysis.get("confidence", 50),
                "reasoning": analysis.get("reasoning", "AI analysis"),
                "suggested_allocation_pct": analysis.get("suggested_allocation_pct", 10),
                "expected_profit_pct": analysis.get("expected_profit_pct", 1.0),
                "raw_analysis": analysis
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {response_text}")
            logger.error(f"JSON error: {e}")
            return {
                "signal_type": "hold",
                "confidence": 0,
                "reasoning": "Failed to parse AI response",
                "suggested_allocation_pct": 0,
                "expected_profit_pct": 0
            }
        except Exception as e:
            logger.error(f"Error calling Claude API: {e}", exc_info=True)
            return {
                "signal_type": "hold",
                "confidence": 0,
                "reasoning": f"Error: {str(e)}",
                "suggested_allocation_pct": 0,
                "expected_profit_pct": 0
            }

    async def _get_gemini_analysis(self, market_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call Gemini API for market analysis

        Uses structured prompt to get concise, parseable responses
        """
        try:
            # Lazy import of Gemini library
            import google.generativeai as genai
        except ImportError:
            logger.error("google-generativeai not installed. Run: pip install google-generativeai")
            return {
                "signal_type": "hold",
                "confidence": 0,
                "reasoning": "Gemini library not installed",
                "suggested_allocation_pct": 0,
                "expected_profit_pct": 0
            }

        # Initialize Gemini client
        api_key = settings.gemini_api_key
        if not api_key:
            logger.error("GEMINI_API_KEY not set in .env file")
            return {
                "signal_type": "hold",
                "confidence": 0,
                "reasoning": "Gemini API key not configured",
                "suggested_allocation_pct": 0,
                "expected_profit_pct": 0
            }

        genai.configure(api_key=api_key)

        risk_tolerance = self.config.get("risk_tolerance", "moderate")
        market_focus = self.config.get("market_focus", "BTC")
        custom_instructions = self.config.get("custom_instructions", "").strip()

        sentiment_info = ""
        if "sentiment" in market_context:
            sent = market_context["sentiment"]
            sentiment_info = f"""
**Market Sentiment & News:**
- Twitter Sentiment: {sent.get('twitter_sentiment', 'N/A')}
- News Headlines: {', '.join(sent.get('news_headlines', [])[:3])}
- Reddit Sentiment: {sent.get('reddit_sentiment', 'N/A')}
- Fear & Greed Index: {sent.get('fear_greed_index', 'N/A')}/100
- Summary: {sent.get('summary', 'No sentiment data available')}
"""

        prompt = f"""You are an expert cryptocurrency trading AI analyzing market data.

**Current Market Data:**
- Current Price: {market_context['current_price']}
- 24h Change: {market_context['price_change_24h_pct']}%
- Period High: {market_context['period_high']}
- Period Low: {market_context['period_low']}
- Volatility: {market_context['volatility']}%
- Recent Price Trend: {market_context['recent_prices'][-5:]}
{sentiment_info}
**Trading Parameters:**
- Risk Tolerance: {risk_tolerance}
- Market Focus: {market_focus} pairs
{f"- Custom Instructions: {custom_instructions}" if custom_instructions else ""}

**Your Task:**
Analyze this data (including sentiment/news if provided) and provide a trading recommendation. Consider both technical patterns AND real-world sentiment/news. Respond ONLY with a JSON object (no markdown formatting) in this exact format:

{{
  "action": "buy" or "hold" or "sell",
  "confidence": 0-100,
  "reasoning": "brief explanation (1-2 sentences)",
  "suggested_allocation_pct": 0-100,
  "expected_profit_pct": 0-10
}}

Remember:
- Only suggest "buy" if you see clear profit opportunity
- Only suggest "sell" if you're confident price will drop
- Suggest "hold" if market is unclear
- Be {risk_tolerance} in your recommendations
- Keep reasoning concise"""

        try:
            model = genai.GenerativeModel('gemini-2.5-flash')  # Latest Gemini 2.5 Flash
            response = model.generate_content(prompt)

            # Parse response
            response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            analysis = json.loads(response_text)

            # Track token usage (Gemini provides usage metadata)
            if hasattr(response, 'usage_metadata'):
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
                self._total_tokens_used += input_tokens + output_tokens
                logger.info(f"📊 Gemini API - Input: {input_tokens} tokens, Output: {output_tokens} tokens, Total: {self._total_tokens_used}")

            # Convert to our signal format
            signal_type = "none"
            if analysis["action"] == "buy":
                signal_type = "buy"
            elif analysis["action"] == "sell":
                signal_type = "sell"

            return {
                "signal_type": signal_type,
                "confidence": analysis.get("confidence", 50),
                "reasoning": analysis.get("reasoning", "AI analysis"),
                "suggested_allocation_pct": analysis.get("suggested_allocation_pct", 10),
                "expected_profit_pct": analysis.get("expected_profit_pct", 1.0),
                "raw_analysis": analysis
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {response_text}")
            logger.error(f"JSON error: {e}")
            return {
                "signal_type": "hold",
                "confidence": 0,
                "reasoning": "Failed to parse AI response",
                "suggested_allocation_pct": 0,
                "expected_profit_pct": 0
            }
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}", exc_info=True)
            return {
                "signal_type": "hold",
                "confidence": 0,
                "reasoning": f"Error: {str(e)}",
                "suggested_allocation_pct": 0,
                "expected_profit_pct": 0
            }

    async def should_buy(
        self,
        signal_data: Dict[str, Any],
        position: Optional[Any],
        btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should buy based on Claude's analysis

        Rules:
        - Only buy if AI suggests it with good confidence
        - Respect budget limits
        - Don't buy if we already have a position (for now)
        """

        if signal_data.get("signal_type") != "buy":
            return False, 0.0, "AI did not suggest buying"

        confidence = signal_data.get("confidence", 0)
        if confidence < 60:
            return False, 0.0, f"AI confidence too low ({confidence}%)"

        # Don't open multiple positions for same pair (simplified for now)
        if position is not None:
            return False, 0.0, "Already have open position for this pair"

        # Calculate buy amount based on AI suggestion and budget
        suggested_pct = signal_data.get("suggested_allocation_pct", 10)
        max_pct = self.config.get("max_position_size_percentage", 25)

        # Use lesser of AI suggestion and max allowed
        use_pct = min(suggested_pct, max_pct)

        # Smart budget division by max concurrent deals (3Commas style)
        max_deals = self.config.get("max_concurrent_deals", 1)
        if max_deals > 1:
            # Divide budget equally among max concurrent deals
            use_pct = use_pct / max_deals

        btc_amount = btc_balance * (use_pct / 100.0)

        if btc_amount <= 0:
            return False, 0.0, "Insufficient balance"

        reasoning = signal_data.get("reasoning", "AI recommends buying")
        return True, btc_amount, f"AI BUY ({confidence}% confidence): {reasoning}"

    async def should_sell(
        self,
        signal_data: Dict[str, Any],
        position: Any,
        current_price: float
    ) -> Tuple[bool, str]:
        """
        Determine if we should sell

        Rules:
        - NEVER sell at a loss (user requirement)
        - Only sell if profit >= min_profit_percentage
        - Consider AI recommendation
        - Calculate profit based on selected method (cost_basis or base_order)
        """

        # Determine profit calculation method
        profit_method = self.config.get("profit_calculation_method", "cost_basis")

        # Get entry price based on selected method
        if profit_method == "base_order":
            # Calculate from first trade (base order) only
            buy_trades = [t for t in position.trades if t.side == "buy"]
            if not buy_trades:
                return False, "No entry price yet - position has no trades"
            # Sort by timestamp to get first trade
            buy_trades.sort(key=lambda t: t.timestamp)
            entry_price = buy_trades[0].price
        else:
            # Default: cost_basis - use average buy price across all trades
            entry_price = position.average_buy_price
            if entry_price == 0:
                return False, "No entry price yet - position has no trades"

        profit_pct = ((current_price - entry_price) / entry_price * 100)

        min_profit = self.config.get("min_profit_percentage", 1.0)

        # RULE 1: Never sell at a loss
        if profit_pct <= 0:
            return False, f"Never sell at loss (current: {profit_pct:.2f}%)"

        # RULE 2: Only sell if profit meets minimum
        if profit_pct < min_profit:
            return False, f"Profit {profit_pct:.2f}% below minimum {min_profit}%"

        # RULE 3: Consider AI recommendation
        if signal_data.get("signal_type") == "sell":
            confidence = signal_data.get("confidence", 0)
            if confidence >= 70:
                reasoning = signal_data.get("reasoning", "AI recommends selling")
                return True, f"AI SELL ({confidence}% confidence, {profit_pct:.2f}% profit): {reasoning}"

        # RULE 4: Sell if we hit expected profit from AI's original analysis
        expected_profit = signal_data.get("expected_profit_pct", 0)
        if expected_profit > 0 and profit_pct >= expected_profit:
            return True, f"Hit expected profit target ({profit_pct:.2f}% >= {expected_profit}%)"

        return False, f"Holding for more profit (current: {profit_pct:.2f}%)"
