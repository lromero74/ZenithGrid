"""
Strategy definition and parameters for AI Autonomous trading strategy

Contains the full parameter list for bot configuration UI
"""

from app.strategies import StrategyDefinition, StrategyParameter


def get_strategy_definition() -> StrategyDefinition:
    """Get strategy definition with all parameters organized into logical groups"""
    return StrategyDefinition(
        id="ai_autonomous",
        name="AI Autonomous Trading",
        description="AI-powered autonomous trading that analyzes markets and makes intelligent decisions to maximize profit. Never sells at a loss.",
        parameters=[
            # ========================================
            # AI CONFIGURATION
            # ========================================
            StrategyParameter(
                name="ai_provider",
                display_name="AI Provider",
                description="Which AI model to use for market analysis",
                type="string",
                default="claude",
                options=["claude", "gemini", "grok"],
                group="AI Configuration",
            ),
            StrategyParameter(
                name="risk_tolerance",
                display_name="Risk Tolerance",
                description="How aggressive should the AI be? Conservative/Moderate/Aggressive use preset confidence thresholds. Choose Manual to set custom thresholds.",
                type="string",
                default="moderate",
                options=["conservative", "moderate", "aggressive", "manual"],
                group="AI Configuration",
            ),
            # Confidence thresholds (only shown when Risk Tolerance = Manual)
            StrategyParameter(
                name="min_confidence_to_open",
                display_name="Min AI Confidence to Open Position (%)",
                description="Minimum AI confidence required to open a new position (50-100%).",
                type="int",
                default=75,
                min_value=50,
                max_value=100,
                required=False,
                group="AI Configuration",
                visible_when={"risk_tolerance": "manual"},
            ),
            StrategyParameter(
                name="min_confidence_for_dca",
                display_name="Min AI Confidence for DCA (%)",
                description="Minimum AI confidence required to execute DCA orders (50-100%).",
                type="int",
                default=70,
                min_value=50,
                max_value=100,
                required=False,
                group="AI Configuration",
                visible_when={"risk_tolerance": "manual"},
            ),
            StrategyParameter(
                name="min_confidence_to_close",
                display_name="Min AI Confidence to Sell (%)",
                description="Minimum AI confidence required to close a position (50-100%).",
                type="int",
                default=65,
                min_value=50,
                max_value=100,
                required=False,
                group="AI Configuration",
                visible_when={"risk_tolerance": "manual"},
            ),
            StrategyParameter(
                name="custom_instructions",
                display_name="Custom Instructions (Optional)",
                description="Additional instructions to guide the AI's trading decisions (e.g., 'Focus on high-volume pairs only' or 'Avoid meme coins')",
                type="text",
                default="",
                required=False,
                group="AI Configuration",
            ),

            # ========================================
            # BUDGET & POSITION SIZING
            # ========================================
            StrategyParameter(
                name="max_concurrent_deals",
                display_name="Max Concurrent Positions",
                description="Maximum number of positions that can be open simultaneously. Bot budget is divided equally among this number (e.g., 33% budget ÷ 3 positions = 11% per position).",
                type="int",
                default=3,
                min_value=1,
                max_value=10,
                group="Budget & Position Sizing",
            ),
            StrategyParameter(
                name="max_position_budget_percentage",
                display_name="Max Total Position Size (%)",
                description="Maximum percentage of per-position budget that can be spent in total (initial buy + all DCAs). 100% allows using full position budget.",
                type="float",
                default=100.0,
                min_value=5.0,
                max_value=100.0,
                group="Budget & Position Sizing",
            ),

            # ========================================
            # DCA (SAFETY ORDERS)
            # ========================================
            StrategyParameter(
                name="enable_dca",
                display_name="Enable DCA (Dollar Cost Averaging)",
                description="Allow adding to existing positions when price drops (averaging down). If disabled, each position gets only one buy.",
                type="bool",
                default=True,
                group="DCA (Safety Orders)",
            ),
            StrategyParameter(
                name="max_safety_orders",
                display_name="Max DCA Buys Per Position",
                description="Maximum number of additional buys (DCA) after the initial purchase. Example: 3 means up to 4 total buys (1 initial + 3 DCA).",
                type="int",
                default=3,
                min_value=0,
                max_value=10,
                group="DCA (Safety Orders)",
            ),

            # ========================================
            # PROFIT & EXIT STRATEGY
            # ========================================
            StrategyParameter(
                name="min_profit_percentage",
                display_name="Minimum Profit to Sell (%)",
                description="Only sell if profit is at least this percentage. Prevents selling too early. Combines with AI's sell recommendations.",
                type="float",
                default=1.0,
                min_value=0.1,
                max_value=10.0,
                group="Profit & Exit",
            ),
            StrategyParameter(
                name="profit_calculation_method",
                display_name="Profit Calculation Method",
                description="How to calculate profit: cost_basis (average of all buys) or base_order (only from first buy price).",
                type="string",
                default="cost_basis",
                options=["cost_basis", "base_order"],
                group="Profit & Exit",
            ),
            StrategyParameter(
                name="custom_sell_conditions",
                display_name="Custom Sell Conditions (Optional)",
                description="Add technical indicators as additional sell triggers. Position sells if AI recommends sell OR custom conditions are met. All sells still require profit >= min_profit_percentage.",
                type="conditions",
                default=None,
                required=False,
                group="Profit & Exit",
            ),

            # ========================================
            # ANALYSIS TIMING
            # ========================================
            StrategyParameter(
                name="analysis_interval_minutes",
                display_name="Analysis Interval (minutes)",
                description="How often to run AI analysis when looking for new positions to open. For Gemini free tier (250 API calls/day), use minimum 6 minutes.",
                type="int",
                default=15,
                min_value=5,
                max_value=120,
                group="Analysis Timing",
            ),
            StrategyParameter(
                name="position_management_interval_minutes",
                display_name="Position Check Interval (minutes)",
                description="How often to check positions when at max concurrent deals (only managing existing positions, not looking for new ones). Can be faster than analysis_interval.",
                type="int",
                default=6,
                min_value=1,
                max_value=60,
                group="Analysis Timing",
            ),

            # ========================================
            # MARKET FILTERS
            # ========================================
            StrategyParameter(
                name="market_focus",
                display_name="Market Focus",
                description="Which trading pairs to analyze: BTC (only BTC pairs like ETH-BTC), USD (only USD pairs like ETH-USD), or ALL (both).",
                type="string",
                default="BTC",
                options=["BTC", "USD", "ALL"],
                group="Market Filters",
            ),
            StrategyParameter(
                name="min_daily_volume",
                display_name="Minimum Daily Volume",
                description="Minimum 24-hour trading volume in quote currency. Filters out low-liquidity pairs that may be hard to exit.",
                type="float",
                default=100.0,
                min_value=0.0,
                max_value=1000000.0,
                group="Market Filters",
            ),

            # ========================================
            # WEB SEARCH (OPTIONAL)
            # ========================================
            StrategyParameter(
                name="use_web_search",
                display_name="Enable Web Search",
                description="Allow AI to search the web for recent news, sentiment, and market events. Uses more API tokens but provides better context.",
                type="bool",
                default=False,
                group="Web Search (Optional)",
            ),
            StrategyParameter(
                name="search_on_open",
                display_name="Search Before Opening",
                description="Search for news before opening a new position (recommended if web search enabled).",
                type="bool",
                default=True,
                group="Web Search (Optional)",
            ),
            StrategyParameter(
                name="search_on_close",
                display_name="Search Before Closing",
                description="Search for news before closing a position (recommended if web search enabled).",
                type="bool",
                default=True,
                group="Web Search (Optional)",
            ),
            StrategyParameter(
                name="search_while_holding",
                display_name="Search While Holding",
                description="When to search while holding positions: never, smart (only when considering action), or periodic (on schedule).",
                type="string",
                default="smart",
                options=["never", "smart", "periodic"],
                group="Web Search (Optional)",
            ),
            StrategyParameter(
                name="search_interval_hours",
                display_name="Periodic Search Interval (hours)",
                description="If 'Search While Holding' is set to periodic, search every N hours.",
                type="int",
                default=6,
                min_value=1,
                max_value=24,
                group="Web Search (Optional)",
            ),
        ],
    )
