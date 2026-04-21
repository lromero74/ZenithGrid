"""
AI Spot Opinion Indicator

A unified AI-powered indicator that combines technical metrics with LLM reasoning
to provide buy/sell/hold signals with confidence scores.

This indicator:
- Pre-filters buy opportunities using basic technical indicators
- Uses LLM (Claude/GPT/Gemini) to analyze metrics and provide spot opinions
- Time-gates analysis to run once per candle close (respects timeframe)
- Returns: signal ("buy"/"sell"/"hold"), confidence (0-100), reasoning

Usage:
    evaluator = AISpotOpinionEvaluator()
    result = await evaluator.evaluate(
        candles=candles,
        current_price=price,
        product_id="ETH-BTC",
        params=params,
        is_sell_check=False  # True only if checking exit for held position
    )

    # Returns:
    {
        "signal": "buy" | "sell" | "hold",
        "confidence": 75,  # 0-100
        "reasoning": "Bullish MACD crossover with strong volume...",
        "should_prefilter_pass": True/False,  # For debugging
        "metrics": {...}  # All calculated indicators
    }
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from app.indicator_calculator import IndicatorCalculator

if TYPE_CHECKING:
    from app.indicators.ai_tools import ToolContext


async def log_opinion(**kwargs):
    """Lazy proxy to ai_opinion_logger.log_opinion.

    Direct top-level import triggers the same circular-import problem
    `_tools_module()` works around — resolving the logger on first call
    avoids re-entering app.indicators.__init__ while this module is still
    loading. Patching `_mod.log_opinion` in tests still works because this
    symbol lives in the module namespace.
    """
    from app.indicators.ai_opinion_logger import log_opinion as _impl
    await _impl(**kwargs)

logger = logging.getLogger(__name__)


def _tools_module():
    """Lazy import of the ai_tools package.

    Kept local to sidestep a circular import at module load time: app.indicators
    __init__ pulls AISpotOpinionEvaluator, and ai_tools lives under app.indicators.
    Importing it at the top of this file would re-enter the package __init__
    before AISpotOpinionEvaluator is defined. Loading on first use avoids that.
    """
    from app.indicators import ai_tools as mod
    return mod


async def execute_tool(name: str, input: Dict[str, Any], ctx: "ToolContext") -> Dict[str, Any]:
    return await _tools_module().execute(name, input, ctx)


# Argument-taking tools (Phase C). Static tools (get_portfolio_context /
# get_position_context) are pre-fetched and injected into the prompt via
# _collect_auto_context — they don't belong in the provider tool loop since
# they take no arguments. These three DO take arguments, so the model decides
# when and how to call them.
_ARG_TOOL_NAMES: List[str] = [
    "get_candle_window",
    "get_recent_news",
    "get_trade_history",
    "get_prior_ai_signals",
]


def _arg_tool_schemas() -> List[Dict[str, Any]]:
    """Resolve the argument-taking tools' canonical schemas from the registry."""
    return _tools_module().get_schemas_for(_ARG_TOOL_NAMES)


# Short, user-written hints for the prompt. Lives next to _ARG_TOOL_NAMES so
# additions are a single-line change in one place.
_TOOL_USE_HINTS: Dict[str, str] = {
    "get_candle_window": (
        "zoom into price action on a chosen timeframe when summary metrics "
        "look ambiguous (5m/15m/1h/6h/1d, up to 100 candles)."
    ),
    "get_recent_news": (
        "scan cached headlines for this pair's base asset — use before confirming "
        "a buy when metrics look clean to rule out a catalyst."
    ),
    "get_trade_history": (
        "review recent closed positions on this pair for this user — win rate, "
        "avg PnL%, and avg hold time — to calibrate conviction."
    ),
    "get_prior_ai_signals": (
        "audit your own recent calls on this pair (up to 90 days): signal, "
        "confidence, and outcome (win/loss/breakeven + realized PnL %) where "
        "the parent position has closed — use this when conviction feels "
        "familiar to check if past similar calls paid off."
    ),
}


# The UI-facing `ai_model` string the user picks is distinct from the credential
# slug used to look up their API key (e.g. "gpt" → stored under "openai").
_CREDENTIAL_NAMES = {"claude": "claude", "gpt": "openai", "openai": "openai", "gemini": "gemini"}


def _credential_name_for(ai_model: str) -> str:
    key = (ai_model or "").lower()
    try:
        return _CREDENTIAL_NAMES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown AI model: {ai_model}") from exc


