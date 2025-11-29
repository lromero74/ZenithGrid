"""
Trading decision logic for AI autonomous strategy

Contains buy/sell decision logic and DCA (Dollar Cost Averaging) decisions
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def calculate_manual_dca_amount(
    position: Any,
    config: Dict[str, Any],
    remaining_budget: float,
    current_price: float,
    aggregate_value: float = None,
) -> Tuple[bool, float, str]:
    """
    Calculate DCA amount using manual 3Commas-style settings.

    This replaces AI decision-making when use_manual_sizing is enabled.
    Uses fixed rules with configurable multipliers for order size and drop requirements.

    Args:
        position: Current position object
        config: Strategy configuration with manual sizing parameters
        remaining_budget: Remaining budget for this position (used as cap)
        current_price: Current market price
        aggregate_value: Total account liquidation value (used for percentage calculations)

    Returns:
        Tuple of (should_buy: bool, btc_amount: float, reasoning: str)
    """
    # Get manual DCA config
    dca_type = config.get("dca_order_type", "percentage")
    base_dca_value = config.get("dca_order_value", 20.0)
    dca_multiplier = config.get("dca_order_multiplier", 1.0)
    base_drop_pct = config.get("manual_dca_min_drop_pct", 2.0)
    drop_multiplier = config.get("dca_drop_multiplier", 1.0)
    max_dcas = config.get("manual_max_dca_orders", 3)

    # Count existing DCAs
    current_dcas = len([t for t in position.trades if t.side == "buy" and t.trade_type != "initial"])

    if current_dcas >= max_dcas:
        return False, 0.0, f"Max manual DCA orders reached ({current_dcas}/{max_dcas})"

    # Calculate required drop for THIS DCA order
    # Each subsequent DCA requires more drop: base_drop × (drop_multiplier ^ dca_number)
    required_drop = base_drop_pct * (drop_multiplier ** current_dcas)

    # Check if price has dropped enough from average entry
    price_drop_pct = ((position.average_buy_price - current_price) / position.average_buy_price) * 100
    if price_drop_pct < required_drop:
        return False, 0.0, f"Manual DCA: drop {price_drop_pct:.2f}% < required {required_drop:.2f}% for DCA #{current_dcas + 1}"

    # Calculate DCA order size with multiplier
    # Each subsequent DCA is larger: base_value × (dca_multiplier ^ dca_number)
    order_size = base_dca_value * (dca_multiplier ** current_dcas)

    if dca_type == "percentage":
        # Use aggregate value for percentage (total liquidation value of market)
        # This gives predictable order sizes based on total portfolio
        base_for_pct = aggregate_value if aggregate_value is not None else remaining_budget
        btc_amount = base_for_pct * (order_size / 100.0)
        pct_source = "aggregate" if aggregate_value is not None else "remaining"
    else:  # fixed
        btc_amount = order_size
        pct_source = "fixed"

    # Cap to remaining budget (can't spend more than allocated to this position)
    if btc_amount > remaining_budget:
        logger.info(f"  📊 Manual DCA: {btc_amount:.8f} exceeds remaining {remaining_budget:.8f}, capping")
        btc_amount = remaining_budget

    if btc_amount <= 0:
        return False, 0.0, "Insufficient remaining budget for manual DCA"

    return True, btc_amount, f"Manual DCA #{current_dcas + 1}: {order_size:.1f}% of {pct_source} = {btc_amount:.8f} after {price_drop_pct:.2f}% drop"


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
    aggregate_value: float = None,
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
        aggregate_value: Total account liquidation value for manual % calculations

    Returns:
        Dict with AI's decision: {"should_buy": bool, "amount": float, "reasoning": str}
    """
    import json

    # Check if manual sizing is enabled - bypass AI decision entirely
    if config.get("use_manual_sizing", False):
        should_buy, amount, reasoning = calculate_manual_dca_amount(
            position, config, remaining_budget, current_price, aggregate_value
        )
        return {
            "should_buy": should_buy,
            "amount": round(amount, 8),
            "amount_percentage": (amount / remaining_budget * 100) if remaining_budget > 0 else 0,
            "confidence": 100 if should_buy else 0,  # Manual mode always has 100% confidence (rule-based)
            "reasoning": reasoning,
        }

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
    aggregate_value: float = None,
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
        btc_balance: Available balance (per-position budget, used as cap)
        config: Strategy configuration
        get_confidence_threshold_func: Function to get confidence threshold
        ask_dca_decision_func: Function to ask AI for DCA decision
        product_minimum: Minimum order size for this product (in quote currency)
        aggregate_value: Total account liquidation value (for manual % calculations)

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

        # CRITICAL DCA RULE: Only DCA when price is REASONABLY BELOW reference price
        # DCA (Dollar Cost Averaging) means buying MORE at LOWER prices to reduce average cost
        # Buying at or near current average moves the goal post AWAY and defeats the purpose of DCA

        # Get configurable DCA settings
        min_drop_for_dca_pct = config.get("min_dca_drop_pct", 1.0)
        dca_drop_reference = config.get("dca_drop_reference", "cost_basis")

        # Determine reference price based on config
        if dca_drop_reference == "last_buy":
            # Use the price of the most recent buy/DCA
            buy_trades = [t for t in position.trades if t.side == "buy"]
            if buy_trades:
                buy_trades.sort(key=lambda t: t.timestamp, reverse=True)
                reference_price = buy_trades[0].price
                reference_label = "last buy"
            else:
                reference_price = position.average_buy_price
                reference_label = "avg cost"
        else:
            # Default: use average cost basis
            reference_price = position.average_buy_price
            reference_label = "avg cost"

        price_drop_from_ref = ((reference_price - current_price) / reference_price) * 100  # Positive = price dropped

        if price_drop_from_ref < min_drop_for_dca_pct:
            if current_price >= reference_price:
                return False, 0.0, f"DCA rejected: price ({current_price:.8f}) is ABOVE {reference_label} ({reference_price:.8f}). DCA only on significant drops."
            else:
                return False, 0.0, f"DCA rejected: drop {price_drop_from_ref:.2f}% below {reference_label} is too small (need {min_drop_for_dca_pct}%+). Waiting for better entry."

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

    # Check if manual sizing mode is enabled
    use_manual_sizing = config.get("use_manual_sizing", False)

    if use_manual_sizing:
        # MANUAL MODE: Use fixed base order sizing (3Commas style)
        # For percentage mode, use aggregate value (total liquidation value of market)
        base_type = config.get("base_order_type", "percentage")
        base_value = config.get("base_order_value", 40.0)

        if base_type == "percentage":
            # Use aggregate value for percentage (total liquidation value of market)
            # This gives predictable order sizes based on total portfolio
            base_for_pct = aggregate_value if aggregate_value is not None else btc_balance
            btc_amount = base_for_pct * (base_value / 100.0)
            pct_source = "aggregate" if aggregate_value is not None else "budget"
            logger.info(f"  📊 Manual base order: {base_value}% of {pct_source} ({base_for_pct:.8f}) = {btc_amount:.8f}")
        else:  # fixed
            btc_amount = base_value
            logger.info(f"  📊 Manual base order: fixed {base_value}")

        # Cap to available per-position budget (can't spend more than allocated)
        if btc_amount > btc_balance:
            logger.info(f"  📊 Manual base order: {btc_amount:.8f} exceeds position budget {btc_balance:.8f}, capping")
            btc_amount = btc_balance

    else:
        # AI MODE: Calculate DCA budget reserve if DCA is enabled
        max_initial_pct = 100.0  # Default: can use full budget if no DCA
        if config.get("enable_dca", True):
            max_safety_orders = config.get("max_safety_orders", 3)
            safety_order_pct = config.get("safety_order_percentage", 20.0)

            # Reserve budget for all potential DCA safety orders
            required_dca_reserve = max_safety_orders * safety_order_pct
            max_initial_pct = max(100.0 - required_dca_reserve, 10.0)  # Reserve DCA budget, but allow at least 10%

            logger.info(
                f"  💰 DCA Reserve: {max_safety_orders} orders × {safety_order_pct}% = {required_dca_reserve}% reserved, "
                f"max initial buy: {max_initial_pct}%"
            )

        # Determine initial buy percentage
        initial_budget_pct = config.get("initial_budget_percentage", None)
        if initial_budget_pct is not None:
            # User explicitly configured initial budget percentage - use it (capped by DCA reserve)
            use_pct = min(initial_budget_pct, max_initial_pct)
            logger.info(f"  📊 Using configured initial_budget_percentage: {initial_budget_pct}% (capped at {use_pct}%)")
        else:
            # Let AI decide, but cap by both max_position_budget_percentage AND DCA reserve
            suggested_pct = signal_data.get("suggested_allocation_pct", 10)
            max_pct = config.get("max_position_budget_percentage", 100)
            use_pct = min(suggested_pct, max_pct, max_initial_pct)
            logger.info(
                f"  🤖 AI suggested {suggested_pct}%, capped by max_position ({max_pct}%) and DCA reserve ({max_initial_pct}%) "
                f"= {use_pct}%"
            )

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

    # MANUAL EXIT RULES (3Commas style) - checked first if manual sizing is enabled
    if config.get("use_manual_sizing", False):
        # Check manual take-profit (overrides AI if set > 0)
        manual_tp = config.get("manual_take_profit_pct", 0)
        if manual_tp > 0 and profit_pct >= manual_tp:
            return True, f"📈 Manual take-profit triggered at {profit_pct:.2f}% (target: {manual_tp}%)"

        # Check manual stop-loss (overrides "never sell at loss" rule if set > 0)
        manual_sl = config.get("manual_stop_loss_pct", 0)
        if manual_sl > 0 and profit_pct <= -manual_sl:
            return True, f"🛑 Manual stop-loss triggered at {profit_pct:.2f}% (limit: -{manual_sl}%)"

    # RULE 1: Never sell at a loss (unless manual stop-loss triggered above)
    if profit_pct <= 0:
        return False, f"Never sell at loss (current: {profit_pct:.2f}%)"

    # RULE 2: Only sell if profit meets minimum
    if profit_pct < min_profit:
        return False, f"Profit {profit_pct:.2f}% below minimum {min_profit}%"

    # RULE 3: Check take profit conditions (if configured) - uses PhaseConditionEvaluator
    # Supports conditions like: BB% crossing below 90, RSI crossing below 70, etc.
    take_profit_conditions = config.get("take_profit_conditions", [])
    take_profit_logic = config.get("take_profit_logic", "or")

    import logging
    _logger = logging.getLogger(__name__)

    if take_profit_conditions and market_context:
        from app.phase_conditions import PhaseConditionEvaluator
        from app.indicator_calculator import IndicatorCalculator

        try:
            evaluator = PhaseConditionEvaluator(IndicatorCalculator())
            # Get previous indicators for crossing detection
            previous_indicators = market_context.get("_previous")

            # Debug: Log BB% values for take profit evaluation
            current_bb = market_context.get("bb_percent", "N/A")
            prev_bb = previous_indicators.get("bb_percent", "N/A") if previous_indicators else "None"
            _logger.info(f"    📊 Take profit check: BB% current={current_bb:.1f}%, prev={prev_bb}, profit={profit_pct:.2f}%")

            if evaluator.evaluate_phase_conditions(
                take_profit_conditions, take_profit_logic, market_context, previous_indicators
            ):
                # Technical condition triggered - sell with profit protection
                _logger.warning(f"    🎯 TAKE PROFIT TRIGGERED: BB% crossed below 90% at {profit_pct:.2f}% profit!")
                return True, f"Take profit condition triggered at {profit_pct:.2f}% profit"
        except Exception as e:
            # Log error but don't block trading if condition evaluation fails
            _logger.warning(f"Error evaluating take profit conditions: {e}")

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
