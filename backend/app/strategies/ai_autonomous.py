"""
AI Autonomous Trading Strategy

Uses Claude AI to analyze markets and make autonomous trading decisions.
Maximizes profit while never selling at a loss.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import anthropic
import httpx

from app.config import settings
from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)

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

        # Track last web search time per position (for periodic search)
        self._last_search_time: Dict[int, datetime] = {}

    def _should_perform_web_search(
        self,
        position: Optional[Any],
        action_context: str  # "open", "close", "hold", "dca"
    ) -> bool:
        """
        Determine if we should perform a web search based on configuration and context.

        Args:
            position: Current position (None if considering opening)
            action_context: What we're considering - "open", "close", "hold", "dca"

        Returns:
            bool: True if we should search
        """
        # Check if web search is enabled
        if not self.config.get("use_web_search", False):
            return False

        # Opening a position
        if action_context == "open" and position is None:
            return self.config.get("search_on_open", True)

        # Closing a position
        if action_context == "close":
            return self.config.get("search_on_close", True)

        # Holding or DCA - check search_while_holding setting
        search_mode = self.config.get("search_while_holding", "smart")

        if search_mode == "never":
            return False

        if search_mode == "periodic":
            # Check if enough time has passed since last search
            if position and position.id in self._last_search_time:
                hours_since_search = (datetime.utcnow() - self._last_search_time[position.id]).total_seconds() / 3600
                interval = self.config.get("search_interval_hours", 6)
                if hours_since_search < interval:
                    return False
            return True

        if search_mode == "smart":
            # Only search when considering significant actions
            if action_context == "dca":
                return True  # DCA is a significant decision

            # For hold decisions, search if:
            # - Holding for more than 24 hours
            # - Price has moved significantly (>5%) from entry
            if position:
                holding_hours = (datetime.utcnow() - position.opened_at).total_seconds() / 3600
                if holding_hours > 24:
                    # Check if we've searched recently
                    if position.id in self._last_search_time:
                        hours_since_search = (datetime.utcnow() - self._last_search_time[position.id]).total_seconds() / 3600
                        if hours_since_search < 6:  # Don't search more than every 6 hours for holds
                            return False
                    return True

            return False  # Default: don't search for routine holds

        return False

    def _format_price(self, price: float, product_id: str) -> str:
        """Format price with correct precision and currency based on product_id"""
        quote_currency = product_id.split('-')[1] if '-' in product_id else 'BTC'
        if quote_currency == 'USD':
            return f"{price:.2f} USD"
        else:
            return f"{price:.8f} BTC"

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
                    options=["claude", "gemini", "grok"]
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
                    name="enable_dca",
                    display_name="Enable DCA (Dollar Cost Averaging)",
                    description="Allow AI to add to existing positions when confident",
                    type="bool",
                    default=True
                ),
                StrategyParameter(
                    name="max_safety_orders",
                    display_name="Max Safety Orders (DCA Buys)",
                    description="Maximum number of additional buys (DCA) per position",
                    type="int",
                    default=3,
                    min_value=0,
                    max_value=10
                ),
                StrategyParameter(
                    name="safety_order_percentage",
                    display_name="Safety Order Size %",
                    description="Percentage of budget for each DCA buy",
                    type="float",
                    default=5.0,
                    min_value=1.0,
                    max_value=25.0
                ),
                StrategyParameter(
                    name="min_price_drop_for_dca",
                    display_name="Min Price Drop for DCA %",
                    description="Minimum price drop from average before allowing DCA (helps average down)",
                    type="float",
                    default=2.0,
                    min_value=0.0,
                    max_value=20.0
                ),
                StrategyParameter(
                    name="dca_confidence_threshold",
                    display_name="DCA Confidence Threshold %",
                    description="AI confidence required to DCA (higher = more selective)",
                    type="int",
                    default=80,
                    min_value=50,
                    max_value=95
                ),
                StrategyParameter(
                    name="safety_order_type",
                    display_name="Safety Order Type",
                    description="Market orders execute immediately; limit orders wait at target price (AI bots use market)",
                    type="string",
                    default="market",
                    options=["market", "limit"]
                ),
                StrategyParameter(
                    name="min_daily_volume",
                    display_name="Minimum Daily Volume",
                    description="Minimum 24h trading volume in quote currency (BTC or USD). Pairs below this threshold are filtered out.",
                    type="float",
                    default=100.0,
                    min_value=0.0,
                    max_value=1000000.0
                ),
                StrategyParameter(
                    name="custom_instructions",
                    display_name="Custom Instructions (Optional)",
                    description="Additional instructions to guide the AI's trading decisions",
                    type="text",
                    default="",
                    required=False
                ),
                StrategyParameter(
                    name="use_web_search",
                    display_name="Enable Web Search",
                    description="Allow AI to search the web for recent news and sentiment (uses more tokens)",
                    type="bool",
                    default=False
                ),
                StrategyParameter(
                    name="search_on_open",
                    display_name="Search Before Opening Position",
                    description="Search for news before opening a new position (recommended)",
                    type="bool",
                    default=True
                ),
                StrategyParameter(
                    name="search_on_close",
                    display_name="Search Before Closing Position",
                    description="Search for news before closing a position (recommended)",
                    type="bool",
                    default=True
                ),
                StrategyParameter(
                    name="search_while_holding",
                    display_name="Search While Holding",
                    description="When to search for news while holding: never, smart (only when considering action), or periodic",
                    type="string",
                    default="smart",
                    options=["never", "smart", "periodic"]
                ),
                StrategyParameter(
                    name="search_interval_hours",
                    display_name="Periodic Search Interval (hours)",
                    description="If search_while_holding is 'periodic', search every N hours",
                    type="int",
                    default=6,
                    min_value=1,
                    max_value=24
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
        candles_by_timeframe: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        position: Optional[Any] = None,
        action_context: str = "hold"
    ) -> Optional[Dict[str, Any]]:
        """
        Use Claude AI to analyze market data and generate trading signals

        Token Optimization:
        - Cache analyses for configured interval
        - Summarize data instead of sending raw candles
        - Use structured output for parsing

        Web Search Integration:
        - Performs web search when configured (open, close, smart/periodic while holding)
        - Includes search results in AI prompt for informed decision making
        """

        # Check if we should skip analysis (token optimization)
        if self._should_skip_analysis():
            logger.info("Skipping analysis (within cache interval)")
            return self._get_cached_analysis()

        try:
            # Prepare market context (summarized to save tokens)
            market_context = self._prepare_market_context(candles, current_price)

            # Determine product_id from position or config
            product_id = None
            if position and hasattr(position, 'product_id'):
                product_id = position.product_id
            elif 'product_id' in self.config:
                product_id = self.config['product_id']

            # Perform web search if configured
            web_search_results = None
            if product_id and self._should_perform_web_search(position, action_context):
                web_search_results = await self._perform_web_search(product_id, action_context)
                if web_search_results:
                    market_context['web_search_results'] = web_search_results
                    self._last_search_time = datetime.utcnow()
                    logger.info(f"🔍 Web search results added to market context")

            # Call AI for analysis based on selected provider
            provider = self.config.get("ai_provider", "claude").lower()
            logger.info(f"🤖 Calling {provider.upper()} AI for market analysis...")

            if provider == "claude":
                analysis = await self._get_claude_analysis(market_context)
            elif provider == "gemini":
                analysis = await self._get_gemini_analysis(market_context)
            elif provider == "grok":
                analysis = await self._get_grok_analysis(market_context)
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

    async def _perform_web_search(self, product_id: str, action_context: str) -> Optional[str]:
        """
        Perform web search for recent crypto news and sentiment.

        This gives the AI access to real-time news, market sentiment, and
        recent developments that could affect the trading decision.

        Args:
            product_id: Trading pair (e.g., "AAVE-BTC")
            action_context: What we're considering ("open", "close", "hold", "dca")

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
                response = self.client.messages.create(
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
                self._total_tokens_used += response.usage.input_tokens + response.usage.output_tokens
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

    def _build_standard_analysis_prompt(self, market_context: Dict[str, Any]) -> str:
        """
        Build standardized analysis prompt used by ALL AI providers (Claude, Gemini, Grok)

        This ensures all AI models receive identical instructions and context,
        making their performance directly comparable.
        """
        risk_tolerance = self.config.get("risk_tolerance", "moderate")
        market_focus = self.config.get("market_focus", "BTC")
        custom_instructions = self.config.get("custom_instructions", "").strip()

        # Sentiment info (if available)
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

        # Web search results (if available)
        web_search_info = ""
        if "web_search_results" in market_context:
            web_search_info = f"""
**Real-Time Web Search Results:**
{market_context['web_search_results']}
"""

        # Format price with appropriate precision
        current_price = market_context['current_price']
        price_str = f"{current_price:.8f}" if current_price < 1 else f"{current_price:.2f}"

        prompt = f"""You are an expert cryptocurrency trading AI analyzing market data.

**Current Market Data:**
- Current Price: {price_str} BTC
- 24h Change: {market_context['price_change_24h_pct']}%
- Period High: {market_context['period_high']:.8f} BTC
- Period Low: {market_context['period_low']:.8f} BTC
- Volatility: {market_context['volatility']}%
- Recent Price Trend: {[f"{p:.8f}" for p in market_context['recent_prices'][-5:]]}
{sentiment_info}{web_search_info}
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

        return prompt

    def _build_standard_batch_analysis_prompt(self, pairs_data: Dict[str, Dict[str, Any]]) -> str:
        """
        Build standardized batch analysis prompt for ALL AI providers (Claude, Gemini, Grok)

        Analyzes multiple trading pairs in a single API call for efficiency.
        """
        risk_tolerance = self.config.get("risk_tolerance", "moderate")

        # Build summary for all pairs
        pairs_summary = []
        for product_id, data in pairs_data.items():
            ctx = data.get("market_context", {})
            price_str = self._format_price(ctx.get('current_price', 0), product_id)
            recent_prices = ctx.get('recent_prices', [])[-3:]
            pairs_summary.append(f"""
**{product_id}:**
- Current Price: {price_str}
- 24h Change: {ctx.get('price_change_24h_pct', 0):.2f}%
- Volatility: {ctx.get('volatility', 0):.2f}%
- Recent Trend: {recent_prices}""")

        prompt = f"""You are analyzing {len(pairs_data)} cryptocurrency pairs simultaneously. Provide trading recommendations for ALL pairs in a single JSON response.

**Market Data for All Pairs:**
{''.join(pairs_summary)}

**Trading Parameters:**
- Risk Tolerance: {risk_tolerance}

**Your Task:**
Analyze ALL pairs and respond with a JSON object where keys are product IDs and values are analysis objects. Format:

{{
  "ETH-BTC": {{
    "action": "buy" | "hold" | "sell",
    "confidence": 0-100,
    "reasoning": "brief 1-2 sentence explanation",
    "suggested_allocation_pct": 0-100,
    "expected_profit_pct": 0-10
  }},
  "SOL-BTC": {{...}},
  ...
}}

Remember:
- Analyze each pair independently
- Only suggest "buy" if you see clear profit opportunity
- Only suggest "sell" if you're confident price will drop
- Suggest "hold" if market is unclear
- Be {risk_tolerance} in your recommendations
- Keep reasoning concise to save tokens
- Return valid JSON only (no markdown, no code blocks)"""

        return prompt

    async def _get_claude_analysis(self, market_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call Claude API for market analysis

        Uses standardized prompt template shared across all AI providers
        """
        # Use shared prompt template
        prompt = self._build_standard_analysis_prompt(market_context)

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",  # Claude Sonnet 4.5 (latest)
                max_tokens=1000,  # Allow for detailed reasoning
                temperature=0,  # Deterministic responses (eliminates flip-flopping)
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
                "current_price": market_context['current_price'],  # Include current price for DCA logic
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

        Uses standardized prompt template shared across all AI providers
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

        # Use shared prompt template
        prompt = self._build_standard_analysis_prompt(market_context)

        try:
            model = genai.GenerativeModel(
                'gemini-2.5-flash',  # Latest Gemini 2.5 Flash
                generation_config={"temperature": 0}  # Deterministic responses
            )
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
                "current_price": market_context['current_price'],  # Include current price for DCA logic
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

    async def analyze_multiple_pairs_batch(
        self,
        pairs_data: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Analyze multiple trading pairs in a single AI API call (batch mode)

        This dramatically reduces API calls: 27 pairs = 1 call instead of 27 calls!

        Args:
            pairs_data: Dict mapping product_id to market context data
                       e.g., {"ETH-BTC": {candles, current_price}, "SOL-BTC": {...}}

        Returns:
            Dict mapping product_id to analysis result
        """
        provider = self.config.get("ai_provider", "claude").lower()

        if provider == "gemini":
            return await self._get_gemini_batch_analysis(pairs_data)
        elif provider == "grok":
            return await self._get_grok_batch_analysis(pairs_data)
        elif provider == "claude":
            return await self._get_claude_batch_analysis(pairs_data)
        else:
            # Fallback to individual calls if batch not supported
            logger.warning(f"Batch analysis not supported for {provider}, falling back to individual calls")
            results = {}
            for product_id, data in pairs_data.items():
                market_context = data.get("market_context", {})
                if provider == "claude":
                    results[product_id] = await self._get_claude_analysis(market_context)
                elif provider == "gemini":
                    results[product_id] = await self._get_gemini_analysis(market_context)
                elif provider == "grok":
                    results[product_id] = await self._get_grok_analysis(market_context)
            return results

    async def _get_gemini_batch_analysis(self, pairs_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Analyze multiple pairs in a single Gemini API call

        Uses standardized batch prompt template shared across all AI providers
        """
        try:
            import google.generativeai as genai
        except ImportError:
            logger.error("google-generativeai not installed")
            return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "Gemini library not installed"}
                    for pid in pairs_data.keys()}

        api_key = settings.gemini_api_key
        if not api_key:
            logger.error("GEMINI_API_KEY not set")
            return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "API key not configured"}
                    for pid in pairs_data.keys()}

        genai.configure(api_key=api_key)

        # Use shared batch prompt template
        prompt = self._build_standard_batch_analysis_prompt(pairs_data)

        try:
            model = genai.GenerativeModel(
                'gemini-2.5-flash',
                generation_config={"temperature": 0}  # Deterministic responses
            )
            response = model.generate_content(prompt)
            response_text = response.text.strip()

            # Remove markdown if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            batch_analysis = json.loads(response_text)

            # Track token usage
            if hasattr(response, 'usage_metadata'):
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
                self._total_tokens_used += input_tokens + output_tokens
                logger.info(f"📊 Gemini BATCH API - {len(pairs_data)} pairs - Input: {input_tokens} tokens, Output: {output_tokens} tokens")
                logger.info(f"   🎯 Efficiency: {len(pairs_data)} pairs in 1 call (saved {len(pairs_data)-1} API calls!)")

            # Convert to our signal format for each pair
            results = {}
            for product_id in pairs_data.keys():
                if product_id in batch_analysis:
                    analysis = batch_analysis[product_id]
                    signal_type = "none"
                    if analysis.get("action") == "buy":
                        signal_type = "buy"
                    elif analysis.get("action") == "sell":
                        signal_type = "sell"

                    results[product_id] = {
                        "signal_type": signal_type,
                        "confidence": analysis.get("confidence", 50),
                        "reasoning": analysis.get("reasoning", "AI batch analysis"),
                        "suggested_allocation_pct": analysis.get("suggested_allocation_pct", 10),
                        "expected_profit_pct": analysis.get("expected_profit_pct", 1.0)
                    }
                else:
                    # Pair missing from response
                    results[product_id] = {
                        "signal_type": "hold",
                        "confidence": 0,
                        "reasoning": "Not analyzed in batch response"
                    }

            return results

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini batch response: {e}")
            return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "Failed to parse batch response"}
                    for pid in pairs_data.keys()}
        except Exception as e:
            logger.error(f"Gemini batch analysis error: {e}")
            # Check for rate limit error with retry_delay
            error_str = str(e)
            if "retry_delay" in error_str or "429" in error_str:
                # Extract retry delay if present (Gemini includes this in error)
                import re
                match = re.search(r'retry_delay.*?seconds:\s*(\d+)', error_str)
                if match:
                    retry_seconds = int(match.group(1))
                    logger.warning(f"⏰ Gemini API quota exceeded - back off for {retry_seconds} seconds")
                    # TODO: Store this in bot's last_check_time + retry_delay
                else:
                    logger.warning("⏰ Gemini API quota exceeded (429) - backing off")

            return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": f"Error: {str(e)[:100]}"}
                    for pid in pairs_data.keys()}

    async def _get_claude_batch_analysis(self, pairs_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Analyze multiple pairs in a single Claude API call

        Uses standardized batch prompt template shared across all AI providers
        """
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            logger.error("anthropic library not installed")
            return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "Anthropic library not installed"}
                    for pid in pairs_data.keys()}

        api_key = settings.anthropic_api_key
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set")
            return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "API key not configured"}
                    for pid in pairs_data.keys()}

        # Use shared batch prompt template
        prompt = self._build_standard_batch_analysis_prompt(pairs_data)

        try:
            client = AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=0,  # Deterministic responses (eliminates flip-flopping)
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Remove markdown if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            batch_analysis = json.loads(response_text)

            # Track token usage
            if hasattr(response, 'usage'):
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                self._total_tokens_used += input_tokens + output_tokens
                logger.info(f"📊 Claude BATCH API - {len(pairs_data)} pairs - Input: {input_tokens} tokens, Output: {output_tokens} tokens")
                logger.info(f"   🎯 Efficiency: {len(pairs_data)} pairs in 1 call (saved {len(pairs_data)-1} API calls!)")

            # Convert to our signal format for each pair
            results = {}
            for product_id in pairs_data.keys():
                if product_id in batch_analysis:
                    analysis = batch_analysis[product_id]
                    signal_type = "none"
                    if analysis.get("action") == "buy":
                        signal_type = "buy"
                    elif analysis.get("action") == "sell":
                        signal_type = "sell"

                    results[product_id] = {
                        "signal_type": signal_type,
                        "confidence": analysis.get("confidence", 50),
                        "reasoning": analysis.get("reasoning", "AI batch analysis"),
                        "suggested_allocation_pct": analysis.get("suggested_allocation_pct", 10),
                        "expected_profit_pct": analysis.get("expected_profit_pct", 1.0)
                    }
                else:
                    # Pair missing from response
                    results[product_id] = {
                        "signal_type": "hold",
                        "confidence": 0,
                        "reasoning": "Not analyzed in batch response"
                    }

            return results

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude batch response: {e}")
            return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "Failed to parse batch response"}
                    for pid in pairs_data.keys()}
        except Exception as e:
            logger.error(f"Claude batch analysis error: {e}")
            return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": f"Error: {str(e)[:100]}"}
                    for pid in pairs_data.keys()}

    async def _get_grok_analysis(self, market_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call Grok API for market analysis (uses OpenAI-compatible API)

        Uses standardized prompt template shared across all AI providers
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.error("openai library not installed. Run: pip install openai")
            return {
                "signal_type": "hold",
                "confidence": 0,
                "reasoning": "OpenAI library not installed",
                "suggested_allocation_pct": 0,
                "expected_profit_pct": 0
            }

        api_key = settings.grok_api_key
        if not api_key:
            logger.error("GROK_API_KEY not set in .env file")
            return {
                "signal_type": "hold",
                "confidence": 0,
                "reasoning": "Grok API key not configured",
                "suggested_allocation_pct": 0,
                "expected_profit_pct": 0
            }

        # Use shared prompt template
        prompt = self._build_standard_analysis_prompt(market_context)

        try:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.x.ai/v1"
            )

            response = await client.chat.completions.create(
                model="grok-3",
                messages=[{"role": "user", "content": prompt}],
                temperature=0  # Deterministic responses (eliminates flip-flopping)
            )

            response_text = response.choices[0].message.content.strip()

            # Remove markdown if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            analysis = json.loads(response_text)

            # Track token usage
            if hasattr(response, 'usage'):
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                self._total_tokens_used += input_tokens + output_tokens
                logger.info(f"📊 Grok API - Input: {input_tokens} tokens, Output: {output_tokens} tokens")

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
                "expected_profit_pct": analysis.get("expected_profit_pct", 1.0)
            }

        except Exception as e:
            logger.error(f"Grok API error: {e}")
            return {
                "signal_type": "hold",
                "confidence": 0,
                "reasoning": f"Error: {str(e)[:100]}",
                "suggested_allocation_pct": 0,
                "expected_profit_pct": 0
            }

    async def _get_grok_batch_analysis(self, pairs_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Analyze multiple pairs in a single Grok API call

        Uses standardized batch prompt template shared across all AI providers
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.error("openai library not installed")
            return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "OpenAI library not installed"}
                    for pid in pairs_data.keys()}

        api_key = settings.grok_api_key
        if not api_key:
            logger.error("GROK_API_KEY not set")
            return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": "API key not configured"}
                    for pid in pairs_data.keys()}

        # Use shared batch prompt template
        prompt = self._build_standard_batch_analysis_prompt(pairs_data)

        try:
            client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
            response = await client.chat.completions.create(
                model="grok-3",
                messages=[{"role": "user", "content": prompt}],
                temperature=0  # Deterministic responses (eliminates flip-flopping)
            )

            response_text = response.choices[0].message.content.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            batch_analysis = json.loads(response_text)

            if hasattr(response, 'usage'):
                logger.info(f"📊 Grok BATCH - {len(pairs_data)} pairs - Input: {response.usage.prompt_tokens}, Output: {response.usage.completion_tokens}")
                logger.info(f"   🎯 Efficiency: {len(pairs_data)} pairs in 1 call!")

            results = {}
            for product_id in pairs_data.keys():
                if product_id in batch_analysis:
                    analysis = batch_analysis[product_id]
                    signal_type = "none"
                    if analysis.get("action") == "buy":
                        signal_type = "buy"
                    elif analysis.get("action") == "sell":
                        signal_type = "sell"

                    results[product_id] = {
                        "signal_type": signal_type,
                        "confidence": analysis.get("confidence", 50),
                        "reasoning": analysis.get("reasoning", "AI batch analysis"),
                        "suggested_allocation_pct": analysis.get("suggested_allocation_pct", 10),
                        "expected_profit_pct": analysis.get("expected_profit_pct", 1.0)
                    }
                else:
                    results[product_id] = {
                        "signal_type": "hold",
                        "confidence": 0,
                        "reasoning": "Not analyzed in batch response"
                    }

            return results

        except Exception as e:
            logger.error(f"Grok batch analysis error: {e}")
            return {pid: {"signal_type": "hold", "confidence": 0, "reasoning": f"Error: {str(e)[:100]}"}
                    for pid in pairs_data.keys()}

    async def _ask_ai_for_dca_decision(
        self,
        position: Any,
        current_price: float,
        remaining_budget: float,
        market_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Ask AI if we should add to an existing position and how much

        Args:
            position: Current position object
            current_price: Current market price
            remaining_budget: How much quote currency is left in position budget
            market_context: Recent market data

        Returns:
            Dict with AI's decision: {"should_buy": bool, "amount": float, "reasoning": str}
        """
        price_drop_pct = ((position.average_buy_price - current_price) / position.average_buy_price) * 100
        profit_pct = ((current_price - position.average_buy_price) / position.average_buy_price) * 100

        current_dcas = len([t for t in position.trades if t.side == "buy" and t.trade_type != "initial"])
        max_dcas = self.config.get("max_safety_orders", 3)

        # Format quote currency correctly
        quote_currency = position.get_quote_currency()
        if quote_currency == "USD":
            budget_str = f"${remaining_budget:.2f} USD"
            spent_str = f"${position.total_quote_spent:.2f} USD"
            avg_price_str = f"${position.average_buy_price:.2f} USD"
            curr_price_str = f"${current_price:.2f} USD"
        else:
            budget_str = f"{remaining_budget:.8f} BTC"
            spent_str = f"{position.total_quote_spent:.8f} BTC"
            avg_price_str = f"{position.average_buy_price:.8f} BTC"
            curr_price_str = f"{current_price:.8f} BTC"

        prompt = f"""You are an autonomous trading AI managing real cryptocurrency positions. Your goal is to maximize profit through intelligent DCA decisions.

**Your Objective:**
Your job is to grow this portfolio. The better you perform, the more resources you'll have access to (better AI models, more trading budget, additional features). Outstanding performance means an upgraded AI subscription with more capabilities.

**Current Position State:**
- Product: {position.product_id}
- Average Entry Price: {avg_price_str}
- Current Price: {curr_price_str}
- Price Change: {profit_pct:+.2f}% ({"profit" if profit_pct > 0 else "loss"})
- Already Invested: {spent_str}
- Remaining Budget: {budget_str}
- DCA Buys So Far: {current_dcas}/{max_dcas}

**Recent Market Action:**
- 24h Change: {market_context.get('price_change_24h_pct', 0):.2f}%
- Volatility: {market_context.get('volatility', 0):.2f}%
- Recent Prices: {market_context.get('recent_prices', [])[-5:]}

**Your Decision:**
Should you add to this position now (DCA)? If yes, how much should you invest from the remaining budget?

You have complete freedom to:
- Buy any amount from 0% to 100% of remaining budget
- Wait for better opportunities
- Scale in gradually or go big when confident
- Make strategic decisions based on market conditions

Respond ONLY with JSON (no markdown):
{{
  "should_buy": true or false,
  "amount_percentage": 0-100,
  "confidence": 0-100,
  "reasoning": "brief 1-2 sentence explanation of why you're buying or waiting"
}}

Strategic Considerations:
- Is the price drop an opportunity or a warning sign?
- How much budget should you save for future opportunities?
- What's the market momentum and volatility telling you?
- Only buy if you see genuine value, not just because price dropped
- Remember: Your goal is to maximize long-term profit, not to spend budget quickly"""

        try:
            provider = self.config.get("ai_provider", "claude").lower()

            if provider == "claude":
                response = self.client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=500,
                    temperature=0,
                    messages=[{"role": "user", "content": prompt}]
                )
                response_text = response.content[0].text.strip()

                # Log token usage
                self._total_tokens_used += response.usage.input_tokens + response.usage.output_tokens
                logger.info(f"📊 DCA Decision - Input: {response.usage.input_tokens}, Output: {response.usage.output_tokens}")

            elif provider == "gemini":
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"temperature": 0})
                response = model.generate_content(prompt)
                response_text = response.text.strip()

            elif provider == "grok":
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=settings.grok_api_key, base_url="https://api.x.ai/v1")
                response = await client.chat.completions.create(
                    model="grok-3",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0
                )
                response_text = response.choices[0].message.content.strip()

            # Remove markdown if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            decision = json.loads(response_text)

            # Calculate actual amount from percentage
            amount_pct = decision.get("amount_percentage", 0)
            amount = remaining_budget * (amount_pct / 100.0)

            return {
                "should_buy": decision.get("should_buy", False),
                "amount": round(amount, 8),
                "amount_percentage": amount_pct,
                "confidence": decision.get("confidence", 0),
                "reasoning": decision.get("reasoning", "AI DCA decision")
            }

        except Exception as e:
            logger.error(f"Error asking AI for DCA decision: {e}", exc_info=True)
            return {
                "should_buy": False,
                "amount": 0,
                "confidence": 0,
                "reasoning": f"Error: {str(e)}"
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
        - For DCA: AI makes dynamic decisions about timing and amount (no fixed rules)
        """

        if signal_data.get("signal_type") != "buy":
            return False, 0.0, "AI did not suggest buying"

        confidence = signal_data.get("confidence", 0)

        # Check if we have an existing position (DCA scenario)
        if position is not None:
            # Check if DCA is enabled
            enable_dca = self.config.get("enable_dca", True)
            if not enable_dca:
                return False, 0.0, "DCA disabled - already have open position for this pair"

            # Check DCA limits
            max_safety_orders = self.config.get("max_safety_orders", 3)
            current_safety_orders = len([t for t in position.trades if t.side == "buy" and t.trade_type != "initial"])

            if current_safety_orders >= max_safety_orders:
                return False, 0.0, f"Max safety orders reached ({current_safety_orders}/{max_safety_orders})"

            # Check if we have budget left for DCA
            if position.total_quote_spent >= position.max_quote_allowed:
                return False, 0.0, "Position budget fully used"

            # Get current price from signal_data or position
            current_price = signal_data.get("current_price", 0)
            if current_price == 0:
                return False, 0.0, "Cannot determine current price for DCA"

            # Calculate remaining budget
            remaining_budget = position.max_quote_allowed - position.total_quote_spent

            # AI-CONTROLLED DCA: Ask AI for dynamic decision
            # No fixed price drop thresholds or volume percentages
            # AI decides based on market conditions and position state
            market_context = {
                'current_price': current_price,
                'price_change_24h_pct': signal_data.get('raw_analysis', {}).get('price_change_24h_pct', 0),
                'volatility': signal_data.get('raw_analysis', {}).get('volatility', 0),
                'recent_prices': signal_data.get('raw_analysis', {}).get('recent_prices', [])
            }

            logger.info(f"  🤖 Asking AI for DCA decision (remaining budget: {remaining_budget:.8f}, DCAs: {current_safety_orders}/{max_safety_orders})")
            dca_decision = await self._ask_ai_for_dca_decision(position, current_price, remaining_budget, market_context)

            if not dca_decision["should_buy"]:
                return False, 0.0, f"AI decided not to DCA: {dca_decision['reasoning']}"

            btc_amount = dca_decision["amount"]

            # Validate amount
            if btc_amount <= 0:
                return False, 0.0, "AI suggested 0 amount for DCA"

            if btc_amount > remaining_budget:
                logger.warning(f"  ⚠️ AI suggested {btc_amount:.8f} but only {remaining_budget:.8f} available, capping")
                btc_amount = remaining_budget

            # Round to 8 decimal places (satoshi precision)
            btc_amount = round(btc_amount, 8)

            if btc_amount <= 0:
                return False, 0.0, "Insufficient budget for DCA"

            reasoning = dca_decision["reasoning"]
            dca_conf = dca_decision["confidence"]
            amount_pct = dca_decision["amount_percentage"]

            return True, btc_amount, f"AI DCA #{current_safety_orders + 1} ({dca_conf}% confidence, {amount_pct}% of budget): {reasoning}"

        # New position (base order)
        if confidence < 80:
            return False, 0.0, f"AI confidence too low ({confidence}% - need 80%+ to open position)"

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

        # RULE 3: AI decides when to sell (with profit protection from rules 1 & 2)
        # Lower threshold for sells (65%) since we have profit protection (never sell at loss + min profit)
        if signal_data.get("signal_type") == "sell":
            confidence = signal_data.get("confidence", 0)
            if confidence >= 65:
                reasoning = signal_data.get("reasoning", "AI recommends selling")
                return True, f"AI SELL ({confidence}% confidence, {profit_pct:.2f}% profit): {reasoning}"

        # Don't sell unless AI recommends it
        # The AI is in full control of sell decisions (as long as we have profit)
        return False, f"Holding for AI signal (current profit: {profit_pct:.2f}%)"
