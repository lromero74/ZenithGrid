"""
Strategy definition and parameters for AI Autonomous trading strategy

Contains the full parameter list for bot configuration UI
"""

from app.strategies import StrategyDefinition, StrategyParameter


def get_strategy_definition() -> StrategyDefinition:
    """Get strategy definition with all parameters"""
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
                name="min_confidence_to_open",
                display_name="Min Confidence to Open Position (%)",
                description="Minimum AI confidence to open position. Leave unset to auto-adjust based on Risk Tolerance (Aggressive=70, Moderate=75, Conservative=80)",
                type="int",
                default=None,
                min_value=50,
                max_value=100,
                required=False
            ),
            StrategyParameter(
                name="min_confidence_for_dca",
                display_name="Min Confidence for DCA (%)",
                description="Minimum AI confidence for DCA orders. Leave unset to auto-adjust based on Risk Tolerance (Aggressive=65, Moderate=70, Conservative=75)",
                type="int",
                default=None,
                min_value=50,
                max_value=100,
                required=False
            ),
            StrategyParameter(
                name="min_confidence_to_close",
                display_name="Min Confidence to Close Position (%)",
                description="Minimum AI confidence to sell. Leave unset to auto-adjust based on Risk Tolerance (Aggressive=60, Moderate=65, Conservative=70)",
                type="int",
                default=None,
                min_value=50,
                max_value=100,
                required=False
            ),
            StrategyParameter(
                name="analysis_interval_minutes",
                display_name="Analysis Interval (minutes)",
                description="How often to ask AI for new analysis when looking for new positions. For Gemini free tier (250/day), use minimum 6 minutes to stay under limit.",
                type="int",
                default=15,
                min_value=5,
                max_value=120
            ),
            StrategyParameter(
                name="position_management_interval_minutes",
                display_name="Position Management Interval (minutes)",
                description="How often to ask AI for analysis when at max concurrent deals (only managing positions, not opening new ones). For Gemini free tier (250/day limit), use minimum 6 minutes.",
                type="int",
                default=6,
                min_value=1,
                max_value=60
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