@dataclass
class AISpotOpinionParams:
    """Parameters for AI Spot Opinion indicator."""

    # LLM Configuration
    ai_model: str = "claude"  # "claude", "gpt", or "gemini"
    ai_timeframe: str = "15m"  # Candle timeframe (5m, 15m, 1h, 4h, etc.)
    ai_min_confidence: int = 60  # Minimum confidence to trigger signal

    # Pre-filter settings (for buys only)
    enable_buy_prefilter: bool = True
    prefilter_rsi_max: float = 70.0  # Don't ask AI if RSI > this (overbought)
    prefilter_volume_min_ratio: float = 1.2  # Require volume > avg * this
    prefilter_max_drop_24h: float = 10.0  # Don't buy if price dropped > this % in 24h

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "AISpotOpinionParams":
        """Create params from strategy config dict."""
        return cls(
            ai_model=config.get("ai_model", "claude"),
            ai_timeframe=config.get("ai_timeframe", "15m"),
            ai_min_confidence=config.get("ai_min_confidence", 60),
            enable_buy_prefilter=config.get("enable_buy_prefilter", True),
            prefilter_rsi_max=config.get("prefilter_rsi_max", 70.0),
            prefilter_volume_min_ratio=config.get("prefilter_volume_min_ratio", 1.2),
            prefilter_max_drop_24h=config.get("prefilter_max_drop_24h", 10.0),
        )


