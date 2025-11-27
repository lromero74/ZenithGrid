"""
Prompt templates for AI trading strategy

Contains standardized prompts used across all AI providers (Claude, Gemini, Grok)
"""

from typing import Any, Dict


def build_standard_analysis_prompt(market_context: Dict[str, Any], config: Dict[str, Any], format_price_func) -> str:
    """
    Build standardized analysis prompt used by ALL AI providers (Claude, Gemini, Grok)

    This ensures all AI models receive identical instructions and context,
    making their performance directly comparable.
    """
    risk_tolerance = config.get("risk_tolerance", "moderate")
    market_focus = config.get("market_focus", "BTC")
    custom_instructions = config.get("custom_instructions", "").strip()

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
    current_price = market_context["current_price"]
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
- Keep reasoning concise to save tokens

**CRITICAL - Exchange Minimum Order Requirements:**
- Coinbase requires minimum 0.0001 BTC per order (or equivalent USD for USD pairs)
- When suggesting allocation percentage, ensure the resulting amount meets this minimum
- If available budget is too small for minimum order size, suggest 0% allocation (hold)
- Example: With 0.0002 BTC budget, 40% = 0.00008 BTC (TOO SMALL - suggest 80%+ or hold)
- Never suggest buying amounts below exchange minimums - orders will fail!"""

    return prompt


def build_standard_batch_analysis_prompt(
    pairs_data: Dict[str, Dict[str, Any]], config: Dict[str, Any], format_price_func, per_position_budget: float = None
) -> str:
    """
    Build standardized batch analysis prompt for ALL AI providers (Claude, Gemini, Grok)

    Analyzes multiple trading pairs in a single API call for efficiency.

    Args:
        pairs_data: Market data for each trading pair
        config: Bot configuration
        format_price_func: Function to format prices
        per_position_budget: Available budget per position (total budget / max_concurrent_deals)
    """
    risk_tolerance = config.get("risk_tolerance", "moderate")
    max_concurrent_deals = config.get("max_concurrent_deals", 1)

    # Build summary for all pairs
    pairs_summary = []
    for product_id, data in pairs_data.items():
        ctx = data.get("market_context", {})
        price_str = format_price_func(ctx.get("current_price", 0), product_id)
        recent_prices = ctx.get("recent_prices", [])[-3:]
        pairs_summary.append(
            f"""
**{product_id}:**
- Current Price: {price_str}
- 24h Change: {ctx.get('price_change_24h_pct', 0):.2f}%
- Volatility: {ctx.get('volatility', 0):.2f}%
- Recent Trend: {recent_prices}"""
        )

    # Budget information
    budget_info = ""
    if per_position_budget is not None:
        # Determine currency from first pair
        first_pair = list(pairs_data.keys())[0] if pairs_data else "BTC-USD"
        quote_currency = first_pair.split("-")[1] if "-" in first_pair else "BTC"

        if quote_currency == "USD":
            budget_str = f"${per_position_budget:.2f} USD"
            min_str = "$1.00 USD"
        else:
            budget_str = f"{per_position_budget:.8f} BTC"
            min_str = "0.0001 BTC"

        # Calculate DCA reserve information
        dca_info = ""
        if config.get("enable_dca", True):
            max_safety_orders = config.get("max_safety_orders", 3)
            safety_order_pct = config.get("safety_order_percentage", 20.0)
            required_dca_reserve = max_safety_orders * safety_order_pct
            max_initial_pct = max(100.0 - required_dca_reserve, 10.0)

            dca_info = f"""
- DCA Enabled: {max_safety_orders} safety orders configured at {safety_order_pct}% each
- DCA Budget Reserved: {required_dca_reserve}% of position budget
- Max Initial Buy: {max_initial_pct}% (rest reserved for DCA)"""

        budget_info = f"""
**Available Budget Per Position:**
- Budget per deal: {budget_str}
- Max concurrent positions: {max_concurrent_deals}
- Exchange minimum: {min_str}
- Your allocation % is applied to the per-position budget above{dca_info}"""

    prompt = f"""You are analyzing {len(pairs_data)} cryptocurrency pairs simultaneously. Provide trading recommendations for ALL pairs in a single JSON response.

