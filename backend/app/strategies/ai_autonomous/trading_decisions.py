"""
Trading decision logic for AI autonomous strategy

Contains buy/sell decision logic and DCA (Dollar Cost Averaging) decisions
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


async def ask_ai_for_dca_decision(
    client,
    provider: str,
    position: Any,
    current_price: float,
    remaining_budget: float,
    market_context: Dict[str, Any],
    config: Dict[str, Any],
    build_dca_prompt_func,
    settings,
    total_tokens_tracker: Dict[str, int],
    product_minimum: float = 0.0001,
) -> Dict[str, Any]:
    """
    Ask AI if we should add to an existing position and how much

    Args:
        client: AI client instance (Anthropic, Gemini, or Grok)
        provider: AI provider name ("claude", "gemini", or "grok")
        position: Current position object
        current_price: Current market price
        remaining_budget: How much quote currency is left in position budget
        market_context: Recent market data
        config: Strategy configuration (contains safety_order_percentage)
        build_dca_prompt_func: Function to build DCA prompt
        settings: App settings (for API keys)
        total_tokens_tracker: Dict with 'total' key to track token usage
        product_minimum: Minimum order size for this product (in quote currency)

    Returns:
        Dict with AI's decision: {"should_buy": bool, "amount": float, "reasoning": str}
    """
    import json

    prompt = build_dca_prompt_func(position, current_price, remaining_budget, market_context, config, product_minimum)

    try:
        if provider == "claude":
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=500,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = response.content[0].text.strip()

            # Log token usage
            total_tokens_tracker["total"] += response.usage.input_tokens + response.usage.output_tokens
            logger.info(
                f"📊 DCA Decision - Input: {response.usage.input_tokens}, Output: {response.usage.output_tokens}"
            )

        elif provider == "gemini":
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-2.5-flash", generation_config={"temperature": 0})
            response = model.generate_content(prompt)
            response_text = response.text.strip()

        elif provider == "grok":
            from openai import AsyncOpenAI

            grok_client = AsyncOpenAI(api_key=settings.grok_api_key, base_url="https://api.x.ai/v1")
            response = await grok_client.chat.completions.create(
                model="grok-3", messages=[{"role": "user", "content": prompt}], temperature=0
            )
            response_text = response.choices[0].message.content.strip()

        # Remove markdown if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        decision = json.loads(response_text)

        # AI decides DCA amount dynamically based on market conditions
        amount_pct = decision.get("amount_percentage", 5)
        amount = remaining_budget * (amount_pct / 100.0)

        return {
            "should_buy": decision.get("should_buy", False),
            "amount": round(amount, 8),
            "amount_percentage": amount_pct,
            "confidence": decision.get("confidence", 0),
            "reasoning": decision.get("reasoning", "AI DCA decision"),
        }

    except Exception as e:
        logger.error(f"Error asking AI for DCA decision: {e}", exc_info=True)
        return {"should_buy": False, "amount": 0, "confidence": 0, "reasoning": f"Error: {str(e)}"}


async def should_buy(
    signal_data: Dict[str, Any],
    position: Optional[Any],
    btc_balance: float,
    config: Dict[str, Any],
    get_confidence_threshold_func,
    ask_dca_decision_func,
    product_minimum: float = 0.0001,
) -> Tuple[bool, float, str]:
    """
    Determine if we should buy based on AI's analysis

    Rules:
    - Only buy if AI suggests it with good confidence
    - Respect budget limits
    - For DCA: AI makes dynamic decisions about timing and amount (no fixed rules)
    - Validate against exchange minimums

    Args:
        signal_data: AI analysis result
        position: Current position (None for new position)
        btc_balance: Available balance
        config: Strategy configuration
        get_confidence_threshold_func: Function to get confidence threshold
        ask_dca_decision_func: Function to ask AI for DCA decision
        product_minimum: Minimum order size for this product (in quote currency)

    Returns:
        Tuple of (should_buy: bool, amount: float, reasoning: str)
    """
    print(f"🔍 should_buy() called with signal_data keys: {signal_data.keys()}")
    print(f"🔍 signal_type={signal_data.get('signal_type')}, confidence={signal_data.get('confidence')}")

    if signal_data.get("signal_type") != "buy":
        return False, 0.0, "AI did not suggest buying"

    confidence = signal_data.get("confidence", 0)

    # Check if we have an existing position (DCA scenario)
    if position is not None:
        # Check if DCA is enabled
        enable_dca = config.get("enable_dca", True)
        if not enable_dca:
            return False, 0.0, "DCA disabled - already have open position for this pair"

        # Check DCA limits
        max_safety_orders = config.get("max_safety_orders", 3)
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

        # CRITICAL DCA RULE: Only DCA when price is REASONABLY BELOW average cost basis
        # DCA (Dollar Cost Averaging) means buying MORE at SIGNIFICANTLY LOWER prices to reduce average cost
        # Buying at or near current average moves the goal post AWAY and defeats the purpose of DCA
        avg_cost = position.average_buy_price
        price_drop_from_avg = ((avg_cost - current_price) / avg_cost) * 100  # Positive = price dropped

        # Require meaningful drop below average (not just barely below)
        # Use a reasonable minimum drop - AI can't override this constraint
        min_drop_for_dca_pct = 1.0  # Require at least 1% drop below average cost basis

        if price_drop_from_avg < min_drop_for_dca_pct:
            if current_price >= avg_cost:
                return False, 0.0, f"DCA rejected: price ({current_price:.8f}) is ABOVE avg cost ({avg_cost:.8f}). DCA only on significant drops."
            else:
                return False, 0.0, f"DCA rejected: drop {price_drop_from_avg:.2f}% below avg cost is too small (need {min_drop_for_dca_pct}%+). Waiting for better entry."

        # Calculate remaining budget
        remaining_budget = position.max_quote_allowed - position.total_quote_spent

        # AI-Directed DCA: AI decides both WHEN and HOW MUCH to buy
        # AI evaluates market conditions, position state, and remaining budget to make intelligent decisions
        market_context = {
            "current_price": current_price,
            "price_change_24h_pct": signal_data.get("raw_analysis", {}).get("price_change_24h_pct", 0),
            "volatility": signal_data.get("raw_analysis", {}).get("volatility", 0),
            "recent_prices": signal_data.get("raw_analysis", {}).get("recent_prices", []),
        }

        logger.info(
            f"  🤖 Asking AI for DCA decision (remaining budget: {remaining_budget:.8f}, DCAs: {current_safety_orders}/{max_safety_orders})"
        )
        dca_decision = await ask_dca_decision_func(position, current_price, remaining_budget, market_context)

        if not dca_decision["should_buy"]:
            return False, 0.0, f"AI decided not to DCA: {dca_decision['reasoning']}"

        # Check DCA confidence threshold
        dca_conf = dca_decision["confidence"]
        min_dca_confidence = get_confidence_threshold_func("dca")
        if dca_conf < min_dca_confidence:
            return False, 0.0, f"AI DCA confidence too low ({dca_conf}% - need {min_dca_confidence}%+)"

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

        # CRITICAL: Validate against exchange minimum order size
        if btc_amount < product_minimum:
            quote_currency = position.get_quote_currency()
            return (
                False,
                0.0,
                f"DCA amount {btc_amount:.8f} {quote_currency} below exchange minimum {product_minimum:.8f} {quote_currency}. "
                f"AI should suggest at least {product_minimum:.8f} {quote_currency} or skip DCA.",
            )

        reasoning = dca_decision["reasoning"]
        amount_pct = dca_decision["amount_percentage"]

        return (
            True,
            btc_amount,
            f"AI DCA #{current_safety_orders + 1} ({dca_conf}% confidence, {amount_pct}% of budget): {reasoning}",
        )

    # New position (base order)
    min_confidence = get_confidence_threshold_func("open")
    if min_confidence is None:
        return False, 0.0, "AI confidence threshold not configured for opening positions"
    if confidence < min_confidence:
        return False, 0.0, f"AI confidence too low ({confidence}% - need {min_confidence}%+ to open position)"

    # AI decides allocation percentage based on opportunity and confidence
    suggested_pct = signal_data.get("suggested_allocation_pct", 10)
    max_pct = config.get("max_position_budget_percentage", 100)
    use_pct = min(suggested_pct, max_pct)

    # NOTE: Do NOT divide by max_concurrent_deals here - the btc_balance
    # passed in has ALREADY been divided by max_concurrent_deals in trading_engine_v2.py
    # (per_position_budget = reserved_balance / max_concurrent_deals)

    btc_amount = btc_balance * (use_pct / 100.0)

    if btc_amount <= 0:
        return False, 0.0, "Insufficient balance"

    # CRITICAL: Validate against exchange minimum order size
    if btc_amount < product_minimum:
        # Get quote currency from signal data or config
        quote_currency = "BTC"  # Default
        if position and hasattr(position, "get_quote_currency"):
            quote_currency = position.get_quote_currency()
        return (
            False,
            0.0,
            f"Initial buy amount {btc_amount:.8f} {quote_currency} below exchange minimum {product_minimum:.8f} {quote_currency}. "
            f"AI should suggest larger allocation or skip this pair.",
        )

    reasoning = signal_data.get("reasoning", "AI recommends buying")
    return True, btc_amount, f"AI BUY ({confidence}% confidence): {reasoning}"


async def should_sell_failsafe(
    position: Any,
    current_price: float,
    config: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    FAILSAFE: Check if position should be sold when AI analysis fails

    This is a safety mechanism that protects profits when AI is unavailable
    (e.g., API errors, token limits exceeded, service outages).

    Rules:
    - Only triggers when AI analysis fails
    - Only sells if position is in profit
    - Only sells if profit meets minimum threshold
    - Uses limit orders for profit protection (mark price → bid price fallback)

    Args:
        position: Current position
        current_price: Current market price
        config: Strategy configuration

    Returns:
        Tuple of (should_sell: bool, reasoning: str)
    """
    # Determine profit calculation method
    profit_method = config.get("profit_calculation_method", "cost_basis")

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

    profit_pct = (current_price - entry_price) / entry_price * 100
    min_profit = config.get("min_profit_percentage", 1.0)

    # FAILSAFE RULE 1: Never sell at a loss
    if profit_pct <= 0:
        return False, f"AI failsafe: not selling at loss (current: {profit_pct:.2f}%)"

    # FAILSAFE RULE 2: Only sell if profit meets minimum
    if profit_pct < min_profit:
        return False, f"AI failsafe: profit {profit_pct:.2f}% below minimum {min_profit}%"

    # FAILSAFE ACTIVATED: Position is in profit and AI is unavailable
    # Sell to protect profits (limit order will be used)
    return True, f"🛡️ AI FAILSAFE ACTIVATED: Protecting profit ({profit_pct:.2f}%) - AI analysis unavailable"