class AISpotOpinionEvaluator:
    """
    Evaluates trading opportunities using technical metrics + LLM reasoning.

    For buys: Pre-filters with basic metrics, then asks LLM for opinion
    For sells: Only checks positions we hold, asks LLM directly
    """

    def __init__(self):
        self.indicator_calc = IndicatorCalculator()
        # Cache to track last check time per product/timeframe
        self._last_check_cache: Dict[str, datetime] = {}

    def _should_check_now(self, product_id: str, timeframe: str) -> bool:
        """
        Check if enough time has passed since last analysis.
        Only run once per candle close.
        """
        cache_key = f"{product_id}:{timeframe}"
        last_check = self._last_check_cache.get(cache_key)

        if not last_check:
            return True

        # Parse timeframe (e.g., "15m" -> 15 minutes)
        timeframe_seconds = self._timeframe_to_seconds(timeframe)
        elapsed = (datetime.utcnow() - last_check).total_seconds()

        return elapsed >= timeframe_seconds

    def _timeframe_to_seconds(self, timeframe: str) -> int:
        """Convert timeframe string to seconds."""
        timeframe = timeframe.lower()
        if timeframe.endswith('m'):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith('h'):
            return int(timeframe[:-1]) * 3600
        elif timeframe.endswith('d'):
            return int(timeframe[:-1]) * 86400
        else:
            logger.warning(f"Unknown timeframe format: {timeframe}, defaulting to 15m")
            return 900  # 15 minutes

    def _update_last_check(self, product_id: str, timeframe: str):
        """Update last check timestamp."""
        cache_key = f"{product_id}:{timeframe}"
        self._last_check_cache[cache_key] = datetime.utcnow()

    def _calculate_metrics(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate all technical indicators."""
        if not candles or len(candles) < 50:
            return {}

        # Extract OHLCV data
        closes = [float(c['close']) for c in candles]
        _highs = [float(c['high']) for c in candles]  # noqa: F841
        _lows = [float(c['low']) for c in candles]  # noqa: F841
        volumes = [float(c['volume']) for c in candles]

        current_price = closes[-1]

        # Calculate indicators
        rsi = self.indicator_calc.calculate_rsi(closes, period=14)
        macd_line, signal_line, _ = self.indicator_calc.calculate_macd(closes)
        bb_upper, bb_middle, bb_lower = self.indicator_calc.calculate_bollinger_bands(closes, period=20)

        # Volume analysis
        avg_volume = sum(volumes[-20:]) / min(20, len(volumes))
        current_volume = volumes[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        # Price action
        ma_20 = sum(closes[-20:]) / min(20, len(closes))
        ma_50 = sum(closes[-50:]) / min(50, len(closes))
        price_vs_ma20 = ((current_price - ma_20) / ma_20 * 100) if ma_20 > 0 else 0
        price_vs_ma50 = ((current_price - ma_50) / ma_50 * 100) if ma_50 > 0 else 0

        # 24h change
        price_24h_ago = closes[-24] if len(closes) >= 24 else closes[0]
        price_change_24h = ((current_price - price_24h_ago) / price_24h_ago * 100) if price_24h_ago > 0 else 0

        # Bollinger position
        bb_position = ((current_price - bb_lower) / (bb_upper - bb_lower) * 100) if (bb_upper - bb_lower) > 0 else 50

        # MACD status
        macd_bullish = macd_line > signal_line if macd_line and signal_line else False
        macd_bearish = macd_line < signal_line if macd_line and signal_line else False

        return {
            "rsi": rsi,
            "macd_bullish": macd_bullish,
            "macd_bearish": macd_bearish,
            "macd_line": macd_line,
            "signal_line": signal_line,
            "bb_position": bb_position,
            "current_price": current_price,
            "ma_20": ma_20,
            "ma_50": ma_50,
            "price_vs_ma20": price_vs_ma20,
            "price_vs_ma50": price_vs_ma50,
            "volume_ratio": volume_ratio,
            "price_change_24h": price_change_24h,
        }

    def _check_buy_prefilter(self, metrics: Dict[str, Any], params: AISpotOpinionParams) -> tuple[bool, str]:
        """
        Pre-filter for buy opportunities using basic metrics.
        Returns (should_pass, reason)
        """
        if not params.enable_buy_prefilter:
            return True, "Prefilter disabled"

        rsi = metrics.get("rsi", 50)
        volume_ratio = metrics.get("volume_ratio", 0)
        price_change_24h = metrics.get("price_change_24h", 0)

        # Check RSI (don't buy if overbought)
        if rsi > params.prefilter_rsi_max:
            return False, f"RSI too high ({rsi:.1f} > {params.prefilter_rsi_max})"

        # Check volume (require above-average volume)
        if volume_ratio < params.prefilter_volume_min_ratio:
            return False, f"Volume too low ({volume_ratio:.2f}x < {params.prefilter_volume_min_ratio}x)"

        # Check price action (don't buy if crashing)
        if price_change_24h < -params.prefilter_max_drop_24h:
            return False, f"Price dropped too much ({price_change_24h:.1f}% < -{params.prefilter_max_drop_24h}%)"

        return True, "Prefilter passed"

    async def _call_llm(
        self,
        *,
        db: Any,
        user_id: int,
        ai_model: str,
        prompt: str,
        tool_ctx: Optional["ToolContext"] = None,
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[str, int, str, List[Any]]:
        """Dispatch the LLM call, letting the provider drive its own tool loop.

        If `tool_schemas` is empty, `provider.call_with_tools` short-circuits to
        a single request. If non-empty, the provider iterates its native
        tool-use loop (up to 4 turns) and returns every tool invocation it made.

        Returns (signal, confidence, reasoning, tool_calls). `tool_calls` is a
        list of `NormalizedToolCall` dataclass instances, always — empty on the
        single-shot path.
        """
        from app.indicators.ai_providers import get_provider
        from app.services.ai_credential_service import get_user_api_key

        credential_name = _credential_name_for(ai_model)
        api_key = await get_user_api_key(db, user_id, credential_name)
        if not api_key:
            raise ValueError(
                f"No API key configured for {credential_name}. "
                f"Please add your {credential_name.upper()} API key in Settings."
            )

        schemas = list(tool_schemas or [])
        try:
            provider = get_provider(ai_model, api_key=api_key)
            max_turns = 4 if schemas else 1
            text, tool_calls = await provider.call_with_tools(
                system=None,
                user=prompt,
                tools=schemas,
                tool_ctx=tool_ctx,
                max_turns=max_turns,
            )
            signal, confidence, reasoning = self._parse_llm_response(text)
            return signal, confidence, reasoning, tool_calls
        except Exception as e:
            logger.error(f"Error calling LLM ({ai_model}): {e}")
            return "hold", 0, f"LLM error: {str(e)}", []

    async def _collect_auto_context(self, tool_ctx: Optional["ToolContext"]) -> Dict[str, Any]:
        """Pre-fetch portfolio + position context for prompt injection.

        Both tools are called directly (no tool-use loop) and their outputs are
        packed into a dict the caller can render into the prompt. This gives
        every provider feature parity for static context in Phase A — the real
        provider tool loop is reserved for argument-taking tools added in Phase C.
        """
        if tool_ctx is None:
            return {}

        context: Dict[str, Any] = {}
        if tool_ctx.account_id is not None:
            context["portfolio"] = await execute_tool("get_portfolio_context", {}, tool_ctx)
        if tool_ctx.position is not None or tool_ctx.is_sell_check:
            context["position"] = await execute_tool("get_position_context", {}, tool_ctx)
        return context

    async def evaluate(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        product_id: str,
        db: Any,
        user_id: int,
        params: Optional[AISpotOpinionParams] = None,
        is_sell_check: bool = False,
        bot: Optional[Any] = None,
        account_id: Optional[int] = None,
        position: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Main evaluation function.

        Args:
            candles: Historical candle data
            current_price: Current market price
            product_id: Trading pair (e.g., "ETH-BTC")
            db: Database session for fetching user's API keys
            user_id: User ID to fetch API keys for
            params: Configuration parameters
            is_sell_check: True if checking sell for held position, False for buy check

        Returns:
            {
                "signal": "buy" | "sell" | "hold",
                "confidence": 0-100,
                "reasoning": "explanation",
                "prefilter_passed": True/False,
                "metrics": {...}
            }
        """
        if params is None:
            params = AISpotOpinionParams()

        # Check time-gating (only run once per candle)
        if not self._should_check_now(product_id, params.ai_timeframe):
            logger.debug(f"Skipping {product_id} - still on same {params.ai_timeframe} candle")
            return {
                "signal": "hold",
                "confidence": 0,
                "reasoning": f"Waiting for next {params.ai_timeframe} candle",
                "prefilter_passed": None,
                "metrics": {}
            }

        # Calculate technical metrics
        metrics = self._calculate_metrics(candles)
        if not metrics:
            logger.warning(f"Insufficient candle data for {product_id}")
            return {
                "signal": "hold",
                "confidence": 0,
                "reasoning": "Insufficient data",
                "prefilter_passed": None,
                "metrics": {}
            }

        # For buys: Check pre-filter
        prefilter_passed = True
        prefilter_reason = "N/A (sell check)" if is_sell_check else "Prefilter passed"

        if not is_sell_check:
            prefilter_passed, prefilter_reason = self._check_buy_prefilter(metrics, params)
            if not prefilter_passed:
                logger.info(f"Buy prefilter failed for {product_id}: {prefilter_reason}")
                self._update_last_check(product_id, params.ai_timeframe)
                prefilter_reasoning = f"Prefilter: {prefilter_reason}"
                await self._write_opinion_log(
                    db=db, user_id=user_id, account_id=account_id,
                    bot_id=getattr(bot, "id", None),
                    position_id=getattr(position, "id", None),
                    product_id=product_id, is_sell_check=is_sell_check,
                    signal="hold", confidence=0,
                    reasoning=prefilter_reasoning, tool_calls=[],
                    ai_model=params.ai_model,
                )
                return {
                    "signal": "hold",
                    "confidence": 0,
                    "reasoning": prefilter_reasoning,
                    "prefilter_passed": False,
                    "metrics": metrics
                }

        # Phase A: portfolio + position are pre-fetched and injected into the
        # prompt (they take no args — no reason to spend a tool turn).
        # Phase C: argument-taking tools (candle_window, recent_news,
        # trade_history) are handed to the provider so the model can decide
        # when to call them.
        from app.indicators.ai_tools import ToolContext as _ToolContext
        tool_ctx = _ToolContext(
            db=db,
            user_id=user_id,
            product_id=product_id,
            current_price=current_price,
            bot=bot,
            position=position,
            account_id=account_id,
            is_sell_check=is_sell_check,
        )
        context = await self._collect_auto_context(tool_ctx)
        arg_schemas = _arg_tool_schemas()
        prompt = self._build_prompt(
            product_id=product_id,
            metrics=metrics,
            is_sell_check=is_sell_check,
            context=context,
            enabled_tools=[s["name"] for s in arg_schemas],
        )
        signal, confidence, reasoning, raw_tool_calls = await self._call_llm(
            db=db,
            user_id=user_id,
            ai_model=params.ai_model,
            prompt=prompt,
            tool_ctx=tool_ctx,
            tool_schemas=arg_schemas,
        )
        tool_calls: List[Dict[str, Any]] = [
            {
                "name": tc.name,
                "input": tc.input,
                "output_summary": tc.output_summary,
                "turn": tc.turn,
            }
            for tc in raw_tool_calls
        ]

        # Update last check timestamp
        self._update_last_check(product_id, params.ai_timeframe)

        logger.info(
            f"AI Opinion for {product_id}: {signal.upper()} "
            f"(confidence: {confidence}%, tools={len(tool_calls)}, reason: {reasoning})"
        )

        await self._write_opinion_log(
            db=db, user_id=user_id, account_id=account_id,
            bot_id=getattr(bot, "id", None),
            position_id=getattr(position, "id", None),
            product_id=product_id, is_sell_check=is_sell_check,
            signal=signal, confidence=confidence, reasoning=reasoning,
            tool_calls=tool_calls, ai_model=params.ai_model,
        )

        return {
            "signal": signal,
            "confidence": confidence,
            "reasoning": reasoning,
            "prefilter_passed": prefilter_passed,
            "metrics": metrics,
            "tool_calls": tool_calls,
        }

    @staticmethod
    async def _write_opinion_log(**kwargs) -> None:
        """Fire-and-forget audit write. Any exception is swallowed so a broken
        audit log can never break evaluate()."""
        try:
            await log_opinion(**kwargs)
        except Exception:
            logger.exception("ai_opinion_log write failed — continuing")

    @staticmethod
    def _build_prompt(
        product_id: str,
        metrics: Dict[str, Any],
        is_sell_check: bool,
        enabled_tools: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Shared prompt builder for single-shot and tool-use paths."""
        action_type = "SELL" if is_sell_check else "BUY"
        ma20_val = metrics.get("price_vs_ma20", 0)
        ma50_val = metrics.get("price_vs_ma50", 0)
        ma20_dir = "above" if ma20_val > 0 else "below"
        ma50_dir = "above" if ma50_val > 0 else "below"
        macd_str = (
            "Bullish" if metrics.get("macd_bullish")
            else "Bearish" if metrics.get("macd_bearish")
            else "Neutral"
        )

        tools_section = ""
        if enabled_tools:
            hints = []
            for name in enabled_tools:
                hint = _TOOL_USE_HINTS.get(name)
                if hint:
                    hints.append(f"- `{name}` — {hint}")
            hint_block = "\n".join(hints) if hints else ""
            tools_section = (
                "\n## Tools available\n"
                f"{hint_block}\n\n"
                "Call a tool only if its information would change your decision — "
                "do not call tools redundantly. Prefer inspecting the Available "
                "Context section first; only reach for tools when it is not enough.\n"
            )

        context_section = ""
        context_consider_line = ""
        if context:
            context_section = (
                "\n## Available Context (live data pre-fetched for you):\n"
                "```json\n"
                f"{json.dumps(context, default=str, indent=2)}\n"
                "```\n"
            )
            context_consider_line = (
                "\n- Use the Available Context section above to factor in position age, "
                "PnL, portfolio concentration, and other open positions."
            )

        return f"""You are a cryptocurrency trading AI analyzing {product_id}.

Current Technical Metrics:
- RSI: {metrics.get('rsi', 'N/A'):.1f} (14-period)
- MACD: {macd_str}
- Price vs 20-period MA: {ma20_val:.2f}% {ma20_dir}
- Price vs 50-period MA: {ma50_val:.2f}% {ma50_dir}
- Bollinger Band Position: {metrics.get('bb_position', 50):.1f}% (0=lower band, 100=upper band)
- Volume: {metrics.get('volume_ratio', 0):.2f}x average
- 24h Price Change: {metrics.get('price_change_24h', 0):.2f}%
{context_section}{tools_section}
Question: Should I {action_type} this position right now?

Respond with ONLY valid JSON in this exact format:
{{
  "signal": "buy" or "sell" or "hold",
  "confidence": 75,
  "reasoning": "Brief 1-2 sentence explanation"
}}

Consider:
- For BUYS: Is momentum building? Are indicators aligning? Is this a good entry?
- For SELLS: Has momentum peaked? Are there warning signs? Should we take profit or cut losses?{context_consider_line}

Be decisive but realistic. Confidence should reflect conviction (0-100).
"""

    @staticmethod
    def _parse_llm_response(response_text: str) -> tuple[str, int, str]:
        """Parse the final JSON response from the LLM. Tolerates ```code blocks```."""
        text = (response_text or "").strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if len(lines) > 2 else lines)

        try:
            data = json.loads(text)
        except Exception as e:
            logger.warning(f"Could not parse LLM JSON: {e} / raw={text!r}")
            return "hold", 0, f"Parse error: {e}"

        signal = str(data.get("signal", "hold")).lower()
        confidence = int(data.get("confidence", 0))
        reasoning = str(data.get("reasoning", "No reasoning provided"))

        if signal not in ("buy", "sell", "hold"):
            logger.warning(f"Invalid signal from LLM: {signal}, defaulting to hold")
            signal = "hold"
        confidence = max(0, min(100, confidence))
        return signal, confidence, reasoning
