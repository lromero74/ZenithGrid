"""
AI Autonomous Trading Strategy

Uses Claude AI to analyze markets and make autonomous trading decisions.
Maximizes profit while never selling at a loss.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from app.config import settings
from app.strategies import (
    StrategyDefinition,
    StrategyRegistry,
    TradingStrategy,
)

# Import extracted modules
from . import prompts
from . import market_analysis
from . import trading_decisions
from .api_providers import claude, gemini, grok

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

        # Token tracker dict for passing to API functions
        self._token_tracker = {"total": 0}

    def _get_confidence_threshold_for_action(self, action_type: str) -> int:
        """
        Get confidence threshold for a specific action type.

        Uses risk tolerance to set intelligent defaults, but allows user override.

        Confidence Threshold Matrix:
        ┌──────────────┬──────┬──────┬──────┐
        │              │ Open │ DCA  │ Sell │
        ├──────────────┼──────┼──────┼──────┤
        │ Aggressive   │  70  │  65  │  60  │
        │ Moderate     │  75  │  70  │  65  │
        │ Conservative │  80  │  75  │  70  │
        └──────────────┴──────┴──────┴──────┘

        Args:
            action_type: "open", "dca", or "close"

        Returns:
            Confidence threshold percentage (0-100)
        """
        print(f"🔍 _get_confidence_threshold_for_action({action_type})")
        print(f"🔍 self.config keys: {list(self.config.keys())}")
        risk_tolerance = self.config.get("risk_tolerance", "moderate")
        print(f"🔍 risk_tolerance: {risk_tolerance}")

        # Define threshold matrix
        thresholds = {
            "aggressive": {"open": 70, "dca": 65, "close": 60},
            "moderate": {"open": 75, "dca": 70, "close": 65},
            "conservative": {"open": 80, "dca": 75, "close": 70},
        }

        # Get default based on risk tolerance
        default_threshold = thresholds.get(risk_tolerance, thresholds["moderate"])[action_type]
        print(f"🔍 default_threshold for {action_type}: {default_threshold}")

        # Allow user override via explicit config
        config_key_map = {
            "open": "min_confidence_to_open",
            "dca": "min_confidence_for_dca",
            "close": "min_confidence_to_close",
        }

        config_key = config_key_map[action_type]
        print(f"🔍 config_key: {config_key}, value in config: {self.config.get(config_key, 'NOT SET')}")

        # Return user's explicit setting if provided, otherwise use risk-based default
        try:
            result = self.config.get(config_key, default_threshold)
            print(f"🔍 Returning threshold: {result} (type: {type(result)})")
            if result is None:
                print(f"❌ WARNING: Threshold is None! default_threshold was: {default_threshold}")
                # Fallback to default if somehow None
                result = default_threshold
            return result
        except Exception as e:
            print(f"❌ EXCEPTION in _get_confidence_threshold_for_action: {e}")
            import traceback

            traceback.print_exc()
            # Return safe default
            return default_threshold

    def _should_perform_web_search(
        self, position: Optional[Any], action_context: str  # "open", "close", "hold", "dca"
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
                        hours_since_search = (
                            datetime.utcnow() - self._last_search_time[position.id]
                        ).total_seconds() / 3600
                        if hours_since_search < 6:  # Don't search more than every 6 hours for holds
                            return False
                    return True

            return False  # Default: don't search for routine holds

        return False

    def _get_product_minimum(self, position: Optional[Any], signal_data: Dict[str, Any]) -> float:
        """
        Get minimum order size for a product from product_precision.json

        Args:
            position: Current position (if exists)
            signal_data: Signal data containing product_id

        Returns:
            Minimum order size in quote currency (BTC or USD)
        """
        # Determine product_id
        product_id = None
        if position and hasattr(position, "product_id"):
            product_id = position.product_id
        elif "product_id" in signal_data:
            product_id = signal_data.get("product_id")
        elif "product_id" in self.config:
            product_id = self.config.get("product_id")

        if not product_id:
            # Conservative default for BTC pairs
            return 0.0001

        # Load product precision data
        import json
        import os

        precision_file = os.path.join(os.path.dirname(__file__), "..", "..", "product_precision.json")
        try:
            with open(precision_file, "r") as f:
                precision_data = json.load(f)

            # Get product-specific data
            product_data = precision_data.get(product_id, {})
            quote_increment = product_data.get("quote_increment", "0.0001")

            # Convert increment string to minimum (typically 10x increment for safety)
            from decimal import Decimal
            min_value = Decimal(quote_increment) * 10

            return float(min_value)

        except Exception as e:
            logger.warning(f"Could not load product minimum for {product_id}: {e}")
            # Fallback based on quote currency
            quote_currency = product_id.split("-")[1] if "-" in product_id else "BTC"
            return 1.0 if quote_currency == "USD" else 0.0001

    def _format_price(self, price: float, product_id: str) -> str:
        """Format price with correct precision and currency based on product_id"""
        quote_currency = product_id.split("-")[1] if "-" in product_id else "BTC"
        if quote_currency == "USD":
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
        """Get strategy definition with all parameters"""
        # Import the full parameter list from original file (lines 227-456)
        # This is preserved exactly as-is from the original
        from .strategy_definition import get_strategy_definition

        return get_strategy_definition()

    def validate_config(self):
        """Validate configuration parameters"""
        required = [
            "ai_provider",
            "market_focus",
            "initial_budget_percentage",
            "max_position_size_percentage",
            "risk_tolerance",
            "analysis_interval_minutes",
            "min_profit_percentage",
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
        action_context: str = "hold",
    ) -> Optional[Dict[str, Any]]:
        """
        Use AI to analyze market data and generate trading signals

        Token Optimization:
        - Cache analyses for configured interval
        - Summarize data instead of sending raw candles
        - Use structured output for parsing

        Web Search Integration:
        - Performs web search when configured (open, close, smart/periodic while holding)
        - Includes search results in AI prompt for informed decision making
        """

        # Check if we should skip analysis (token optimization)
        if market_analysis.should_skip_analysis(self._last_analysis_time, self.config, position):
            logger.info("Skipping analysis (within cache interval)")
            return market_analysis.get_cached_analysis(self._analysis_cache)

        try:
            # Prepare market context (summarized to save tokens)
            market_context = market_analysis.prepare_market_context(candles, current_price)

            # Determine product_id from position or config
            product_id = None
            if position and hasattr(position, "product_id"):
                product_id = position.product_id
            elif "product_id" in self.config:
                product_id = self.config["product_id"]

            # Perform web search if configured
            web_search_results = None
            if product_id and self._should_perform_web_search(position, action_context):
                web_search_results = await market_analysis.perform_web_search(
                    self.client, product_id, action_context, self._token_tracker
                )
                if web_search_results:
                    market_context["web_search_results"] = web_search_results
                    self._last_search_time = datetime.utcnow()
                    logger.info("🔍 Web search results added to market context")

            # Call AI for analysis based on selected provider
            provider = self.config.get("ai_provider", "claude").lower()
            logger.info(f"🤖 Calling {provider.upper()} AI for market analysis...")

            # Build prompt using extracted module
            # TODO: Consider converting lambda to def function for better debugging
            build_prompt = lambda ctx: prompts.build_standard_analysis_prompt(ctx, self.config, self._format_price)

            if provider == "claude":
                analysis = await claude.get_claude_analysis(
                    self.client, market_context, build_prompt, self._token_tracker
                )
            elif provider == "gemini":
                analysis = await gemini.get_gemini_analysis(market_context, build_prompt, self._token_tracker)
            elif provider == "grok":
                analysis = await grok.get_grok_analysis(market_context, build_prompt, self._token_tracker)
            else:
                raise ValueError(f"Unknown AI provider: {provider}")

            # Sync token tracker back
            self._total_tokens_used = self._token_tracker["total"]

            # Cache the result
            cache_key = f"{current_price}_{len(candles)}"
            self._analysis_cache[cache_key] = (datetime.utcnow(), analysis)
            self._last_analysis_time = datetime.utcnow()

            return analysis

        except Exception as e:
            logger.error(f"Error in AI analysis: {e}", exc_info=True)
            return None

    async def analyze_multiple_pairs_batch(self, pairs_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
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

        # Build batch prompt
        # TODO: Consider converting lambda to def function for better debugging
        build_batch_prompt = lambda data: prompts.build_standard_batch_analysis_prompt(
            data, self.config, self._format_price
        )

        if provider == "gemini":
            return await gemini.get_gemini_batch_analysis(pairs_data, build_batch_prompt, self._token_tracker)
        elif provider == "grok":
            return await grok.get_grok_batch_analysis(pairs_data, build_batch_prompt, self._token_tracker)
        elif provider == "claude":
            return await claude.get_claude_batch_analysis(pairs_data, build_batch_prompt, self._token_tracker)
        else:
            # Fallback to individual calls if batch not supported
            logger.warning(f"Batch analysis not supported for {provider}, falling back to individual calls")
            results = {}
            # TODO: Consider converting lambda to def function for better debugging
            build_prompt = lambda ctx: prompts.build_standard_analysis_prompt(ctx, self.config, self._format_price)

            for product_id, data in pairs_data.items():
                market_context = data.get("market_context", {})
                if provider == "claude":
                    results[product_id] = await claude.get_claude_analysis(
                        self.client, market_context, build_prompt, self._token_tracker
                    )
                elif provider == "gemini":
                    results[product_id] = await gemini.get_gemini_analysis(
                        market_context, build_prompt, self._token_tracker
                    )
                elif provider == "grok":
                    results[product_id] = await grok.get_grok_analysis(
                        market_context, build_prompt, self._token_tracker
                    )
            return results

    async def should_buy(
        self, signal_data: Dict[str, Any], position: Optional[Any], btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should buy based on AI's analysis

        Uses extracted trading_decisions module
        """

        # Get product minimum from product_precision.json
        product_minimum = self._get_product_minimum(position, signal_data)

        # Create wrapper for DCA decision that uses instance methods
        async def ask_dca_wrapper(pos, price, budget, ctx):
            return await trading_decisions.ask_ai_for_dca_decision(
                self.client,
                self.config.get("ai_provider", "claude").lower(),
                pos,
                price,
                budget,
                ctx,
                self.config,
                lambda p, cp, rb, mc, cfg, pmin=product_minimum: prompts.build_dca_decision_prompt(p, cp, rb, mc, cfg, pmin),
                settings,
                self._token_tracker,
                product_minimum,
            )

        return await trading_decisions.should_buy(
            signal_data, position, btc_balance, self.config, self._get_confidence_threshold_for_action, ask_dca_wrapper, product_minimum
        )

    async def should_sell(self, signal_data: Dict[str, Any], position: Any, current_price: float) -> Tuple[bool, str]:
        """
        Determine if we should sell

        Uses extracted trading_decisions module
        """
        return await trading_decisions.should_sell(
            signal_data, position, current_price, self.config, self._get_confidence_threshold_for_action
        )

    async def should_sell_failsafe(self, position: Any, current_price: float) -> Tuple[bool, str]:
        """
        FAILSAFE: Check if position should be sold when AI analysis fails

        This protects profits when AI is unavailable (API errors, token limits, etc.)

        Uses extracted trading_decisions module
        """
        return await trading_decisions.should_sell_failsafe(position, current_price, self.config)
