"""
DSL Trading Strategy

Lets advanced users write custom trading logic in a small, sandboxed
domain-specific language (DSL) that is evaluated as a bot strategy.

The sandbox is enforced by the DSL interpreter (``dsl_interpreter.py``).
User-supplied text is NEVER passed to ``eval()``, ``exec()``, or
``compile()``; every AST node is whitelisted before execution.

Config
------
script : str
    The DSL script text.  Example::

        limit('buy', 'BTC-USD', 0.01, price='-1%')
        if rsi(14) < 30: limit('buy', 'ETH-USD', 0.05)
        if price('BTC-USD') > 100000: market('sell', 'BTC-USD', all)

    Validated (and rejected with a clear error) at ``validate_config()`` time
    so mis-typed scripts fail on bot creation, not silently at runtime.

trigger : str
    When to run the script.  Currently only ``'every_tick'`` is supported
    (evaluate on every ``analyze_signal`` call).  Defaults to
    ``'every_tick'``.
"""

import logging
from typing import Any, Dict, List, Optional

from app.indicator_calculator import IndicatorCalculator
from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)
from app.strategies.dsl_interpreter import (
    DSLError,
    OrderIntent,
    evaluate,
    parse_script,
)

logger = logging.getLogger(__name__)


@StrategyRegistry.register
class DSLTradingStrategy(TradingStrategy):
    """
    DSL scripting strategy — executes user-authored custom trading logic.

    Account-scoped: each instance holds the parsed script for a single bot;
    no class-level state is shared across accounts.
    """

    def __init__(self, config: Dict[str, Any]):
        # Reset per-instance state before validate_config() runs
        self._parsed_script = None
        self.indicator_calculator = None
        super().__init__(config)

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="dsl_trading",
            name="Custom Script (DSL)",
            description=(
                "Write custom trading logic in a sandboxed mini-language. "
                "Supports price(), rsi(), macd(), bb_pct() data functions and "
                "limit()/market() action functions with if-condition guards."
            ),
            parameters=[
                StrategyParameter(
                    name="script",
                    display_name="Trading Script",
                    description=(
                        "DSL script text. Each line is either an action call "
                        "(limit/market) or an 'if <condition>: <action>' statement. "
                        "Example: if rsi(14) < 30: limit('buy', 'ETH-USD', 0.05)"
                    ),
                    type="string",
                    default="",
                    required=True,
                ),
                StrategyParameter(
                    name="trigger",
                    display_name="Execution Trigger",
                    description="When to evaluate the script",
                    type="string",
                    default="every_tick",
                    options=["every_tick"],
                ),
            ],
        )

    def validate_config(self):
        """Parse and validate the DSL script at config time.

        Raises:
            DSLError: If the script is syntactically or structurally invalid,
                or if it contains any forbidden AST node (sandbox violation).
        """
        # Initialise the indicator calculator (same class used by indicator_based)
        self.indicator_calculator = IndicatorCalculator()

        script_text = self.config.get("script", "")
        if not isinstance(script_text, str):
            raise DSLError("'script' config key must be a string")

        # parse_script performs full whitelist validation — fail fast on bad scripts
        self._parsed_script = parse_script(script_text)

    # ------------------------------------------------------------------
    # Indicator calculation
    # ------------------------------------------------------------------

    def _build_context(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the data context dict for ``evaluate()``.

        Calculates the indicators referenced by the script and packages them
        into the format expected by ``dsl_interpreter.evaluate()``.

        We calculate a broad set of indicators regardless of what the script
        references; the overhead is negligible and avoids having to pre-scan
        the AST for required indicators.

        Args:
            candles: Recent OHLCV candles (same list as passed to
                ``analyze_signal``).
            current_price: Current market price.
            symbol: The product symbol for the primary pair (e.g. 'BTC-USD').

        Returns:
            Context dict with keys ``"price"``, ``"rsi"``, ``"macd"``, and
            ``"bb_pct"``.
        """
        # Always include the current price for the primary symbol
        price_map: Dict[str, float] = {}
        if symbol:
            price_map[symbol] = current_price

        rsi_map: Dict[int, float] = {}
        macd_info: Dict[str, float] = {}
        bb_pct_value: Optional[float] = None

        if candles:
            required = {"rsi_14", "macd_12_26_9", "bb_upper_20_2", "bb_middle_20_2", "bb_lower_20_2"}
            indicators = self.indicator_calculator.calculate_all_indicators(candles, required)

            # RSI — expose as {period: value} dict
            rsi_14 = indicators.get("rsi_14")
            if rsi_14 is not None:
                rsi_map[14] = float(rsi_14)

            # MACD line
            macd_line = indicators.get("macd_12_26_9")
            if macd_line is not None:
                macd_info["line"] = float(macd_line)
                signal_line = indicators.get("macd_signal_12_26_9")
                if signal_line is not None:
                    macd_info["signal"] = float(signal_line)
                histogram = indicators.get("macd_histogram_12_26_9")
                if histogram is not None:
                    macd_info["histogram"] = float(histogram)

            # Bollinger Band %B = (price - lower) / (upper - lower)
            bb_upper = indicators.get("bb_upper_20_2")
            bb_lower = indicators.get("bb_lower_20_2")
            if bb_upper is not None and bb_lower is not None and bb_upper != bb_lower:
                bb_pct_value = (current_price - bb_lower) / (bb_upper - bb_lower)

            # Also include the live price from the most recent candle
            live_price = indicators.get("price")
            if live_price is not None and symbol:
                price_map[symbol] = float(live_price)

        context: Dict[str, Any] = {
            "price": price_map,
            "rsi": rsi_map,
            "macd": macd_info,
        }
        if bb_pct_value is not None:
            context["bb_pct"] = bb_pct_value
            context["bb"] = bb_pct_value

        return context

    # ------------------------------------------------------------------
    # TradingStrategy abstract interface
    # ------------------------------------------------------------------

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Evaluate the DSL script and return a signal dict.

        Kwargs:
            symbol: Product pair (e.g. ``'BTC-USD'``) to expose as the
                ``price()`` key in the context.

        Returns:
            Signal dict with ``signal_type`` ``'dsl_result'``, the list of
            ``OrderIntent`` dicts, and a summary ``reasoning`` string.  Returns
            ``None`` if no intents were produced (script evaluated but no
            conditions were satisfied).
        """
        if self._parsed_script is None:
            logger.error("dsl_trading: parsed script is None — validate_config may have been skipped")
            return None

        symbol = kwargs.get("symbol")
        context = self._build_context(candles, current_price, symbol=symbol)

        try:
            intents: List[OrderIntent] = evaluate(self._parsed_script, context)
        except DSLError as exc:
            logger.warning("dsl_trading: script evaluation error — %s", exc)
            return {
                "signal_type": "dsl_error",
                "confidence": 0,
                "reasoning": f"DSL evaluation error: {exc}",
                "intents": [],
                "error": str(exc),
            }

        if not intents:
            return None

        intent_dicts = [
            {
                "side": i.side,
                "symbol": i.symbol,
                "order_type": i.order_type,
                "size": i.size,
                "price_offset": i.price_offset,
                "size_is_all": i.size_is_all,
            }
            for i in intents
        ]

        reasoning = "; ".join(
            f"{i.order_type}({i.side} {i.symbol} {'all' if i.size_is_all else i.size})"
            for i in intents
        )

        return {
            "signal_type": "dsl_result",
            "confidence": 100,
            "reasoning": reasoning,
            "intents": intent_dicts,
            "raw_intents": intents,
        }

    async def should_buy(
        self,
        signal_data: Dict[str, Any],
        position: Optional[Any],
        btc_balance: float,
        **kwargs,
    ) -> tuple:
        """Return a buy decision from DSL intents.

        Returns the first ``buy`` intent from the evaluated script, or False
        if no buy intents are present.

        Returns:
            ``(should_buy: bool, btc_amount: float, reason: str)``
        """
        if not signal_data or signal_data.get("signal_type") not in ("dsl_result",):
            return False, 0.0, "No DSL signal"

        intents: List[OrderIntent] = signal_data.get("raw_intents", [])
        for intent in intents:
            if intent.side == "buy":
                size = intent.size if not intent.size_is_all else btc_balance
                return (
                    True,
                    float(size or 0.0),
                    f"DSL {intent.order_type} buy {intent.symbol}"
                    + (f" @ {intent.price_offset}" if intent.price_offset else ""),
                )

        return False, 0.0, "No buy intent in DSL result"

    async def should_sell(
        self,
        signal_data: Dict[str, Any],
        position: Any,
        current_price: float,
        **kwargs,
    ) -> tuple:
        """Return a sell decision from DSL intents.

        Returns the first ``sell`` intent from the evaluated script, or False
        if no sell intents are present.

        Returns:
            ``(should_sell: bool, reason: str)``
        """
        if not signal_data or signal_data.get("signal_type") not in ("dsl_result",):
            return False, "No DSL signal"

        intents: List[OrderIntent] = signal_data.get("raw_intents", [])
        for intent in intents:
            if intent.side == "sell":
                return (
                    True,
                    f"DSL {intent.order_type} sell {intent.symbol}"
                    + (" (all)" if intent.size_is_all else f" size={intent.size}"),
                )

        return False, "No sell intent in DSL result"