**Market Data for All Pairs:**
{''.join(pairs_summary)}

**Trading Parameters:**
- Risk Tolerance: {risk_tolerance}{budget_info}

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
- Return valid JSON only (no markdown, no code blocks)

**CRITICAL - Budget Allocation Rules:**
1. Exchange Minimums: Coinbase requires minimum 0.0001 BTC per order (or equivalent USD)
2. DCA Reserve: If DCA is enabled, you MUST leave budget for safety orders (see max_initial_buy % above)
3. Your suggested_allocation_pct is applied to the PER-POSITION budget
4. Ensure allocation meets BOTH exchange minimum AND leaves room for DCA
5. Example: With 0.00126 BTC per-position budget, 3 DCA orders at 20% each = 60% reserved
   - Max initial: 40% × 0.00126 = 0.000504 BTC ✓ (above minimum and leaves DCA room)
   - Too high: 80% × 0.00126 = 0.001008 BTC ✗ (leaves only 0.000252 for 3 DCAs - insufficient!)
6. Never suggest allocations that violate exchange minimums OR leave insufficient DCA budget!"""

    return prompt


def build_dca_decision_prompt(
    position: Any, current_price: float, remaining_budget: float, market_context: Dict[str, Any], config: Dict[str, Any], product_minimum: float = 0.0001
) -> str:
    """
    Build prompt for AI to decide on DCA (Dollar Cost Averaging) action

    Args:
        position: Current position object
        current_price: Current market price
        remaining_budget: Remaining budget for this position
        market_context: Recent market data
        config: Strategy configuration
        product_minimum: Minimum order size for this product (in quote currency)

    Returns:
        Formatted prompt string for AI DCA decision
    """
    profit_pct = ((current_price - position.average_buy_price) / position.average_buy_price) * 100

    current_dcas = len([t for t in position.trades if t.side == "buy" and t.trade_type != "initial"])
    max_dcas = config.get("max_safety_orders", 3)

    # Format quote currency correctly
    quote_currency = position.get_quote_currency()
    if quote_currency == "USD":
        budget_str = f"${remaining_budget:.2f} USD"
        spent_str = f"${position.total_quote_spent:.2f} USD"
        avg_price_str = f"${position.average_buy_price:.2f} USD"
        curr_price_str = f"${current_price:.2f} USD"
        min_order_str = f"${product_minimum:.2f} USD"
    else:
        budget_str = f"{remaining_budget:.8f} BTC"
        spent_str = f"{position.total_quote_spent:.8f} BTC"
        avg_price_str = f"{position.average_buy_price:.8f} BTC"
        curr_price_str = f"{current_price:.8f} BTC"
        min_order_str = f"{product_minimum:.8f} BTC"

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
- **MINIMUM ORDER SIZE: {min_order_str}** (Coinbase exchange requirement)

**CRITICAL RULE - DCA CONSTRAINT:**
You can ONLY make this DCA decision if the current price is BELOW the average entry price.
- Current Price: {curr_price_str}
- Average Entry: {avg_price_str}
- This ensures DCA actually LOWERS the average cost, not raises it!
- If you're seeing this prompt, the price IS below average (constraint already enforced)

**Recent Market Action:**
- 24h Change: {market_context.get('price_change_24h_pct', 0):.2f}%
- Volatility: {market_context.get('volatility', 0):.2f}%
- Recent Prices: {market_context.get('recent_prices', [])[-5:]}

**Your Decision:**
Should you add to this position now (DCA)? If yes, how much should you invest from the remaining budget?

You have complete freedom to:
- Buy any amount from 0% to 100% of remaining budget
- Wait for even better opportunities (price might drop more!)
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
- Price is already below average - but is this the right time to buy more?
- Is the price drop an opportunity or a warning sign?
- How much budget should you save for even deeper discounts?
- What's the market momentum and volatility telling you?
- Only buy if you see genuine value, not just because price dropped
- Remember: Your goal is to maximize long-term profit, not to spend budget quickly
- IMPORTANT: Ensure your buy amount meets the minimum order size ({min_order_str}) - orders below this will be rejected by the exchange"""

    return prompt