async def should_sell(
    signal_data: Dict[str, Any],
    position: Any,
    current_price: float,
    config: Dict[str, Any],
    get_confidence_threshold_func,
    market_context: Dict[str, Any] = None,
) -> Tuple[bool, str]:
    """
    Determine if we should sell

    Rules:
    - NEVER sell at a loss (user requirement)
    - Only sell if profit >= min_profit_percentage
    - Check custom technical conditions (if configured)
    - Consider AI recommendation
    - Calculate profit based on selected method (cost_basis or base_order)

    Args:
        signal_data: AI analysis result
        position: Current position
        current_price: Current market price
        config: Strategy configuration
        get_confidence_threshold_func: Function to get confidence threshold
        market_context: Market data with indicators (for custom conditions)

    Returns:
        Tuple of (should_sell: bool, reasoning: str)
    """

    # Determine profit calculation method
    profit_method = config.get("profit_calculation_method", "cost_basis")

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

    profit_pct = (current_price - entry_price) / entry_price * 100

    min_profit = config.get("min_profit_percentage", 1.0)

    # RULE 1: Never sell at a loss
    if profit_pct <= 0:
        return False, f"Never sell at loss (current: {profit_pct:.2f}%)"

    # RULE 2: Only sell if profit meets minimum
    if profit_pct < min_profit:
        return False, f"Profit {profit_pct:.2f}% below minimum {min_profit}%"

    # RULE 3: Check custom technical sell conditions (if configured)
    custom_conditions = config.get("custom_sell_conditions")
    if custom_conditions and market_context:
        from app.conditions import ConditionEvaluator

        try:
            evaluator = ConditionEvaluator(custom_conditions)
            if evaluator.evaluate(market_context):
                # Custom condition triggered - sell with profit protection
                return True, f"Custom technical condition triggered at {profit_pct:.2f}% profit"
        except Exception as e:
            # Log error but don't block trading if condition evaluation fails
            import logging
            logging.getLogger(__name__).warning(f"Error evaluating custom sell conditions: {e}")

    # RULE 4: AI decides when to sell (with profit protection from rules 1 & 2)
    if signal_data.get("signal_type") == "sell":
        confidence = signal_data.get("confidence", 0)
        min_sell_confidence = get_confidence_threshold_func("close")
        if confidence >= min_sell_confidence:
            reasoning = signal_data.get("reasoning", "AI recommends selling")
            return True, f"AI SELL ({confidence}% confidence, {profit_pct:.2f}% profit): {reasoning}"
        else:
            return False, f"AI sell confidence too low ({confidence}% - need {min_sell_confidence}%+)"

    # Don't sell unless AI recommends it
    # The AI is in full control of sell decisions (as long as we have profit)
    return False, f"Holding for AI signal (current profit: {profit_pct:.2f}%)"
